import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.harness_evidence import store


class PrivateEvidenceStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "store"
        self.source = self.base / "synthetic"
        self.source.write_bytes(b"synthetic opt-in evidence")
        self.source.chmod(0o600)

    def capture(self, **kwargs):
        return store.capture(self.root, self.source, "synthetic-session", opt_in=True, **kwargs)

    def test_capture_requires_opt_in_and_does_not_create_store(self):
        with self.assertRaises(ValueError):
            store.capture(self.root, self.source, "session")
        self.assertFalse(self.root.exists())

    def test_digest_retrieval_exact_bytes_and_private_modes(self):
        record = self.capture()
        self.assertEqual(store.retrieve(self.root, record["evidence_uri"], record["transcript_sha256"]), self.source.read_bytes())
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o700)
        entry = self.root / record["object_id"]
        self.assertEqual(entry.stat().st_mode & 0o777, 0o700)
        for file in entry.iterdir():
            self.assertEqual(file.stat().st_mode & 0o777, 0o600)

    def test_tampered_payload_or_caller_digest_fails_verification(self):
        record = self.capture()
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            store.retrieve(self.root, record["evidence_uri"], "0" * 64)
        (self.root / record["object_id"] / "payload").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            store.retrieve(self.root, record["evidence_uri"], record["transcript_sha256"])

    def test_expiry_uses_recorded_creation_and_preserves_unrelated_files(self):
        record = self.capture()
        other = self.root / "unrelated.txt"
        other.write_text("untouched")
        before = datetime.fromisoformat(record["created_at"]) + timedelta(days=29)
        self.assertEqual(store.cleanup(self.root, now=before), {"deleted": 0, "retained": 1, "refused": 1})
        after = before + timedelta(days=1)
        self.assertEqual(store.cleanup(self.root, now=after)["deleted"], 1)
        self.assertEqual(other.read_text(), "untouched")
        with self.assertRaises(FileNotFoundError):
            store.retrieve(self.root, record["evidence_uri"], record["transcript_sha256"])

    def test_same_content_sessions_keep_independent_retention(self):
        short = self.capture(retention_days=1)
        long = self.capture(retention_days=60)
        self.assertNotEqual(short["object_id"], long["object_id"])
        when = datetime.now(timezone.utc) + timedelta(days=31)
        self.assertEqual(store.cleanup(self.root, now=when), {"deleted": 1, "retained": 1, "refused": 0})
        self.assertTrue(store.retrieve(self.root, long["evidence_uri"], long["transcript_sha256"]))

    def test_indefinite_requires_per_object_choice_and_explicit_delete_works(self):
        with self.assertRaises(ValueError):
            self.capture(retention_days=None)
        record = self.capture(retention_days=None, keep_indefinitely=True)
        self.assertEqual(store.cleanup(self.root, now=datetime.now(timezone.utc) + timedelta(days=4000))["retained"], 1)
        self.assertEqual(store.cleanup(self.root, object_id=record["object_id"])["deleted"], 1)
        with self.assertRaises(FileNotFoundError):
            store.retrieve(self.root, record["evidence_uri"], record["transcript_sha256"])

    def test_forged_indefinite_record_is_preserved_and_reported(self):
        record = self.capture()
        file = self.root / record["object_id"] / "record.json"
        value = json.loads(file.read_text())
        value["retention_days"] = None
        file.write_text(json.dumps(value))
        self.assertEqual(store.cleanup(self.root)["refused"], 1)

    def test_source_symlink_and_public_permissions_are_refused(self):
        link = self.base / "link"
        link.symlink_to(self.source)
        with self.assertRaises(OSError):
            store.capture(self.root, link, "session", opt_in=True)
        self.source.chmod(0o644)
        with self.assertRaises(ValueError):
            self.capture()

    def test_symlinked_root_and_object_cannot_escape(self):
        outside = self.base / "outside"
        outside.mkdir(mode=0o700)
        self.root.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            self.capture()
        self.root.unlink()
        record = self.capture()
        entry = self.root / record["object_id"]
        for file in entry.iterdir():
            file.unlink()
        entry.rmdir()
        entry.symlink_to(outside, target_is_directory=True)
        self.assertEqual(store.cleanup(self.root)["refused"], 1)
        self.assertTrue(outside.is_dir())

    def test_unknown_entry_files_and_hardlinks_are_never_swept(self):
        record = self.capture()
        entry = self.root / record["object_id"]
        (entry / "unknown").write_text("untouched")
        self.assertEqual(store.cleanup(self.root, object_id=record["object_id"])["refused"], 1)
        (entry / "unknown").unlink()
        (self.base / "hardlink").hardlink_to(entry / "payload")
        self.assertEqual(store.cleanup(self.root, object_id=record["object_id"])["refused"], 1)

    def test_foreign_locator_and_invalid_object_id_are_refused(self):
        record = self.capture()
        for locator in (self.source.as_uri(), record["evidence_uri"] + "?credential=x", "https://example.invalid/evidence"):
            with self.assertRaises(ValueError):
                store.retrieve(self.root, locator, record["transcript_sha256"])
        with self.assertRaises(ValueError):
            store.cleanup(self.root, object_id="../../outside")

    def test_size_limit_and_missing_store_do_not_capture(self):
        self.assertEqual(store.cleanup(self.root), {"deleted": 0, "retained": 0, "refused": 0})
        self.assertFalse(self.root.exists())
        with patch.object(store, "MAX_BYTES", 1), self.assertRaises(ValueError):
            self.capture()
        self.assertFalse(self.root.exists())


if __name__ == "__main__":
    unittest.main()
