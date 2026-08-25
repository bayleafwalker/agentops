"""Coordinator-authored oracle: stratified registered gates (agentops#2046).

The tract asks for "stratified registered gates (fast attempt falsifiers,
focused candidate gates, and one full suite after independent approval or wave
integration)" and, in the same breath, that "gate stratification does not skip
the final required repository gate".

Those two pull against each other, and the whole value of this row is in the
second. Stratification reorders and short-circuits *work*; it must never reduce
*what has to pass*. So the seam under test is deliberately shaped to make the
cheap answer wrong: a plan that runs the fast tier and stops is a legal plan,
and a candidate minted from it is not.

The subject is a new module, ``templates/dispatch/scripts/gate_tiers.py``,
exposing:

    TIER_ORDER = ("fast", "focused", "full")

    stratify(packet) -> dict[str, list[str]]
        The packet's ``gate_tiers`` mapping, validated against
        ``allowed_command_ids``. A packet that declares none is not an error:
        every granted id lands in ``full``, which is exactly today's behaviour.

    plan(packet) -> list[tuple[str, list[str]]]
        Tiers in TIER_ORDER, empty tiers omitted. This is the run order.

    candidate_ready(packet, results) -> bool
        Whether the evidence in ``results`` is sufficient to mint a candidate.
        ``results`` is an iterable of {"command_id", "exit_code"}.

    unmet_for_candidate(packet, results) -> list[str]
        The granted ids that have not yet run green, in TIER_ORDER then packet
        order. ``candidate_ready`` is true exactly when this is empty.

Rule 11: this file's subject is ``gate_tiers.py``. It runs no git, no
subprocess, and never imports the driver.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

# Loading a module by path writes a .pyc beside it. This oracle is run under
# strace at freeze time, where a write into the repository is a finding.
sys.dont_write_bytecode = True

ROOT = Path(__file__).parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


tiers = _load_module("gate_tiers_subject", SCRIPTS / "gate_tiers.py")


def _packet(granted, gate_tiers=None) -> dict:
    packet = {"allowed_command_ids": list(granted)}
    if gate_tiers is not None:
        packet["gate_tiers"] = gate_tiers
    return packet


def _green(*ids) -> list[dict]:
    return [{"command_id": i, "exit_code": 0} for i in ids]


class TierOrderTests(unittest.TestCase):
    def test_the_order_is_fast_then_focused_then_full(self):
        # The order is the contract: the cheapest falsifier first, the full
        # suite last. A different order would spend the expensive gate on work
        # a fast falsifier would have rejected.
        self.assertEqual(tiers.TIER_ORDER, ("fast", "focused", "full"))


class StratifyTests(unittest.TestCase):
    def test_an_undeclared_packet_puts_every_granted_id_in_full(self):
        # Backward compatibility is a requirement, not a nicety: every packet
        # frozen before this row must keep meaning exactly what it meant.
        result = tiers.stratify(_packet(["a", "b"]))
        self.assertEqual(result, {"fast": [], "focused": [], "full": ["a", "b"]})

    def test_every_tier_key_is_present_even_when_empty(self):
        result = tiers.stratify(_packet(["a"], {"full": ["a"]}))
        self.assertEqual(set(result), set(tiers.TIER_ORDER))

    def test_a_declared_split_is_returned_as_declared(self):
        packet = _packet(["a", "b", "c"], {"fast": ["a"], "focused": ["b"], "full": ["c"]})
        self.assertEqual(
            tiers.stratify(packet), {"fast": ["a"], "focused": ["b"], "full": ["c"]}
        )

    def test_packet_order_is_preserved_within_a_tier(self):
        packet = _packet(["a", "b", "c"], {"full": ["c", "a", "b"]})
        self.assertEqual(tiers.stratify(packet)["full"], ["c", "a", "b"])

    def test_an_id_not_granted_by_the_packet_is_refused(self):
        # allowed_command_ids is the grant. A tier naming something outside it
        # would let a packet widen its own authority through a new field.
        with self.assertRaises(ValueError):
            tiers.stratify(_packet(["a"], {"full": ["a"], "fast": ["b"]}))

    def test_an_unknown_tier_name_is_refused(self):
        with self.assertRaises(ValueError):
            tiers.stratify(_packet(["a"], {"full": ["a"], "smoke": []}))

    def test_an_id_in_two_tiers_is_refused(self):
        # Otherwise "it ran in fast" could be quietly counted as "full ran".
        with self.assertRaises(ValueError):
            tiers.stratify(_packet(["a"], {"fast": ["a"], "full": ["a"]}))

    def test_a_granted_id_in_no_tier_is_refused(self):
        # A granted gate that no tier names would never run, and the packet
        # would look stratified while silently dropping a gate.
        with self.assertRaises(ValueError):
            tiers.stratify(_packet(["a", "b"], {"full": ["a"]}))

    def test_a_declared_split_with_an_empty_full_tier_is_refused(self):
        # This is the criterion, enforced at freeze rather than at gate time:
        # there is always a final required repository gate.
        with self.assertRaises(ValueError):
            tiers.stratify(_packet(["a"], {"fast": ["a"], "full": []}))

    def test_the_packet_is_not_mutated(self):
        packet = _packet(["a", "b"], {"full": ["a", "b"]})
        before = {"allowed_command_ids": ["a", "b"], "gate_tiers": {"full": ["a", "b"]}}
        tiers.stratify(packet)
        self.assertEqual(packet, before)


class PlanTests(unittest.TestCase):
    def test_the_plan_is_tier_order_with_empty_tiers_omitted(self):
        packet = _packet(["a", "b"], {"fast": ["a"], "full": ["b"]})
        self.assertEqual(tiers.plan(packet), [("fast", ["a"]), ("full", ["b"])])

    def test_an_undeclared_packet_plans_one_full_step(self):
        self.assertEqual(tiers.plan(_packet(["a", "b"])), [("full", ["a", "b"])])

    def test_the_plan_names_every_granted_id_exactly_once(self):
        packet = _packet(["a", "b", "c"], {"fast": ["a"], "focused": ["b"], "full": ["c"]})
        planned = [i for _, ids in tiers.plan(packet) for i in ids]
        self.assertEqual(sorted(planned), ["a", "b", "c"])
        self.assertEqual(len(planned), len(set(planned)))

    def test_full_is_always_the_last_step(self):
        packet = _packet(["a", "b", "c"], {"fast": ["a"], "focused": ["b"], "full": ["c"]})
        self.assertEqual(tiers.plan(packet)[-1][0], "full")


class CandidateTests(unittest.TestCase):
    """The criterion. Stratification reorders work; it never reduces what must
    pass before a candidate may be minted."""

    def test_a_fast_tier_green_alone_does_not_mint_a_candidate(self):
        # THE falsifier. An implementation that stops at the first green tier
        # passes every other test in this file and fails this one.
        packet = _packet(["fastid", "fullid"], {"fast": ["fastid"], "full": ["fullid"]})
        self.assertFalse(tiers.candidate_ready(packet, _green("fastid")))

    def test_the_unmet_list_names_the_gate_that_was_skipped(self):
        packet = _packet(["fastid", "fullid"], {"fast": ["fastid"], "full": ["fullid"]})
        self.assertEqual(tiers.unmet_for_candidate(packet, _green("fastid")), ["fullid"])

    def test_every_tier_green_mints_a_candidate(self):
        packet = _packet(["a", "b", "c"], {"fast": ["a"], "focused": ["b"], "full": ["c"]})
        self.assertTrue(tiers.candidate_ready(packet, _green("a", "b", "c")))
        self.assertEqual(tiers.unmet_for_candidate(packet, _green("a", "b", "c")), [])

    def test_a_red_result_does_not_count_as_having_run(self):
        packet = _packet(["a"], {"full": ["a"]})
        results = [{"command_id": "a", "exit_code": 1}]
        self.assertFalse(tiers.candidate_ready(packet, results))
        self.assertEqual(tiers.unmet_for_candidate(packet, results), ["a"])

    def test_a_result_for_an_ungranted_id_is_ignored(self):
        # A worker cannot satisfy a gate by reporting a command nobody granted.
        packet = _packet(["a"], {"full": ["a"]})
        self.assertFalse(tiers.candidate_ready(packet, _green("something-else")))

    def test_an_undeclared_packet_still_requires_every_granted_id(self):
        packet = _packet(["a", "b"])
        self.assertFalse(tiers.candidate_ready(packet, _green("a")))
        self.assertTrue(tiers.candidate_ready(packet, _green("a", "b")))

    def test_unmet_is_reported_in_tier_order_then_packet_order(self):
        packet = _packet(
            ["a", "b", "c", "d"], {"fast": ["c"], "focused": ["a"], "full": ["d", "b"]}
        )
        self.assertEqual(tiers.unmet_for_candidate(packet, []), ["c", "a", "d", "b"])

    def test_ready_is_exactly_the_empty_unmet_list(self):
        # The two are pinned to each other in both directions so a later change
        # cannot make one lenient while the other stays strict.
        packet = _packet(["a", "b"], {"fast": ["a"], "full": ["b"]})
        for results in ([], _green("a"), _green("b"), _green("a", "b")):
            self.assertEqual(
                tiers.candidate_ready(packet, results),
                tiers.unmet_for_candidate(packet, results) == [],
            )

    def test_results_may_be_a_one_shot_iterator(self):
        packet = _packet(["a", "b"], {"fast": ["a"], "full": ["b"]})
        self.assertTrue(tiers.candidate_ready(packet, iter(_green("a", "b"))))

    def test_a_duplicate_green_result_does_not_satisfy_a_second_gate(self):
        packet = _packet(["a", "b"], {"fast": ["a"], "full": ["b"]})
        self.assertFalse(tiers.candidate_ready(packet, _green("a", "a")))


if __name__ == "__main__":
    unittest.main()
