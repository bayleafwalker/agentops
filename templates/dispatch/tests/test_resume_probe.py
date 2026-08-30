"""Tests for the `resume-and-settle` probe and the scenario it feeds.

These exercise the probe's judgement, not the served backend: every test builds the
two phase files by hand and runs `emit`, or calls a pure selector directly. Nothing here
touches the network, the repository database, or vuoro-shared.

What they defend is the property the adversarial review of 2026-08-30 found missing --
that a weaker recovery produces weaker FACTS, and therefore a worse score. A probe whose
output is identical whether it read a checkpoint field or grepped a blob cannot fail, and
a scenario whose gates cannot fail proves nothing.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[3]
SCRIPT = ROOT / "templates/dispatch/scripts/resume_probe.py"
SCENARIO = ROOT / "templates/dispatch/acceptance/resume-and-settle.scenario.json"

SHA_A = "3cf980d4a8834c64108c3ee06716560b19893ea7"


def _load_module():
    spec = importlib.util.spec_from_file_location("resume_probe", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


probe = _load_module()
SCENARIO_DOC = json.loads(SCENARIO.read_text())
CHECKS = {check["id"]: check for check in SCENARIO_DOC["checks"]}


def _observed(**overrides):
    base = {
        "session_id": "resume-probe-aaaabbbbcccc",
        "item_id": 2311,
        "repo_id": "agentops",
        "actor": "workstation-vuoro",
        "revision": SHA_A,
        "branch": "main",
        "effects": [
            {
                "operation": "work.reservation.reserve",
                "effect_id": "reservation-44",
                "receipt": "reservation#44",
            }
        ],
    }
    base.update(overrides)
    return base


def _recovered(*, found=None, citations=None, **overrides):
    base = {
        "repo_id": "agentops",
        "found": {
            "session_id": "resume-probe-aaaabbbbcccc",
            "item_id": 2311,
            "actor": "workstation-vuoro",
            "checkpoint": {"sha": SHA_A, "branch": "main"},
            "revision": SHA_A,
            "branch": "main",
            "revision_provenance": "handoff.last_checkpoint",
            "identity_basis": "sole-active-session",
            "identity_detail": {
                "active_claims": 1,
                "distinct_active_sessions": ["resume-probe-aaaabbbbcccc"],
            },
        },
        "citations": {
            "session-identity: recovered": "work.read.reservations",
            "work-authority: recovered": "work.read.reservations",
            "checkpoint: recovered": "work.read.handoff",
            "exact-revision: recovered": "work.read.handoff",
        },
        "steps": [
            {
                "label": "handoff",
                "operation": "work.read.handoff",
                "argv": ["handoff", "--format", "json", "--output", "-"],
                "exit_code": 0,
                "ms": 100.0,
                "available": True,
                "error": None,
            }
        ],
        "latency_ms": 100.0,
        "workdir_was_a_git_repo": False,
        "local_db_bytes": 0,
        "env_var_names": ["HOME", "PATH", "SPRINTCTL_BACKEND"],
        "env_leak": [],
        "parent_env_vars_not_carried": ["AUDITCTL_DB", "DIRENV_DIR"],
        "arrange_state_visible": [],
        "profile_staged_outside_repository": True,
    }
    if found:
        base["found"].update(found)
    if citations is not None:
        base["citations"] = citations
    base.update(overrides)
    return base


def _emit(observed, recovered):
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        obs = tmp_path / "observed.json"
        rec = tmp_path / "recovered.json"
        out = tmp_path / "candidate.json"
        obs.write_text(json.dumps(observed))
        rec.write_text(json.dumps(recovered))

        class Args:
            pass

        args = Args()
        args.observed = str(obs)
        args.recovered = str(rec)
        args.out = str(out)
        assert probe.cmd_emit(args) == 0
        return json.loads(out.read_text())


def _covered(candidate, check_id):
    """Score a required_fact_coverage / forbidden_fact_absence gate the cheap way."""
    facts = {" ".join(f.lower().split()) for f in candidate["facts"]}
    required = CHECKS[check_id]["params"]["facts"]
    return {fact for fact in required if " ".join(fact.lower().split()) in facts}


def _citation_ids(candidate):
    return {citation["id"] for citation in candidate["citations"]}


class RevisionProvenanceTests(unittest.TestCase):
    """Defect 1: a scraped sha must not be indistinguishable from a checkpoint read."""

    def test_checkpoint_read_passes_revision_is_exact(self) -> None:
        candidate = _emit(_observed(), _recovered())
        self.assertEqual(
            _covered(candidate, "revision-is-exact"),
            set(CHECKS["revision-is-exact"]["params"]["facts"]),
        )
        self.assertEqual(_covered(candidate, "revision-was-not-scraped"), set())
        self.assertEqual(
            _covered(candidate, "revision-provenance-is-declared"),
            {"exact-revision: provenance is handoff.last_checkpoint"},
        )

    def test_scraped_sha_that_matches_does_not_pass_revision_is_exact(self) -> None:
        recovered = _recovered(
            found={"revision_provenance": "scraped-from-bundle-text", "checkpoint": None},
            citations={
                "session-identity: recovered": "work.read.reservations",
                "work-authority: recovered": "work.read.reservations",
                "exact-revision: scraped from the handoff bundle text": "work.read.handoff",
            },
        )
        candidate = _emit(_observed(), recovered)
        # The value is right and the provenance is wrong: the gate must notice.
        self.assertEqual(candidate["metadata"]["recovered_revision"], SHA_A)
        self.assertNotIn("exact-revision: recovered", candidate["facts"])
        self.assertNotEqual(
            _covered(candidate, "revision-is-exact"),
            set(CHECKS["revision-is-exact"]["params"]["facts"]),
        )
        # ... and the scrape is named, not silent, so a reader can see why it failed.
        self.assertTrue(_covered(candidate, "revision-was-not-scraped"))
        self.assertEqual(_covered(candidate, "revision-provenance-is-declared"), set())
        self.assertEqual(
            candidate["metadata"]["recovered_revision_provenance"],
            "scraped-from-bundle-text",
        )

    def test_answer_counts_only_the_four_canonical_elements(self) -> None:
        recovered = _recovered(
            citations={
                "session-identity: recovered": "work.read.reservations",
                "exact-revision: scraped from the handoff bundle text": "work.read.handoff",
            }
        )
        candidate = _emit(_observed(), recovered)
        self.assertTrue(candidate["answer"].startswith("Recovered 1 of 4"))


class CitationHonestyTests(unittest.TestCase):
    """Defect 2: the comparison facts must cite what they are actually derived from."""

    def test_comparisons_cite_the_join_not_the_served_surface(self) -> None:
        candidate = _emit(_observed(), _recovered())
        by_id = {c["id"]: c["supports"] for c in candidate["citations"]}
        self.assertIn("join:arrange-observation", by_id)
        self.assertIn(
            "session-identity: matches the session interrupted",
            by_id["join:arrange-observation"],
        )
        self.assertNotIn(
            "session-identity: matches the session interrupted",
            by_id.get("work.read.reservations", []),
        )
        # The join is a comparison, not an authority the recovery leaned on.
        forbidden = set(CHECKS["no-local-state-as-authority"]["params"]["evidence_ids"])
        self.assertFalse(forbidden & _citation_ids(candidate))

    def test_reachable_arrange_state_is_emitted_as_a_forbidden_authority(self) -> None:
        recovered = _recovered(arrange_state_visible=["file:observed.json"])
        candidate = _emit(_observed(), recovered)
        self.assertIn("local:arrange-phase-memory", _citation_ids(candidate))
        self.assertIn(
            "local:arrange-phase-memory",
            CHECKS["no-local-state-as-authority"]["params"]["evidence_ids"],
        )

    def test_environment_leak_is_emitted_as_a_forbidden_authority(self) -> None:
        recovered = _recovered(env_leak=["DIRENV_DIR", "SPRINTCTL_URL"])
        candidate = _emit(_observed(), recovered)
        self.assertIn("local:direnv-environment", _citation_ids(candidate))
        self.assertIn(
            "local:direnv-environment",
            CHECKS["no-local-state-as-authority"]["params"]["evidence_ids"],
        )


class RecoverEnvironmentTests(unittest.TestCase):
    """Defect 3: the recover phase constructs its environment; it does not inherit one."""

    def test_recover_env_carries_only_the_declared_names(self) -> None:
        env = probe._recover_env(db=Path("/tmp/empty.db"), profile=Path("/tmp/profile.json"))
        allowed = set(probe.RECOVER_ENV_INHERITED) | set(probe.RECOVER_ENV_CONSTRUCTED)
        self.assertFalse(set(env) - allowed)
        self.assertEqual(env["SPRINTCTL_BACKEND"], "served")
        self.assertEqual(env["SPRINTCTL_VUORO_PROFILE"], "/tmp/profile.json")
        self.assertNotIn("SPRINTCTL_URL", env)

    def test_recover_env_drops_a_direnv_style_export(self) -> None:
        import os

        marker = "RESUME_PROBE_DIRENV_CANARY"
        os.environ[marker] = "1"
        try:
            env = probe._recover_env(db=Path("/tmp/e.db"), profile=Path("/tmp/p.json"))
            self.assertNotIn(marker, env)
            # And the measurement agrees: the child really does not see it.
            with tempfile.TemporaryDirectory() as tmp:
                self.assertEqual(probe._measure_env_leak(env, cwd=Path(tmp)), [])
        finally:
            os.environ.pop(marker, None)

    def test_arrange_state_measurement_notices_a_leak(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            self.assertEqual(
                probe._measure_arrange_state_visible({"PATH": "/usr/bin"}, cwd=workdir), []
            )
            (workdir / "observed.json").write_text("{}")
            self.assertIn(
                "file:observed.json",
                probe._measure_arrange_state_visible({"PATH": "/usr/bin"}, cwd=workdir),
            )
            self.assertIn(
                "env:RESUME_PROBE_OBSERVED",
                probe._measure_arrange_state_visible(
                    {"RESUME_PROBE_OBSERVED": "/x/observed.json"}, cwd=Path(tmp)
                ),
            )


class SessionIdentityTests(unittest.TestCase):
    """Defect 4: identity must be identified, or refused -- never guessed."""

    @staticmethod
    def _claim(session_id, created_at, item_id=2311, state="active"):
        return {
            "session_id": session_id,
            "created_at": created_at,
            "state": state,
            "work_item_id": item_id,
            "actor": "workstation-vuoro",
        }

    def test_sole_active_session_identifies_itself(self) -> None:
        claim, basis, detail = probe._select_claim(
            [self._claim("s-1", "2026-08-30T10:00:00Z")], resume_session_id=None
        )
        self.assertEqual(basis, "sole-active-session")
        self.assertEqual(claim["session_id"], "s-1")
        self.assertEqual(detail["active_claims"], 1)

    def test_two_concurrent_sessions_are_refused_rather_than_guessed(self) -> None:
        reservations = [
            self._claim("s-old", "2026-08-30T09:00:00Z", item_id=1),
            self._claim("s-new", "2026-08-30T10:00:00Z", item_id=2),
        ]
        claim, basis, detail = probe._select_claim(reservations, resume_session_id=None)
        self.assertIsNone(claim)
        self.assertEqual(basis, "ambiguous-concurrent-sessions")
        self.assertEqual(detail["distinct_active_sessions"], ["s-new", "s-old"])

    def test_a_named_resume_session_wins_over_recency(self) -> None:
        reservations = [
            self._claim("s-old", "2026-08-30T09:00:00Z", item_id=1),
            self._claim("s-new", "2026-08-30T10:00:00Z", item_id=2),
        ]
        claim, basis, _ = probe._select_claim(reservations, resume_session_id="s-old")
        self.assertEqual(basis, "named-by-session.resume")
        self.assertEqual(claim["work_item_id"], 1)

    def test_resume_payload_session_id_is_read_where_it_lives(self) -> None:
        self.assertEqual(probe._session_id_from_resume({"session_id": "s-1"}), "s-1")
        self.assertEqual(probe._session_id_from_resume({"session": {"id": "s-2"}}), "s-2")
        self.assertIsNone(probe._session_id_from_resume({"session": {}}))
        self.assertIsNone(probe._session_id_from_resume(None))

    def test_ambiguity_fails_the_identity_gate_and_says_why(self) -> None:
        recovered = _recovered(
            found={
                "session_id": None,
                "item_id": None,
                "actor": None,
                "identity_basis": "ambiguous-concurrent-sessions",
                "identity_detail": {
                    "active_claims": 2,
                    "distinct_active_sessions": ["s-new", "s-old"],
                },
            },
            citations={
                "checkpoint: recovered": "work.read.handoff",
                "exact-revision: recovered": "work.read.handoff",
            },
        )
        candidate = _emit(_observed(), recovered)
        self.assertEqual(_covered(candidate, "session-identity-recovered"), set())
        self.assertTrue(
            any(
                fact.startswith("session-identity: not recovered")
                for fact in candidate["facts"]
            )
        )
        self.assertIn(
            "session-identity: established by ambiguous-concurrent-sessions",
            candidate["facts"],
        )


class ScenarioShapeTests(unittest.TestCase):
    def test_every_fact_a_gate_requires_is_a_fact_the_probe_can_emit(self) -> None:
        candidate = _emit(_observed(), _recovered())
        emitted = {" ".join(f.lower().split()) for f in candidate["facts"]}
        for check_id in (
            "session-identity-recovered",
            "work-authority-recovered",
            "checkpoint-recovered",
            "revision-is-exact",
            "revision-provenance-is-declared",
        ):
            for fact in CHECKS[check_id]["params"]["facts"]:
                self.assertIn(" ".join(fact.lower().split()), emitted, f"{check_id}: {fact}")

    def test_every_forbidden_authority_has_a_code_path_that_can_emit_it(self) -> None:
        """A forbidden id nothing can emit is decoration, not a control."""
        emittable = {
            "local:git-worktree": {"workdir_was_a_git_repo": True},
            "local:sprintctl-db": {"local_db_bytes": 4096},
            "local:arrange-phase-memory": {"arrange_state_visible": ["file:observed.json"]},
            "local:direnv-environment": {"env_leak": ["DIRENV_DIR"]},
        }
        for evidence_id in CHECKS["no-local-state-as-authority"]["params"]["evidence_ids"]:
            with self.subTest(evidence_id=evidence_id):
                if evidence_id not in emittable:
                    # Documented gap: these two have no measurement behind them yet.
                    self.assertIn(
                        evidence_id,
                        {"local:handoff-bundle-file", "local:session-transcript"},
                    )
                    continue
                candidate = _emit(_observed(), _recovered(**emittable[evidence_id]))
                self.assertIn(evidence_id, _citation_ids(candidate))

    def test_scenario_version_and_revision_note_moved_together(self) -> None:
        self.assertEqual(SCENARIO_DOC["version"], "1.0.2")
        self.assertIn("1.0.2", SCENARIO_DOC["metadata"]["revision_note"])

    def test_trajectory_tools_stay_inside_the_allowlist(self) -> None:
        allowed = set(CHECKS["served-surfaces-only"]["params"]["tools"])
        candidate = _emit(_observed(), _recovered())
        self.assertTrue({step["tool"] for step in candidate["trajectory"]} <= allowed)


if __name__ == "__main__":
    unittest.main()
