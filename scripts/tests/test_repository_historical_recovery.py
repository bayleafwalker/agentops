"""Historical transport intent: no active Work, execution, repair or settlement."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import sys
import sqlite3
from types import SimpleNamespace
from contextlib import redirect_stdout,closing
from io import StringIO
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import repository_delivery as delivery
from shared_execution.runtime import Store


class Contract:
    def __init__(self,*args,**kwargs):self.recovery=kwargs['recovery']


class HistoricalRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'state';self.root.mkdir(mode=0o700)
        self.spec={'schema_version':'agentops-repository-delivery/v1','repository_id':'repo',
            'packet':{'repository_id':'repo','workspace_id':'owner-workspace','executor_id':'native','base_sha':'b'*40,'goal':'Original full goal'},
            'workspace_endpoint':'https://knowledge.invalid','workspace_id':'storage-workspace',
            'workspace_destination':'private-storage','allowed_classes':['C3']}
        self.policy={'schema_version':'agentops-repository-recovery/v1','contract_id':'recovery-copy',
            'destination_id':'private-storage','owner_contract':{'root':'/fixed/owner-sdk','integrity_sha256':'a'*64,
                'source_ref':'https://github.com/bayleafwalker/sovite/blob/'+'a'*40+'/docs/contracts/repository-repair-v1.provenance.json'}}
        self.task={'id':'delivery','state':'BLOCKED','attempt':'sovite:original-key','execution_id':'execution',
            'submission_key':'original-submission-key','submission':{'schema_version':'sovite-repository-run/v1',
                'packet':self.spec['packet'],'preview_id':'a'*64},
            'cause':'work-basis-changed','billing':'unknown'}
        store=Store(self.root/'scheduler');store.setmeta('spec',self.spec);store.save(self.task);self.task=store.tasks()[0];store.close()
        projection={'job_id':'execution','attempt_id':'attempt','workspace_id':'owner-workspace','repository_id':'repo',
            'base_sha':'b'*40,'tip_sha':'c'*40,'patch_sha256':'d'*64,'packet_sha256':'e'*64,
            'within_deadline':False,'publication_eligible':False,'repair_eligible':False}
        bundle=b'retained untrusted historical bytes; never imported'
        self.value={'schema_version':'sovite-repository-candidate-export/v1','kind':'repository-recovery-artifact',
            'run_id':'execution','attempt_id':'attempt','workspace_id':'owner-workspace','repository_id':'repo',
            'base_sha':'b'*40,'tip_sha':'c'*40,'patch_sha256':'d'*64,'receipt_projection':projection,
            'receipt_projection_sha256':delivery.digest(projection),'bundle_base64':base64.b64encode(bundle).decode(),
            'bundle_sha256':hashlib.sha256(bundle).hexdigest(),'outcome':'uncertain','publication_eligible':False,'repair_eligible':False}
        self.raw=delivery.canonical(self.value);self.sha=hashlib.sha256(self.raw).hexdigest()
        self.receipt={'endpoint':'https://knowledge.invalid','workspace_id':'storage-workspace','destination':'private-storage',
            'artifact_id':'artifact','version_id':'version','sha256':self.sha,'size':len(self.raw),
            'output_class':'C3','release_id':'release_'+'f'*64}
        self.run={'id':'execution','idempotency_key':'original-submission-key','state':'blocked','repository_id':'repo',
            'workspace_id':'owner-workspace','executor_id':'native','preview_id':'a'*64,'attempts':[{'id':'attempt','state':'uncertain'}],'evidence':[]}
        self.calls=[];self.lost=None;self.denied=False;self.read_denied=False;self.reads=0
        outer=self
        class Owner:
            def call(self,method,path,**kwargs):
                outer.calls.append((method,path,copy.deepcopy(kwargs)))
                if method=='GET':return {'runs':[copy.deepcopy(outer.run)]} if path=='/runs' else {'run':copy.deepcopy(outer.run)}
                if path.endswith('/candidate-retention'):
                    record=outer.record();assert record['retention_intent']==kwargs['json']
                    outer.run['evidence']=[row for row in outer.run['evidence'] if row.get('label')!='retained-recovery-candidate']+[{
                        'label':'retained-recovery-candidate','attempt_id':'attempt','sha256':outer.sha,'receipt':outer.receipt}]
                    if outer.lost=='retention':outer.lost=None;raise delivery.DeliveryError('execution-owner-unknown-outcome')
                    return {'receipt':copy.deepcopy(outer.receipt)}
                raise AssertionError('Historical recovery must never submit/cancel/repair/settle')
            def recovery_call(self,contract,operation,run_id,body):
                assert contract.recovery and run_id=='execution'
                outer.calls.append((operation,copy.deepcopy(body)))
                record=outer.record()
                if operation=='repositoryRecoveryCapture':
                    assert record['capture_intent']==body
                    result={key:outer.value[key] for key in ('kind','run_id','attempt_id','workspace_id','repository_id','base_sha','tip_sha','outcome','publication_eligible','repair_eligible')}
                    result['source_digest']='sha256:'+outer.sha
                elif operation=='repositoryRecoveryContext':
                    assert record['context_intent']==body
                    if outer.denied:raise delivery.DeliveryError('execution-owner-refused:409:recovery_copy_denied')
                    result={'kind':'repository-recovery-artifact','run_id':run_id,'attempt_id':'attempt','source_digest':'sha256:'+outer.sha,
                        'contract_id':'recovery-copy','contract_revision':'sha256:'+'1'*64,'expected_generation':'sha256:'+'2'*64,
                        'procedure_digest':'sha256:'+'3'*64,'output_class':'C3','destinations':['private-storage'],
                        'publication_eligible':False,'repair_eligible':False}
                elif operation=='repositoryRecoveryRelease':
                    assert record['release_intent']==body
                    result={'release_id':outer.receipt['release_id'],'output_class':'C3','output_digest':'sha256:'+'4'*64,
                        'contract_revision':body['expected_contract_revision'],'destinations':['private-storage']}
                else:raise AssertionError(operation)
                if outer.lost==operation:outer.lost=None;raise delivery.DeliveryError('execution-owner-unknown-outcome')
                return result
        class Workspace:
            def invoke(self,operation,body):
                assert operation=='knowledge.artifact.download-v1'
                outer.reads+=1
                if outer.read_denied:raise delivery.DeliveryError('owner-refused:membership-revoked')
                return {'artifact_id':'artifact','version_id':'version','processing_state':'ready','sha256':outer.sha,
                    'size':len(outer.raw),'content_base64':base64.b64encode(outer.raw).decode()}
        self.owner,self.workspace=Owner(),Workspace()
        self.adapter=None
        patcher=patch.object(delivery,'OwnerRepairContract',Contract);patcher.start();self.addCleanup(patcher.stop)
        self.addCleanup(self.close)

    def record(self):
        with closing(sqlite3.connect(self.root/'scheduler/state.sqlite3')) as connection:
            rows=connection.execute("SELECT body FROM meta WHERE key LIKE 'recovery:%'").fetchall()
        self.assertEqual(len(rows),1);return json.loads(rows[0][0])
    def close(self):
        if self.adapter:self.adapter.close();self.adapter=None
    def open(self,**kwargs):
        self.close();self.adapter=delivery.HistoricalRecovery(self.root,self.spec,self.workspace,self.owner,self.policy,
                                                            attempt_id='attempt',**kwargs)
        return self.adapter
    def unchanged(self):self.assertEqual(self.adapter.store.tasks()[0],self.task)

    def test_machine_procedure_preserves_blocked_task_and_recovers_only_private_evidence(self):
        result=self.open().step()
        self.assertEqual(result['state'],'recovery-retained');self.assertFalse(result['publication_eligible']);self.assertFalse(result['repair_eligible'])
        self.assertEqual(Path(result['artifact_path']).read_bytes(),self.raw)
        self.assertFalse(Path(result['artifact_path']).stat().st_mode&0o077)
        self.unchanged();self.assertFalse((self.root/'candidate').exists())
        self.assertNotEqual(self.record()['release']['output_digest'],'sha256:'+self.receipt['sha256'])

    def test_each_lost_response_keeps_exact_durable_intent_and_no_new_execution(self):
        for lost in ['repositoryRecoveryCapture','repositoryRecoveryContext','repositoryRecoveryRelease','retention']:
            with self.subTest(lost=lost):
                self.close();self.run['evidence']=[]
                store=Store(self.root/'scheduler');store.db.execute("DELETE FROM meta WHERE key LIKE 'recovery:%'");store.db.commit();store.close()
                self.lost=lost
                with self.assertRaises(delivery.DeliveryError):self.open().step()
                before=self.record();self.unchanged()
                result=self.open().step();self.assertEqual(result['state'],'recovery-retained');self.unchanged()
                after=self.record()
                for key in ('capture_intent','release_intent','retention_intent'):
                    if key in before:self.assertEqual(after[key],before[key])

    def test_actual_release_selector_does_not_invent_an_approver(self):
        self.denied=True
        with self.assertRaisesRegex(delivery.DeliveryError,'recovery_copy_denied'):self.open().step()
        self.assertNotIn('release_intent',self.record());self.unchanged()
        stopped=self.adapter.failure('execution-owner-refused:409:recovery_copy_denied')
        self.assertEqual(stopped['release_request']['source_digest'],'sha256:'+self.sha)
        self.assertIn('--release-id',stopped['next_action'])
        self.calls=[]
        result=self.open(release_id=self.receipt['release_id']).step()
        self.assertEqual(result['state'],'recovery-retained')
        self.assertFalse(any(row[0] in {'repositoryRecoveryContext','repositoryRecoveryRelease'} for row in self.calls));self.unchanged()

    def test_ready_owner_history_uses_fresh_workspace_reader_without_producer_reapproval(self):
        self.run['evidence']=[{'label':'retained-recovery-candidate','attempt_id':'attempt','sha256':self.sha,'receipt':self.receipt}]
        self.denied=True
        result=self.open().step();self.assertEqual(result['state'],'recovery-retained')
        self.assertFalse(any(row[0].startswith('repositoryRecovery') for row in self.calls));self.assertEqual(self.reads,1)
        self.read_denied=True
        with self.assertRaisesRegex(delivery.DeliveryError,'membership-revoked'):self.open().step()
        self.assertEqual(self.reads,2);self.unchanged()

    def test_unknown_child_intent_never_falls_back_to_old_parent_or_submits(self):
        store=Store(self.root/'scheduler')
        task=store.tasks()[0];task['repair_pending']={'submission_key':'unknown-child-key','submission':{'parent_run_id':'execution'}}
        store.save(task);self.task=store.tasks()[0];store.close()
        with self.assertRaisesRegex(delivery.DeliveryError,'historical-submission-outcome-unknown'):self.open().step()
        self.assertEqual([row[0] for row in self.calls],['GET']);self.unchanged()

    def test_recovery_artifact_is_refused_by_active_candidate_ingestion(self):
        with self.assertRaisesRegex(delivery.DeliveryError,'recovery-is-not-publication-candidate'):
            delivery.validate_export(self.raw,self.receipt,repository_id='repo',base_sha='b'*40,run_id='execution')

    def test_running_or_wrong_owned_source_never_captures(self):
        for key,value in [('state','running'),('idempotency_key','foreign-key'),('repository_id','foreign'),('preview_id','f'*64)]:
            with self.subTest(key=key):
                original=self.run[key];self.run[key]=value;self.calls=[]
                with self.assertRaises(delivery.DeliveryError):self.open().step()
                self.assertFalse(any(row[0].startswith('repositoryRecovery') for row in self.calls));self.unchanged()
                self.run[key]=original


    def test_cli_historical_mode_never_initializes_missing_work_profile(self):
        self.spec.update(workspace_profile='workspace-only',sovite_endpoint='https://execution.invalid',
                         sovite_credential_ref='file:/fixture-only')
        store=Store(self.root/'scheduler');store.setmeta('spec',self.spec);store.close()
        spec_path=Path(self.tmp.name)/'spec.json';spec_path.write_bytes(delivery.canonical(self.spec))
        policy_path=Path(self.tmp.name)/'policy.json';policy_path.write_bytes(delivery.canonical(self.policy));policy_path.chmod(0o600)
        self.workspace.client=SimpleNamespace(profile=SimpleNamespace(endpoint='https://knowledge.invalid'))
        self.workspace.close=lambda:None;self.owner.close=lambda:None
        calls=[]
        def client(profile):
            calls.append(profile);self.assertEqual(profile,'workspace-only');return self.workspace
        output=StringIO()
        with patch.object(delivery,'Vuoro',side_effect=client),patch.object(delivery,'Sovite',return_value=self.owner),redirect_stdout(output):
            self.assertEqual(delivery.main(['--spec',str(spec_path),'--state',str(self.root),
                '--recovery-policy',str(policy_path),'--attempt-id','attempt']),0)
        self.assertEqual(calls,['workspace-only'])
        self.assertEqual(json.loads(output.getvalue())['state'],'recovery-retained')
        store=Store(self.root/'scheduler');self.assertEqual(store.tasks()[0],self.task);store.close()


    def test_repair_recovery_requires_saved_ack_and_exact_owner_predecessor(self):
        store=Store(self.root/'scheduler');task=store.tasks()[0]
        key='delivery-repair-exact-child-key'
        task.update(submission_key=key,submission={'schema_version':'sovite-repository-repair/v1',
            'parent_run_id':'parent','candidate_sha256':'9'*64},repair_ack={'run_id':'execution'})
        store.save(task);self.task=store.tasks()[0];store.close()
        self.run.update(idempotency_key=key,preview_id='different-child-packet-preview',evidence=[{
            'label':'repair-predecessor','uri':'sovite://repository-runs/parent','sha256':'9'*64}])
        self.assertEqual(self.open().step()['state'],'recovery-retained');self.unchanged()
        self.run['evidence'][0]['uri']='sovite://repository-runs/foreign-parent'
        with self.assertRaisesRegex(delivery.DeliveryError,'historical-repair-lineage-mismatch'):self.open().step()
        self.unchanged()
