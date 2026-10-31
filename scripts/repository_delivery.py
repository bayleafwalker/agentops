#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "vuoro-contracts @ https://github.com/bayleafwalker/vuoro/releases/download/vuoro-contracts-v0.2.0/vuoro_contracts-0.2.0-py3-none-any.whl#sha256=7bc6558076fff11591b6382641608a95afebb846c254309673351a29854e12c9",
#   "vuoro-client @ https://github.com/bayleafwalker/vuoro/releases/download/vuoro-client-v0.1.6/vuoro_client-0.1.6-py3-none-any.whl#sha256=b2267290ed28e89e522c94616e46e1167d155334888cbe6bc0bc287b14fcb59d",
# ]
# ///
"""Repository delivery project adapter over real Sovite and Vuoro owner APIs.

Run one shared scheduler tick. Private local state is transport/scheduling
intent, not work, execution, disclosure or acceptance authority. Mutable
execution and trusted acceptance drivers must be separately commissioned.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import math
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import tempfile
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

from shared_execution.runtime import Store, atomic
from shared_execution.scheduler import tick
from shared_execution.process import run_child
from execution_authority import _file_credential

MAX_ARTIFACT = 8 * 1024 * 1024
SHA = re.compile(r'^[0-9a-f]{64}$')
GIT = shutil.which("git")
COMMIT = re.compile(r'^[0-9a-f]{40}$')


class DeliveryError(ValueError):
    pass


def need(value, code):
    if not value:
        raise DeliveryError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'duplicate-json-key')
        result[key] = value
    return result


def load(path, limit=2*MAX_ARTIFACT):
    path = Path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_size <= limit, 'invalid-input-file')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            return json.loads(stream.read(limit+1), object_pairs_hook=unique_pairs,
                              parse_constant=lambda value: need(False, 'invalid-json-number'))
    finally:
        os.close(fd)


def write_exact(path, data):
    fd, temporary = tempfile.mkstemp(prefix='.'+path.name, dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def private_root(root):
    root = Path(root).absolute()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = root.stat()
    need(root.resolve() == root and info.st_uid == os.getuid() and not stat.S_IMODE(info.st_mode) & 0o077,
         'protected-state-root-required')
    return root


class Vuoro:
    def __init__(self, profile):
        from vuoro_client import AsyncVuoroClient
        from vuoro_client.profile import load_profile
        self.loop = asyncio.new_event_loop()
        self.client = AsyncVuoroClient(load_profile(profile), _file_credential)
        self.loop.run_until_complete(self.client.__aenter__())

    def invoke(self, operation, arguments, repo=None):
        try:
            return self.loop.run_until_complete(self.client.invoke(operation, arguments, repo_id=repo))
        except Exception as exc:
            raise DeliveryError('owner-refused:' + getattr(exc, 'code', 'unknown-outcome')) from None

    def catalog(self):
        try:
            return self.loop.run_until_complete(self.client.catalog(force_refresh=True))
        except Exception:
            raise DeliveryError('owner-catalog-unavailable') from None

    def close(self):
        self.loop.run_until_complete(self.client.__aexit__(None, None, None)); self.loop.close()


REPAIR_OPERATIONS = {
    'repositoryRepairSubmit':'/api/repository-runs/v1/repairs',
    'repositoryRepairFeedbackContext':'/api/repository-runs/v1/repair-feedback-context',
}


RECOVERY_OPERATIONS = {
    'repositoryRecoveryCapture':'/api/repository-runs/v1/runs/{run_id}/recovery',
    'repositoryRecoveryContext':'/api/repository-runs/v1/runs/{run_id}/recovery-context',
    'repositoryRecoveryRelease':'/api/repository-runs/v1/runs/{run_id}/recovery-release',
}


class OwnerRepairContract:
    """Read the actual pinned owner bundle; never copy its domain schema."""
    def __init__(self, value, state_root, *, recovery=False):
        self.operations = RECOVERY_OPERATIONS if recovery else REPAIR_OPERATIONS
        need(type(value) is dict and set(value) == {'root','integrity_sha256','source_ref'}, 'repair-contract-required')
        path = Path(value['root'])
        need(path.is_absolute() and path.resolve(strict=True) == path and path.is_dir()
             and state_root not in path.parents and path != state_root
             and SHA.fullmatch(value['integrity_sha256']) and isinstance(value['source_ref'], str)
             and re.fullmatch(r'https://github.com/bayleafwalker/sovite/blob/[0-9a-f]{40}/docs/contracts/repository-repair-v1\.provenance\.json', value['source_ref']), 'repair-contract-required')
        for parent in (path, *path.parents):
            info = parent.stat()
            sticky = parent != path and info.st_uid == 0 and info.st_mode & stat.S_ISVTX
            need(info.st_uid in (0, os.getuid()) and (not info.st_mode & 0o022 or sticky), 'repair-contract-unprotected')
        from vuoro_contracts import ContractBundle
        self.bundle = ContractBundle.load(path, integrity_sha256=value['integrity_sha256'])
        need(self.bundle.manifest['contractId'] == 'sovite.repository-repair.v1'
             and self.bundle.manifest['contractVersion'] in ({'1.3.0'} if recovery else {'1.1.0','1.2.0','1.3.0'}), 'repair-contract-unsupported')
        for operation, route in self.operations.items():
            metadata = self.bundle.manifest['operations'].get(operation)
            need(metadata and metadata['method'] == 'POST' and metadata['path'] == route
                 and metadata['exposure'] == 'internal', 'repair-contract-unsupported')

    def request(self, operation, body, *, run_id=None):
        need(operation in self.operations, 'repository-operation-unsupported')
        if '{run_id}' in self.operations[operation]:
            self.bundle.validate_parameter(operation,'path','run_id',run_id)
        else: need(run_id is None,'repository-operation-unsupported')
        self.bundle.validate_request(operation, body)

    def response(self, operation, status, body): self.bundle.validate_response(operation, status, body)
    def feedback(self, body): self.bundle.validate_schema('RepairFeedback.json', body)


class Sovite:
    def __init__(self, endpoint, credential_ref):
        import httpx
        url = urlsplit(endpoint)
        need(url.scheme == 'https' and url.netloc and url.path in ('', '/') and not url.username
             and not url.password and not url.query and not url.fragment, 'invalid-execution-endpoint')
        self.client = httpx.Client(base_url=endpoint, headers={'Authorization':'Bearer '+_file_credential(credential_ref)},
                                   timeout=30, follow_redirects=False)

    def _response(self, method, path, **kwargs):
        try:
            response = self.client.request(method, path, **kwargs)
            need(len(response.content) <= 2*MAX_ARTIFACT, 'execution-response-too-large')
            if not 200 <= response.status_code < 300:
                code = None
                try: code = response.json().get('detail', {}).get('code')
                except Exception: pass
                code = code if isinstance(code, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,96}', code) else 'refused'
                raise DeliveryError('execution-owner-refused:' + str(response.status_code) + ':' + code)
            return response
        except DeliveryError:
            raise
        except Exception:
            raise DeliveryError('execution-owner-unknown-outcome') from None

    def call(self, method, path, **kwargs):
        return self._response(method, '/api/repository-runs/v1' + path, **kwargs).json()

    def repair_call(self, contract, operation, body, *, key=None):
        contract.request(operation, body)
        response = self._response('POST', REPAIR_OPERATIONS[operation], json=body,
                                  headers={'Idempotency-Key':key} if key else {})
        result = response.json()
        contract.response(operation, response.status_code, result)
        return result

    def recovery_call(self, contract, operation, run_id, body):
        need(operation in RECOVERY_OPERATIONS,'recovery-operation-unsupported')
        contract.request(operation,body,run_id=run_id)
        route=RECOVERY_OPERATIONS[operation].replace('{run_id}',run_id)
        response=self._response('POST',route,json=body)
        result=response.json();contract.response(operation,response.status_code,result)
        return result

    def approve_feedback(self, body):
        # The existing output owner authenticates the actual caller and applies
        # its installed procedure; this adapter creates no approval authority.
        return self._response('POST', '/api/output-releases', json=body).json()

    def close(self): self.client.close()


def _git_result(repo, *args):
    # Repository data cannot enable hooks, filters, replacement objects,
    # attributes helpers, fsmonitor or environment-supplied Git configuration.
    env = {'PATH':os.defpath, 'LANG':'C', 'GIT_CONFIG_NOSYSTEM':'1', 'GIT_CONFIG_GLOBAL':'/dev/null',
           'GIT_NO_REPLACE_OBJECTS':'1', 'GIT_GRAFT_FILE':'/dev/null', 'GIT_TERMINAL_PROMPT':'0'}
    result = subprocess.run([GIT, '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false',
                             '-c', 'core.attributesFile=/dev/null', '-C', str(repo), *args],
                            env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
    need(len(result.stdout) <= 16*MAX_ARTIFACT, 'repository-output-too-large')
    return result


def git(repo, *args):
    result = _git_result(repo, *args)
    need(result.returncode == 0, 'repository-operation-refused')
    return result.stdout


def git_ancestor(repo, ancestor, descendant):
    result = _git_result(repo, 'merge-base', '--is-ancestor', ancestor, descendant)
    need(result.returncode in (0, 1), 'canonical-integration-unknown')
    return result.returncode == 0


def validate_export(raw, receipt, *, repository_id, base_sha, run_id):
    need(len(raw) == receipt['size'] and hashlib.sha256(raw).hexdigest() == receipt['sha256'], 'retained-content-changed')
    data = json.loads(raw)
    need(data['schema_version'] == 'sovite-repository-candidate-export/v1'
         and data['repository_id'] == repository_id and data['base_sha'] == base_sha and data['run_id'] == run_id
         and COMMIT.fullmatch(data['tip_sha']), 'candidate-source-mismatch')
    need(data.get('kind') != 'repository-recovery-artifact'
         and data.get('publication_eligible') is not False and data.get('repair_eligible') is not False,
         'recovery-is-not-publication-candidate')
    need('fence' not in data['receipt_projection'] and digest(data['receipt_projection']) == data['receipt_projection_sha256'],
         'candidate-receipt-changed')
    projection = data['receipt_projection']
    need(projection['base_sha'] == base_sha and projection['tip_sha'] == data['tip_sha']
         and projection['patch_sha256'] == data['patch_sha256'], 'candidate-receipt-mismatch')
    bundle = base64.b64decode(data['bundle_base64'], validate=True)
    need(len(bundle) <= MAX_ARTIFACT and hashlib.sha256(bundle).hexdigest() == data['bundle_sha256'], 'candidate-bundle-changed')
    return data, bundle


def import_candidate(root, remote, data, bundle, allowed_areas):
    """Build a new clean checkout from canonical base and exact retained bundle."""
    root = Path(root)
    branch = 'dispatch/run-' + digest(data)[:16]
    if root.exists():
        need(root.resolve() == root and git(root, 'remote', 'get-url', 'origin').decode().strip() == remote
             and git(root, 'rev-parse', 'HEAD').decode().strip() == data['tip_sha']
             and git(root, 'symbolic-ref', '--short', 'HEAD').decode().strip() == branch
             and not git(root, 'status', '--porcelain', '--untracked-files=all'), 'existing-checkout-requires-reconciliation')
        return branch
    root.mkdir(mode=0o700)
    git(root, 'init', '-b', 'main')
    git(root, 'remote', 'add', 'origin', remote)
    git(root, 'fetch', '--no-tags', '--no-recurse-submodules', 'origin', data['base_sha'])
    need(git(root, 'rev-parse', 'FETCH_HEAD').decode().strip() == data['base_sha'], 'canonical-base-changed')
    git(root, 'update-ref', 'refs/remotes/origin/main', data['base_sha'])
    # Put the bundle under protected Git metadata; it never enters the worktree.
    path = root/'.git'/'retained.bundle'; path.write_bytes(bundle)
    git(root, 'bundle', 'verify', str(path))
    need(git(root, 'bundle', 'list-heads', str(path)).decode().splitlines() == [data['tip_sha']+' refs/heads/candidate'],
         'bundle-head-mismatch')
    git(root, 'fetch', '--no-tags', '--no-recurse-submodules', str(path), 'refs/heads/candidate:refs/heads/candidate')
    lines = git(root, 'rev-list', '--reverse', '--parents', data['base_sha']+'..'+data['tip_sha']).decode().splitlines()
    need(0 < len(lines) <= 1000, 'candidate-history-limit')
    previous = data['base_sha']
    for line in lines:
        fields = line.split(); need(len(fields) == 2 and fields[1] == previous, 'nonlinear-candidate')
        previous = fields[0]
    need(previous == data['tip_sha'], 'candidate-tip-mismatch')
    patch = git(root, 'diff', '--binary', '--no-ext-diff', '--no-textconv', '--no-renames',
                data['base_sha'], data['tip_sha'], '--')
    need(hashlib.sha256(patch).hexdigest() == data['patch_sha256'], 'candidate-patch-changed')
    paths = git(root, 'diff', '--name-only', '-z', '--no-renames', data['base_sha'], data['tip_sha'], '--').split(b'\0')
    for raw in filter(None, paths):
        name = raw.decode('utf-8')
        need(any(area == '.' or name == area or name.startswith(area+'/') for area in allowed_areas), 'candidate-area-denied')
    # Only regular files are supported by this first adapter. No symlink or
    # gitlink can redirect trusted verification outside the clean checkout.
    for entry in git(root, 'ls-tree', '-rz', data['tip_sha']).split(b'\0'):
        if entry:
            need(entry.split(b' ', 1)[0] in (b'100644', b'100755'), 'candidate-file-mode-denied')
    branch = 'dispatch/run-' + digest(data)[:16]
    git(root, 'checkout', '-b', branch, data['tip_sha'])
    need(not git(root, 'status', '--porcelain', '--untracked-files=all'), 'candidate-checkout-dirty')
    return branch


class _Quota:
    def blocked(self, provider): return False  # Sovite owns actual admission/budget.


class RepositoryDelivery:
    def __init__(self, root, spec, work, workspace, execution, *, predecessor=None):
        self.root = private_root(root)
        self.spec, self.work, self.workspace, self.execution = spec, work, workspace, execution
        need(spec.get('schema_version') == 'agentops-repository-delivery/v1', 'unsupported-delivery-profile')
        need(type(spec.get('max_repairs')) is int and 0 <= spec['max_repairs'] <= 3, 'repair-policy-unsupported')
        self.repair_contract = None
        if spec['max_repairs']:
            policy = spec.get('repair')
            need(type(policy) is dict and set(policy) == {'owner_contract','feedback_contract_id','max_cost_usd'}
                 and isinstance(policy['feedback_contract_id'], str) and policy['feedback_contract_id']
                 and type(policy['max_cost_usd']) in (int,float) and math.isfinite(policy['max_cost_usd'])
                 and 0 <= policy['max_cost_usd'] <= spec['packet']['max_cost_usd'], 'repair-policy-invalid')
            self.repair_contract = OwnerRepairContract(policy['owner_contract'], self.root)
        need(isinstance(spec.get('basis'), dict) and SHA.fullmatch(spec['basis'].get('current_release_digest') or ''),
             'current-work-release-required')
        source_url = urlsplit(spec['canonical_url'])
        need(source_url.scheme == 'https' and source_url.netloc and not source_url.username
             and not source_url.password and not source_url.query and not source_url.fragment, 'public-source-url-required')
        need(COMMIT.fullmatch(spec['packet']['base_sha']), 'full-base-required')
        need(spec['packet']['repository_id'] == spec['repository_id'], 'repository-binding-mismatch')
        self.config, self.quota = {'max_workers':1, 'launch_spacing':0}, _Quota()
        self.store = Store(self.root/'scheduler')
        old = self.store.meta('spec')
        selectors = {'publication_attempt_id', 'repair_feedback'}
        if old is not None and old != spec and {k:v for k,v in old.items() if k not in selectors} == {k:v for k,v in spec.items() if k not in selectors}:
            task = self.store.tasks()[0]
            if old.get('publication_attempt_id') != spec.get('publication_attempt_id'):
                need(task['state'] in ('REVIEWED', 'MERGING'), 'publication-selector-too-early')
            if old.get('repair_feedback') != spec.get('repair_feedback'):
                need(task['state'] == 'BLOCKED' and task.get('repair_pending'), 'repair-selector-too-early')
                selected = spec.get('repair_feedback')
                need(selected is None or (type(selected) is dict and set(selected) == {'parent_run_id','release_id'}
                     and selected['parent_run_id'] == task['repair_pending']['parent_run_id']), 'repair-feedback-selector-invalid')
            self.current()
            self.store.event('owner-selector-selected', publication_attempt_id=spec.get('publication_attempt_id'),
                             repair_feedback=spec.get('repair_feedback'))
            self.store.setmeta('spec', spec)
            old = spec
        if old is not None and old != spec:
            need(predecessor == old['run_id'] and old['run_id'] != spec['run_id'], 'profile-changed-requires-new-continuation')
            mutable = {'run_id', 'grant_id', 'lease_id', 'basis', 'publication_attempt_id', 'repair_feedback'}
            need({k:v for k,v in old.items() if k not in mutable} ==
                 {k:v for k,v in spec.items() if k not in mutable}, 'continuation-profile-changed')
            self.current()
            parent = self.work.invoke('work.run.predecessor-context-v1', {'run_id':spec['run_id']}, spec['repo_id'])
            need(parent['predecessor_run_id'] == predecessor, 'predecessor-not-owner-bound')
            self.store.event('successor-bound', predecessor=predecessor, run_id=spec['run_id'])
            self.store.setmeta('spec', spec)
        if old is None:
            self.current()
            self.store.setmeta('spec', spec)
            self.store.save({'id': 'delivery', 'state':'PLANNED', 'areas':spec['allowed_areas'],
                'provider':'sovite', 'model':spec['packet']['executor_id'], 'dependencies':[],
                'attempt':None, 'worktree':str(self.root/'candidate')})

    def close(self): self.store.close()
    def candidate_path(self, task):
        count = task.get('repair_count', 0)
        need(type(count) is int and 0 <= count <= 3, 'repair-history-invalid')
        return self.root / ('candidate' if count == 0 else 'candidate-'+str(count))

    def driver_directory(self, name, task):
        count = task.get('repair_count', 0)
        self.candidate_path(task)
        return self.root / ('driver-'+name+('-'+str(count) if count else ''))

    def current(self):
        s = self.spec
        binding = self.work.invoke('work.run.resolve-v2', {'run_id':s['run_id']}, s['repo_id'])
        need(binding['run_id'] == s['run_id'] and binding['grant_id'] == s['grant_id']
             and binding['state'] == 'active' and binding['superseded_by_run_id'] is None, 'stale-work-run')
        delta = self.work.invoke('work.run.continuation-delta-v1', {'run_id':s['run_id'], 'item_id':s['item_id'],
                                 'checkpoint':s['basis']}, s['repo_id'])['delta']
        need(all(isinstance(delta['current'].get(key), str)
                 and re.fullmatch(r'sha256:[0-9a-f]{64}', delta['current'][key])
                 for key in ('current_decision_digest','current_reference_set_digest')), 'current-work-basis-unavailable')
        need(delta['current'] == s['basis'] and delta['work']['status'] in ('pending','active'), 'work-basis-changed')
        item = self.work.invoke('work.read.item', {'item_id':s['item_id']}, s['repo_id'])['item']
        need(item['edit_revision'] == s['basis']['work_edit_revision']
             and s['packet']['goal'] == item['description'], 'current-requirements-mismatch')
        lease = self.work.invoke('work.lease.read-v1' , {'item_id':s['item_id']}, s['repo_id'])['current_lease']
        need(lease and lease['lease_id'] == s['lease_id'] and lease['run_id'] == s['run_id']
             and lease['state'] == 'active' and lease['stale'] is False, 'stale-work-lease')
        release = self.work.invoke('work.read.release', {'item_id':s['item_id']}, s['repo_id'])['release']
        need(release and release['release_digest'] == s['basis']['current_release_digest']
             and lease.get('basis_release_digest') == release['release_digest']
             and isinstance(lease.get('basis_item_revision'), str)
             and lease['basis_item_revision'] == release['item_revision'], 'work-lease-basis-unavailable')
        # The owner refreshes the same lease. No claim takeover occurs here.
        self.work.invoke('work.lease.heartbeat-v1', {'lease_id':s['lease_id'], 'run_id':s['run_id']}, s['repo_id'])
        return lease

    def step(self):
        if self.store.tasks()[0]['state'] == 'MERGED': return self.store.tasks()[0]
        task = self.store.tasks()[0]
        if task['state'] == 'MERGING' and task.get('outcome_payload'):
            if self.observe_settlement(task): return self.store.tasks()[0]
        if task.get('work_stop'):
            self.stop_owned_execution(task, task['work_stop'])
            return self.store.tasks()[0]
        try:
            self.current()
            tick(self)
        except DeliveryError as exc:
            if str(exc) in {'stale-work-run', 'work-basis-changed', 'current-requirements-mismatch',
                            'stale-work-lease', 'work-lease-basis-unavailable', 'current-work-basis-unavailable'}:
                self.stop_owned_execution(self.store.tasks()[0], str(exc))
                return self.store.tasks()[0]
            raise
        return self.store.tasks()[0]
    def stop_owned_execution(self, task, reason):
        current = self.store.tasks()[0]
        need(current['id'] == task['id'] and current['state'] != 'MERGED', 'cancellation-task-changed')
        # The tick may already have acknowledged a child or durably stored its
        # submission. Never replace those facts with a pre-tick task snapshot.
        task = current
        # A stale Work poll has bounded local effect. The execution owner owns
        # cancellation and in-flight calls may already have crossed admission.
        pending = task.get('repair_pending') or {}
        key = pending.get('submission_key') or task.get('submission_key')
        run_id = None if pending.get('submission_key') else task.get('execution_id')
        task = self.save(task, 'BLOCKED', work_stop=reason, cause=reason, resume=None,
                         cancellation_intent={'submission_key':key, 'run_id':run_id, 'reason':reason})
        if not key:
            self.save(task, cancellation_state='no-submission-intent'); return
        params = {'workspace_id':self.spec['packet']['workspace_id']}
        if not run_id:
            listed = self.execution.call('GET', '/runs', params=dict(params, limit=100))['runs']
            found = [r for r in listed if r.get('idempotency_key') == key
                     and r.get('repository_id') == self.spec['repository_id']
                     and r.get('workspace_id') == params['workspace_id']]
            need(len(found) <= 1, 'cancellation-owner-history-ambiguous')
            if not found:
                self.save(task, cancellation_state='submission-outcome-unknown'); return
            run_id = found[0]['id']
        run = self.execution.call('GET', '/runs/'+run_id, params=params)['run']
        need(run['id'] == run_id and run.get('idempotency_key') == key
             and run['repository_id'] == self.spec['repository_id']
             and run['workspace_id'] == params['workspace_id'], 'cancellation-source-mismatch')
        if run['state'] not in ('completed','failed','cancelled','blocked'):
            run = self.execution.call('POST', '/runs/'+run_id+'/cancel', params=params)['run']
            need(run['id'] == run_id, 'cancellation-source-mismatch')
        self.save(task, cancellation_state=run['state'], cancellation_receipt=run)

    def ingest(self): pass
    def ingest_usage(self): pass
    def retry_deferred_failovers(self): pass
    def resume_quota_blocked(self, task):
        if task.get('repair_pending'):
            self.progress_repair(task)
    def capture_checkpoints(self, task): return task
    def finalize_tick(self): pass
    def waiting(self, task, cause): return task
    def save(self, task, state=None, **updates): return self.store.save(task, state, **updates)
    def block(self, task, cause, resume): return self.save(task, 'BLOCKED', cause=cause, resume=resume)

    def start_worker(self, task):
        self.current()
        s = self.spec
        if task.get('repair_ack'):
            ack = task['repair_ack']
            need(ack['repair_number'] == task['repair_count'] and task['execution_id'] == ack['run_id'], 'repair-acknowledgement-changed')
            self.save(task, 'RUNNING', attempt='sovite:'+task['submission_key'], cause=None, resume=None)
            return
        caps = self.execution.call('GET', '/capabilities', params={'workspace_id':s['packet']['workspace_id']})
        eligible = [e for e in caps['executors'] if e['id'] == s['packet']['executor_id'] and e['launch_supported'] is True
                    and e['availability'] == 'available' and s['repository_id'] in e['repository_ids']]
        need(len(eligible) == 1, 'qualified-mutable-executor-unavailable')
        preview = digest({'packet':s['packet'], 'principal':s['sovite_principal']})
        body = {'schema_version':'sovite-repository-run/v1', 'preview_id':preview, 'packet':s['packet']}
        key = 'delivery-' + digest({'run':s['run_id'], 'packet':s['packet']})
        self.save(task, 'RUNNING', attempt='sovite:'+key, submission=body, submission_key=key, execution_id=None)
        # Sending happens on status(), after the exact intent is persisted.

    def status(self, attempt):
        if attempt.startswith('sovite:'):
            self.current()
            task = self.store.tasks()[0]
            if not task.get('execution_id'):
                run = self.execution.call('POST', '/runs', json=task['submission'],
                    headers={'Idempotency-Key':task['submission_key']})['run']
                need(run['preview_id'] == task['submission']['preview_id'], 'execution-submission-mismatch')
                task = self.save(task, execution_id=run['id'])
            run = self.execution.call('GET', '/runs/'+task['execution_id'],
                    params={'workspace_id':self.spec['packet']['workspace_id']})['run']
            need(run['repository_id'] == self.spec['repository_id'] and run['id'] == task['execution_id'], 'execution-source-mismatch')
            if run['state'] in ('failed','cancelled','blocked'):
                return {'exit':'check_failed', 'run':run}
            if run['state'] != 'completed': return None
            retained = [e for e in run['evidence'] if e.get('label') == 'retained-candidate']
            if not retained:
                if task.get('waiting_cause') != 'candidate-retention-pending':
                    self.save(task, waiting_cause='candidate-retention-pending')
                return None  # output procedure/retention is pending at its owner
            need(len(retained) == 1 and retained[0]['sha256'] == retained[0]['receipt']['sha256'], 'retention-evidence-invalid')
            return {'exit':'committed', 'run':run, 'retained':retained[0]['receipt']}
        result = self.store.meta(attempt)
        if result is None:
            task = self.store.tasks()[0]
            need(task.get('attempt') == attempt and re.fullmatch(r'verify-[1-4]', attempt), 'verification-attempt-mismatch')
            directory = self.driver_directory('check', task)
            need((directory/'result.json').is_file(), 'driver-outcome-unknown')
            # Reconcile an fsynced completed driver result after the scheduler
            # acknowledgement was lost. driver() validates and never reruns it.
            result = self.driver('check', task)
            self.store.setmeta(attempt, result)
        return result

    def finish_worker(self, task, result):
        # status() may have persisted the owner's submission acknowledgement
        # during this same scheduler tick. Collect against that current record,
        # rather than overwrite it with the scheduler's pre-status snapshot.
        current = self.store.tasks()[0]
        need(current['id'] == task['id'] and current['state'] == 'RUNNING'
             and current['attempt'] == task['attempt'], 'execution-collection-changed')
        task = current
        if result['exit'] != 'committed':
            self.block(task, 'execution-failed-or-uncertain', 'PLANNED'); return
        self.current()
        receipt = result['retained']; s = self.spec
        need(receipt['endpoint'] == s['workspace_endpoint'].rstrip('/') and receipt['workspace_id'] == s['workspace_id']
             and receipt['destination'] == s['workspace_destination'] and receipt['output_class'] in s['allowed_classes']
             and type(receipt['size']) is int and 0 <= receipt['size'] <= MAX_ARTIFACT, 'current-reader-policy-denied')
        response = self.workspace.invoke('knowledge.artifact.download-v1', {'workspace_id':receipt['workspace_id'],
            'artifact_id':receipt['artifact_id'], 'version':receipt['version_id']})
        need(response['artifact_id'] == receipt['artifact_id'] and response['version_id'] == receipt['version_id']
             and response['processing_state'] == 'ready' and response['sha256'] == receipt['sha256']
             and response['size'] == receipt['size'] and len(response['content_base64']) <= 4*((MAX_ARTIFACT+2)//3), 'retained-version-changed')
        raw = base64.b64decode(response['content_base64'], validate=True)
        data, bundle = validate_export(raw, receipt, repository_id=s['repository_id'],
                                      base_sha=s['packet']['base_sha'], run_id=task['execution_id'])
        need(any(a['id'] == data['attempt_id'] and a['state'] == 'completed' for a in result['run']['attempts']), 'execution-attempt-mismatch')
        count = task.get('repair_count', 0)
        retained_path = self.root / ('retained-export.json' if not count else 'retained-export-'+str(count)+'.json')
        need(not retained_path.exists() or retained_path.read_bytes() == raw, 'retained-export-changed')
        write_exact(retained_path, raw)
        candidate = self.candidate_path(task)
        branch = import_candidate(candidate, s['canonical_url'], data, bundle, s['allowed_areas'])
        self.save(task, 'READY', worker_commit=data['tip_sha'], attempt=None, retained=receipt, branch=branch,
                  execution_receipt=result['run'], waiting_cause=None, worktree=str(candidate),
                  check=None, review=None, verification_done=False, verified_tip=None)

    def main_tip(self):
        task = self.store.tasks()[0]
        if not task.get('worker_commit'): return self.spec['packet']['base_sha']
        data = git(self.candidate_path(task), 'ls-remote', 'origin', 'refs/heads/main').decode().split()
        need(len(data) == 2 and COMMIT.fullmatch(data[0]), 'canonical-main-unavailable')
        return data[0]

    def integrity(self, task):
        repo = self.candidate_path(task)
        need(git(repo, 'rev-parse', 'HEAD').decode().strip() == task['worker_commit']
             and not git(repo, 'status', '--porcelain', '--untracked-files=all'), 'candidate-mutated')

    def verification_command(self): return [self.spec['acceptance']['check']['path']]
    def attempt(self, kind, task, command, cwd, provider, model, base):
        self.current(); self.integrity(task)
        need(base == self.spec['packet']['base_sha'], 'canonical-base-changed')
        number = task.get('attempts', 0) + 1
        need(number <= task.get('repair_count', 0)+1, 'verification-retry-requires-reconciliation')
        name = 'verify-'+str(number)
        self.store.setmeta(name+':intent', {'base':base, 'tip':task['worker_commit']})
        return name, number

    def driver(self, name, task):
        policy = self.spec['acceptance']; driver = policy[name]
        from datetime import datetime, timezone
        expires = datetime.fromisoformat(policy['expires_at'].replace('Z','+00:00'))
        need(expires.tzinfo and expires > datetime.now(timezone.utc) and policy['qualification_ref'], 'acceptance-profile-unqualified')
        need(task['retained']['output_class'] in policy['allowed_classes'], 'acceptance-clearance-denied')
        path = Path(driver['path'])
        need(path.is_absolute() and path.resolve() == path and path.is_file()
             and path.stat().st_uid in (0, os.getuid()) and not path.stat().st_mode & 0o022
             and self.root not in path.parents and hashlib.sha256(path.read_bytes()).hexdigest() == driver['sha256'], 'trusted-driver-changed')
        directory = self.driver_directory(name, task)
        need(type(driver['timeout_seconds']) is int and 1 <= driver['timeout_seconds'] <= 3600, 'driver-timeout-invalid')
        if directory.exists():
            need((directory/'result.json').is_file(), 'driver-outcome-unknown')
            result = load(directory/'result.json', 65536)
            clean = directory/'checkout'
            need(result['candidate'] == task['worker_commit'] and result['base'] == self.spec['packet']['base_sha']
                 and result['driver_sha256'] == driver['sha256'] and result['profile'] == digest(policy)
                 and result['log_sha256'] == hashlib.sha256((directory/'output.log').read_bytes()).hexdigest()
                 and git(clean, 'rev-parse', 'HEAD').decode().strip() == task['worker_commit']
                 and not git(clean, 'status', '--porcelain', '--untracked-files=all'), 'driver-result-changed')
            return result
        directory.mkdir(mode=0o700)
        clean = directory/'checkout'
        # Independent clean checkout for check and review. The qualified driver
        # owns sandboxing; candidate configuration never supplies its command.
        git(directory, 'clone', '--no-hardlinks', '--no-checkout', str(self.candidate_path(task)), str(clean))
        git(clean, 'checkout', '--detach', task['worker_commit'])
        command = [str(path), str(clean), self.spec['packet']['base_sha'], task['worker_commit']]
        atomic(directory/'intent.json', {'command':command, 'driver_sha256':driver['sha256'], 'profile':digest(policy)})
        with (directory/'output.log').open('w') as output:
            code = run_child(command, output, spec={'cwd':str(directory), 'timeout':driver['timeout_seconds']},
                attempt_dir=directory, env={'PATH':os.defpath, 'LANG':'C'}, started_at=time.time())
        need(hashlib.sha256(path.read_bytes()).hexdigest() == driver['sha256']
             and git(clean, 'rev-parse', 'HEAD').decode().strip() == task['worker_commit']
             and not git(clean, 'status', '--porcelain', '--untracked-files=all'), 'verification-input-mutated')
        result = {'exit':'committed' if code == 0 else 'check_failed', 'candidate':task['worker_commit'],
                  'base':self.spec['packet']['base_sha'], 'driver_sha256':driver['sha256'], 'profile':digest(policy),
                  'log_sha256':hashlib.sha256((directory/'output.log').read_bytes()).hexdigest(), 'exit_code':code}
        atomic(directory/'result.json', result)
        return result

    def launch(self, path):
        task = self.store.tasks()[0]
        self.current(); self.integrity(task)
        self.store.setmeta(str(path), self.driver('check', task))

    def finish_verify(self, task, result):
        self.current(); self.integrity(task)
        if result['exit'] != 'committed' or result['candidate'] != task['worker_commit']:
            self.begin_repair(task, 'check', result); return
        self.save(task, verification_done=True, verified_tip=result['candidate'], check=result)

    def accept_review(self, task):
        self.current(); self.integrity(task)
        need(self.spec['acceptance']['check']['sha256'] != self.spec['acceptance']['review']['sha256'], 'independent-review-required')
        result = self.driver('review', task)
        if result['exit'] != 'committed':
            self.begin_repair(task, 'review', result); return
        self.save(task, 'REVIEWED', review=result)

    def begin_repair(self, task, name, result):
        cause = 'verification-failed' if name == 'check' else 'independent-review-failed'
        if not self.spec.get('max_repairs'):
            self.block(task, cause, 'READY'); return
        count = task.get('repair_count', 0)
        if count >= self.spec['max_repairs']:
            self.block(task, 'repair-budget-exhausted', 'READY'); return
        # Only a completed qualified driver failure is repair evidence. Missing
        # results, timeout/process-control failures and model-run failure have
        # separate reconciliation paths and cannot acquire repair authority.
        need(result.get('exit') == 'check_failed' and type(result.get('exit_code')) is int
             and 1 <= result['exit_code'] < 124 and result['candidate'] == task['worker_commit'],
             'repair-feedback-result-unavailable')
        need(self.driver(name, task) == result, 'repair-feedback-result-changed')
        pending = {'parent_run_id':task['execution_id'], 'root_run_id':task.get('repair_root_run_id', task['execution_id']),
                   'candidate_sha256':task['retained']['sha256'], 'candidate_tip_sha':task['worker_commit'],
                   'repair_number':count+1, 'driver':name, 'result':result}
        self.save(task, 'BLOCKED', cause='repair-feedback-pending', resume='PLANNED', repair_pending=pending)

    def progress_repair(self, task):
        self.current(); self.integrity(task)
        pending = dict(task['repair_pending'])
        need(pending['repair_number'] == task.get('repair_count', 0)+1
             and pending['repair_number'] <= self.spec['max_repairs']
             and pending['parent_run_id'] == task['execution_id']
             and pending['candidate_sha256'] == task['retained']['sha256']
             and pending['candidate_tip_sha'] == task['worker_commit']
             and self.driver(pending['driver'], task) == pending['result'], 'repair-history-changed')
        selected = self.spec.get('repair_feedback')
        if selected is not None:
            need(type(selected) is dict and set(selected) == {'parent_run_id', 'release_id'}
                 and isinstance(selected['release_id'], str)
                 and re.fullmatch(r'release_[0-9a-f]{64}', selected['release_id']), 'repair-feedback-selector-invalid')
        if not pending.get('feedback_release_id') and selected and selected['parent_run_id'] == pending['parent_run_id']:
            pending['feedback_release_id'] = selected['release_id']
            task = self.save(task, repair_pending=pending)
        if not pending.get('feedback_release_id'):
            try:
                context = self.execution.repair_call(self.repair_contract, 'repositoryRepairFeedbackContext', {
                    'parent_run_id':pending['parent_run_id'], 'feedback_contract_id':self.spec['repair']['feedback_contract_id']})
            except DeliveryError as exc:
                if str(exc).startswith('execution-owner-refused:403:'):
                    self.save(task, cause='repair-feedback-release-required', repair_pending=pending)
                    return
                raise
            need(context['parent_run_id'] == pending['parent_run_id']
                 and context['candidate_sha256'] == pending['candidate_sha256']
                 and context['candidate_tip_sha'] == pending['candidate_tip_sha'], 'repair-feedback-context-changed')
            if pending.get('feedback_context'):
                need(pending['feedback_context'] == context, 'repair-feedback-context-changed')
            else:
                directory = self.driver_directory(pending['driver'], task)
                with (directory/'output.log').open('rb') as stream:
                    excerpt = stream.read(12000).decode('utf-8', errors='replace')
                feedback = {'schema_version':'sovite-repository-repair-feedback/v1',
                    'parent_run_id':pending['parent_run_id'], 'candidate_export_sha256':pending['candidate_sha256'],
                    'candidate_tip_sha':pending['candidate_tip_sha'],
                    'result':'check_failed' if pending['driver'] == 'check' else 'review_failed',
                    'feedback':canonical({'driver_result':pending['result'], 'log_excerpt':excerpt,
                        'log_excerpt_max_bytes':12000, 'full_log_sha256':pending['result']['log_sha256']}).decode()}
                self.repair_contract.feedback(feedback)
                result_sha = digest(pending['result'])
                approval = {'source_job_id':context['parent_run_id'], 'source_digest':context['source_digest'],
                    'contract_id':context['contract_id'], 'expected_contract_revision':context['contract_revision'],
                    'expected_generation':context['expected_generation'], 'content':canonical(feedback).decode(),
                    'evidence_refs':[{'owner':'agentops.repository-delivery', 'resource_id':'driver-result:'+result_sha,
                        'revision':'sha256:'+pending['result']['driver_sha256'], 'content_digest':'sha256:'+result_sha}]}
                pending.update(feedback_context=context, approval=approval)
                task = self.save(task, repair_pending=pending, cause='repair-feedback-approval-pending')
            # The eligible owned-parent context was reacquired above on every
            # retry. A different credential cannot approve as another actor.
            self.current()
            release = self.execution.approve_feedback(pending['approval'])
            need(isinstance(release.get('release_id'), str)
                 and re.fullmatch(r'release_[0-9a-f]{64}', release['release_id'])
                 and release.get('contract_revision') == context['contract_revision'], 'repair-feedback-approval-unknown')
            pending['feedback_release_id'] = release['release_id']
            task = self.save(task, repair_pending=pending)
        if not pending.get('submission'):
            repair = {'parent_run_id':pending['parent_run_id'], 'candidate_sha256':pending['candidate_sha256'],
                      'feedback_release_id':pending['feedback_release_id'], 'max_cost_usd':self.spec['repair']['max_cost_usd']}
            body = dict(repair, schema_version='sovite-repository-repair/v1',
                        preview_id=digest({'principal':self.spec['sovite_principal'], 'repair':repair}))
            self.repair_contract.request('repositoryRepairSubmit', body)
            pending.update(submission=body, submission_key='delivery-repair-'+digest({'run_id':self.spec['run_id'],
                           'repair_number':pending['repair_number'], 'repair':body}))
            task = self.save(task, repair_pending=pending, cause='repair-submission-pending')
        self.current()
        ack = self.execution.repair_call(self.repair_contract, 'repositoryRepairSubmit', pending['submission'], key=pending['submission_key'])
        need(ack['parent_run_id'] == pending['parent_run_id'] and ack['root_run_id'] == pending['root_run_id']
             and ack['repair_number'] == pending['repair_number'] and ack['run_id'] != pending['parent_run_id'], 'repair-submission-mismatch')
        history = [*task.get('repair_history', []), {'parent_run_id':task['execution_id'],
            'retained':task['retained'], 'candidate_tip_sha':task['worker_commit'], 'driver':pending['driver'],
            'driver_result':pending['result'], 'feedback_context':pending.get('feedback_context'),
            'approval':pending.get('approval'), 'feedback_release_id':pending['feedback_release_id'],
            'submission':pending['submission'], 'submission_key':pending['submission_key'], 'acknowledgement':ack}]
        self.save(task, 'PLANNED', repair_history=history, repair_pending=None, repair_ack=ack,
                  repair_count=pending['repair_number'], repair_root_run_id=pending['root_run_id'],
                  execution_id=ack['run_id'], submission=pending['submission'], submission_key=pending['submission_key'],
                  attempt=None, cause=None, resume=None, check=None, review=None, verification_done=False,
                  verified_tip=None, publication=None)

    def integrate(self, task):
        self.current(); self.integrity(task)
        from dispatch_publish import authority_gate, publish
        s = self.spec
        # Existing redeemed exact-target effect attempt is required. This
        # consumer neither accepts effects nor grants itself merge authority.
        need(s.get('publication_attempt_id') or task.get('publication'), 'publication-attempt-required')
        args = SimpleNamespace(authority_environment=Path(s['authority_environment']), authority_repo=s['repo_id'],
            run_id=s['run_id'], grant_id=s['grant_id'], attempt_id=s['publication_attempt_id'],
            profile=Path(s['work_profile']), repo=str(self.candidate_path(task)), tip=task['worker_commit'])
        if not task.get('publication'):
            refusal, target = authority_gate(args)
            need(refusal is None and target, 'publication-authority-refused')
            need(self.main_tip() == task['verified_base'], 'canonical-base-changed')
            self.store.setmeta('publication-intent', {'tip':task['worker_commit'], 'target':target})
            result = publish(str(self.candidate_path(task)), task['worker_commit'], task['branch'], [task['worker_commit']],
                             [str(s['item_id'])], target)
            task = self.save(task, publication=result)
        # Branch/PR creation is not canonical integration. The repository
        # owner's existing landing path must integrate the exact verified tip.
        git(self.candidate_path(task), 'fetch', '--no-tags', 'origin', 'refs/heads/main:refs/remotes/origin/main')
        if not git_ancestor(self.candidate_path(task), task['worker_commit'], 'origin/main'):
            return  # exact candidate still awaiting the repository owner
        self.current()
        payload = {'candidate':task['worker_commit'], 'base':task['verified_base'], 'basis':s['basis'],
                   'retained':task['retained'], 'verification':task['check'], 'review':task['review'], 'publication':task['publication']}
        self.report_outcome(task, payload)

    def report_outcome(self, task, payload):
        s = self.spec
        if not task.get('outcome_payload'):
            catalog = self.work.catalog()
            operations = [op for op in catalog['operations'] if op['name'] == 'work.lease.report-outcome-v2']
            need(len(operations) <= 1, 'owner-catalog-operation-ambiguous')
            if operations:
                need('checkpoint' in operations[0]['input_schema']['required'], 'owner-outcome-basis-contract-unsupported')
                lease = self.current()
                body = {'lease_id':s['lease_id'], 'run_id':s['run_id'], 'outcome':'succeeded',
                    'summary':'Verified exact repository candidate integrated on canonical main',
                    'payload':payload, 'checks':[{'name':'review','status':'passed'}, {'name':'tests','status':'passed'}],
                    'checkpoint':s['basis'], 'idempotency_key':'delivery-outcome-'+digest(payload)}
                task = self.save(task, outcome_payload=payload, outcome_intent=body,
                                 settlement_principal_id=lease['principal_id'])
            else:
                # Legacy owners preserve full evidence but cannot atomically
                # compare this exact reference/Decision basis at settlement.
                note = self.work.invoke('work.session-note.write-v1', {'run_id':s['run_id'],
                    'note':canonical({'schema':'agentops-repository-delivery-result/v1', 'result':payload,
                                      'sha256':digest(payload)}).decode(),
                    'idempotency_key':'delivery-evidence-'+digest(payload)}, s['repo_id'])
                self.save(task, outcome_payload=payload, outcome_note_id=note['note_id'],
                          outcome_report={'settled':False, 'reason':'owner-exact-basis-operation-unavailable', 'note_id':note['note_id']})
                return
        if task.get('outcome_intent') and not task.get('owner_outcome_report'):
            result = self.work.invoke('work.lease.report-outcome-v2', task['outcome_intent'], s['repo_id'])
            self.match_outcome_report(task, result['report'])
            self.save(task, owner_outcome_report=result['report'], outcome_report=result)

    def match_outcome_report(self, task, report):
        body = task['outcome_intent']
        need(report.get('lease_id') == body['lease_id'] and report.get('run_id') == body['run_id']
             and report.get('item_id') == self.spec['item_id']
             and report.get('principal_id') == task['settlement_principal_id']
             and all(report.get(k) == body[k] for k in ('outcome','summary','payload','checks'))
             and isinstance(report.get('payload_digest'), str) and SHA.fullmatch(report['payload_digest']),
             'owner-outcome-report-mismatch')

    def observe_settlement(self, task):
        s = self.spec
        decisions = self.work.invoke('work.read.item-decisions', {'item_id':s['item_id']}, s['repo_id'])
        if decisions['status'] != 'done': return False
        if task.get('outcome_intent'):
            observed = self.work.invoke('work.lease.read-v1', {'item_id':s['item_id']}, s['repo_id'])
            reports = [r for r in observed['outcome_reports'] if r.get('lease_id') == s['lease_id']
                       and r.get('run_id') == s['run_id'] and r.get('disposition') == 'settled']
            need(len(reports) == 1, 'owner-outcome-report-unavailable')
            report = reports[0]
            if task.get('owner_outcome_report'):
                need(report['report_id'] == task['owner_outcome_report']['report_id'], 'owner-outcome-report-mismatch')
            self.match_outcome_report(task, report)
            need(report['disposition'] == 'settled' and report['decision_id'] == decisions['terminal_decision_id'], 'owner-outcome-not-settled')
            payload_sha = report['payload_digest']
        else:
            payload_sha = digest(task['outcome_payload'])
        accepted = [d for d in decisions['decisions'] if d.get('id') == decisions['terminal_decision_id']
                    and d.get('kind') == 'accept' and d.get('release_digest') == s['basis']['current_release_digest']
                    and payload_sha in d.get('evidence_digests', [])]
        need(len(accepted) == 1, 'owner-settled-different-basis-or-evidence')
        self.save(task, 'MERGED', outcome_report={'settled':True, 'decision':accepted[0],
                                                 'payload_sha256':payload_sha})
        return True



def recovery_policy(path,state_root):
    path=Path(path).absolute();state_root=Path(state_root).absolute()
    need(path.resolve(strict=True)==path and path.is_file() and state_root not in path.parents,
         'protected-recovery-policy-required')
    for parent in (path,*path.parents):
        info=parent.stat();sticky=parent!=path and info.st_uid==0 and info.st_mode&stat.S_ISVTX
        need(info.st_uid in {0,os.getuid()} and (not info.st_mode&0o022 or sticky),
             'protected-recovery-policy-required')
    return load(path,65536)


class HistoricalRecovery:
    """Retain/read an already owned failed attempt without active Work authority."""
    def __init__(self, root, spec, workspace, execution, policy, *, attempt_id, execution_id=None, release_id=None):
        self.root=private_root(root)
        need((self.root/'scheduler'/'state.sqlite3').is_file(),'existing-delivery-state-required')
        self.spec,self.workspace,self.execution=spec,workspace,execution
        need(spec.get('schema_version')=='agentops-repository-delivery/v1'
             and COMMIT.fullmatch(spec['packet']['base_sha'])
             and spec['packet']['repository_id']==spec['repository_id'],'historical-delivery-profile-invalid')
        need(type(policy) is dict and set(policy)=={'schema_version','owner_contract','contract_id','destination_id'}
             and policy['schema_version']=='agentops-repository-recovery/v1'
             and isinstance(policy['contract_id'],str) and policy['contract_id']
             and policy['destination_id']==spec['workspace_destination'],'recovery-policy-invalid')
        self.policy=policy
        self.contract=OwnerRepairContract(policy['owner_contract'],self.root,recovery=True)
        need(isinstance(attempt_id,str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}',attempt_id),'recovery-attempt-invalid')
        need(release_id is None or re.fullmatch(r'release_[0-9a-f]{64}',release_id),'recovery-release-selector-invalid')
        self.attempt_id,self.execution_id,self.release_id=attempt_id,execution_id,release_id
        self.policy_digest=digest({**policy,'owner_contract':{key:value for key,value in policy['owner_contract'].items() if key!='root'}})
        self.store=Store(self.root/'scheduler')
        try:
            need(self.store.meta('spec')==spec,'historical-delivery-profile-changed')
            need(len(self.store.tasks())==1 and self.store.tasks()[0]['id']=='delivery','historical-delivery-task-required')
        except Exception:
            self.store.close();raise

    def close(self):self.store.close()

    def _run(self):
        task=self.store.tasks()[0]
        pending=task.get('repair_pending') or {}
        key=pending.get('submission_key') or task.get('submission_key')
        need(isinstance(key,str) and re.fullmatch(r'[A-Za-z0-9_.-]{16,128}',key),'historical-submission-intent-required')
        selected=self.execution_id or (None if pending.get('submission_key') else task.get('execution_id'))
        if selected is None:
            receipt=task.get('cancellation_receipt') or {}
            if receipt.get('idempotency_key')==key:selected=receipt.get('id')
        params={'workspace_id':self.spec['packet']['workspace_id']}
        if selected is None:
            runs=self.execution.call('GET','/runs',params={**params,'limit':500})['runs']
            matches=[row for row in runs if row.get('idempotency_key')==key
                and row.get('workspace_id')==params['workspace_id'] and row.get('repository_id')==self.spec['repository_id']]
            need(len(matches)==1,'historical-submission-outcome-unknown')
            selected=matches[0]['id']
        need(isinstance(selected,str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}',selected),'historical-run-selector-invalid')
        run=self.execution.call('GET','/runs/'+selected,params=params)['run']
        need(run['id']==selected and run.get('idempotency_key')==key
             and run['repository_id']==self.spec['repository_id'] and run['workspace_id']==params['workspace_id']
             and run['executor_id']==self.spec['packet']['executor_id'],'historical-source-mismatch')
        submission=pending.get('submission') if pending.get('submission_key') else task.get('submission')
        need(type(submission) is dict,'historical-submission-intent-required')
        if submission.get('schema_version')=='sovite-repository-run/v1':
            need(submission.get('packet')==self.spec['packet']
                 and isinstance(submission.get('preview_id'),str) and SHA.fullmatch(submission['preview_id'])
                 and run.get('preview_id')==submission['preview_id'],'historical-preview-mismatch')
        elif submission.get('schema_version')=='sovite-repository-repair/v1':
            predecessors=[row for row in run.get('evidence',[]) if row.get('label')=='repair-predecessor']
            need(len(predecessors)==1 and predecessors[0].get('uri')=='sovite://repository-runs/'+submission['parent_run_id']
                 and predecessors[0].get('sha256')==submission['candidate_sha256'],'historical-repair-lineage-mismatch')
            ack=task.get('repair_ack') if not pending.get('submission_key') else None
            need(ack is None or ack['run_id']==run['id'],'historical-repair-acknowledgement-changed')
        else:need(False,'historical-submission-intent-required')
        need(run['state'] in {'blocked','failed','cancelled'},'historical-terminal-execution-required')
        attempts=[row for row in run['attempts'] if row['id']==self.attempt_id]
        need(len(attempts)==1 and attempts[0]['state'] in {'uncertain','interrupted','failed','cancelled'},'historical-attempt-unavailable')
        name='recovery:'+digest({'task_id':task['id'],'submission_key':key,'attempt_id':self.attempt_id})
        identity={'schema_version':'agentops-repository-recovery-state/v1','task_id':task['id'],
            'submission_key':key,'run_id':selected,'attempt_id':self.attempt_id,'policy_digest':self.policy_digest}
        record=self.store.meta(name)
        if record is None:record=identity;self.store.setmeta(name,record)
        need(all(record.get(field)==value for field,value in identity.items()),'historical-recovery-intent-changed')
        return name,record,run

    def _save(self,name,record,**updates):
        record={**record,**updates};self.store.setmeta(name,record);return record

    def _receipt(self,receipt,source_digest=None):
        s=self.spec
        need(receipt['endpoint']==s['workspace_endpoint'].rstrip('/') and receipt['workspace_id']==s['workspace_id']
             and receipt['destination']==s['workspace_destination'] and receipt['output_class'] in s['allowed_classes']
             and type(receipt['size']) is int and 0<=receipt['size']<=MAX_ARTIFACT
             and SHA.fullmatch(receipt['sha256']) and re.fullmatch(r'release_[0-9a-f]{64}',receipt['release_id']),
             'recovery-current-reader-policy-denied')
        need(source_digest is None or source_digest=='sha256:'+receipt['sha256'],'recovery-retained-source-changed')
        return receipt

    def _download(self,receipt,run_id):
        receipt=self._receipt(receipt)
        response=self.workspace.invoke('knowledge.artifact.download-v1',{'workspace_id':receipt['workspace_id'],
            'artifact_id':receipt['artifact_id'],'version':receipt['version_id']})
        need(response['artifact_id']==receipt['artifact_id'] and response['version_id']==receipt['version_id']
             and response['processing_state']=='ready' and response['sha256']==receipt['sha256']
             and response['size']==receipt['size'] and len(response['content_base64'])<=4*((MAX_ARTIFACT+2)//3),
             'recovery-retained-version-changed')
        raw=base64.b64decode(response['content_base64'],validate=True)
        need(len(raw)==receipt['size'] and hashlib.sha256(raw).hexdigest()==receipt['sha256'],'recovery-retained-content-changed')
        data=json.loads(raw,object_pairs_hook=unique_pairs,parse_constant=lambda _:need(False,'invalid-json-number'))
        need(canonical(data)==raw and data['schema_version']=='sovite-repository-candidate-export/v1'
             and data['kind']=='repository-recovery-artifact' and data['run_id']==run_id
             and data['attempt_id']==self.attempt_id and data['workspace_id']==self.spec['packet']['workspace_id']
             and data['repository_id']==self.spec['repository_id'] and data['base_sha']==self.spec['packet']['base_sha']
             and COMMIT.fullmatch(data['tip_sha']) and data['outcome'] in {'uncertain','interrupted','failed','cancelled'}
             and data['publication_eligible'] is False and data['repair_eligible'] is False,'recovery-artifact-source-mismatch')
        projection=data['receipt_projection']
        need('fence' not in projection and digest(projection)==data['receipt_projection_sha256']
             and projection['job_id']==run_id and projection['attempt_id']==self.attempt_id
             and projection['within_deadline'] is False and projection['publication_eligible'] is False
             and projection['repair_eligible'] is False and SHA.fullmatch(projection['packet_sha256'])
             and all(projection[key]==data[key] for key in ('workspace_id','repository_id','base_sha','tip_sha','patch_sha256')),
             'recovery-artifact-provenance-changed')
        bundle=base64.b64decode(data['bundle_base64'],validate=True)
        need(len(bundle)<=MAX_ARTIFACT and hashlib.sha256(bundle).hexdigest()==data['bundle_sha256'],'recovery-artifact-bundle-changed')
        directory=self.root/'recoveries';directory.mkdir(mode=0o700,exist_ok=True)
        need(directory.resolve()==directory and directory.stat().st_uid==os.getuid()
             and not directory.stat().st_mode&0o077,'recovery-storage-unprotected')
        path=directory/(receipt['sha256']+'.json')
        need(not path.is_symlink() and (not path.exists() or path.read_bytes()==raw),'recovery-storage-changed')
        write_exact(path,raw)
        return {'state':'recovery-retained','run_id':run_id,'attempt_id':self.attempt_id,'outcome':data['outcome'],
            'receipt':receipt,'artifact_path':str(path),'publication_eligible':False,'repair_eligible':False}

    def failure(self,reason):
        records=[]
        for row in self.store.db.execute("SELECT body FROM meta WHERE key LIKE 'recovery:%'"):
            record=json.loads(row[0])
            if record.get('attempt_id')==self.attempt_id:records.append(record)
        result={'state':'recovery-unavailable','reason':reason,'attempt_id':self.attempt_id,
                'publication_eligible':False,'repair_eligible':False}
        if len(records)==1:
            record=records[0];result['run_id']=record['run_id']
            if record.get('capture'):
                result['release_request']={'run_id':record['run_id'],'attempt_id':self.attempt_id,
                    'source_digest':record['capture']['source_digest'],'contract_id':self.policy['contract_id'],
                    'destination_id':self.policy['destination_id']}
        if 'recovery_copy_denied' in reason:
            result['next_action']='Use an actual owner-approved --release-id or correct the installed exact-copy policy; this client grants no approval.'
        elif 'unknown-outcome' in reason:
            result['next_action']='Repeat the same recovery invocation to reconcile its saved exact intent.'
        return result

    def step(self):
        name,record,run=self._run();run_id=record['run_id']
        source=(record.get('capture') or {}).get('source_digest')
        history=[row for row in run.get('evidence',[]) if row.get('label')=='retained-recovery-candidate'
                 and row.get('attempt_id')==self.attempt_id]
        need(len(history)<=1,'recovery-retention-history-ambiguous')
        if history:
            entry=history[0];receipt=self._receipt(entry['receipt'],source)
            need(entry['sha256']==receipt['sha256'],'recovery-retention-history-changed')
            if record.get('receipt'):need(record['receipt']==receipt,'recovery-retention-history-changed')
            if self.release_id:need(receipt['release_id']==self.release_id,'recovery-release-selector-changed')
            record=self._save(name,record,receipt=receipt)
        if record.get('receipt'):
            return self._download(record['receipt'],run_id)
        body={'workspace_id':self.spec['packet']['workspace_id'],'attempt_id':self.attempt_id}
        if 'capture_intent' not in record:record=self._save(name,record,capture_intent=body)
        need(record['capture_intent']==body,'recovery-capture-intent-changed')
        if 'capture' not in record:
            captured=self.execution.recovery_call(self.contract,'repositoryRecoveryCapture',run_id,body)
            need(captured['kind']=='repository-recovery-artifact' and captured['run_id']==run_id
                 and captured['attempt_id']==self.attempt_id and captured['workspace_id']==body['workspace_id']
                 and captured['repository_id']==self.spec['repository_id'] and captured['base_sha']==self.spec['packet']['base_sha']
                 and captured['publication_eligible'] is False and captured['repair_eligible'] is False,
                 'recovery-capture-source-changed')
            record=self._save(name,record,capture=captured)
        captured=record['capture']
        selector={**body,'source_digest':captured['source_digest'],'contract_id':self.policy['contract_id'],
                  'destination_id':self.policy['destination_id']}
        if self.release_id:
            need(not record.get('release_id') or record['release_id']==self.release_id,'recovery-release-selector-changed')
            record=self._save(name,record,release_id=self.release_id)
        if not record.get('release_id'):
            if not record.get('context'):
                if 'context_intent' not in record:record=self._save(name,record,context_intent=selector)
                need(record['context_intent']==selector,'recovery-context-intent-changed')
                context=self.execution.recovery_call(self.contract,'repositoryRecoveryContext',run_id,selector)
                need(context['run_id']==run_id and context['attempt_id']==self.attempt_id
                     and context['source_digest']==captured['source_digest'] and context['contract_id']==self.policy['contract_id']
                     and self.policy['destination_id'] in context['destinations']
                     and context['output_class'] in self.spec['allowed_classes']
                     and context['publication_eligible'] is False and context['repair_eligible'] is False,
                     'recovery-procedure-context-changed')
                record=self._save(name,record,context=context)
            context=record['context']
            approval={**selector,'expected_generation':context['expected_generation'],
                      'expected_contract_revision':context['contract_revision']}
            if 'release_intent' not in record:record=self._save(name,record,release_intent=approval)
            need(record['release_intent']==approval,'recovery-release-intent-changed')
            released=self.execution.recovery_call(self.contract,'repositoryRecoveryRelease',run_id,record['release_intent'])
            need(released['contract_revision']==context['contract_revision'] and released['output_class']==context['output_class']
                 and self.policy['destination_id'] in released['destinations'],'recovery-output-release-changed')
            record=self._save(name,record,release=released,release_id=released['release_id'])
        retention={**body,'release_id':record['release_id']}
        if 'retention_intent' not in record:record=self._save(name,record,retention_intent=retention)
        need(record['retention_intent']==retention,'recovery-retention-intent-changed')
        receipt=self.execution.call('POST','/runs/'+run_id+'/candidate-retention',json=retention)['receipt']
        self._receipt(receipt,captured['source_digest'])
        need(receipt['release_id']==record['release_id'],'recovery-retention-release-changed')
        record=self._save(name,record,receipt=receipt)
        return self._download(receipt,run_id)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--predecessor', help='owner-bound predecessor run when adopting a retained continuation')
    parser.add_argument('--recovery-policy',type=Path,help='explicit historical recovery policy; does not run an active delivery tick')
    parser.add_argument('--attempt-id',help='exact failed/uncertain owner attempt for historical recovery')
    parser.add_argument('--execution-id',help='exact already-owned execution selector when its acknowledgement was lost')
    parser.add_argument('--release-id',help='optional actual owner output release selector; grants no approval authority')
    args = parser.parse_args(argv)
    clients = []; adapter = None
    try:
        spec = load(args.spec)
        need(bool(args.recovery_policy)==bool(args.attempt_id),'historical-recovery-selectors-required')
        need(args.recovery_policy or not (args.execution_id or args.release_id),'historical-recovery-mode-required')
        if args.recovery_policy:
            need(args.predecessor is None,'historical-recovery-predecessor-unsupported')
            policy=recovery_policy(args.recovery_policy,args.state)
            workspace=Vuoro(spec['workspace_profile']);clients.append(workspace)
            need(workspace.client.profile.endpoint.rstrip('/')==spec['workspace_endpoint'].rstrip('/'),'workspace-endpoint-mismatch')
            execution=Sovite(spec['sovite_endpoint'],spec['sovite_credential_ref']);clients.append(execution)
            adapter=HistoricalRecovery(args.state,spec,workspace,execution,policy,attempt_id=args.attempt_id,
                execution_id=args.execution_id,release_id=args.release_id)
            print(json.dumps(adapter.step()));return 0
        work = Vuoro(spec['work_profile']); clients.append(work)
        workspace = Vuoro(spec['workspace_profile']); clients.append(workspace)
        need(workspace.client.profile.endpoint.rstrip('/') == spec['workspace_endpoint'].rstrip('/'), 'workspace-endpoint-mismatch')
        execution = Sovite(spec['sovite_endpoint'], spec['sovite_credential_ref']); clients.append(execution)
        adapter = RepositoryDelivery(args.state, spec, work, workspace, execution, predecessor=args.predecessor)
        task = adapter.step()
        print(json.dumps({'state':task['state'], 'execution_id':task.get('execution_id'),
                          'candidate':task.get('worker_commit'), 'cause':task.get('cause') or task.get('waiting_cause'),
                          'outcome':task.get('outcome_report')}))
        return 0
    except Exception as exc:
        code = str(exc) if isinstance(exc, DeliveryError) else 'delivery-unknown-outcome'
        report=adapter.failure(code) if isinstance(adapter,HistoricalRecovery) else {'state':'stopped','reason':code}
        print(json.dumps(report),file=sys.stderr)
        return 1
    finally:
        if adapter: adapter.close()
        for client in reversed(clients): client.close()


if __name__ == '__main__':
    raise SystemExit(main())
