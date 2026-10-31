"""Explicit actual Work PG/service/installed guard/Sovite owner qualification."""
import copy
import hashlib
import json
import time
import uuid

import httpx
import pytest
import yaml

from repository_delivery import digest
from repository_currentness import FixedWorkCurrentness, OPERATION
from repository_delivery_owners import WorkOwner
from sovite.db import Job
from sovite.repository_currentness import CurrentnessError
from sovite.service import PlatformError
from sovite.worker import Worker
from test_repository_runs import setup, make_repo, BindingResolver, make_owner, packet, submit
from sprintctl import pg, pg_migrations
from sprintctl.vuoro_adapter import register_work_catalog
from tests.pg.test_run_delegation import _instance, _declaration
from vuoro_service.app import ServiceSettings, create_app
from vuoro_service.catalog import CatalogRegistry
from vuoro_service.identity import StaticBearerIdentityResolver
from vuoro_service.run_delegation import DelegatedBearerIdentityResolver


def private_json(path, value):
    path.write_text(json.dumps(value))
    path.chmod(0o600)


@pytest.fixture
def actual_guard(setup,tmp_path):
    settings,platform = setup
    bundle,_ = platform.active()
    bundle = copy.deepcopy(bundle)
    next(row for row in bundle['grants'] if row['id']=='incident-forensics')['repository_currentness_required'] = True
    policy = tmp_path/'guarded.yaml'; policy.write_text(yaml.safe_dump(bundle)); platform.reload(str(policy))
    mirror,base = make_repo(tmp_path)
    resolver = BindingResolver(mirror,base,platform.active()[1])
    owner = make_owner(platform,resolver,executor=lambda *_:None)
    value = packet(base)
    value['goal'] += ' Unicode exact requirement: ä.'
    work = WorkOwner(value['goal'])
    work.store.remote_schema_version = pg_migrations.CURRENT_SCHEMA_VERSION
    instance = _instance()
    work.invoke('work.agent.register-v1',{'instance_id':instance,'declaration':_declaration(),
        'idempotency_key':uuid.uuid4().hex})
    issued = work.invoke('work.run.delegate-v1',{'run_id':work.run,'creator_instance_id':instance,
        'operations':[OPERATION],'ttl_seconds':300,'idempotency_key':uuid.uuid4().hex})
    registry = CatalogRegistry(); register_work_catalog(registry,work.app)
    identity = DelegatedBearerIdentityResolver(StaticBearerIdentityResolver({}),environment='vuoro-dev',
        lookup=work.app.resolve_run_delegation_digest,allowed_repo_ids=frozenset({work.repo}))
    service = create_app(settings=ServiceSettings(environment_name='vuoro-dev',environment_class='development'),
        registry=registry,identity_resolver=identity)
    token = tmp_path/'read-token'; token.write_text(issued['token']); token.chmod(0o600)
    profile = tmp_path/'read-profile.json'
    private_json(profile,{'schema_version':'vuoro-client-profile/v1','id':'guard-fixture','revision':1,
        'source_environment_id':'qualification','target':{'environment_id':'vuoro-dev',
        'environment_class':'development','endpoint':'https://fixture'},'credential_ref':'file:'+str(token),
        'required_authorities':['work:read'],'production_endpoint_denied':True})
    spec = {'schema_version':'agentops-repository-delivery/v1','packet':value,'sovite_principal':'cloud-codex',
        'repo_id':work.repo,'run_id':work.run,'lease_id':work.lease['lease_id'],'grant_id':None,
        'basis':work.basis,'max_repairs':2,'repair':{'max_cost_usd':1}}
    path = tmp_path/'spec.json'; private_json(path,spec)
    operation = next(row for row in work.catalog()['operations'] if row['name']==OPERATION)
    config = {'schema_version':'agentops-work-currentness-config/v1','authorization_budget_seconds':5,
        'watchdog_poll_seconds':0.25,'deliveries':[{'spec_path':str(path),
        'currentness_profile':str(profile),'operation_sha256':digest(operation)}]}
    config_path = tmp_path/'guard.json'; private_json(config_path,config)
    class Boundary(httpx.AsyncBaseTransport):
        lose = False
        delay = 0
        calls = 0
        async def handle_async_request(self,request):
            import asyncio
            if self.delay: await asyncio.sleep(self.delay)
            response = await httpx.ASGITransport(app=service).handle_async_request(request)
            if response.status_code >= 400:
                await response.aread()
                print('actual-owner refusal',response.status_code,response.json().get('error',{}).get('code'))
            if request.url.path == '/api/invoke/v1':
                self.calls += 1
                if self.lose:
                    self.lose = False
                    await response.aclose()
                    raise httpx.ReadError('fixture discarded actual read reply')
            return response
    boundary = Boundary()
    guard = FixedWorkCurrentness(config_path,transport_factory=lambda:boundary)
    platform.repository_currentness_authorizer = guard
    key = 'delivery-'+digest({'run':work.run,'packet':value})
    try:
        yield locals()
    finally:
        guard.close(); work.close()


def admitted(fixture):
    return submit(fixture['owner'],fixture['value'],idempotency_key=fixture['key'])


def test_actual_owner_guard_binds_uuid_complete_basis_unicode_goal_and_read_only_scope(actual_guard):
    f=actual_guard
    result=admitted(f)
    job=f['platform'].get_job(result['id'])
    record=job.resolved['repository_run']['project_currentness']
    inner=record['binding']
    assert record['job_id']==job.id==inner['root_job_id']
    assert inner['request']=={'run_id':f['work'].run,'lease_id':f['work'].lease['lease_id'],'checkpoint':f['work'].basis}
    assert inner['requirements_sha256']=='sha256:'+hashlib.sha256(job.task.encode()).hexdigest()
    with f['platform'].db.sessions() as session:
        f['platform'].authorize_existing_job(session,session.get(Job,job.id))
    assert f['boundary'].calls==2
    assert 'vrd_' not in json.dumps(record) and 'observed_at' not in json.dumps(record)


@pytest.mark.parametrize('fault',['key','goal','base','cost','ambiguous'])
def test_protected_actual_intent_must_match_uniquely_before_owner_admission(actual_guard,fault):
    f=actual_guard; value=copy.deepcopy(f['value']); key=f['key']
    if fault=='key': key='unauthorized-sibling-intent'
    elif fault=='ambiguous':
        f['config']['deliveries']*=2; private_json(f['config_path'],f['config'])
        f['guard'].config=copy.deepcopy(f['config'])
    elif fault=='goal': value['goal']+=' changed'
    elif fault=='base': value['base_sha']='f'*40
    else: value['max_cost_usd']=0.5
    with pytest.raises(Exception): submit(f['owner'],value,idempotency_key=key)
    assert f['boundary'].calls==0
    assert f['owner'].list(principal_id='cloud-codex',workspace_id='workspace-1')==[]


@pytest.mark.parametrize('change',['reference','description','cancel-lease','revoke'])
def test_fresh_owner_veto_keeps_history_reconcile_cancel_available(actual_guard,change):
    f=actual_guard; result=admitted(f); work=f['work']; platform=f['platform']
    if change=='reference': pg.add_ref(work.store,work.item,'doc','https://example.invalid/new')
    elif change=='description': pg.update_work_item_description(work.store,work.item,'changed exact goal',actor='fixture')
    elif change=='revoke': work.invoke('work.run.delegation-revoke-v1',{'delegation_id':f['issued']['delegation_id'],
        'reason':'fixture','idempotency_key':uuid.uuid4().hex})
    else:
        work.invoke('work.lease.report-outcome-v1',{'run_id':work.run,'lease_id':work.lease['lease_id'],
            'outcome':'failed','summary':'fixture holder stopped','idempotency_key':uuid.uuid4().hex})
    with platform.db.sessions() as session:
        with pytest.raises(PlatformError) as denied:
            platform.authorize_existing_job(session,session.get(Job,result['id']))
        assert denied.value.code=='repository_currentness_revoked'
        platform.authorize_existing_job(session,session.get(Job,result['id']),purpose='observe')
    assert admitted(f)['id']==result['id']
    assert f['owner'].get(result['id'],principal_id='cloud-codex')['id']==result['id']
    assert Worker(platform,repository_run_executor=object()).claim() is None
    assert f['owner'].cancel(result['id'],principal_id='cloud-codex',workspace_id='workspace-1')['id']==result['id']


def test_lost_read_reply_does_not_mint_job_or_cache_permission(actual_guard):
    f=actual_guard; f['boundary'].lose=True
    with pytest.raises(PlatformError) as denied: admitted(f)
    assert denied.value.code=='repository_currentness_unavailable'
    assert f['owner'].list(principal_id='cloud-codex',workspace_id='workspace-1')==[]
    assert admitted(f)['id']
    assert f['boundary'].calls==2


def test_total_authorization_deadline_includes_prior_recursive_work_and_response_duration(actual_guard):
    f=actual_guard; result=admitted(f); job=f['platform'].get_job(result['id'])
    binding=job.resolved['repository_run']['project_currentness']['binding']
    before=f['boundary'].calls
    with pytest.raises(CurrentnessError) as refused:
        f['guard'].check_job(job=job,binding=binding,authorization_started_at=time.monotonic()-6)
    assert refused.value.code=='repository_currentness_unavailable' and f['boundary'].calls==before
    f['boundary'].delay=1
    started=time.monotonic()
    with pytest.raises(CurrentnessError):
        f['guard'].check_job(job=job,binding=binding,authorization_started_at=started-4.9)
    assert time.monotonic()-started<1


def test_plain_job_and_absent_guard_cannot_bypass_requirement(actual_guard):
    f=actual_guard; platform=f['platform']
    with pytest.raises(PlatformError) as denied:
        platform.submit('incident-forensics','plain bypass','cloud-codex','plain-attempt')
    assert denied.value.code=='repository_currentness_required'
    result=admitted(f); platform.repository_currentness_authorizer=None
    with platform.db.sessions() as session:
        with pytest.raises(PlatformError) as denied:
            platform.authorize_existing_job(session,session.get(Job,result['id']))
        assert denied.value.code=='repository_currentness_unavailable'
        platform.authorize_existing_job(session,session.get(Job,result['id']),purpose='observe')
    assert admitted(f)['id']==result['id']


def test_actual_broader_credential_cannot_replace_read_only_guard_delegation(actual_guard):
    f=actual_guard; work=f['work']
    work.invoke('work.run.delegation-revoke-v1',{'delegation_id':f['issued']['delegation_id'],
        'reason':'fixture-replace','idempotency_key':uuid.uuid4().hex})
    broad=work.invoke('work.run.delegate-v1',{'run_id':work.run,'creator_instance_id':f['instance'],
        'operations':[OPERATION,'work.session-note.write-v1'],'ttl_seconds':300,'idempotency_key':uuid.uuid4().hex})
    f['token'].write_text(broad['token'])
    with pytest.raises(PlatformError) as denied: admitted(f)
    assert denied.value.code=='repository_currentness_binding_invalid'
    assert f['owner'].list(principal_id='cloud-codex',workspace_id='workspace-1')==[]


def test_changed_protected_configuration_and_wrong_published_operation_pin_refuse(actual_guard):
    f=actual_guard
    changed=copy.deepcopy(f['config']); changed['deliveries'][0]['operation_sha256']='0'*64
    private_json(f['config_path'],changed)
    with pytest.raises(PlatformError): admitted(f)
    assert f['boundary'].calls==0
    # A newly installed configuration may deliberately pin another contract;
    # actual catalog discovery must still refuse its mismatched descriptor.
    f['guard'].config=changed
    with pytest.raises(PlatformError) as denied: admitted(f)
    assert denied.value.code=='repository_currentness_unavailable'
    assert f['boundary'].calls==0


def test_repair_uses_actual_parent_work_tuple_and_exact_existing_consumer_intent(actual_guard):
    from repository_currentness import _repair_key
    f=actual_guard; result=admitted(f)
    parent=f['platform'].get_job(result['id'])
    inherited=parent.resolved['repository_run']['project_currentness']['binding']
    repair={'parent_run_id':parent.id,'root_run_id':parent.id,'repair_number':1,
        'candidate_sha256':'a'*64,'feedback_release_id':'release_'+'b'*64}
    child={**parent.resolved['repository_run'],'max_cost_usd':1,'repair':repair}
    child['idempotency_key']=_repair_key(f['spec'],repair,parent.caller)
    recipe=copy.deepcopy(parent.resolved)
    admission=f['guard'].admit(repository_run=child,task=parent.task,caller=parent.caller,recipe=recipe,parent=parent)
    assert admission==inherited
    from types import SimpleNamespace
    child_job=SimpleNamespace(id=uuid.uuid4().hex)
    assert f['guard'].bind_job(job=child_job,admission=admission)==inherited
    child['idempotency_key']='unauthorized-repair-sibling'
    with pytest.raises(CurrentnessError):
        f['guard'].admit(repository_run=child,task=parent.task,caller=parent.caller,recipe=recipe,parent=parent)
    child['idempotency_key']=_repair_key(f['spec'],repair,parent.caller)
    pg.add_ref(f['work'].store,f['work'].item,'doc','https://example.invalid/stale-before-repair')
    with pytest.raises(CurrentnessError) as stale:
        f['guard'].admit(repository_run=child,task=parent.task,caller=parent.caller,recipe=recipe,parent=parent)
    assert stale.value.code=='repository_currentness_revoked'


def test_local_protected_selection_consumes_same_admission_deadline(actual_guard,monkeypatch):
    import repository_currentness
    f=actual_guard
    changed=copy.deepcopy(f['config']); changed['authorization_budget_seconds']=0.1
    private_json(f['config_path'],changed); f['guard'].config=changed
    original=repository_currentness._read
    def slow(path):
        if path==str(f['path']): time.sleep(0.15)
        return original(path)
    monkeypatch.setattr(repository_currentness,'_read',slow)
    with pytest.raises(PlatformError) as refused: admitted(f)
    assert refused.value.code=='repository_currentness_unavailable'
    assert f['boundary'].calls==0


def test_fixed_factory_composes_same_guard_and_closes_lifecycle(actual_guard):
    from fastapi.testclient import TestClient
    from repository_currentness import create_app as fixed_app
    f=actual_guard; f['platform'].repository_currentness_authorizer=None
    app=fixed_app(currentness_config=f['config_path'],settings=f['settings'])
    installed=app.state.platform.repository_currentness_authorizer
    assert installed is app.state.platform.repository_currentness_authorizer
    assert installed is not f['guard'] and installed.thread.is_alive()
    with TestClient(app): pass
    assert not installed.thread.is_alive()
