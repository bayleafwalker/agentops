"""Actual source consumer / Sovite HTTP / released Workspace HTTP / Work PG.

Explicit qualification target: not collected by the ordinary stdlib test job.
Sovite source fixtures are imported at the CI-pinned owner commit. Mutable
execution is deterministic and does not qualify a native driver or deployment.
"""
import asyncio
import base64
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from importlib import resources
import hashlib
import json
import os
from pathlib import Path
import sys
import sqlite3
from types import SimpleNamespace
import uuid

import httpx
import jsonschema
import pytest
from sqlalchemy import create_engine

from repository_delivery import RepositoryDelivery, OwnerRepairContract, Sovite, DeliveryError, digest
from shared_execution.runtime import Store
from sovite.api import create_app
from sovite.db import Base
from sovite.repository_repair_contract import runtime as contract
from sovite.repository_candidate_retention import CandidateRetention
from sovite.service import Platform
from sovite.worker import Worker
from test_repository_repairs import (prepared, served_workspace, configured, candidate_destinations,
                                     candidate_model_destination)
from test_repository_candidate_export import release
from test_repository_runs import CALLER, git as owner_git
from test_workflows import revision_ref
from sprintctl import pg
from sprintctl.application import WorkApplication
from sprintctl.pg_testing import assert_disposable_connection
from sprintctl.vuoro_adapter import WORK_OPERATION_CONTRACTS, catalog_operation_specs
import psycopg
from psycopg.rows import dict_row


@pytest.fixture
def feedback_machine_eligible(): return True


@pytest.fixture
def candidate_additional_contracts(feedback_machine_eligible):
    return [{'id':'repair-feedback', 'source_class':'C3', 'output_class':'C3',
             'destinations':['private-runtime'], 'approvers':['operator','cloud-codex'] if feedback_machine_eligible else ['operator'],
             'procedure_ref':revision_ref('trusted-repair-feedback')}]


@pytest.fixture
def postgres_prepared(prepared):
    url = os.environ['SOVITE_TEST_POSTGRES_URL']
    if url.startswith(('postgresql://','postgres://')):
        url = 'postgresql+psycopg://' + url.split('://',1)[1]
    platform, exporter, job, attempt, mirror, base = prepared
    admin = create_engine(url)
    schema = 'consumer_' + uuid.uuid4().hex
    with admin.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    target = Platform(replace(platform.settings, database_url=url, database_schema=schema))
    target.db.migrate()
    with platform.db.engine.connect() as source, target.db.engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables): connection.execute(table.delete())
        for table in Base.metadata.sorted_tables:
            rows = [dict(row) for row in source.execute(table.select()).mappings()]
            if rows: connection.execute(table.insert(), rows)
    exporter.platform = exporter.execution.platform = target
    try:
        yield target, exporter, target.get_job(job.id), attempt, mirror, base
    finally:
        target.db.engine.dispose()
        with admin.begin() as connection: connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        admin.dispose()


class WorkOwner:
    """Actual WorkApplication/PG with published request/result validation."""
    def __init__(self, goal):
        self.conn = psycopg.connect(os.environ['SPRINTCTL_TEST_PG_URL'], row_factory=dict_row)
        assert_disposable_connection(self.conn)
        self.repo = 'itest-consumer-' + uuid.uuid4().hex[:12]
        self.store = pg.PgStore(conn=self.conn, repo_id=self.repo, authority_repo_uuid=str(uuid.uuid4()),
            connection_factory=lambda: psycopg.connect(os.environ['SPRINTCTL_TEST_PG_URL'], row_factory=dict_row))
        pg.init_db(self.store)
        self.app = WorkApplication.postgres(self.store)
        identity = SimpleNamespace(actor='qualified-fixture-controller', environment='disposable-fixture',
            authorities=frozenset({'work:evidence','work:claim','work:read'}), principal_id='fixture:controller',
            workspace_id='fixture-workspace', client_id=None, grant_id=None)
        self.context = SimpleNamespace(identity=identity, request_id='fixture-request', basis_revision=None,
            catalog_revision='actual-source-contract', idempotency_requirement='not-allowed', idempotency_key=None)
        self.contracts = {c.name:c for c in WORK_OPERATION_CONTRACTS}
        sprint = pg.create_sprint(self.store,'Consumer fixture','exact basis','2026-01-01','2026-12-31','active')
        track = pg.get_or_create_track(self.store,sprint,'consumer')
        self.item = pg.create_work_item(self.store,sprint,track,'Consumer delivery',description=goal)
        reservation = pg.reserve(self.store,self.item,actor='fixture',session_id=uuid.uuid4().hex,
            role='execution',acceptance_contract={'evidence_obligations':['tests','review']})
        pg.release_reservation(self.store,reservation['id'])
        self.run = self.invoke('work.run.register-v1',{'harness_id':'codex','harness_build':'fixture','model_id':'fixture',
            'recipe_id':'fixture','observed_profile':{'instruction_digest':'sha256:'+'a'*64,'skill_digests':[]},
            'idempotency_key':uuid.uuid4().hex})['run']['run_id']
        self.lease = self.invoke('work.lease.acquire-v1',{'item_id':self.item,'run_id':self.run,'idempotency_key':uuid.uuid4().hex})['lease']
        self.basis = self.invoke('work.run.continuation-delta-v1',{'run_id':self.run,'item_id':self.item})['delta']['current']
        self.lose_outcome = False
        self.calls = []

    def invoke(self, operation, arguments, repo=None):
        if getattr(self,'before_invoke',None): self.before_invoke(operation,arguments)
        if hasattr(self,'calls'): self.calls.append(operation)
        schema = self.contracts[operation]
        jsonschema.validate(arguments,schema.input_schema)
        result = self.app.invoke(operation,arguments,self.context)
        jsonschema.validate(result,schema.result_schema)
        if operation == 'work.lease.report-outcome-v2' and self.lose_outcome:
            self.lose_outcome = False
            raise DeliveryError('owner-refused:unknown-outcome')  # actual committed effect, lost reply
        return result

    def catalog(self): return {'operations':catalog_operation_specs(resource_schema_available=True)}
    def close(self): self.conn.close()


class HttpBridge(httpx.BaseTransport):
    def __init__(self, loop, client): self.loop,self.client=loop,client
    def handle_request(self, request):
        async def invoke():
            response = await self.client.request(request.method,str(request.url),headers=request.headers,content=request.content)
            await response.aread()
            return httpx.Response(response.status_code,headers=response.headers,content=response.content,request=request)
        return asyncio.run_coroutine_threadsafe(invoke(),self.loop).result(timeout=30)


@pytest.mark.parametrize(('lost_path','stale','feedback_machine_eligible','exhausted'), [('/api/output-releases',False,True,False),('/api/repository-runs/v1/repairs',False,True,False),(None,False,True,False),('/api/repository-runs/v1/repairs',True,True,False),(None,False,False,False),(None,False,True,True),(None,'before-post',True,False),(None,'after-ack',True,False)], indirect=['feedback_machine_eligible'])
def test_actual_consumer_repair_preserves_failed_candidate_and_recovers_exact_lost_reply(postgres_prepared, served_workspace, tmp_path, lost_path, stale, feedback_machine_eligible, exhausted):
    async def scenario():
        service, original, reader = await configured(postgres_prepared,served_workspace,tmp_path)
        platform, exporter, parent, attempt, mirror, base = postgres_prepared
        app = create_app(platform.settings,platform,repository_run_owner=service.owner)
        app.state.repository_repair_service = service
        class Loss(httpx.AsyncBaseTransport):
            def __init__(self): self.inner=httpx.ASGITransport(app=app); self.lost=False; self.paths=[]
            async def handle_async_request(self, request):
                self.paths.append((request.method,request.url.path))
                if request.url.path in ('/api/output-releases','/api/repository-runs/v1/repairs'):
                    # Independent SQLite reader at the actual HTTP boundary:
                    # transport intent must be committed before any owner write.
                    with sqlite3.connect(tmp_path/'controller/scheduler/state.sqlite3') as journal:
                        stored=json.loads(journal.execute("SELECT body FROM tasks WHERE id='delivery'").fetchone()[0])
                    pending=stored['repair_pending']
                    body=json.loads(request.content)
                    if request.url.path=='/api/output-releases':
                        assert pending['approval']==body
                    else:
                        assert pending['submission']==body
                        assert pending['submission_key']==request.headers['Idempotency-Key']
                response = await self.inner.handle_async_request(request)
                if lost_path and request.url.path == lost_path and response.status_code < 300 and not self.lost:
                    self.lost=True
                    raise httpx.ReadError('fixture loss after real owner commit')
                return response
        loss = Loss()
        loop = asyncio.get_running_loop()
        controller_thread = ThreadPoolExecutor(max_workers=1)
        async with httpx.AsyncClient(transport=loss,base_url='http://testserver',headers={'Authorization':'Bearer '+CALLER}) as actual_http:
            execution = Sovite.__new__(Sovite)
            execution.client = httpx.Client(transport=HttpBridge(loop,actual_http),base_url='http://testserver',headers={'Authorization':'Bearer '+CALLER})
            class Workspace:
                def invoke(self, operation, arguments):
                    return asyncio.run_coroutine_threadsafe(reader.invoke(operation,arguments),loop).result(timeout=30)
            def controller():
                work = WorkOwner(parent.task)
                root = tmp_path/'controller'; root.mkdir(mode=0o700)
                check = tmp_path/'trusted-check'
                check.write_text('#!'+sys.executable+'\nimport sys\nfrom pathlib import Path\n'
                    'print("qualified fixture check: repair src/main.txt")\n'
                    'sys.exit(1 if (Path(sys.argv[1])/"src/main.txt").read_text()=="candidate\\n" else 0)\n')
                if exhausted: check.write_text(check.read_text().replace('sys.exit(1 if', 'sys.exit(1 if True or'))
                check.chmod(0o700)
                review = tmp_path/'trusted-review'
                review.write_text('#!'+sys.executable+'\nprint("independent fixture review")\n'); review.chmod(0o700)
                data = Path(resources.files(contract.PACKAGE).joinpath('data'))
                adapter = RepositoryDelivery.__new__(RepositoryDelivery)
                adapter.root=root; adapter.work=work; adapter.workspace=Workspace(); adapter.execution=execution
                adapter.store=Store(root/'scheduler'); adapter.config={'max_workers':1,'launch_spacing':0}
                adapter.quota=SimpleNamespace(blocked=lambda provider:False)
                adapter.spec={'max_repairs':1 if exhausted else 2,'repo_id':work.repo,'run_id':work.run,'grant_id':None,'lease_id':work.lease['lease_id'],
                    'basis':work.basis,'item_id':work.item,'repository_id':'repo-1','canonical_url':mirror.as_uri(),'allowed_areas':['src'],
                    'sovite_principal':parent.caller,'packet':{'workspace_id':'workspace-1','base_sha':base,'goal':parent.task},
                    'workspace_endpoint':'https://workspace.invalid','workspace_id':served_workspace[2],
                    'workspace_destination':'workspace-'+served_workspace[2],'allowed_classes':['C3'],
                    'repair':{'feedback_contract_id':'repair-feedback','max_cost_usd':1},
                    'acceptance':{'expires_at':'2099-01-01T00:00:00Z','qualification_ref':'fixture-only-not-installed',
                        'allowed_classes':['C3'],
                        'check':{'path':str(check),'sha256':hashlib.sha256(check.read_bytes()).hexdigest(),'timeout_seconds':5},
                        'review':{'path':str(review),'sha256':hashlib.sha256(review.read_bytes()).hexdigest(),'timeout_seconds':5}}}
                adapter.repair_contract=OwnerRepairContract({'root':str(data),'integrity_sha256':contract.INTEGRITY,
                    'source_ref':'https://github.com/bayleafwalker/sovite/blob/ca09603fc1cf7c1cd04fefe18ca282d019f99140/docs/contracts/repository-repair-v1.provenance.json'},root)
                adapter.store.save({'id':'delivery','state':'RUNNING','attempt':'sovite:original',
                    'execution_id':parent.id,'submission_key':parent.resolved['repository_run']['idempotency_key'],
                    'areas':['src'],'provider':'sovite','model':'fixture','dependencies':[],'worktree':str(root/'candidate')})
                if stale in ('before-post','after-ack'):
                    def change_work_at_boundary(operation,arguments):
                        if operation!='work.run.resolve-v2': return
                        durable=adapter.store.tasks()[0]
                        pending=durable.get('repair_pending') or {}
                        reached=(bool(pending.get('submission')) if stale=='before-post'
                                 else durable['state']=='PLANNED' and bool(durable.get('repair_ack')))
                        if reached:
                            work.before_invoke=None
                            pg.add_ref(work.store,work.item,'doc','https://example.invalid/mid-tick','changed at durable boundary')
                    work.before_invoke=change_work_at_boundary
                try:
                    for _ in range(12):
                        try: task=adapter.step()
                        except DeliveryError as exc:
                            assert str(exc)=='execution-owner-unknown-outcome'
                            # Actual durable scheduler is reopened after the lost reply.
                            adapter.close(); adapter.store=Store(root/'scheduler')
                            if stale is True:
                                pg.add_ref(work.store,work.item,'doc','https://example.invalid/new-requirements','changed after lost repair ack')
                                return adapter,work,adapter.step()
                            continue
                        if task.get('cause')=='repair-feedback-release-required':
                            assert not feedback_machine_eligible
                            assert len(service.owner.list(principal_id=parent.caller,workspace_id='workspace-1'))==1
                            assert 'approval' not in task['repair_pending']
                            adapter.spec['repair_feedback']={'parent_run_id':parent.id,'release_id':original['feedback_release_id']}
                            continue
                        if task.get('work_stop'): return adapter,work,task
                        if task.get('repair_ack'):
                            return adapter, work, task
                    raise AssertionError('repair did not progress')
                except BaseException:
                    adapter.close(); work.close(); raise
            adapter, work, task = await loop.run_in_executor(controller_thread,controller)
            try:
                if stale:
                    assert task['work_stop']=='work-basis-changed'
                    if stale=='before-post':
                        assert task['repair_pending']['submission']
                        assert task['cancellation_state']=='submission-outcome-unknown'
                        assert task['cancellation_intent']['submission_key']==task['repair_pending']['submission_key']
                        assert ('POST','/api/repository-runs/v1/repairs') not in loss.paths
                        assert ('POST','/api/repository-runs/v1/runs/'+parent.id+'/cancel') not in loss.paths
                        assert platform.get_job(parent.id).status=='completed'
                    else:
                        assert task['cancellation_state']=='cancelled'
                        child_id=task['cancellation_receipt']['id']
                        assert child_id != parent.id
                        assert platform.get_job(child_id).status=='cancelled'
                        expected_key=(task.get('repair_pending') or {}).get('submission_key') or task['submission_key']
                        assert expected_key==task['cancellation_receipt']['idempotency_key']
                        if stale=='after-ack':
                            assert task['repair_ack']['run_id']==child_id and len(task['repair_history'])==1
                    again=await loop.run_in_executor(controller_thread,adapter.step)
                    assert again['cancellation_state']==task['cancellation_state']
                else:
                    assert task['repair_count']==1 and len(task['repair_history'])==1
                    assert task['execution_id'] != parent.id
                    if not feedback_machine_eligible:
                        assert task['repair_history'][0]['approval'] is None
                        assert task['repair_history'][0]['feedback_release_id']==original['feedback_release_id']
                    child=platform.get_job(task['execution_id'])
                    assert child.task==parent.task and child.resolved['repository_run']['base_sha']==base
                    assert task['repair_history'][0]['submission']['parent_run_id']==parent.id
                    if lost_path is None and feedback_machine_eligible:
                        async def repair(worktree,goal,deadline,budget,authorization_check,*,repair_context=None):
                            assert goal==parent.task
                            assert repair_context['parent_run_id']==parent.id
                            assert 'qualified fixture check' in json.loads(repair_context['feedback'])['log_excerpt']
                            authorization_check()
                            budget.acquire_slot('fixture-child')
                            budget.reserve_cost('fixture-child-call',0.5)
                            (worktree/'src/main.txt').write_text('repaired\n')
                            owner_git('add','-A',cwd=worktree)
                            owner_git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','repair',cwd=worktree)
                            budget.settle_cost('fixture-child-call',0.25)
                            budget.release_slot('fixture-child')
                        repair.supports_repository_repair_context=True
                        service.owner.executor.executor=repair
                        assert await Worker(platform,repository_run_executor=service.owner.executor).run_once()
                        child=platform.get_job(task['execution_id'])
                        assert child.status=='completed',child.error_code
                        child_attempt=child.resolved['repository_run']['attempts'][-1]['id']
                        content=exporter._prepare_for_owner_review(child.id,child_attempt,principal_id=parent.caller,workspace_id='workspace-1')
                        release_id=release(platform,child,content)
                        retained=CandidateRetention(tmp_path/'child-publication',service.retention.target,reader)
                        retention_key=await retained.prepare(exporter,child.id,child_attempt,release_id=release_id,
                            principal_id=parent.caller,workspace_id='workspace-1')
                        await retained.retain(exporter,retention_key)
                        for _ in range(8):
                            checked=await loop.run_in_executor(controller_thread,adapter.step)
                            if checked['state'] in ('REVIEWED','BLOCKED'): break
                        assert checked['state']==('BLOCKED' if exhausted else 'REVIEWED')
                        if exhausted: assert checked['cause']=='repair-budget-exhausted'
                        assert (adapter.root/'candidate-1/src/main.txt').read_text()=='repaired\n'
                        assert (adapter.root/'driver-check-1/result.json').is_file()
                        if not exhausted: assert (adapter.root/'driver-review-1/result.json').is_file()
                        assert (adapter.root/'retained-export.json').read_bytes() != (adapter.root/'retained-export-1.json').read_bytes()
                assert (adapter.root/'candidate/src/main.txt').read_text()=='candidate\n'
                assert (adapter.root/'driver-check/result.json').is_file()
                jobs=service.owner.list(principal_id=parent.caller,workspace_id='workspace-1')
                assert len(jobs)==(1 if stale=='before-post' else 2)
                if lost_path: assert loss.lost
            finally:
                await loop.run_in_executor(controller_thread,adapter.close)
                await loop.run_in_executor(controller_thread,work.close)
                controller_thread.shutdown()
                execution.client.close()
                await reader.__aexit__(None,None,None)
    asyncio.run(scenario())


def test_actual_work_pg_lost_outcome_ack_uses_owner_digest_and_never_reissues_accept(tmp_path):
    work=WorkOwner('Exact fixture requirements')
    adapter=RepositoryDelivery.__new__(RepositoryDelivery)
    adapter.root=tmp_path/'settlement'; adapter.root.mkdir(mode=0o700)
    adapter.store=Store(adapter.root/'scheduler'); adapter.work=work
    adapter.spec={'repo_id':work.repo,'run_id':work.run,'lease_id':work.lease['lease_id'],
                  'grant_id':None,'basis':work.basis,'item_id':work.item,
                  'packet':{'goal':'Exact fixture requirements'}}
    adapter.store.save({'id':'delivery','state':'MERGING'})
    payload={'evidence':'source outcome regression; no publication effect asserted'}
    work.lose_outcome=True
    try:
        with pytest.raises(DeliveryError,match='unknown-outcome'):
            adapter.report_outcome(adapter.store.tasks()[0],payload)
        adapter.close(); adapter.store=Store(adapter.root/'scheduler')
        # current() would now reject ended lease and changed status/Decision;
        # committed-report reconciliation must precede it.
        result=adapter.step()
        assert result['state']=='MERGED'
        reports=work.invoke('work.lease.read-v1',{'item_id':work.item})['outcome_reports']
        assert len(reports)==1
        assert reports[0]['payload_digest'] != digest(payload)
        assert result['outcome_report']['payload_sha256']==reports[0]['payload_digest']
        assert len(pg.list_decisions(work.store,work.item))==1
        assert work.calls.count('work.lease.report-outcome-v2')==1
    finally:
        adapter.close(); work.close()


def test_released_owner_catalog_keeps_legacy_evidence_only_and_no_autoaccept(tmp_path):
    import subprocess
    command=[os.environ['RELEASED_WORK_OWNER_PYTHON'],'-I','-c',
             'import json;from sprintctl.vuoro_adapter import catalog_operation_specs;'
             'print(json.dumps({"operations":catalog_operation_specs(resource_schema_available=True)}))']
    old=json.loads(subprocess.run(command,check=True,capture_output=True,text=True,cwd=tmp_path).stdout)
    assert not any(op['name']=='work.lease.report-outcome-v2' for op in old['operations'])
    work=WorkOwner('Exact legacy fixture requirements')
    adapter=RepositoryDelivery.__new__(RepositoryDelivery)
    adapter.root=tmp_path/'legacy'; adapter.root.mkdir(mode=0o700)
    adapter.store=Store(adapter.root/'scheduler'); adapter.work=work
    work.catalog=lambda:old
    adapter.spec={'repo_id':work.repo,'run_id':work.run,'lease_id':work.lease['lease_id'],
                  'grant_id':None,'basis':work.basis,'item_id':work.item,
                  'packet':{'goal':'Exact legacy fixture requirements'}}
    adapter.store.save({'id':'delivery','state':'MERGING'})
    try:
        adapter.report_outcome(adapter.store.tasks()[0],{'evidence':'legacy source regression'})
        task=adapter.store.tasks()[0]
        assert task['outcome_report']['reason']=='owner-exact-basis-operation-unavailable'
        assert not work.invoke('work.lease.read-v1',{'item_id':work.item})['outcome_reports']
        assert not pg.list_decisions(work.store,work.item)
        assert pg.get_work_item(work.store,work.item)['status']=='active'
        assert not any(name.startswith('work.lease.report-outcome') for name in work.calls)
    finally:
        adapter.close(); work.close()


@pytest.mark.parametrize('fault',['unknown-reference-population','legacy-unbound-lease'])
def test_actual_work_basis_must_be_proven_before_execution_admission(fault):
    work=WorkOwner('Exact admission fixture requirements')
    adapter=RepositoryDelivery.__new__(RepositoryDelivery)
    adapter.work=work
    adapter.spec={'repo_id':work.repo,'run_id':work.run,'lease_id':work.lease['lease_id'],
                  'grant_id':None,'basis':work.basis,'item_id':work.item,
                  'packet':{'goal':'Exact admission fixture requirements'}}
    def forbidden(*args,**kwargs): raise AssertionError('unproven basis reached execution owner')
    adapter.execution=SimpleNamespace(call=forbidden)
    try:
        if fault=='unknown-reference-population':
            for i in range(65): pg.add_ref(work.store,work.item,'doc',f'https://example.invalid/{i}')
            adapter.spec['basis']=work.invoke('work.run.continuation-delta-v1',{'run_id':work.run,'item_id':work.item})['delta']['current']
            assert adapter.spec['basis']['current_reference_set_digest'] is None
            reason='current-work-basis-unavailable'
        else:
            with work.conn.cursor() as cur:
                cur.execute('UPDATE work_lease SET basis_item_revision=NULL,basis_release_digest=NULL WHERE repo_id=%s AND lease_id=%s',
                            (work.repo,work.lease['lease_id']))
            work.conn.commit()
            reason='work-lease-basis-unavailable'
        with pytest.raises(DeliveryError,match=reason): adapter.start_worker({'state':'PLANNED'})
    finally: work.close()
