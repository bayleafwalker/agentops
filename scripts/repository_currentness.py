#!/usr/bin/env python3
"""Fixed installed AgentOps currentness veto for Sovite repository jobs.

An owner snapshot is a condition on active work, never a paid/resource grant.
Every check reads the actual owner again. Historical data access, cancellation
and idempotent reconciliation remain governed by their existing owners.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
from contextlib import asynccontextmanager
import hashlib
import json
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit

from repository_delivery import digest, unique_pairs

OPERATION = 'work.lease.currentness-v1'
SCHEMA = 'agentops-work-currentness-binding/v1'
_MUTABLE_SPEC = {'publication_attempt_id', 'repair_feedback'}


def _refuse(code='repository_currentness_binding_invalid'):
    from sovite.repository_currentness import CurrentnessError
    raise CurrentnessError(code)


def _need(condition, code='repository_currentness_binding_invalid'):
    if not condition:
        _refuse(code)


def _read(path):
    from sovite.repository_runtime import protected_bytes
    try:
        return json.loads(protected_bytes(path), object_pairs_hook=unique_pairs,
            parse_constant=lambda _: _refuse())
    except Exception:
        _refuse()


def _stable(spec):
    return {key:value for key,value in spec.items() if key not in _MUTABLE_SPEC}


def _packet(run, task):
    from sovite.repository_runs import validate_run_packet
    return validate_run_packet({'schema_version':'portable-work/v1', 'goal':task,
        **{key:run[key] for key in ('workspace_id','repository_id','executor_id','base_sha',
                                   'max_cost_usd','deadline','concurrency')}})


def _packet_digest(packet):
    # The owner uses its own canonicalization, including Unicode escaping.
    from sovite.repository_runs import canonical_packet_digest
    return canonical_packet_digest(packet)


def _repair_key(spec, repair, caller):
    _need(type(repair['repair_number']) is int and 1 <= repair['repair_number'] <= spec['max_repairs'])
    body = {key:repair[key] for key in ('parent_run_id','candidate_sha256','feedback_release_id')}
    body['max_cost_usd'] = spec['repair']['max_cost_usd']
    body = {**body,'schema_version':'sovite-repository-repair/v1',
        'preview_id':digest({'principal':caller,'repair':body})}
    return 'delivery-repair-'+digest({'run_id':spec['run_id'],'repair_number':repair['repair_number'],'repair':body})


class FixedWorkCurrentness:
    """One protected project implementation; requests cannot select a router.

    The token profile is separate from the delivery coordinator's write profile.
    Its actual owner scope must contain exactly this one read operation. The
    opaque persisted tuple contains selectors and digests, never credentials or
    cached observation times. Owner/service schemas come from the pinned actual
    catalog descriptor and are validated by the released Vuoro client.
    """
    def __init__(self, config_path, *, transport_factory=None):
        self.path = str(Path(config_path).absolute())
        self.config = _read(self.path)
        _need(set(self.config) == {'schema_version','authorization_budget_seconds',
            'watchdog_poll_seconds','deliveries'} and
            self.config['schema_version'] == 'agentops-work-currentness-config/v1')
        for key, bound in (('authorization_budget_seconds',5),):
            value = self.config[key]
            _need(type(value) in (int,float) and 0 < value <= bound)
        _need(type(self.config['watchdog_poll_seconds']) in (int,float)
            and self.config['watchdog_poll_seconds'] == 0.25)
        _need(type(self.config['deliveries']) is list and 1 <= len(self.config['deliveries']) <= 256)
        for entry in self.config['deliveries']:
            _need(type(entry) is dict and set(entry) == {'spec_path','currentness_profile','operation_sha256'})
            _need(type(entry['operation_sha256']) is str and len(entry['operation_sha256']) == 64
                and all(c in '0123456789abcdef' for c in entry['operation_sha256']))
        self.transport_factory = transport_factory
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, name='repository-currentness', daemon=True)
        self.thread.start()

    def close(self):
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5)
        _need(not self.thread.is_alive(),'repository_currentness_unavailable')
        self.loop.close()

    def _budget(self, started):
        _need(time.monotonic()-started < self.config['authorization_budget_seconds'],
            'repository_currentness_unavailable')

    def _entries(self, started):
        self._budget(started)
        _need(_read(self.path) == self.config)
        from vuoro_client.profile import Profile, _profile_schema
        from jsonschema import Draft202012Validator, FormatChecker
        entries = []
        for entry in self.config['deliveries']:
            self._budget(started)
            spec = _read(entry['spec_path'])
            self._budget(started)
            profile = _read(entry['currentness_profile'])
            self._budget(started)
            Draft202012Validator(_profile_schema(),format_checker=FormatChecker()).validate(profile)
            target = profile['target']
            url = urlsplit(target['endpoint'])
            _need(url.scheme == 'https' and url.netloc and not url.username and not url.password
                and url.path in ('','/') and not url.query and not url.fragment)
            _need(not (target['environment_class'] == 'production' and profile['production_endpoint_denied']))
            _need(profile['credential_ref'].startswith('file:/'))
            _need(profile['required_authorities'] == ['work:read'])
            client_profile = Profile(profile['id'],target['endpoint'],profile['credential_ref'],target['environment_id'])
            stable = _stable(spec)
            identity = digest({'spec':stable,'profile':profile,'operation_sha256':entry['operation_sha256']})
            entries.append((identity,stable,client_profile,entry['operation_sha256']))
        self._budget(started)
        return entries

    def _select(self, identity, started):
        selected = [row for row in self._entries(started) if row[0] == identity]
        _need(len(selected) == 1)
        return selected[0]

    def _observe(self, selected, request, started):
        remaining = self.config['authorization_budget_seconds'] - (time.monotonic()-started)
        _need(remaining > 0,'repository_currentness_unavailable')
        future = asyncio.run_coroutine_threadsafe(self._read_owner(selected, request, remaining), self.loop)
        try:
            result = future.result(timeout=remaining)
        except Exception as exc:
            future.cancel()
            code = getattr(exc,'code',None)
            revoked = {'work-basis-stale','work-basis-unavailable','lease-basis-stale','lease-basis-unavailable','lease-expired',
                'lease-not-active','lease-ended','lease-not-found','work-state-changed',
                'claim-superseded','work-settled','work-not-active',
                'run-not-found','run-superseded','credential-invalid',
                'delegation-run-mismatch','delegation-operation-not-allowed','authority-required'}
            _refuse('repository_currentness_revoked' if code in revoked else 'repository_currentness_unavailable')
        _need(time.monotonic()-started < self.config['authorization_budget_seconds'],
            'repository_currentness_unavailable')
        return result

    async def _read_owner(self, selected, request, timeout):
        import httpx
        from vuoro_client import AsyncVuoroClient
        from sovite.repository_runtime import protected_bytes
        _, spec, profile, contract_digest = selected
        underlying = self.transport_factory() if self.transport_factory else httpx.AsyncHTTPTransport(retries=0)
        class BoundedTransport(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                response = await underlying.handle_async_request(request)
                cap = 8*1024*1024 if request.url.path == '/api/catalog/v1' else 32*1024
                data = bytearray()
                try:
                    async for chunk in response.aiter_bytes():
                        if len(data)+len(chunk) > cap:
                            _refuse('repository_currentness_unavailable')
                        data.extend(chunk)
                finally:
                    await response.aclose()
                headers = [(key,value) for key,value in response.headers.multi_items()
                    if key.lower() not in {'content-encoding','content-length'}]
                return httpx.Response(response.status_code, headers=headers, content=bytes(data),request=request)
            async def aclose(self):
                await underlying.aclose()
        def credential(reference):
            _need(reference == profile.credential_ref and reference.startswith('file:/'))
            token = protected_bytes(reference[5:],limit=4096).decode('ascii').strip()
            _need(token.startswith('vrd_') and len(token) == 56)
            return token
        async def read():
            async with AsyncVuoroClient(profile, credential, transport=BoundedTransport()) as client:
                await client.handshake()
                catalog = await client.catalog(force_refresh=True)
                operations = [row for row in catalog['operations'] if row['name'] == OPERATION]
                _need(len(operations) == 1 and digest(operations[0]) == contract_digest)
                result = await client.invoke(OPERATION,request,repo_id=spec['repo_id'])
                _need(result['repo_id'] == spec['repo_id'])
                return result['currentness']
        return await asyncio.wait_for(read(),timeout=timeout)

    def _facts(self, selected, request, started):
        facts = self._observe(selected,request,started)
        _,spec,_,_ = selected
        _need(facts['schema_version'] == 'sprintctl-work-currentness/v1'
            and facts['authorizes_effect'] is False and facts['run_id'] == request['run_id']
            and facts['lease_id'] == request['lease_id'] and facts['checkpoint'] == request['checkpoint'])
        _need(facts['requirements_sha256'] == 'sha256:'+hashlib.sha256(spec['packet']['goal'].encode('utf-8')).hexdigest())
        _need(facts['holder']['grant_id'] == spec['grant_id'])
        _need(type(facts['delegation']) is dict and facts['delegation']['run_id'] == request['run_id']
            and facts['delegation']['operations'] == [OPERATION])
        return facts

    def admit(self, *, repository_run, task, caller, recipe, parent):
        started = time.monotonic()
        _need(recipe['grant'].get('repository_currentness_required') is True)
        packet = _packet(repository_run,task)
        if parent is None:
            matching = [row for row in self._entries(started) if row[1]['packet'] == packet
                and row[1]['sovite_principal'] == caller
                and repository_run['idempotency_key'] == 'delivery-'+digest({'run':row[1]['run_id'],'packet':packet})]
            _need(len(matching) == 1)
            selected = matching[0]
            identity,spec,_,_ = selected
            request = {'run_id':spec['run_id'],'lease_id':spec['lease_id'],'checkpoint':spec['basis']}
            facts = self._facts(selected,request,started)
            return {'schema_version':SCHEMA,'spec_digest':identity,'request':request,'holder':facts['holder'],
                'requirements_sha256':facts['requirements_sha256'],'root_packet_sha256':_packet_digest(packet),
                'root_job_id':None}
        inherited = copy.deepcopy(parent.resolved['repository_run']['project_currentness']['binding'])
        selected = self._validate(inherited,started)
        _,spec,_,_ = selected
        repair = repository_run['repair']
        _need(parent.caller == caller == spec['sovite_principal'] and repair['parent_run_id'] == parent.id
            and repair['root_run_id'] == inherited['root_job_id']
            and type(repair['repair_number']) is int and 1 <= repair['repair_number'] <= spec['max_repairs'])
        maximum = spec['repair']['max_cost_usd']
        _need(packet == {**spec['packet'],'max_cost_usd':maximum})
        _need(repository_run['idempotency_key'] == _repair_key(spec,repair,caller))
        facts = self._facts(selected,inherited['request'],started)
        _need(facts['holder'] == inherited['holder'])
        return inherited

    def _validate(self, binding, started):
        _need(type(binding) is dict and set(binding) == {'schema_version','spec_digest','request','holder',
            'requirements_sha256','root_packet_sha256','root_job_id'} and binding['schema_version'] == SCHEMA)
        selected = self._select(binding['spec_digest'],started)
        _,spec,_,_ = selected
        _need(binding['request'] == {'run_id':spec['run_id'],'lease_id':spec['lease_id'],'checkpoint':spec['basis']}
            and binding['root_packet_sha256'] == _packet_digest(spec['packet'])
            and binding['requirements_sha256'] == 'sha256:'+hashlib.sha256(spec['packet']['goal'].encode('utf-8')).hexdigest())
        return selected

    def bind_job(self, *, job, admission):
        self._validate(admission,time.monotonic())
        result = copy.deepcopy(admission)
        if result['root_job_id'] is None:
            result['root_job_id'] = job.id
        _need(type(result['root_job_id']) is str and result['root_job_id'])
        return result

    def check_job(self, *, job, binding, authorization_started_at):
        selected = self._validate(binding,authorization_started_at)
        _,spec,_,_ = selected
        run = job.resolved['repository_run']
        repair = run.get('repair')
        _need(job.caller == spec['sovite_principal'])
        if repair is None:
            _need(job.id == binding['root_job_id'] and _packet(run,job.task) == spec['packet']
                and run['idempotency_key'] == 'delivery-'+digest({'run':spec['run_id'],'packet':spec['packet']}))
        else:
            _need(repair['root_run_id'] == binding['root_job_id']
                and _packet(run,job.task) == {**spec['packet'],'max_cost_usd':spec['repair']['max_cost_usd']}
                and run['idempotency_key'] == _repair_key(spec,repair,job.caller))
        facts = self._facts(selected,binding['request'],authorization_started_at)
        _need(facts['holder'] == binding['holder'])


def create_app(*, currentness_config, **kwargs):
    """Fixed composition; production installs must pin released dependencies."""
    from sovite.api import create_app as sovite_app
    from sovite.settings import Settings
    _need('repository_currentness_authorizer' not in kwargs and 'platform' not in kwargs)
    guard = FixedWorkCurrentness(currentness_config)
    try:
        settings = kwargs.get('settings') or Settings.from_env()
        _need(settings.lease_seconds >= 3*guard.config['authorization_budget_seconds'])
        kwargs['settings'] = settings
        app = sovite_app(repository_currentness_authorizer=guard,**kwargs)
        original = app.router.lifespan_context
        @asynccontextmanager
        async def lifespan(app):
            try:
                async with original(app):
                    yield
            finally:
                guard.close()
        app.router.lifespan_context = lifespan
        return app
    except BaseException:
        guard.close()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--currentness-config',required=True)
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8000)
    args = parser.parse_args()
    import uvicorn
    uvicorn.run(create_app(currentness_config=args.currentness_config),host=args.host,port=args.port)


if __name__ == '__main__':
    main()
