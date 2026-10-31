"""Actual Git and trusted-driver boundaries; these do not simulate acceptance."""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from repository_delivery import DeliveryError, RepositoryDelivery, canonical, digest, git, import_candidate, validate_export
from shared_execution.runtime import Store
from shared_execution.scheduler import tick


class DeliveryArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root/'source'; self.source.mkdir()
        git(self.source, 'init', '-b', 'main')
        git(self.source, 'config', 'user.name', 'Test')
        git(self.source, 'config', 'user.email', 'test@example.invalid')
        (self.source/'src').mkdir(); (self.source/'src'/'value.txt').write_text('base\n')
        git(self.source, 'add', '.'); git(self.source, 'commit', '-m', 'base')
        self.base = git(self.source, 'rev-parse', 'HEAD').decode().strip()
        (self.source/'src'/'value.txt').write_text('candidate\n')
        git(self.source, 'add', '.'); git(self.source, 'commit', '-m', 'candidate')
        self.tip = git(self.source, 'rev-parse', 'HEAD').decode().strip()
        git(self.source, 'update-ref', 'refs/heads/candidate', self.tip)
        # The canonical repository contains only base; the bundle must supply tip.
        git(self.source, 'update-ref', 'refs/heads/main', self.base)
        patch = git(self.source, 'diff', '--no-ext-diff', '--no-textconv', '--binary', '--no-renames', self.base, self.tip, '--')
        bundle_path = self.root/'candidate.bundle'
        git(self.source, 'bundle', 'create', str(bundle_path), 'refs/heads/candidate', '^'+self.base)
        self.bundle = bundle_path.read_bytes()
        projection = {'base_sha':self.base, 'tip_sha':self.tip, 'patch_sha256':hashlib.sha256(patch).hexdigest()}
        self.data = {'schema_version':'sovite-repository-candidate-export/v1', 'run_id':'owner-run', 'attempt_id':'owner-attempt',
                     'repository_id':'project', 'base_sha':self.base, 'tip_sha':self.tip, 'patch_sha256':projection['patch_sha256'],
                     'receipt_projection':projection, 'receipt_projection_sha256':digest(projection),
                     'bundle_base64':base64.b64encode(self.bundle).decode(), 'bundle_sha256':hashlib.sha256(self.bundle).hexdigest()}
        self.raw = canonical(self.data)
        self.receipt = {'sha256':hashlib.sha256(self.raw).hexdigest(), 'size':len(self.raw)}

    def tearDown(self): self.temp.cleanup()
    def checked(self, raw=None):
        return validate_export(raw or self.raw, self.receipt, repository_id='project', base_sha=self.base, run_id='owner-run')

    def test_base_only_consumer_reconstructs_exact_candidate_and_restart_reuses_it(self):
        data, bundle = self.checked()
        checkout = self.root/'consumer'
        branch = import_candidate(checkout, str(self.source), data, bundle, ['src'])
        self.assertEqual(git(checkout, 'rev-parse', 'HEAD').decode().strip(), self.tip)
        self.assertEqual((checkout/'src'/'value.txt').read_text(), 'candidate\n')
        self.assertEqual(import_candidate(checkout, str(self.source), data, bundle, ['src']), branch)
        (checkout/'src'/'value.txt').write_text('tamper')
        with self.assertRaises(DeliveryError): import_candidate(checkout, str(self.source), data, bundle, ['src'])

    def test_outer_digest_wrong_source_and_inner_digest_are_refused(self):
        with self.assertRaises(DeliveryError): self.checked(self.raw+b' ')
        changed = dict(self.data, run_id='foreign-run')
        raw = canonical(changed); receipt = {'sha256':hashlib.sha256(raw).hexdigest(), 'size':len(raw)}
        with self.assertRaisesRegex(DeliveryError, 'source-mismatch'):
            validate_export(raw, receipt, repository_id='project', base_sha=self.base, run_id='owner-run')
        changed = dict(self.data, bundle_sha256='0'*64)
        raw = canonical(changed); receipt = {'sha256':hashlib.sha256(raw).hexdigest(), 'size':len(raw)}
        with self.assertRaisesRegex(DeliveryError, 'bundle-changed'):
            validate_export(raw, receipt, repository_id='project', base_sha=self.base, run_id='owner-run')

    def test_allowed_area_cannot_be_inherited_from_candidate(self):
        with self.assertRaisesRegex(DeliveryError, 'area-denied'):
            import_candidate(self.root/'denied', str(self.source), self.data, self.bundle, ['docs'])

    def test_driver_does_not_inherit_credentials_and_missing_result_is_unknown(self):
        adapter = RepositoryDelivery.__new__(RepositoryDelivery)
        adapter.root = self.root/'protected'; adapter.root.mkdir(mode=0o700)
        import_candidate(adapter.root/'candidate', str(self.source), self.data, self.bundle, ['src'])
        driver = self.root/'trusted-check'
        driver.write_text('#!'+sys.executable+'\nimport os,sys\nfrom pathlib import Path\n'
                          'assert "FJ_TOKEN" not in os.environ\n'
                          'assert (Path(sys.argv[1])/"src/value.txt").read_text()=="candidate\\n"\n')
        driver.chmod(0o700)
        adapter.spec = {'packet':{'base_sha':self.base}, 'acceptance':{'expires_at':'2099-01-01T00:00:00Z',
            'qualification_ref':'local-fixture-only', 'allowed_classes':['C1'],
            'check':{'path':str(driver), 'sha256':hashlib.sha256(driver.read_bytes()).hexdigest(), 'timeout_seconds':5}}}
        task = {'worker_commit':self.tip, 'retained':{'output_class':'C1'}}
        old = os.environ.get('FJ_TOKEN'); os.environ['FJ_TOKEN']='synthetic-not-inherited'
        try: result = adapter.driver('check', task)
        finally:
            if old is None: del os.environ['FJ_TOKEN']
            else: os.environ['FJ_TOKEN']=old
        self.assertEqual(result['exit'], 'committed')
        self.assertEqual(adapter.driver('check', task), result)
        (adapter.root/'driver-check'/'result.json').unlink()
        with self.assertRaisesRegex(DeliveryError, 'outcome-unknown'): adapter.driver('check', task)
        driver.write_text(driver.read_text()+'# changed\n')
        with self.assertRaisesRegex(DeliveryError, 'driver-changed'): adapter.driver('check', task)

    def test_driver_completed_result_survives_lost_scheduler_ack_without_rerun(self):
        adapter = RepositoryDelivery.__new__(RepositoryDelivery)
        adapter.root = self.root/'driver-recovery'; adapter.root.mkdir(mode=0o700)
        adapter.store = Store(adapter.root/'scheduler')
        import_candidate(adapter.root/'candidate', str(self.source), self.data, self.bundle, ['src'])
        counter = self.root/'driver-effects'
        driver = self.root/'trusted-recovery-check'
        driver.write_text('#!'+sys.executable+'\nfrom pathlib import Path\n'
                          'p=Path('+repr(str(counter))+')\np.write_text(p.read_text()+"x" if p.exists() else "x")\n')
        driver.chmod(0o700)
        adapter.spec = {'packet':{'base_sha':self.base}, 'acceptance':{'expires_at':'2099-01-01T00:00:00Z',
            'qualification_ref':'local-fixture-only', 'allowed_classes':['C1'],
            'check':{'path':str(driver), 'sha256':hashlib.sha256(driver.read_bytes()).hexdigest(), 'timeout_seconds':5}}}
        task = {'id':'delivery', 'state':'VERIFYING', 'attempt':'verify-1',
                'worker_commit':self.tip, 'retained':{'output_class':'C1'}}
        adapter.store.save(task)
        result = adapter.driver('check', task)  # effect + fsynced result; drop scheduler acknowledgement
        adapter.close()
        adapter.store = Store(adapter.root/'scheduler')
        try:
            self.assertIsNone(adapter.store.meta('verify-1'))
            self.assertEqual(adapter.status('verify-1'), result)
            self.assertEqual(adapter.status('verify-1'), result)
            self.assertEqual(counter.read_text(), 'x')
            adapter.store.db.execute("DELETE FROM meta WHERE key='verify-1'"); adapter.store.db.commit()
            (adapter.root/'driver-check/result.json').unlink()
            with self.assertRaisesRegex(DeliveryError, 'driver-outcome-unknown'):
                adapter.status('verify-1')
            self.assertEqual(counter.read_text(), 'x')
        finally: adapter.close()

    def immediate_execution(self, state):
        """Transport projections only; exercise actual scheduler/import state."""
        adapter = RepositoryDelivery.__new__(RepositoryDelivery)
        adapter.root = self.root/'delivery'; adapter.root.mkdir(mode=0o700)
        adapter.store = Store(adapter.root/'scheduler')
        adapter.current = lambda: None
        adapter.config = {'max_workers':1, 'launch_spacing':0}
        adapter.spec = {'repo_id':'project', 'run_id':'work-run', 'repository_id':'project',
            'packet':{'workspace_id':'workspace', 'base_sha':self.base},
            'canonical_url':str(self.source), 'allowed_areas':['src'],
            'workspace_endpoint':'https://workspace.example.invalid', 'workspace_id':'workspace',
            'workspace_destination':'workspace-workspace', 'allowed_classes':['C1']}
        receipt = dict(self.receipt, endpoint=adapter.spec['workspace_endpoint'], workspace_id='workspace',
                       destination='workspace-workspace', output_class='C1', artifact_id='artifact', version_id='version')
        run = {'id':'owner-run', 'repository_id':'project', 'preview_id':'preview', 'state':state,
               'attempts':[{'id':'owner-attempt', 'state':'completed'}],
               'evidence':[{'label':'retained-candidate', 'sha256':receipt['sha256'], 'receipt':receipt}]}
        calls = []
        class ExecutionProjection:
            def call(self, method, path, **kwargs):
                calls.append((method, path))
                return {'run':run}
        class ArtifactProjection:
            def invoke(self, operation, arguments):
                return dict(receipt, processing_state='ready', content_base64=base64.b64encode(self_raw).decode())
        self_raw = self.raw
        adapter.execution = ExecutionProjection(); adapter.workspace = ArtifactProjection()
        adapter.store.save({'id':'delivery', 'state':'RUNNING', 'attempt':'sovite:submission-key',
            'submission':{'preview_id':'preview'}, 'submission_key':'submission-key', 'execution_id':None,
            'areas':['src'], 'provider':'sovite', 'model':'executor', 'dependencies':[],
            'worktree':str(adapter.root/'candidate')})
        # Stop after the actual scheduler has collected the terminal response;
        # verification is a separate commissioned boundary.
        adapter.attempt = lambda *args: ('verify-1', 1)
        adapter.launch = lambda path: None
        adapter.verification_command = lambda: []
        adapter.main_tip = lambda: self.base
        return adapter, calls

    def test_immediate_completed_submission_keeps_acknowledgement_through_collection(self):
        adapter, calls = self.immediate_execution('completed')
        try:
            tick(adapter)
            task = adapter.store.tasks()[0]
            self.assertEqual(task['execution_id'], 'owner-run')
            self.assertEqual(task['worker_commit'], self.tip)
            self.assertEqual(task['state'], 'VERIFYING')
            self.assertEqual((adapter.root/'retained-export.json').read_bytes(), self.raw)
            self.assertEqual(calls, [('POST','/runs'), ('GET','/runs/owner-run')])
        finally: adapter.close()

    def test_immediate_failed_submission_preserves_acknowledged_owner_run(self):
        adapter, calls = self.immediate_execution('failed')
        try:
            tick(adapter)
            task = adapter.store.tasks()[0]
            self.assertEqual(task['execution_id'], 'owner-run')
            self.assertEqual(task['state'], 'BLOCKED')
            self.assertEqual(task['cause'], 'execution-failed-or-uncertain')
            self.assertEqual(calls, [('POST','/runs'), ('GET','/runs/owner-run')])
        finally: adapter.close()

    def test_unreleased_work_and_credential_bearing_source_refuse_before_any_owner_call(self):
        spec = {'schema_version':'agentops-repository-delivery/v1', 'max_repairs':0,
                'basis':{'current_release_digest':None}, 'canonical_url':'https://github.com/example/project'}
        with self.assertRaisesRegex(DeliveryError, 'work-release-required'):
            RepositoryDelivery(self.root/'protected', spec, None, None, None)
        spec['basis']['current_release_digest'] = 'a'*64
        spec['canonical_url'] = 'https://user:synthetic-secret@example.invalid/project'
        with self.assertRaisesRegex(DeliveryError, 'public-source-url-required'):
            RepositoryDelivery(self.root/'protected', spec, None, None, None)

    def test_canonical_integration_cannot_inherit_a_foreign_git_directory(self):
        # The true canonical main still contains only base. A different local
        # repository claims the candidate is its origin/main; ambient GIT_DIR
        # must not select that history for the actual integration observation.
        adapter = RepositoryDelivery.__new__(RepositoryDelivery)
        adapter.root = self.root/'integration'; adapter.root.mkdir(mode=0o700)
        adapter.store = Store(adapter.root/'scheduler')
        branch = import_candidate(adapter.root/'candidate', str(self.source), self.data, self.bundle, ['src'])
        foreign = self.root/'foreign'; foreign.mkdir()
        git(foreign, 'init', '-b', 'main')
        git(foreign, 'fetch', str(self.source), 'refs/heads/candidate:refs/remotes/origin/main')
        adapter.current = lambda: None
        adapter.spec = {'authority_environment':str(adapter.root/'environment.json'), 'repo_id':'project',
            'run_id':'work-run', 'grant_id':'grant', 'publication_attempt_id':None,
            'work_profile':str(adapter.root/'profile.json'), 'item_id':1, 'basis':{}}
        task = {'id':'delivery', 'state':'MERGING', 'worker_commit':self.tip, 'verified_base':self.base,
            'branch':branch, 'publication':{'fixture':'already-published'}, 'retained':self.receipt,
            'check':{'exit':'committed'}, 'review':{'exit':'committed'}}
        adapter.store.save(task)
        class NoUnlandedEvidence:
            def invoke(self, *args):
                raise AssertionError('unlanded candidate incorrectly reported as canonical')
        adapter.work = NoUnlandedEvidence()
        previous = os.environ.get('GIT_DIR'); os.environ['GIT_DIR'] = str(foreign/'.git')
        try:
            adapter.integrate(task)
            self.assertNotIn('outcome_payload', adapter.store.tasks()[0])
            self.assertEqual(git(adapter.root/'candidate', 'rev-parse', 'origin/main').decode().strip(), self.base)
        finally:
            if previous is None: del os.environ['GIT_DIR']
            else: os.environ['GIT_DIR'] = previous
            adapter.close()

    def test_owner_terminal_decision_must_bind_exact_release_and_evidence(self):
        # Read-projection fixtures isolate the matching rule; this is not a
        # simulated successful delivery or owner authority implementation.
        from shared_execution.runtime import Store
        adapter = RepositoryDelivery.__new__(RepositoryDelivery)
        adapter.root = self.root/'state'; adapter.root.mkdir(mode=0o700)
        adapter.store = Store(adapter.root/'scheduler')
        adapter.spec = {'repo_id':'project', 'item_id':1, 'basis':{'current_release_digest':'a'*64}}
        task = {'id':'delivery', 'state':'MERGING', 'outcome_payload':{'candidate':self.tip}}
        adapter.store.save(task)
        reads = {'status':'done', 'terminal_decision_id':1, 'decisions':[{'id':1, 'kind':'accept',
                 'release_digest':'a'*64, 'evidence_digests':['0'*64]}]}
        class DecisionProjection:
            def invoke(self, *args): return reads
        adapter.work = DecisionProjection()
        try:
            with self.assertRaisesRegex(DeliveryError, 'different-basis-or-evidence'):
                adapter.observe_settlement(task)
            self.assertEqual(adapter.store.tasks()[0]['state'], 'MERGING')
            reads['decisions'][0]['evidence_digests'] = [digest(task['outcome_payload'])]
            reads['decisions'][0]['release_digest'] = 'b'*64
            with self.assertRaises(DeliveryError): adapter.observe_settlement(task)
            reads['decisions'][0]['release_digest'] = 'a'*64
            self.assertTrue(adapter.observe_settlement(task))
            self.assertEqual(adapter.store.tasks()[0]['state'], 'MERGED')
        finally: adapter.store.close()


if __name__ == '__main__': unittest.main()
