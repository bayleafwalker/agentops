"""The session-scoped half of the resolved-context invariant, and what it refuses.

`docs/contracts/session-resolved-context.md` splits the invariant by lifetime and
names `AuditContext` as the *write-scoped* instance, explicitly not evidence that the
session-scoped half works. That half had a name and no producer;
`scripts/session_binding.py` is it, and these tests hold it to the three obligations
the contract states for both scopes: atomic, fail-closed on contradiction, attributed.

Two things this file is careful about, both learned on 2026-08-30.

**It is not the capsule.** Two handovers recorded `session-capsule.schema.json` as this
producer's schema. It is not: the capsule is end-of-session exhaust answering "what did
this session do", and a binding is written at the start and answers "what is this
session, and what entitled it". Producing capsules would have satisfied the plan while
leaving the entitlement question exactly as open as it was.

**Fail-closed rules get routed around when they cry wolf.** The contract lists that as
a falsifier in its own words. The first version of this producer put the entry
`source` inside `harness`, so every resume read as a contradiction — a rule that fires
on the normal case teaches its callers to disable it. The split between immutable and
per-entry fields is therefore asserted here in both directions.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[3]
SCRIPT = ROOT / "templates/dispatch/scripts/session_binding.py"
SCHEMA = ROOT / "templates/dispatch/session-mechanization/session-binding.schema.json"
RECORDS = ROOT / "templates/dispatch/environment-record"

sys.path.insert(0, str(ROOT / "templates/dispatch/scripts"))
import schema_check  # noqa: E402


def _run(event: dict, bindings: Path, *, hostname: str = "WorkstationLinux"):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--bindings-dir", str(bindings),
         "--records-dir", str(RECORDS), "--hostname", hostname, "--no-publish"],
        input=json.dumps(event), text=True, capture_output=True,
    )


class SessionBindingV0(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.bindings = self.tmp / "session-bindings"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _binding(self, session_id: str) -> dict:
        return json.loads((self.bindings / f"{session_id}.json").read_text())

    # -- attributed -------------------------------------------------------------

    def test_binding_names_environment_project_and_every_settings_layer(self):
        result = _run({"session_id": "s1", "cwd": str(ROOT), "source": "startup"},
                      self.bindings)
        self.assertEqual(result.returncode, 0, result.stderr)
        binding = self._binding("s1")

        self.assertEqual(binding["schema_version"], "session-binding/v0")
        self.assertEqual(binding["environment"]["resolution_source"], "hostname-match")
        self.assertEqual(binding["environment"]["record"]["id"], "workstation-linux")
        self.assertEqual(binding["workspace"]["project"]["resolution_source"],
                         "ancestor-walk")
        self.assertEqual(binding["workspace"]["project"]["project_id"],
                         "981b2073-d7af-4c28-bff3-3cf807495fba")

        scopes = [s["scope"] for s in binding["entitlement"]["settings_sources"]]
        self.assertEqual(scopes, ["managed", "user", "project", "local"])
        for source in binding["entitlement"]["settings_sources"]:
            # An absent layer is part of the answer, and a present one is pinned by
            # content: that pairing is what makes "who set this" answerable later.
            self.assertEqual(source["present"], source["sha256"] is not None, source)

    def test_instance_satisfies_the_schema(self):
        _run({"session_id": "s2", "cwd": str(ROOT), "source": "startup"}, self.bindings)
        schema = json.loads(SCHEMA.read_text())
        self.assertEqual(schema_check.audit_schema(schema), [])
        self.assertEqual(schema_check.validate(self._binding("s2"), schema), [])

    def test_an_unresolvable_environment_says_so_rather_than_guessing(self):
        result = _run({"session_id": "s3", "cwd": str(ROOT), "source": "startup"},
                      self.bindings, hostname="NoSuchHost")
        self.assertEqual(result.returncode, 0, result.stderr)
        environment = self._binding("s3")["environment"]
        self.assertIsNone(environment["record"])
        self.assertEqual(environment["resolution_source"], "unresolved")
        # The normalizer's own answer, not a re-derivation of it: `NoSuchHost` is a
        # PascalCase hostname exactly like this host's real one.
        self.assertIn("no-such-host", environment["detail"])

    def test_a_workspace_with_no_project_toml_is_undeclared_not_invented(self):
        elsewhere = self.tmp / "unbound"
        elsewhere.mkdir()
        _run({"session_id": "s4", "cwd": str(elsewhere), "source": "startup"},
             self.bindings)
        project = self._binding("s4")["workspace"]["project"]
        self.assertIsNone(project["project_id"])
        self.assertEqual(project["resolution_source"], "undeclared")

    # -- immutable, and only where immutability is true -------------------------

    def test_a_resume_into_the_same_session_is_a_no_op(self):
        _run({"session_id": "s5", "cwd": str(ROOT), "source": "startup"}, self.bindings)
        first = self._binding("s5")
        result = _run({"session_id": "s5", "cwd": str(ROOT), "source": "resume"},
                      self.bindings)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self._binding("s5"), first,
                         "a resume must not rewrite the binding it re-enters")

    def test_re_entry_from_a_different_workspace_fails_closed_and_names_the_fields(self):
        _run({"session_id": "s6", "cwd": str(ROOT), "source": "startup"}, self.bindings)
        before = self._binding("s6")
        result = _run({"session_id": "s6", "cwd": str(ROOT.parent), "source": "resume"},
                      self.bindings)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("workspace", result.stderr)
        self.assertIn("contradiction", result.stderr)
        self.assertEqual(self._binding("s6"), before,
                         "a contradiction must not overwrite the binding on record")

    def test_a_changed_settings_layer_is_a_contradiction(self):
        """The entitlement question, exercised: a shared-scope edit is visible."""
        workspace = self.tmp / "ws"
        (workspace / ".claude").mkdir(parents=True)
        settings = workspace / ".claude" / "settings.json"
        settings.write_text('{"hooks": {}}\n')
        _run({"session_id": "s7", "cwd": str(workspace), "source": "startup"},
             self.bindings)
        settings.write_text('{"hooks": {"Stop": []}}\n')
        result = _run({"session_id": "s7", "cwd": str(workspace), "source": "resume"},
                      self.bindings)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("entitlement", result.stderr)

    # -- a hook must never cost the session its start ---------------------------

    def test_unusable_input_is_reported_and_does_not_fail_the_session(self):
        for payload in ("not json", json.dumps({"cwd": str(ROOT)})):
            with self.subTest(payload=payload[:20]):
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), "--bindings-dir", str(self.bindings),
                     "--records-dir", str(RECORDS), "--no-publish"],
                    input=payload, text=True, capture_output=True,
                )
                self.assertEqual(result.returncode, 0)
                self.assertTrue(result.stderr.strip(), "silence is the defect")


if __name__ == "__main__":
    unittest.main()
