"""Actual historical consumer / loopback Sovite HTTP / released Workspace PG.

Native/cloud transport is the owner's explicit interruption fixture; these
histories qualify recovery protocol, not a deployed VM or provider settlement.
"""
import asyncio
from contextlib import contextmanager,closing
import copy
from importlib import resources
import json
from pathlib import Path
import shutil
import socket
import sqlite3
import threading
import time

import httpx
import pytest
import uvicorn
import yaml

from repository_delivery import HistoricalRecovery,Sovite,DeliveryError
from shared_execution.runtime import Store
from sovite.api import create_app
from sovite.db import Job,MetadataRow
from sovite.repository_candidate_export import CandidateExportOwner
from sovite.repository_candidate_retention import CandidatePublicationService,WorkspaceTarget
from sovite.repository_repair_contract import runtime as contract
from sovite.service import PlatformError
from test_repository_recovery import interrupted
from test_repository_recovery_release import (prepared as source_prepared,sqlite_prepared,candidate_additional_contracts)
from test_repository_candidate_retention import served_workspace
from test_repository_currentness import Guard
from test_repository_runs import CALLER
from vuoro_client.profile import Profile

OWNER_PIN='51d6f1d758963190cbe5dfdab59199346092886f'


@pytest.fixture
def candidate_destinations(served_workspace):return ['private-state','workspace-'+served_workspace[2]]


@pytest.fixture
def prepared(source_prepared,tmp_path):
    platform,exporter,*_=source_prepared
    guard=Guard();platform.repository_currentness_authorizer=guard
    bundle=copy.deepcopy(platform.active()[0])
    next(row for row in bundle['grants'] if row['id']==exporter.resolver.grant_id)['repository_currentness_required']=True
    path=tmp_path/'guarded-recovery.yaml';path.write_text(yaml.safe_dump(bundle))
    exporter.resolver.generation=platform.reload(str(path))
    return source_prepared


@contextmanager
def owner_http(app):
    sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128)
    server=uvicorn.Server(uvicorn.Config(app,log_level='critical',lifespan='on'))
    thread=threading.Thread(target=lambda:asyncio.run(server.serve(sockets=[sock])),daemon=True)
    thread.start();deadline=time.monotonic()+5
    try:
        while not server.started:
            assert thread.is_alive() and time.monotonic()<deadline
            time.sleep(.01)
        yield 'http://127.0.0.1:'+str(sock.getsockname()[1])
    finally:
        server.should_exit=True;thread.join(5);sock.close();assert not thread.is_alive()


class IntentTransport(httpx.BaseTransport):
    """Read the actual committed controller journal before real HTTP writes."""
    def __init__(self,root,*,lost=None):
        self.root,self.lost,self.did_lose=root,lost,False
        self.inner=httpx.HTTPTransport();self.calls=[];self.bodies=[]
    def handle_request(self,request):
        self.calls.append((request.method,request.url.path))
        if request.method=='POST':
            body=json.loads(request.content);self.bodies.append((request.url.path,body))
            with closing(sqlite3.connect(self.root/'scheduler/state.sqlite3')) as connection:
                records=[json.loads(row[0]) for row in connection.execute("SELECT body FROM meta WHERE key LIKE 'recovery:%'")]
            assert len(records)==1;stored=records[0]
            field=next((field for suffix,field in [('/recovery','capture_intent'),('/recovery-context','context_intent'),
                ('/recovery-release','release_intent'),('/candidate-retention','retention_intent')] if request.url.path.endswith(suffix)),None)
            assert field is not None and stored[field]==body,'HTTP intent was not committed before sending'
        response=self.inner.handle_request(request);response.read()
        if self.lost and not self.did_lose and request.url.path.endswith(self.lost) and response.status_code<300:
            self.did_lose=True;raise httpx.ReadError('fixture committed HTTP response lost',request=request)
        return response
    def close(self):self.inner.close()


@pytest.mark.parametrize('interrupted',[100000],indirect=True)
@pytest.mark.parametrize('lost',[None,'/recovery','/recovery-release','/candidate-retention',
    'knowledge.artifact.begin-v1','knowledge.artifact.upload-v1','knowledge.artifact.finalize-v1','existing-owner-release'])
def test_historical_consumer_exact_copy_lost_ack_and_fresh_reader(interrupted,served_workspace,tmp_path,lost):
    platform,owner,before,attempt,effects,exports,_=interrupted
    guard=platform.repository_currentness_authorizer
    assert before.id in guard.bound
    guard.current=False
    with platform.db.sessions() as session:
        with pytest.raises(PlatformError):platform.authorize_existing_job(session,session.get(Job,before.id))
    exporter=CandidateExportOwner(platform,owner.resolver,owner.executor)
    factory,loss,ws,conn,schema=served_workspace
    target=WorkspaceTarget('https://workspace.invalid',ws,'workspace-'+ws,frozenset({'C3'}))
    service=CandidatePublicationService(exporter,tmp_path/'publisher',target,
        Profile('fixture','https://workspace.invalid','producer'),lambda ref:ref,transport=loss)
    app=create_app(platform.settings,platform,repository_run_owner=owner,candidate_publication_service=service)
    root=tmp_path/'controller';root.mkdir(mode=0o700)
    data=tmp_path/'owner-contract';shutil.copytree(Path(resources.files(contract.PACKAGE).joinpath('data')),data);data.chmod(0o700)
    assert contract.INTEGRITY=='4cae80913a14417b45856b7aa4513c80b049a01aad2f59e757a495ca4f5a5b82'
    internal=before.resolved['repository_run']
    packet={'schema_version':'portable-work/v1','goal':before.task,
            **{key:internal[key] for key in ('workspace_id','repository_id','executor_id','base_sha','max_cost_usd','deadline','concurrency')}}
    spec={'schema_version':'agentops-repository-delivery/v1','repository_id':'repo-1','packet':packet,
        'workspace_endpoint':target.endpoint,'workspace_id':ws,'workspace_destination':target.destination,'allowed_classes':['C3'],
        'work_profile':'deliberately-nonexistent-and-stale','basis':{'deliberately':'stale'}}
    policy={'schema_version':'agentops-repository-recovery/v1','contract_id':'recovery-copy','destination_id':target.destination,
        'owner_contract':{'root':str(data),'integrity_sha256':contract.INTEGRITY,
            'source_ref':f'https://github.com/bayleafwalker/sovite/blob/{OWNER_PIN}/docs/contracts/repository-repair-v1.provenance.json'}}
    if lost=='existing-owner-release':policy['contract_id']='candidate-export'
    store=Store(root/'scheduler');store.setmeta('spec',spec)
    store.save({'id':'delivery','state':'BLOCKED','execution_id':before.id,'submission_key':before.resolved['repository_run']['idempotency_key'],
        'cause':'work-basis-changed','attempt':'sovite:'+internal['idempotency_key'],'billing':'unknown',
        'submission':{'schema_version':'sovite-repository-run/v1','packet':packet,'preview_id':internal['preview_id']}})
    original=store.tasks()[0];store.close()
    if lost and lost.startswith('knowledge.'):loss.operation=lost
    async def scenario(origin):
        loop=asyncio.get_running_loop()
        async with factory('successor') as reader:
            class Workspace:
                def invoke(self,operation,body):
                    try:return asyncio.run_coroutine_threadsafe(reader.invoke(operation,body),loop).result(timeout=30)
                    except Exception as error:raise DeliveryError('owner-refused:'+getattr(error,'code','unknown-outcome')) from None
            def controller():
                transport=IntentTransport(root,lost=lost if lost and lost.startswith('/') else None)
                execution=Sovite.__new__(Sovite)
                execution.client=httpx.Client(base_url=origin,transport=transport,headers={'Authorization':'Bearer '+CALLER},timeout=30)
                selected_release=None
                def step():
                    consumer=HistoricalRecovery(root,spec,Workspace(),execution,policy,attempt_id=attempt,release_id=selected_release)
                    try:
                        answer=consumer.step();assert consumer.store.tasks()[0]==original;return answer
                    finally:consumer.close()
                try:
                    if lost:
                        with pytest.raises(DeliveryError):step()
                    if lost=='existing-owner-release':
                        # An independent already-authorized owner procedure
                        # supplies a real release selector. No human review or
                        # operator identity is asserted by this consumer.
                        with closing(sqlite3.connect(root/'scheduler/state.sqlite3')) as journal:
                            saved=json.loads(journal.execute("SELECT body FROM meta WHERE key LIKE 'recovery:%'").fetchone()[0])
                        selector={'workspace_id':'workspace-1','attempt_id':attempt,
                            'source_digest':saved['capture']['source_digest'],'contract_id':'recovery-copy',
                            'destination_id':target.destination}
                        with httpx.Client(base_url=origin,headers={'Authorization':'Bearer '+CALLER},timeout=30) as prior:
                            context=prior.post('/api/repository-runs/v1/runs/'+before.id+'/recovery-context',json=selector)
                            assert context.status_code==200,context.text
                            value=context.json()
                            released=prior.post('/api/repository-runs/v1/runs/'+before.id+'/recovery-release',json={**selector,
                                'expected_generation':value['expected_generation'],'expected_contract_revision':value['contract_revision']})
                            assert released.status_code==200,released.text
                            selected_release=released.json()['release_id']
                        assert 'release_intent' not in saved
                    answer=step();assert answer['state']=='recovery-retained'
                    raw=Path(answer['artifact_path']).read_bytes();assert len(raw)>65536
                    value=json.loads(raw);assert value['kind']=='repository-recovery-artifact'
                    assert value['outcome']=='uncertain' and value['publication_eligible'] is False and value['repair_eligible'] is False
                    assert not (root/'candidate').exists()
                    # Once ready, historical owner locator + current Workspace
                    # reader suffice after the producer binding/runtime is gone.
                    calls=len(transport.calls)
                    owner.resolver.grant_id='retired-producer'
                    platform.repository_currentness_authorizer=None
                    shutil.rmtree(owner.executor.state_root)
                    recovered=step();assert recovered['receipt']==answer['receipt']
                    assert all(method=='GET' for method,_ in transport.calls[calls:])
                    if lost and lost.startswith('/'):assert transport.did_lose
                    for suffix in ('/recovery','/recovery-release','/candidate-retention'):
                        bodies=[body for path,body in transport.bodies if path.endswith(suffix)]
                        assert not bodies or all(body==bodies[0] for body in bodies)
                    assert not any(path.endswith(('/repairs','/cancel')) or method=='POST' and path.endswith('/runs')
                        for method,path in transport.calls)
                    return answer
                finally:execution.close()
            answer=await asyncio.to_thread(controller)
            async with factory('admin') as admin:
                await admin.invoke('knowledge.member.set-v1',{'workspace_id':ws,'principal_id':'test:successor:0','role':None},
                                   idempotency_key='member-revoke-001')
            def revoked_reader():
                execution=Sovite.__new__(Sovite)
                execution.client=httpx.Client(base_url=origin,headers={'Authorization':'Bearer '+CALLER},timeout=30)
                consumer=HistoricalRecovery(root,spec,Workspace(),execution,policy,attempt_id=attempt)
                try:
                    with pytest.raises(DeliveryError,match='owner-refused'):consumer.step()
                    assert consumer.store.tasks()[0]==original
                    assert Path(answer['artifact_path']).exists(), 'Retained local copy is not new read authority'
                finally:consumer.close();execution.close()
            await asyncio.to_thread(revoked_reader)
            return answer
    with owner_http(app) as origin:answer=asyncio.run(scenario(origin))
    current=platform.get_job(before.id)
    assert current.status==before.status=='blocked' and current.error_code==before.error_code=='execution_uncertain'
    for field in ('budget_reservations','active_slots','usage_usd','attempts'):
        assert current.resolved['repository_run'][field]==before.resolved['repository_run'][field]
    assert current.resolved['repository_run']['budget_reservations'][0]['state']=='reserved'
    assert effects==['edit-and-ambiguous-provider-call'] and exports==['export-v1']
    assert conn.execute(f'SELECT count(*) FROM "{schema}".artifact_version').fetchone()[0]==1
    with platform.db.sessions() as session:
        assert len([row for row in session.query(MetadataRow).all() if row.key.startswith('release_')])==1
