#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
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

    def close(self):
        self.loop.run_until_complete(self.client.__aexit__(None, None, None)); self.loop.close()


class Sovite:
    def __init__(self, endpoint, credential_ref):
        import httpx
        url = urlsplit(endpoint)
        need(url.scheme == 'https' and url.netloc and url.path in ('', '/') and not url.username
             and not url.password and not url.query and not url.fragment, 'invalid-execution-endpoint')
        self.client = httpx.Client(base_url=endpoint, headers={'Authorization':'Bearer '+_file_credential(credential_ref)},
                                   timeout=30, follow_redirects=False)

    def call(self, method, path, **kwargs):
        try:
            response = self.client.request(method, '/api/repository-runs/v1' + path, **kwargs)
            need(200 <= response.status_code < 300, 'execution-owner-refused:' + str(response.status_code))
            need(len(response.content) <= 2*MAX_ARTIFACT, 'execution-response-too-large')
            return response.json()
        except DeliveryError:
            raise
        except Exception:
            raise DeliveryError('execution-owner-unknown-outcome') from None

    def close(self): self.client.close()


def git(repo, *args):
    # Repository data cannot enable hooks, filters, replacement objects,
    # attributes helpers, fsmonitor or environment-supplied Git configuration.
    env = {'PATH':os.defpath, 'LANG':'C', 'GIT_CONFIG_NOSYSTEM':'1', 'GIT_CONFIG_GLOBAL':'/dev/null',
           'GIT_NO_REPLACE_OBJECTS':'1', 'GIT_GRAFT_FILE':'/dev/null', 'GIT_TERMINAL_PROMPT':'0'}
    result = subprocess.run([GIT, '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false',
                             '-c', 'core.attributesFile=/dev/null', '-C', str(repo), *args],
                            env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
    need(result.returncode == 0, 'repository-operation-refused')
    need(len(result.stdout) <= 16*MAX_ARTIFACT, 'repository-output-too-large')
    return result.stdout


def validate_export(raw, receipt, *, repository_id, base_sha, run_id):
    need(len(raw) == receipt['size'] and hashlib.sha256(raw).hexdigest() == receipt['sha256'], 'retained-content-changed')
    data = json.loads(raw)
    need(data['schema_version'] == 'sovite-repository-candidate-export/v1'
         and data['repository_id'] == repository_id and data['base_sha'] == base_sha and data['run_id'] == run_id
         and COMMIT.fullmatch(data['tip_sha']), 'candidate-source-mismatch')
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
        need(spec.get('max_repairs') == 0, 'repair-policy-unsupported')
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
        if old is not None and old != spec and {k:v for k,v in old.items() if k != 'publication_attempt_id'} == {k:v for k,v in spec.items() if k != 'publication_attempt_id'}:
            need(self.store.tasks()[0]['state'] in ('REVIEWED', 'MERGING'), 'publication-selector-too-early')
            self.current()
            self.store.event('publication-attempt-selected', attempt_id=spec['publication_attempt_id'])
            self.store.setmeta('spec', spec)
            old = spec
        if old is not None and old != spec:
            need(predecessor == old['run_id'] and old['run_id'] != spec['run_id'], 'profile-changed-requires-new-continuation')
            mutable = {'run_id', 'grant_id', 'lease_id', 'basis', 'publication_attempt_id'}
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
    def current(self):
        s = self.spec
        binding = self.work.invoke('work.run.resolve-v2', {'run_id':s['run_id']}, s['repo_id'])
        need(binding['run_id'] == s['run_id'] and binding['grant_id'] == s['grant_id']
             and binding['state'] == 'active' and binding['superseded_by_run_id'] is None, 'stale-work-run')
        delta = self.work.invoke('work.run.continuation-delta-v1', {'run_id':s['run_id'], 'item_id':s['item_id'],
                                 'checkpoint':s['basis']}, s['repo_id'])['delta']
        need(delta['current'] == s['basis'] and delta['work']['status'] in ('pending','active'), 'work-basis-changed')
        item = self.work.invoke('work.read.item', {'item_id':s['item_id']}, s['repo_id'])['item']
        need(item['edit_revision'] == s['basis']['work_edit_revision']
             and s['packet']['goal'] == item['description'], 'current-requirements-mismatch')
        lease = self.work.invoke('work.lease.read-v1' , {'item_id':s['item_id']}, s['repo_id'])['current_lease']
        need(lease and lease['lease_id'] == s['lease_id'] and lease['run_id'] == s['run_id']
             and lease['state'] == 'active' and lease['stale'] is False, 'stale-work-lease')
        # The owner refreshes the same lease. No claim takeover occurs here.
        self.work.invoke('work.lease.heartbeat-v1', {'lease_id':s['lease_id'], 'run_id':s['run_id']}, s['repo_id'])
        return lease

    def step(self):
        if self.store.tasks()[0]['state'] == 'MERGED': return self.store.tasks()[0]
        task = self.store.tasks()[0]
        if task['state'] == 'MERGING' and task.get('outcome_payload'):
            if self.observe_settlement(task): return self.store.tasks()[0]
        self.current()
        tick(self)
        return self.store.tasks()[0]
    def ingest(self): pass
    def ingest_usage(self): pass
    def retry_deferred_failovers(self): pass
    def resume_quota_blocked(self, task): pass
    def capture_checkpoints(self, task): return task
    def finalize_tick(self): pass
    def waiting(self, task, cause): return task
    def save(self, task, state=None, **updates): return self.store.save(task, state, **updates)
    def block(self, task, cause, resume): return self.save(task, 'BLOCKED', cause=cause, resume=resume)

    def start_worker(self, task):
        self.current()
        s = self.spec
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
        # Missing driver result after restart is UNKNOWN. Do not rerun it.
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
        write_exact(self.root/'retained-export.json', raw)
        branch = import_candidate(self.root/'candidate', s['canonical_url'], data, bundle, s['allowed_areas'])
        self.save(task, 'READY', worker_commit=data['tip_sha'], attempt=None, retained=receipt, branch=branch,
                  execution_receipt=result['run'], waiting_cause=None)

    def main_tip(self):
        task = self.store.tasks()[0]
        if not task.get('worker_commit'): return self.spec['packet']['base_sha']
        data = git(self.root/'candidate', 'ls-remote', 'origin', 'refs/heads/main').decode().split()
        need(len(data) == 2 and COMMIT.fullmatch(data[0]), 'canonical-main-unavailable')
        return data[0]

    def integrity(self, task):
        repo = self.root/'candidate'
        need(git(repo, 'rev-parse', 'HEAD').decode().strip() == task['worker_commit']
             and not git(repo, 'status', '--porcelain', '--untracked-files=all'), 'candidate-mutated')

    def verification_command(self): return [self.spec['acceptance']['check']['path']]
    def attempt(self, kind, task, command, cwd, provider, model, base):
        self.current(); self.integrity(task)
        need(base == self.spec['packet']['base_sha'], 'canonical-base-changed')
        number = task.get('attempts', 0) + 1
        need(number <= 1, 'verification-retry-requires-reconciliation')
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
        directory = self.root/('driver-'+name)
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
        git(directory, 'clone', '--no-hardlinks', '--no-checkout', str(self.root/'candidate'), str(clean))
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
                  'log_sha256':hashlib.sha256((directory/'output.log').read_bytes()).hexdigest()}
        atomic(directory/'result.json', result)
        return result

    def launch(self, path):
        task = self.store.tasks()[0]
        self.current(); self.integrity(task)
        self.store.setmeta(str(path), self.driver('check', task))

    def finish_verify(self, task, result):
        self.current(); self.integrity(task)
        if result['exit'] != 'committed' or result['candidate'] != task['worker_commit']:
            self.block(task, 'verification-failed', 'READY'); return
        self.save(task, verification_done=True, verified_tip=result['candidate'], check=result)

    def accept_review(self, task):
        self.current(); self.integrity(task)
        need(self.spec['acceptance']['check']['sha256'] != self.spec['acceptance']['review']['sha256'], 'independent-review-required')
        result = self.driver('review', task)
        if result['exit'] != 'committed':
            self.block(task, 'independent-review-failed', 'READY'); return
        self.save(task, 'REVIEWED', review=result)

    def integrate(self, task):
        self.current(); self.integrity(task)
        from dispatch_publish import authority_gate, publish
        s = self.spec
        # Existing redeemed exact-target effect attempt is required. This
        # consumer neither accepts effects nor grants itself merge authority.
        need(s.get('publication_attempt_id') or task.get('publication'), 'publication-attempt-required')
        args = SimpleNamespace(authority_environment=Path(s['authority_environment']), authority_repo=s['repo_id'],
            run_id=s['run_id'], grant_id=s['grant_id'], attempt_id=s['publication_attempt_id'],
            profile=Path(s['work_profile']), repo=str(self.root/'candidate'), tip=task['worker_commit'])
        if not task.get('publication'):
            refusal, target = authority_gate(args)
            need(refusal is None and target, 'publication-authority-refused')
            need(self.main_tip() == task['verified_base'], 'canonical-base-changed')
            self.store.setmeta('publication-intent', {'tip':task['worker_commit'], 'target':target})
            result = publish(str(self.root/'candidate'), task['worker_commit'], task['branch'], [task['worker_commit']],
                             [str(s['item_id'])], target)
            task = self.save(task, publication=result)
        # Branch/PR creation is not canonical integration. The repository
        # owner's existing landing path must integrate the exact verified tip.
        git(self.root/'candidate', 'fetch', '--no-tags', 'origin', 'refs/heads/main:refs/remotes/origin/main')
        landed = subprocess.run([GIT, '-C', str(self.root/'candidate'), 'merge-base', '--is-ancestor',
                                 task['worker_commit'], 'origin/main'], capture_output=True)
        if landed.returncode == 1: return  # exact candidate still awaiting the repository owner
        need(landed.returncode == 0, 'canonical-integration-unknown')
        self.current()
        payload = {'candidate':task['worker_commit'], 'base':task['verified_base'], 'basis':s['basis'],
                   'retained':task['retained'], 'verification':task['check'], 'review':task['review'], 'publication':task['publication']}
        # The released lease outcome operation has no atomic expected-basis
        # input. Never use it as an exact-basis acceptance shortcut. Preserve
        # the complete payload at the work owner and observe its independent
        # exact-release/evidence decision through the existing read API.
        if not task.get('outcome_payload'):
            note = self.work.invoke('work.session-note.write-v1', {'run_id':s['run_id'],
                'note':canonical({'schema':'agentops-repository-delivery-result/v1', 'result':payload,
                                  'sha256':digest(payload)}).decode(),
                'idempotency_key':'delivery-evidence-'+digest(payload)}, s['repo_id'])
            self.save(task, outcome_payload=payload, outcome_note_id=note['note_id'],
                      outcome_report={'settled':False, 'reason':'owner-acceptance-pending', 'note_id':note['note_id']})

    def observe_settlement(self, task):
        s = self.spec
        decisions = self.work.invoke('work.read.item-decisions', {'item_id':s['item_id']}, s['repo_id'])
        if decisions['status'] != 'done': return False
        payload_sha = digest(task['outcome_payload'])
        accepted = [d for d in decisions['decisions'] if d.get('id') == decisions['terminal_decision_id']
                    and d.get('kind') == 'accept' and d.get('release_digest') == s['basis']['current_release_digest']
                    and payload_sha in d.get('evidence_digests', [])]
        need(len(accepted) == 1, 'owner-settled-different-basis-or-evidence')
        self.save(task, 'MERGED', outcome_report={'settled':True, 'decision':accepted[0],
                                                 'payload_sha256':payload_sha})
        return True



def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--predecessor', help='owner-bound predecessor run when adopting a retained continuation')
    args = parser.parse_args(argv)
    clients = []; adapter = None
    try:
        spec = load(args.spec)
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
        print(json.dumps({'state':'stopped', 'reason':code}), file=sys.stderr)
        return 1
    finally:
        if adapter: adapter.close()
        for client in reversed(clients): client.close()


if __name__ == '__main__':
    raise SystemExit(main())
