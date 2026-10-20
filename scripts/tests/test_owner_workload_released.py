"""Execute the actual installed CLI/adapter/client against fixture HTTP streams.

Run with the released Sprintctl interpreter using unittest; no live endpoint.
"""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import observe_owner_workload as cohort
import host_adapter
try:
    import httpx
    import sprintctl.cli
except ImportError:
    httpx=None


@unittest.skipIf(httpx is None,'released Sprintctl/client environment required')
class ReleasedCohort(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.old_cwd=Path.cwd();os.chdir(root);self.addCleanup(os.chdir,self.old_cwd)
        # Exact adapter bytes in a writable copy beside its inventory: run() must leave no
        # bytecode there. HOME/XDG dirs are empty and read-only: nothing may be written.
        self.adapter_dir=root/'repo/scripts';self.adapter_dir.mkdir(parents=True)
        shutil.copy(ROOT/'scripts/host_adapter.py',self.adapter_dir/'host_adapter.py')
        inventory=root/'repo/docs/architecture';inventory.mkdir(parents=True)
        shutil.copy(ROOT/'docs/architecture/2026-10-18-estate-first-consumer-contracts.json',inventory)
        self.state={name:root/'state'/name for name in ('home','xdg-state','xdg-cache','xdg-config','xdg-data')}
        env={'HOME':'home','XDG_STATE_HOME':'xdg-state','XDG_CACHE_HOME':'xdg-cache','XDG_CONFIG_HOME':'xdg-config','XDG_DATA_HOME':'xdg-data'}
        for directory in self.state.values():directory.mkdir(parents=True);directory.chmod(0o500)
        self.addCleanup(lambda:[d.chmod(0o700) for d in self.state.values()])
        env_patch=patch.dict(os.environ,{key:str(self.state[name]) for key,name in env.items()});env_patch.start();self.addCleanup(env_patch.stop)
        bytecode=patch.object(sys,'dont_write_bytecode',False);bytecode.start();self.addCleanup(bytecode.stop)
        marker=root/'.sprintctl';marker.mkdir();(marker/'backend.json').write_text(json.dumps({'backend':'served','repo_id':'agentops'}))
        credential=root/'credential';credential.write_text('SECRET-CREDENTIAL');credential.chmod(0o600)
        self.profile=root/'profile.json';self.profile.write_text(json.dumps({
            'schema_version':'vuoro-client-profile/v1','id':'fixture','revision':1,'source_environment_id':'workstation',
            'target':{'environment_id':'fixture','environment_class':'development','endpoint':'https://fixture.invalid'},
            'credential_ref':'file:'+str(credential),'required_authorities':['work:read'],'production_endpoint_denied':True}))
        self.plan=json.loads((ROOT/'verification/fixtures/ec01-controlled-read-cohort-2733.json').read_text())
        self.handshake={'client_protocol':{'minimum':1,'maximum':1},'service_release':{'distribution':'vuoro-service','version':'fixture'},
                        'environment':{'name':'fixture','environment_class':'development'}}
        expected,_=host_adapter._owner_inventory(host_adapter._declared_owner_operations())
        self.catalog={'revision':'fixture','operations':list(copy.deepcopy(expected).values())}
        self.plan['bindings']['service_release_sha256']=cohort.digest(self.handshake['service_release'])
        self.plan['bindings']['catalog_revision_sha256']=cohort.digest('fixture')
        self.requests=[];self.clients=[];self.status=200;self.huge=False;self.compressed=False;self.redirect=False
        self.result={'messages':[],'next_after_seq':12345}
        self.after_request=None
        owner=self
        class Stream(httpx.AsyncByteStream):
            def __init__(self,content):self.content=content
            async def __aiter__(self):
                yield self.content
        def handle(request):
            owner.requests.append((request.method,request.url.path))
            if request.url.path=='/api/meta/v1/handshake': body=owner.handshake
            elif request.url.path=='/api/catalog/v1': body=owner.catalog
            else: body={'status':'accepted','result':owner.result}
            content=json.dumps(body).encode()
            if owner.huge:content=b'x'*(cohort.BOUNDS['max_response_body_bytes']+1)
            headers={'Content-Encoding':'gzip'} if owner.compressed else {}
            if owner.redirect and len(owner.requests)==1:
                response=httpx.Response(302,stream=Stream(b'{}'),headers={'Location':'https://fixture.invalid/api/catalog/v1'})
            else:
                response=httpx.Response(owner.status,stream=Stream(content),headers=headers)
            if owner.after_request:owner.after_request(request)
            return response
        self.handle=handle
        base=httpx.AsyncClient
        class FixtureClient(base):
            def __init__(self,*args,**kwargs):
                kwargs['transport']=httpx.MockTransport(handle)
                super().__init__(*args,**kwargs);owner.clients.append(self)
        self.client_patch=patch('httpx.AsyncClient',FixtureClient);self.client_patch.start();self.addCleanup(self.client_patch.stop)
        self.sleep_patch=patch('observe_owner_workload.time.sleep');self.sleep_patch.start();self.addCleanup(self.sleep_patch.stop)

    def run_cohort(self,mode='served-cli-inbox-read'):
        before=sorted(p.relative_to(self.tmp.name) for p in Path(self.tmp.name).rglob('*'))
        report=cohort.run(self.plan,'fixture-plan',mode,self.profile,self.adapter_dir/'host_adapter.py')
        after=sorted(p.relative_to(self.tmp.name) for p in Path(self.tmp.name).rglob('*'))
        # No local state, cache, receipt or bytecode write anywhere under the fixture root.
        self.assertEqual(before,after)
        self.assertFalse(sys.dont_write_bytecode)
        self.assertEqual(report['window']['requests_sent'],len(report['events']))
        self.assertEqual(report['window']['trials_completed'],len(report['samples']))
        return report

    def test_actual_cli_five_trials_exact_seventeen_requests_with_handshake(self):
        report=self.run_cohort()
        self.assertEqual(report['status'],'complete',report)
        self.assertEqual(len(self.requests),17)
        self.assertEqual(self.requests[:2],cohort.PREFLIGHT)
        # Sprintctl 0.21.0: every trial handshakes its fresh client before catalog+invoke.
        self.assertEqual(self.requests[2:],[cohort.HANDSHAKE,cohort.CATALOG,cohort.INVOKE]*5)
        self.assertEqual(report['window']['request_budget'],17)
        self.assertTrue(all(row['requests']==3 for row in report['samples']))
        self.assertTrue(all(event['outcome']=='ok' for event in report['events']))
        self.assertEqual(len(report['samples']),5)
        self.assertTrue(all(row['empty'] for row in report['samples']))
        self.assertEqual(report['workflow_acceptance'],'unknown')
        self.assertEqual(report['population_representativeness'],'unknown')
        self.assertEqual(report['estate_completeness'],'unknown')
        self.assertEqual(report['max_observed_in_flight'],1)
        self.assertTrue(all(client.is_closed for client in self.clients))
        self.assertNotIn('12345',json.dumps(report))

    def test_actual_adapter_metadata_only_exact_twelve_gets(self):
        report=self.run_cohort('host-adapter-metadata')
        self.assertEqual(report['status'],'complete',report)
        self.assertEqual(self.requests,cohort.METADATA*6)
        self.assertEqual(report['window']['request_budget'],12)
        self.assertTrue(all(row['result_count']==14 for row in report['samples']))
        self.assertTrue(all(client.is_closed for client in self.clients))

    def test_secret_response_keys_values_and_credentials_never_reach_report(self):
        self.result['messages']=[{'message_id':'SECRET-ID','sender_principal_id':'SECRET-SENDER',
          'workspace_id':'SECRET-WORKSPACE','repo_id':'SECRET-REPO','persisted_at':'SECRET-TIME',
          'envelope_digest':'SECRET-DIGEST','inbox_seq':987654321,'receipts':[],
          'SECRET-KEY':'SECRET-BODY'}]
        report=self.run_cohort()
        self.assertEqual(report['status'],'complete',report)
        rendered=json.dumps(report)
        self.assertNotIn('SECRET',rendered);self.assertNotIn('987654321',rendered)
        self.assertNotIn(str(self.profile),rendered)
        self.assertTrue(all(row['result_count']==1 for row in report['samples']))

    def test_wrong_environment_stops_before_catalog_or_read(self):
        self.handshake['environment']['name']='SECRET-WRONG'
        report=self.run_cohort()
        self.assertNotEqual(report['status'],'complete')
        self.assertEqual(self.requests,[cohort.METADATA[0]])
        self.assertNotIn('SECRET',json.dumps(report))

    def test_changed_release_stops_before_catalog_or_read(self):
        self.handshake['service_release']['version']='changed'
        report=self.run_cohort()
        self.assertEqual((report['status'],report['reason']),('incomplete','service-release-mismatch'))
        self.assertEqual(self.requests,[cohort.METADATA[0]])

    def test_changed_catalog_stops_before_read(self):
        self.catalog['revision']='changed'
        report=self.run_cohort()
        self.assertEqual(report['reason'],'catalog-revision-mismatch')
        self.assertEqual(self.requests,cohort.METADATA)

    def test_changed_contract_stops_before_read(self):
        operation=next(x for x in self.catalog['operations'] if x['name']==cohort.READ_OPERATION)
        operation['execution_semantics']='write'
        report=self.run_cohort()
        self.assertEqual(report['reason'],'read-contract-mismatch')
        self.assertEqual(self.requests,cohort.METADATA)

    def test_http_denial_is_explicit_and_no_retry(self):
        self.status=403
        report=self.run_cohort()
        self.assertEqual((report['status'],report['reason']),('incomplete','http-refused'))
        self.assertEqual(len(self.requests),1)
        self.assertEqual(report['events'][0]['status_code'],403)
        self.assertEqual(report['events'][0]['outcome'],'http-refused')

    def test_http_outage_is_explicit_and_no_retry(self):
        self.status=503
        report=self.run_cohort()
        self.assertEqual(report['reason'],'http-refused')
        self.assertEqual(len(self.requests),1)
        self.assertEqual(report['events'][0]['status_code'],503)

    def test_oversize_stream_closes_and_stops(self):
        self.huge=True
        report=self.run_cohort()
        self.assertEqual(report['reason'],'response-size-limit')
        self.assertEqual(len(self.requests),1)
        self.assertTrue(all(client.is_closed for client in self.clients))

    def test_encoded_stream_is_outside_declared_cohort(self):
        self.compressed=True
        report=self.run_cohort()
        self.assertEqual(report['reason'],'encoded-response-not-in-cohort')
        self.assertEqual(len(self.requests),1)

    def test_profile_change_stops_before_first_trial(self):
        def changed(request):
            if len(self.requests)==2:self.profile.write_text('{}')
        self.after_request=changed
        report=self.run_cohort()
        self.assertEqual((report['status'],report['reason']),('incomplete','profile-changed'))
        self.assertEqual(len(self.requests),2)

    def test_source_mismatch_refuses_before_network(self):
        self.plan['bindings']['source_files']['sprintctl.served']['sha256']='0'*64
        report=self.run_cohort()
        self.assertEqual((report['status'],report['reason']),('refused','client-source-mismatch'))
        self.assertEqual(self.requests,[])

    def test_incorrect_repository_marker_refuses_before_network(self):
        Path('.sprintctl/backend.json').write_text(json.dumps({'backend':'local','repo_id':'agentops'}))
        report=self.run_cohort()
        self.assertEqual((report['status'],report['reason']),('refused','repository-binding-mismatch'))
        self.assertEqual(self.requests,[])

    def test_failure_mid_cohort_is_incomplete_with_completed_trials_kept(self):
        def outage(request):
            if len(self.requests)==2+3*2:self.status=503  # next request: trial 2 handshake
        self.after_request=outage
        report=self.run_cohort()
        self.assertEqual((report['status'],report['reason']),('incomplete','http-refused'),report)
        self.assertEqual(len(report['samples']),2)
        self.assertEqual(len(self.requests),9)
        self.assertEqual(report['events'][-1]['trial'],2)

    def test_redirect_is_never_followed_under_the_guard(self):
        # Pins follow_redirects=False: following would send an unadmitted second request.
        self.redirect=True
        report=self.run_cohort()
        self.assertEqual((report['status'],report['reason']),('incomplete','http-refused'),report)
        self.assertEqual(self.requests,[cohort.HANDSHAKE])
        self.assertEqual(report['events'][0]['status_code'],302)

    def test_more_than_one_returned_message_is_refused(self):
        message={'message_id':'SECRET-ID','sender_principal_id':'SECRET-SENDER','workspace_id':'SECRET-WORKSPACE',
                 'repo_id':'SECRET-REPO','persisted_at':'SECRET-TIME','envelope_digest':'SECRET-DIGEST','inbox_seq':1,'receipts':[]}
        self.result['messages']=[message,dict(message)]
        report=self.run_cohort()
        self.assertEqual((report['status'],report['reason']),('incomplete','read-count-limit'),report)
        self.assertEqual(report['samples'],[])
        self.assertNotIn('SECRET',json.dumps(report))

    def test_nonzero_cli_return_code_is_refused(self):
        with patch.object(sprintctl.cli.cli,'main',return_value=1):
            report=self.run_cohort()
        self.assertEqual((report['status'],report['reason']),('incomplete','cli-exit-nonzero'),report)
        self.assertEqual(self.requests,cohort.PREFLIGHT)

    def test_installed_sprintctl_must_be_the_handshake_release(self):
        import importlib.metadata
        self.assertEqual(importlib.metadata.version('sprintctl'),cohort.REQUIRED_SPRINTCTL)
        real=importlib.metadata.version
        with patch('observe_owner_workload.importlib.metadata.version',side_effect=lambda n:'0.20.0' if n=='sprintctl' else real(n)):
            report=self.run_cohort()
        self.assertEqual((report['status'],report['reason']),('refused','sprintctl-version-unsupported'))
        self.assertEqual(self.requests,[])

    def test_unlisted_requests_and_mutations_never_reach_transport(self):
        import asyncio
        body={'schema_version':'invocation/v1','request_id':'fixture','operation':cohort.READ_OPERATION,
              'arguments':dict(cohort.READ_ARGUMENTS),'catalog_revision':'fixture','basis_revision':None,
              'idempotency_key':None,'repo_id':'agentops'}
        cases=[('POST','https://fixture.invalid/api/invoke/v1',dict(body,operation='work.message.send-v1')),
               ('POST','https://fixture.invalid/api/invoke/v1',dict(body,arguments={'after_seq':0,'limit':True})),
               ('POST','https://fixture.invalid/api/invoke/v1',dict(body,unexpected='SECRET')),
               ('POST','https://other.invalid/api/invoke/v1',body),
               ('POST','https://fixture.invalid/api/invoke/v1?secret=SECRET',body),
               ('GET','https://fixture.invalid/other',None)]
        for method,url,payload in cases:
            with self.subTest(method=method,url=url):
                guard=cohort.RequestGuard('https://fixture.invalid','agentops',self.plan,'served-cli-inbox-read')
                guard.begin('fixture',[('POST','/api/invoke/v1')])
                client_type=guard.client_type(httpx.AsyncClient)
                async def invoke():
                    async with client_type() as client:
                        await client.request(method,url,json=payload)
                with self.assertRaises(cohort.Refusal):asyncio.run(invoke())
        self.assertEqual(self.requests,[])


if __name__=='__main__':unittest.main()
