"""Exercise the offline repository-delivery consumer, including refusal paths."""
import hashlib
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from repository_delivery_qualification import Demo, DemoOwner, initialize, git


class RepositoryDeliveryDemoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'demo'
        initialize(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def step(self, owner=None):
        adapter = Demo(self.root, owner or DemoOwner())
        try:
            adapter.step()
            return adapter.task()
        finally:
            adapter.close()

    def test_successor_reconstructs_and_finishes_verified_candidate(self):
        for _ in range(8):
            task = self.step()
            if task['state'] == 'MERGED':
                break
        self.assertEqual(task['state'], 'MERGED')
        self.assertEqual(task['receipt']['candidate'], task['worker_commit'])
        self.assertEqual(task['receipt']['owner'], 'offline-fake-owner')
        self.assertEqual(git(self.root / 'repo', 'rev-parse', 'main'), task['verified_base'])
        self.assertEqual(self.step()['receipt'], task['receipt'])

    def test_candidate_mutation_is_refused_after_verification(self):
        while self.step()['state'] != 'REVIEWED':
            pass
        (self.root / 'candidate' / 'delivery.py').write_text('VALUE = "tampered"\n')
        with self.assertRaisesRegex(ValueError, 'candidate'):
            self.step()

    def test_refuses_denied_owner_and_failing_verification(self):
        for _ in range(4):
            task = self.step(DemoOwner(allow=False))
            if task['state'] == 'BLOCKED':
                break
        self.assertEqual(task['state'], 'BLOCKED')

        self.temp.cleanup()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'demo'
        initialize(self.root, failing_test=True)
        for _ in range(5):
            task = self.step()
            if task['state'] == 'BLOCKED':
                break
        self.assertEqual(task['state'], 'BLOCKED')
        self.assertEqual(task['cause'], 'verification-failed')

    def test_missing_worker_receipt_is_not_replayed_on_restart(self):
        task = self.step()
        candidate = git(self.root / 'candidate', 'rev-parse', 'HEAD')
        adapter = Demo(self.root, DemoOwner())
        try:
            adapter.store.db.execute("DELETE FROM meta WHERE key='offline-worker-1'")
            adapter.store.db.commit()
        finally:
            adapter.close()
        successor = self.step()
        self.assertEqual(successor['state'], 'RUNNING')
        self.assertEqual(successor['worker_envelope'], task['worker_envelope'])
        self.assertEqual(git(self.root / 'candidate', 'rev-parse', 'HEAD'), candidate)

    def test_committed_candidate_change_is_refused(self):
        self.step()
        self.step()
        candidate = self.root / 'candidate'
        (candidate / 'delivery.py').write_text('VALUE = "other"\n')
        git(candidate, 'add', 'delivery.py')
        git(candidate, 'commit', '-m', 'tamper')
        with self.assertRaisesRegex(ValueError, 'candidate'):
            self.step()

    def _replace_worker_candidate(self, mutate):
        self.step()
        candidate = self.root / 'candidate'
        mutate(candidate)
        git(candidate, 'add', '-A')
        git(candidate, 'commit', '--amend', '--no-edit')
        new_commit = git(candidate, 'rev-parse', 'HEAD')
        adapter = Demo(self.root, DemoOwner())
        try:
            adapter.store.setmeta('offline-worker-1', {'exit': 'committed', 'commit': new_commit})
        finally:
            adapter.close()

    def test_unverified_extra_candidate_file_is_refused(self):
        self._replace_worker_candidate(lambda candidate: (candidate / 'unverified.py').write_text('bad = True\n'))
        with self.assertRaisesRegex(ValueError, 'candidate'):
            self.step()

    def test_symlink_candidate_file_is_refused(self):
        def replace(candidate):
            target = self.root / 'outside.py'
            target.write_text('VALUE = "delivered"\n')
            (candidate / 'delivery.py').unlink()
            (candidate / 'delivery.py').symlink_to(target)
        self._replace_worker_candidate(replace)
        with self.assertRaisesRegex(ValueError, 'candidate'):
            self.step()

    def test_trusted_verifier_refuses_symlink_and_blob_mismatch(self):
        verifier = Path(__file__).resolve().parents[1] / 'repository_delivery_verifier.py'
        directory = self.root / 'external-check'
        directory.mkdir()
        (directory / 'delivery.py').write_text('VALUE = "delivered"\n')
        (directory / 'test_delivery.py').write_text(
            'import unittest\nfrom delivery import VALUE\nclass DeliveryTest(unittest.TestCase):\n'
            "    def test_value(self): self.assertEqual(VALUE, 'delivered')\n")
        hashes = [hashlib.sha256((directory / name).read_bytes()).hexdigest()
                  for name in ('delivery.py', 'test_delivery.py')]
        def run(values):
            return subprocess.run([sys.executable, '-I', str(verifier), str(directory), *values],
                                  env={}, capture_output=True).returncode
        self.assertEqual(run(hashes), 0)
        self.assertNotEqual(run(['0' * 64, hashes[1]]), 0)
        (directory / 'delivery.py').unlink()
        target = self.root / 'target.py'
        target.write_text('VALUE = "delivered"\n')
        (directory / 'delivery.py').symlink_to(target)
        self.assertNotEqual(run(hashes), 0)

    def test_process_death_after_candidate_commit_does_not_replay(self):
        script = """
import os, sys
sys.path.insert(0, sys.argv[2])
from repository_delivery_qualification import Demo, DemoOwner
adapter = Demo(sys.argv[1], DemoOwner())
original = adapter.store.setmeta
def stop_before_receipt(key, value):
    if key == 'offline-worker-1': os._exit(73)
    return original(key, value)
adapter.store.setmeta = stop_before_receipt
adapter.step()
"""
        result = subprocess.run([sys.executable, '-c', script, str(self.root),
                                 str(Path(__file__).resolve().parents[1])], capture_output=True)
        self.assertEqual(result.returncode, 73)
        committed = git(self.root / 'candidate', 'rev-parse', 'HEAD')
        successor = self.step()
        self.assertEqual(successor['state'], 'RUNNING')
        self.assertEqual(successor['worker_envelope']['attempt_id'], 'offline-worker-1')
        self.assertEqual(git(self.root / 'candidate', 'rev-parse', 'HEAD'), committed)

    def test_no_change_is_blocked(self):
        self.temp.cleanup()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'demo'
        initialize(self.root, no_change=True)
        self.step()
        self.assertEqual(self.step()['cause'], 'worker-failed')

    def test_modified_tests_are_rejected(self):
        self.step()
        self.step()
        path = self.root / 'candidate' / 'test_delivery.py'
        path.write_text('pass\n')
        with self.assertRaisesRegex(ValueError, 'candidate'):
            self.step()

    def test_changed_base_cannot_be_integrated(self):
        while self.step()['state'] != 'REVIEWED':
            pass
        repo = self.root / 'repo'
        (repo / 'new.txt').write_text('new base\n')
        git(repo, 'add', 'new.txt')
        git(repo, 'commit', '-m', 'new base')
        task = self.step()
        self.assertEqual(task['state'], 'VERIFYING')
        self.assertNotEqual(task['state'], 'MERGED')
        with self.assertRaisesRegex(ValueError, 'base changed'):
            self.step()


if __name__ == '__main__':
    unittest.main()
