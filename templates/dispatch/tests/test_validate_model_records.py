"""Tests for the metanarrative model records.

The acceptance criteria these exist to hold:
* no active lifecycle uses `ratified`;
* no parallel practice ontology -- current practice is a projection;
* commitment and canonicality are dependency relations;
* human participation is never a workflow stage.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_model_records.py"
MODEL = ROOT / "model"

SPEC = importlib.util.spec_from_file_location("validate_model_records", SCRIPT)
assert SPEC and SPEC.loader
V = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(V)

AT = "2026-08-29T09:00:00+03:00"
PATH = Path("record.json")


def _claim(**over):
    claim = {
        "schema_version": "claim/v1",
        "id": "sprintctl-lifecycle-tenet",
        "kind": "tenet",
        "scope": "sprintctl",
        "statement": "sprint lifecycle aligns with market operators and intended user workflows",
        "state": "current",
        "established_by": {
            "actor": "planner",
            "actor_type": "agent",
            "at": AT,
            "authority_basis": "delegated",
        },
        "validity": {"effective_from": AT},
        "basis_for": ["sprintctl-design", "composition-v4"],
        "enforcement_mode": "review",
    }
    claim.update(over)
    return claim


def _session(**over):
    session = {
        "schema_version": "realignment-session/v1",
        "id": "rs-2026-08-29-01",
        "tenet": "sprintctl-lifecycle-tenet",
        "work_ref": "wi:2311",
        "alignment": "divergent",
        "state": "open",
        "resolution_options": ["realign-work", "supersede-tenet"],
    }
    session.update(over)
    return session


class ModelRecordTests(unittest.TestCase):
    def test_schemas_are_loadable_and_versioned(self) -> None:
        for name, version in (
            ("claim", "claim/v1"),
            ("observation", "observation/v1"),
            ("commitment", "commitment/v1"),
            ("realignment-session", "realignment-session/v1"),
        ):
            schema = json.loads((MODEL / f"{name}.schema.json").read_text())
            self.assertEqual(schema["properties"]["schema_version"]["const"], version)

    def test_no_schema_mentions_ratified_or_approval(self) -> None:
        for schema_file in sorted(MODEL.glob("*.schema.json")):
            text = schema_file.read_text().lower()
            with self.subTest(schema=schema_file.name):
                self.assertNotIn("ratified", text)
                self.assertNotIn('"approval"', text)

    def test_claim_lifecycle_has_no_ratified_state(self) -> None:
        self.assertEqual(V.STATES, {"draft", "current", "superseded"})
        with self.assertRaisesRegex(ValueError, "not a lifecycle state"):
            V.validate_claim(_claim(state="ratified"), PATH)

    def test_approval_vocabulary_is_rejected_not_aliased(self) -> None:
        # An alias would keep the idea alive in the data, which is the thing being
        # removed. Each of these must fail rather than be quietly accepted.
        for key in ("ratified", "ratification", "approved", "committed"):
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, "encodes approval as data"):
                    V.validate_claim(_claim(**{key: True}), PATH)

    def test_any_actor_type_may_establish_a_current_claim(self) -> None:
        for actor_type in sorted(V.ACTOR_TYPES):
            with self.subTest(actor_type=actor_type):
                claim = _claim()
                claim["established_by"]["actor_type"] = actor_type
                V.validate_claim(claim, PATH)

    def test_kind_state_provenance_and_validity_are_orthogonal(self) -> None:
        # Every combination of kind and actor_type is legal in the current state:
        # no kind implies an approver and no actor_type implies a state.
        for kind in sorted(V.CLAIM_KINDS):
            for actor_type in sorted(V.ACTOR_TYPES):
                with self.subTest(kind=kind, actor_type=actor_type):
                    claim = _claim(kind=kind)
                    claim["established_by"]["actor_type"] = actor_type
                    if kind != "tenet":
                        claim.pop("enforcement_mode")
                    V.validate_claim(claim, PATH)

    def test_draft_carries_no_provenance_or_validity(self) -> None:
        claim = _claim(state="draft")
        with self.assertRaisesRegex(ValueError, "not allowed while state is draft"):
            V.validate_claim(claim, PATH)

        for field in ("established_by", "validity"):
            claim.pop(field, None)
        V.validate_claim(claim, PATH)

    def test_superseded_requires_a_closed_interval(self) -> None:
        claim = _claim(state="superseded")
        with self.assertRaisesRegex(ValueError, "effective_to is required"):
            V.validate_claim(claim, PATH)
        claim["validity"]["effective_to"] = "2020-01-01T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "must not precede"):
            V.validate_claim(claim, PATH)

    def test_a_tenet_must_declare_how_it_is_enforced(self) -> None:
        # tenet (review) vs invariant (block) is the distinction; a tenet with no
        # enforcement_mode is indistinguishable from an invariant.
        claim = _claim()
        claim.pop("enforcement_mode")
        with self.assertRaisesRegex(ValueError, "enforcement_mode is required for a tenet"):
            V.validate_claim(claim, PATH)

    def test_canonicality_is_a_basis_relation(self) -> None:
        claim = _claim()
        self.assertEqual(claim["basis_for"], ["sprintctl-design", "composition-v4"])
        V.validate_claim(claim, PATH)

        # A claim with no dependents is still legal; canonicality is a relation that
        # may be absent, not a rank earned by dependent count.
        bare = _claim(id="unused-tenet")
        bare.pop("basis_for")
        V.validate_claim(bare, PATH)

    def test_commitment_is_a_relation_with_terms(self) -> None:
        commitment = {
            "schema_version": "commitment/v1",
            "provider": "session-note/v1",
            "consumer": "doc-refs",
            "effective_from": "2026-08-29",
            "compatibility": "backward-compatible",
            "supersedes": None,
        }
        V.validate_commitment(commitment, PATH)

        commitment["consumer"] = commitment["provider"]
        with self.assertRaisesRegex(ValueError, "must differ from provider"):
            V.validate_commitment(commitment, PATH)

    def test_current_practice_is_a_projection_not_an_object(self) -> None:
        old = _claim(id="hosting-github", kind="practice", statement="we host on GitHub")
        old["enforcement_mode"] = "review"
        new = _claim(
            id="hosting-forgejo",
            kind="practice",
            statement="we host on Forgejo",
            supersedes="hosting-github",
        )
        new["enforcement_mode"] = "review"

        self.assertEqual([c["id"] for c in V.current_claims([old])], ["hosting-github"])
        self.assertEqual([c["id"] for c in V.current_claims([old, new])], ["hosting-forgejo"])

    def test_a_claim_can_be_current_and_contradicted(self) -> None:
        # The stated example: "we host on GitHub" stays the declared practice while
        # observations show the Forgejo migration has begun. The discrepancy is
        # reconciliation work, not a reason to rewrite either side.
        claim = _claim(id="hosting-github", kind="practice", statement="we host on GitHub")
        observation = {
            "schema_version": "observation/v1",
            "id": "obs-forgejo-remotes",
            "subject": "hosting-github",
            "stance": "contradicts",
            "observed_at": AT,
            "evidence_ref": "sha:deadbeef",
        }
        V.validate_claim(claim, PATH)
        V.validate_observation(observation, PATH)

        self.assertEqual(claim["state"], "current")
        self.assertEqual(V.observational_status("hosting-github", [observation]), "contradicted")

    def test_only_divergence_opens_a_session(self) -> None:
        for alignment in sorted(V.ALIGNMENTS - {"divergent"}):
            with self.subTest(alignment=alignment):
                with self.assertRaisesRegex(ValueError, "must be divergent"):
                    V.validate_session(_session(alignment=alignment), PATH)
        V.validate_session(_session(), PATH)

    def test_a_session_offers_exactly_two_substantive_resolutions(self) -> None:
        with self.assertRaisesRegex(ValueError, "must offer exactly"):
            V.validate_session(_session(resolution_options=["realign-work", "escalate"]), PATH)

    def test_attention_is_routing_and_leaves_the_session_open(self) -> None:
        session = _session(
            attention_request={
                "reason": "unresolved-value-choice",
                "raised_at": AT,
                "detail": "the tenet and the work encode different product positions",
            }
        )
        V.validate_session(session, PATH)
        self.assertEqual(session["state"], "open")

        session["resolution"] = "realign-work"
        with self.assertRaisesRegex(ValueError, "not allowed while state is open"):
            V.validate_session(session, PATH)

        resolved = _session(state="resolved", resolution="supersede-tenet")
        V.validate_session(resolved, PATH)
        resolved["attention_request"] = {"reason": "owner-reserved-change", "raised_at": AT}
        with self.assertRaisesRegex(ValueError, "attention is routing, not an outcome"):
            V.validate_session(resolved, PATH)

    def test_attention_reasons_are_the_four_grounds_only(self) -> None:
        # "a human should look at this" is not a ground.
        self.assertEqual(
            V.ATTENTION_REASONS,
            {
                "missing-delegated-authority",
                "unresolved-value-choice",
                "owner-reserved-change",
                "conflict-without-precedence",
            },
        )
        with self.assertRaisesRegex(ValueError, "reason must be one of"):
            V.validate_session(
                _session(attention_request={"reason": "needs-human", "raised_at": AT}), PATH
            )

    def test_validate_record_dispatches_on_version(self) -> None:
        self.assertEqual(V.validate_record(_claim(), PATH), "claim/v1")
        self.assertEqual(V.validate_record(_session(), PATH), "realignment-session/v1")
        with self.assertRaisesRegex(ValueError, "schema_version must be one of"):
            V.validate_record({"schema_version": "practice/v1"}, PATH)


if __name__ == "__main__":
    unittest.main()
