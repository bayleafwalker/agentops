"""Coordinator-authored oracle for ``release_unit_packet.py`` -- L-5.

The pathway (`vuoro/docs/plans/2026-08-23-requirements-pathway-v5-v7.md` §4)
splits every release into sub-releases -- v5.0 implementation, v5.1 the big
drop, v5.2 `vuoro-shared`, v5.3 client update, ... v5.9 the refactor pass --
and each one is *one orchestrator hand-off unit with its own gate set (§5)*.

The dumb orchestrator must not have to reconstruct that gate set per
sub-release. L-5 is the template: one function that pre-fills the parts that
are identical for every sub-release, so the only thing an orchestrator supplies
is which release it is, which repo, which sprint item, what may be written and
why.

Three properties carry the row, and each has its own test below:

* the §5 gate set is present **in order**, six entries, 1..6. §5 is ordered on
  purpose -- a cold `prepare` run *after* the suite proves nothing, so a
  set-equality check would pass a shuffled gate set that has lost the point.
* the four encoded L-2 stop conditions are present, so the L-1 driver refuses
  the packet at the boundary instead of running a release unattended.
* ``release_boundary`` is ``True``. A release unit crosses a release boundary
  by definition; a release boundary is an owner touchpoint (C-2), and a
  release-unit packet that does not stop at its own boundary is the exact
  thing L-2 exists to prevent.

Written against the spec only. ``templates/dispatch/scripts/release_unit_packet.py``
does not exist yet, so this oracle fails at import -- that is the declared red.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

# Loading a module by path writes a .pyc beside it. This oracle is run under
# strace at freeze time, where a write into the repository is a finding.
sys.dont_write_bytecode = True

ROOT = Path(__file__).parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"
SCHEMA_PATH = ROOT / "templates/dispatch/hybrid/task-packet.schema.json"


def _load_module(name: str, path: Path):
    if not path.exists():
        raise ModuleNotFoundError(f"no module to grade: {path} does not exist")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


packet_mod = _load_module("release_unit_packet_subject", SCRIPTS / "release_unit_packet.py")


#: The pathway §5 gate set, in §5's order. These identifiers ARE the contract:
#: the module emits exactly these strings under the ``gate`` key of each entry,
#: and each entry carries an ``order`` of 1..6 matching this sequence.
#:
#:  1. hybrid_dispatch.py prepare, cold, from a disposable worktree at the pinned commit
#:  2. repo suite incl. test_falsifier_coverage.py (claim->falsifier->docstring triangle)
#:  3. run_round_checks.py / per-repo equivalent, plus the untracked-file guard
#:  4. release contract digest validation; wheel or chart digest fetched, never trusted
#:  5. hybrid_dispatch.py gate -> receipt
#:  6. PR opened with the receipt attached, then stop (merge is the owner's)
EXPECTED_GATES: tuple[str, ...] = (
    "prepare_cold_worktree_at_pinned_commit",
    "repo_suite_with_falsifier_coverage",
    "round_checks_and_untracked_file_guard",
    "release_contract_digest_validation",
    "hybrid_dispatch_gate_then_receipt",
    "pr_opened_with_receipt_then_stop",
)

#: The four encoded L-2 stop conditions (pathway §5, telemetry plan row L-2).
EXPECTED_STOP_CONDITIONS: frozenset[str] = frozenset({
    "gate_red_twice_on_same_packet",
    "release_boundary_crossing",
    "command_outside_allowed_command_ids",
    "path_outside_writable_patch_paths",
})

#: JSON Schema type name -> the Python types that satisfy it. Used to check the
#: schema's *required* top-level keys without needing ``jsonschema`` installed.
#: ``bool`` is excluded from the numeric types deliberately.
_JSON_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "object": (dict,),
    "array": (list,),
    "boolean": (bool,),
    "integer": (int,),
    "number": (int, float),
    "null": (type(None),),
}

SPRINT_ITEM = {
    "ref": "agentops#2254",
    "claim_id": 24,
    "claim_actor": "workstation-vuoro",
}
WRITABLE = ["templates/dispatch/scripts/**", "templates/dispatch/tests/**"]
PURPOSE = "Run the v5.2 vuoro-shared migration exercise as one hand-off unit."


def _build(release: str = "v5.2", **overrides) -> dict:
    """Call the subject with the standard fixture, deep-copied per call."""
    kwargs = {
        "release": release,
        "repo_id": "agentops",
        "sprint_item": copy.deepcopy(SPRINT_ITEM),
        "writable_patch_paths": copy.deepcopy(WRITABLE),
        "purpose": PURPOSE,
    }
    kwargs.update(overrides)
    return packet_mod.release_unit_packet(**kwargs)


def _load_schema() -> dict:
    """Read the packet schema, or fail loudly. Never skip.

    The whole value of the row is that the generated packet is a *valid*
    packet; a silently skipped schema check would let the row be reported
    green with nothing behind it.
    """
    if not SCHEMA_PATH.exists():
        raise AssertionError(f"packet schema not readable: {SCHEMA_PATH} does not exist")
    try:
        return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:  # pragma: no cover - failure path
        raise AssertionError(f"packet schema not readable: {SCHEMA_PATH}: {exc}") from exc


class ReleaseBoundaryTests(unittest.TestCase):
    """The one flag that keeps a release unit from running unattended."""

    def test_a_release_unit_packet_is_marked_release_boundary(self):
        pkt = _build()
        self.assertIn(
            "release_boundary", pkt,
            "a release-unit packet carries no release_boundary flag, so the "
            "L-1 driver would run a whole sub-release unattended",
        )
        self.assertIs(
            pkt["release_boundary"], True,
            "release_boundary is not True -- a release unit crosses a release "
            "boundary by definition and L-2 must stop on it",
        )

    def test_every_release_is_marked_release_boundary(self):
        for release in ("v5.0", "v5.1", "v5.2", "v5.9", "v6.0", "v7.3"):
            with self.subTest(release=release):
                self.assertIs(_build(release)["release_boundary"], True)


class GateSetTests(unittest.TestCase):
    """Pathway §5, in order, six entries, no gap and no duplicate."""

    def test_the_gate_set_has_exactly_six_entries(self):
        gates = _build()["gate_set"]
        self.assertIsInstance(gates, list, "gate_set is not a list")
        self.assertEqual(
            len(gates), 6,
            f"gate_set has {len(gates)} entries, pathway §5 names six",
        )

    def test_each_entry_carries_an_order_and_a_gate(self):
        for entry in _build()["gate_set"]:
            with self.subTest(entry=entry):
                self.assertIsInstance(entry, dict, "a gate entry is not a dict")
                self.assertIn("order", entry, "a gate entry has no order")
                self.assertIn("gate", entry, "a gate entry has no gate identifier")
                self.assertIsInstance(entry["order"], int)
                self.assertNotIsInstance(entry["order"], bool)
                self.assertIsInstance(entry["gate"], str)
                self.assertTrue(entry["gate"].strip(), "a gate identifier is empty")

    def test_the_orders_are_one_through_six_with_no_gap_or_duplicate(self):
        orders = [entry["order"] for entry in _build()["gate_set"]]
        self.assertEqual(
            sorted(orders), [1, 2, 3, 4, 5, 6],
            f"gate orders are {orders}, not a gapless 1..6 without duplicates",
        )

    def test_the_gates_appear_in_pathway_order(self):
        # Deliberately an ordered comparison. §5 is ordered on purpose: a cold
        # prepare run after the suite proves nothing, and the PR-and-stop gate
        # is last because merge is the owner's. Set equality would pass a
        # shuffled gate set that has lost exactly that.
        gates = _build()["gate_set"]
        self.assertEqual(
            [entry["gate"] for entry in gates], list(EXPECTED_GATES),
            "the gate set is not the pathway §5 list in §5's order",
        )

    def test_the_order_field_agrees_with_the_list_position(self):
        # A generator could emit the right sequence with scrambled order
        # numbers, or the right numbers in scrambled sequence. Both are wrong:
        # the orchestrator reads one of the two and must not get a different
        # answer depending on which.
        gates = _build()["gate_set"]
        for position, entry in enumerate(gates, start=1):
            with self.subTest(position=position):
                self.assertEqual(
                    entry["order"], position,
                    f"gate {entry.get('gate')!r} sits at position {position} "
                    f"but declares order {entry.get('order')!r}",
                )

    def test_sorting_by_order_reproduces_the_pathway_sequence(self):
        gates = sorted(_build()["gate_set"], key=lambda e: e["order"])
        self.assertEqual([entry["gate"] for entry in gates], list(EXPECTED_GATES))

    def test_no_gate_identifier_is_repeated(self):
        names = [entry["gate"] for entry in _build()["gate_set"]]
        self.assertEqual(
            len(set(names)), 6,
            f"a gate identifier is repeated: {names}",
        )


class StopConditionTests(unittest.TestCase):
    """The four encoded L-2 conditions ride on every release-unit packet."""

    def test_all_four_stop_conditions_are_present(self):
        stops = _build()["stop_conditions"]
        self.assertIsInstance(stops, list, "stop_conditions is not a list")
        self.assertEqual(
            set(stops), set(EXPECTED_STOP_CONDITIONS),
            "stop_conditions is not the four encoded L-2 conditions",
        )

    def test_no_stop_condition_is_repeated(self):
        stops = _build()["stop_conditions"]
        self.assertEqual(len(stops), len(set(stops)), f"duplicate stop condition: {stops}")
        self.assertEqual(len(stops), 4)

    def test_the_release_boundary_condition_is_among_them(self):
        # Redundant with the set check by construction, and kept anyway: this
        # is the condition that pairs with release_boundary=True, and a future
        # edit that drops it should fail under a name that says why.
        self.assertIn(
            "release_boundary_crossing", _build()["stop_conditions"],
            "the release-boundary stop condition is missing from a packet "
            "that is itself marked release_boundary",
        )


class CallerInputTests(unittest.TestCase):
    """What the orchestrator supplies arrives unchanged."""

    def test_the_task_id_is_derived_from_the_release(self):
        for release in ("v5.0", "v5.2", "v5.9", "v6.1"):
            with self.subTest(release=release):
                self.assertEqual(
                    _build(release)["task_id"], f"{release}-release-unit",
                    "task_id is not <release>-release-unit",
                )

    def test_the_schema_version_is_v2(self):
        self.assertEqual(_build()["schema_version"], "agentops-task/v2")

    def test_caller_fields_are_carried_through_unchanged(self):
        pkt = _build()
        self.assertEqual(pkt["repo_id"], "agentops")
        self.assertEqual(pkt["sprint_item"], SPRINT_ITEM)
        self.assertEqual(pkt["writable_patch_paths"], WRITABLE)
        self.assertEqual(pkt["purpose"], PURPOSE)

    def test_the_callers_arguments_are_not_mutated(self):
        sprint_item = copy.deepcopy(SPRINT_ITEM)
        writable = copy.deepcopy(WRITABLE)
        packet_mod.release_unit_packet(
            release="v5.2",
            repo_id="agentops",
            sprint_item=sprint_item,
            writable_patch_paths=writable,
            purpose=PURPOSE,
        )
        self.assertEqual(sprint_item, SPRINT_ITEM, "the caller's sprint_item was mutated")
        self.assertEqual(writable, WRITABLE, "the caller's writable_patch_paths was mutated")

    def test_the_packet_does_not_alias_the_callers_containers(self):
        # The coordinator hands the same list to several calls; if the packet
        # keeps a reference, a later edit of that list silently rewrites a
        # packet that has already been frozen.
        writable = copy.deepcopy(WRITABLE)
        sprint_item = copy.deepcopy(SPRINT_ITEM)
        pkt = packet_mod.release_unit_packet(
            release="v5.2",
            repo_id="agentops",
            sprint_item=sprint_item,
            writable_patch_paths=writable,
            purpose=PURPOSE,
        )
        writable.append("etc/**")
        sprint_item["claim_id"] = 999
        self.assertEqual(
            pkt["writable_patch_paths"], WRITABLE,
            "the packet aliases the caller's writable_patch_paths list",
        )
        self.assertEqual(
            pkt["sprint_item"], SPRINT_ITEM,
            "the packet aliases the caller's sprint_item dict",
        )


class PrefilledAcrossReleasesTests(unittest.TestCase):
    """The point of the row: the boilerplate does not vary per sub-release."""

    def test_two_releases_share_an_identical_gate_set_by_value(self):
        a = _build("v5.2")
        b = _build("v5.9")
        self.assertEqual(
            a["gate_set"], b["gate_set"],
            "the gate set varies between sub-releases -- an orchestrator would "
            "have to reason about it, which is what L-5 removes",
        )

    def test_two_releases_share_identical_stop_conditions_by_value(self):
        self.assertEqual(_build("v5.2")["stop_conditions"], _build("v6.0")["stop_conditions"])

    def test_only_release_derived_fields_differ_between_two_releases(self):
        a = _build("v5.2")
        b = _build("v5.9")
        self.assertEqual(set(a), set(b), "two release units have different key sets")
        differing = {key for key in a if a[key] != b[key]}
        self.assertEqual(
            differing, {"task_id"},
            f"fields other than the release-derived task_id differ between "
            f"two sub-releases: {sorted(differing)}",
        )


class FreshObjectTests(unittest.TestCase):
    """Every call returns its own packet, all the way down."""

    def test_two_calls_return_distinct_objects(self):
        a, b = _build(), _build()
        self.assertIsNot(a, b, "release_unit_packet returned the same dict twice")
        self.assertIsNot(a["gate_set"], b["gate_set"], "the gate_set list is shared")
        self.assertIsNot(
            a["stop_conditions"], b["stop_conditions"],
            "the stop_conditions list is shared",
        )
        for index, (left, right) in enumerate(zip(a["gate_set"], b["gate_set"])):
            with self.subTest(index=index):
                self.assertIsNot(left, right, "a gate entry dict is shared between packets")

    def test_mutating_one_packet_does_not_affect_the_next(self):
        # A module-level template returned by reference passes every equality
        # check above and fails here. Reach into the nested entry too: a
        # shallow copy of the template would survive the top-level edits.
        first = _build()
        first["gate_set"].pop()
        first["gate_set"][0]["gate"] = "tampered"
        first["gate_set"][0]["order"] = 99
        first["stop_conditions"].clear()
        first["writable_patch_paths"].append("/etc/**")
        first["sprint_item"]["claim_id"] = 0
        first["release_boundary"] = False

        second = _build()
        self.assertEqual(
            [entry["gate"] for entry in second["gate_set"]], list(EXPECTED_GATES),
            "mutating one packet's gate set changed the next packet's -- the "
            "generator hands out a shared object rather than a fresh packet",
        )
        self.assertEqual([entry["order"] for entry in second["gate_set"]], [1, 2, 3, 4, 5, 6])
        self.assertEqual(set(second["stop_conditions"]), set(EXPECTED_STOP_CONDITIONS))
        self.assertEqual(second["writable_patch_paths"], WRITABLE)
        self.assertEqual(second["sprint_item"], SPRINT_ITEM)
        self.assertIs(second["release_boundary"], True)


class SchemaShapeTests(unittest.TestCase):
    """As much of the packet schema as is checkable without ``jsonschema``.

    The required key list and the declared types are read from
    ``templates/dispatch/hybrid/task-packet.schema.json`` at test time rather
    than copied here, so this stays true when the schema moves.
    """

    def test_the_schema_is_readable(self):
        schema = _load_schema()
        self.assertIsInstance(schema.get("required"), list, "the schema names no required keys")
        self.assertTrue(schema["required"], "the schema's required list is empty")

    def test_every_required_top_level_key_is_present(self):
        schema = _load_schema()
        pkt = _build()
        missing = [key for key in schema["required"] if key not in pkt]
        self.assertEqual(
            missing, [],
            f"the generated packet is missing schema-required keys: {missing}",
        )

    def test_every_present_key_has_the_type_the_schema_declares(self):
        schema = _load_schema()
        properties = schema.get("properties", {})
        pkt = _build()
        for key, value in pkt.items():
            declared = properties.get(key, {}).get("type")
            if declared is None:
                continue
            names = [declared] if isinstance(declared, str) else list(declared)
            allowed: tuple[type, ...] = tuple(
                t for name in names for t in _JSON_TYPES.get(name, ())
            )
            if not allowed:
                continue
            with self.subTest(key=key, declared=declared):
                self.assertIsInstance(
                    value, allowed,
                    f"{key} is {type(value).__name__}, schema declares {declared}",
                )
                if bool not in allowed:
                    self.assertNotIsInstance(
                        value, bool, f"{key} is a bool, schema declares {declared}",
                    )

    def test_enumerated_and_const_fields_hold_a_permitted_value(self):
        schema = _load_schema()
        properties = schema.get("properties", {})
        pkt = _build()
        for key, value in pkt.items():
            rule = properties.get(key, {})
            if "const" in rule:
                with self.subTest(key=key):
                    self.assertEqual(
                        value, rule["const"],
                        f"{key} is {value!r}, schema fixes it at {rule['const']!r}",
                    )
            if "enum" in rule:
                with self.subTest(key=key):
                    self.assertIn(
                        value, rule["enum"],
                        f"{key} is {value!r}, schema allows {rule['enum']}",
                    )

    def test_the_packet_is_json_serializable(self):
        # A packet that cannot round-trip through JSON cannot be frozen to
        # docs/evidence/packets/ or handed to hybrid_dispatch.
        pkt = _build()
        self.assertEqual(json.loads(json.dumps(pkt, sort_keys=True)), pkt)


if __name__ == "__main__":
    unittest.main()
