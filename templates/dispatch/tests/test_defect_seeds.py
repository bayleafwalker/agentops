"""Coordinator-authored oracle: defect-seeded acceptance cases (agentops#2046).

The tract asks for "defect-seeded acceptance cases where empty/list-only
assertions, ignored sprint/track/status filters, already-sorted inputs, or
replacement of the real read boundary must fail", and for those seeds to "fail
deterministically".

Today's `acceptance-properties-discriminating` pre-gate is structural only: it
requires each property to name a `fails_when`, and never checks that the oracle
actually goes red when that condition holds. A packet can therefore declare a
falsifying condition its oracle cannot detect, and nothing notices.

A seed closes that. It is the reference overlay's complement: the reference
must turn the oracle GREEN, a seed must turn it RED. If a seeded defect leaves
the oracle green, the oracle does not test what the packet claims.

The subject is a new module, `templates/dispatch/scripts/defect_seeds.py`,
exposing:

    SEED_ID_RE
        Compiled pattern for a seed id: starts with a letter, then letters,
        digits, '.', '_' or '-'. The same shape as an acceptance property id,
        because both name a requirement in evidence a human will read later.

    parse_seeds(packet) -> list[dict]
        Normalised `oracle.defect_seeds`, each {"id", "patch", "expect_red",
        "description"}. A packet declaring none returns [] and is not an error.
        Raises ValueError when a declaration is unusable.

    seed_falsified(seed, results) -> bool
        Whether this seed did its job: every command in `expect_red` ran and
        every one of them was red.

    unfalsified(packet, outcomes) -> list[str]
        Seed ids that did not falsify, in packet order. `outcomes` maps seed id
        to that seed's results. A seed with no outcome at all counts as
        unfalsified -- silence is not evidence.

Rule 11: the subject is `defect_seeds.py`. No git, no subprocess, no file I/O.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


seeds = _load_module("defect_seeds_subject", SCRIPTS / "defect_seeds.py")

GATE = "agentops.dispatch.tests.example"
OTHER = "agentops.dispatch.tests.other"


def _packet(defect_seeds=None, starts_red=(GATE,)) -> dict:
    oracle: dict = {"starts_red": list(starts_red)}
    if defect_seeds is not None:
        oracle["defect_seeds"] = defect_seeds
    return {"oracle": oracle}


def _seed(seed_id="empty-assertion", patch="docs/evidence/seeds/a.patch", expect_red=(GATE,), **kw):
    seed = {"id": seed_id, "patch": patch, "expect_red": list(expect_red)}
    seed.update(kw)
    return seed


def _red(*ids):
    return [{"command_id": i, "exit_code": 1} for i in ids]


def _green(*ids):
    return [{"command_id": i, "exit_code": 0} for i in ids]


class ParseTests(unittest.TestCase):
    def test_a_packet_with_no_seeds_is_not_an_error(self):
        # Every packet frozen before this row has none, and must keep working.
        self.assertEqual(seeds.parse_seeds(_packet()), [])

    def test_a_packet_with_no_oracle_at_all_is_not_an_error(self):
        self.assertEqual(seeds.parse_seeds({}), [])

    def test_a_seed_is_normalised_with_a_description_default(self):
        parsed = seeds.parse_seeds(_packet([_seed()]))
        self.assertEqual(len(parsed), 1)
        self.assertEqual(
            set(parsed[0]), {"id", "patch", "expect_red", "description"}
        )
        self.assertEqual(parsed[0]["description"], "")

    def test_a_declared_description_is_kept(self):
        parsed = seeds.parse_seeds(_packet([_seed(description="list-only assertion")]))
        self.assertEqual(parsed[0]["description"], "list-only assertion")

    def test_packet_order_is_preserved(self):
        parsed = seeds.parse_seeds(
            _packet([_seed(seed_id="b"), _seed(seed_id="a")])
        )
        self.assertEqual([s["id"] for s in parsed], ["b", "a"])

    def test_defect_seeds_must_be_a_list(self):
        with self.assertRaises(ValueError):
            seeds.parse_seeds(_packet({"id": "a"}))

    def test_a_seed_must_declare_an_id(self):
        seed = _seed()
        del seed["id"]
        with self.assertRaises(ValueError):
            seeds.parse_seeds(_packet([seed]))

    def test_a_seed_id_must_match_the_id_pattern(self):
        with self.assertRaises(ValueError):
            seeds.parse_seeds(_packet([_seed(seed_id="1-leading-digit")]))

    def test_duplicate_seed_ids_are_refused(self):
        # Two seeds under one id would make the evidence unreadable: a reader
        # could not tell which defect the red belongs to.
        with self.assertRaises(ValueError):
            seeds.parse_seeds(_packet([_seed(seed_id="a"), _seed(seed_id="a")]))

    def test_a_seed_must_declare_a_patch(self):
        seed = _seed()
        del seed["patch"]
        with self.assertRaises(ValueError):
            seeds.parse_seeds(_packet([seed]))

    def test_an_absolute_patch_path_is_refused(self):
        with self.assertRaises(ValueError):
            seeds.parse_seeds(_packet([_seed(patch="/etc/passwd.patch")]))

    def test_a_patch_path_escaping_the_repository_is_refused(self):
        with self.assertRaises(ValueError):
            seeds.parse_seeds(_packet([_seed(patch="../outside.patch")]))

    def test_expect_red_must_not_be_empty(self):
        # A seed that expects nothing to go red proves nothing.
        with self.assertRaises(ValueError):
            seeds.parse_seeds(_packet([_seed(expect_red=[])]))

    def test_expect_red_must_name_a_starts_red_command(self):
        # Only the oracle's own commands are evidence here. A seed pointing at
        # some other gate would be red for reasons the packet never froze.
        with self.assertRaises(ValueError):
            seeds.parse_seeds(_packet([_seed(expect_red=[OTHER])]))

    def test_expect_red_may_name_several_starts_red_commands(self):
        packet = _packet([_seed(expect_red=[GATE, OTHER])], starts_red=(GATE, OTHER))
        self.assertEqual(seeds.parse_seeds(packet)[0]["expect_red"], [GATE, OTHER])

    def test_the_packet_is_not_mutated(self):
        seed = _seed()
        packet = _packet([seed])
        seeds.parse_seeds(packet)
        self.assertEqual(packet["oracle"]["defect_seeds"], [seed])
        self.assertNotIn("description", seed)


class FalsifiedTests(unittest.TestCase):
    def test_a_seed_whose_expected_command_went_red_falsified(self):
        self.assertTrue(seeds.seed_falsified(_seed(), _red(GATE)))

    def test_a_seed_whose_expected_command_stayed_green_did_not(self):
        # THE case. A seeded defect the oracle does not notice means the oracle
        # does not test what the packet claims it tests.
        self.assertFalse(seeds.seed_falsified(_seed(), _green(GATE)))

    def test_a_seed_with_no_result_for_its_command_did_not_falsify(self):
        # Silence is not evidence: a command that never ran has not shown
        # anything, and must not be read as success.
        self.assertFalse(seeds.seed_falsified(_seed(), []))

    def test_every_expected_command_must_be_red_not_merely_one(self):
        seed = _seed(expect_red=[GATE, OTHER])
        self.assertFalse(seeds.seed_falsified(seed, _red(GATE) + _green(OTHER)))
        self.assertTrue(seeds.seed_falsified(seed, _red(GATE, OTHER)))

    def test_a_result_for_an_unexpected_command_is_ignored(self):
        self.assertTrue(seeds.seed_falsified(_seed(), _red(GATE) + _green(OTHER)))

    def test_results_may_be_a_one_shot_iterator(self):
        self.assertTrue(seeds.seed_falsified(_seed(), iter(_red(GATE))))


class UnfalsifiedTests(unittest.TestCase):
    def test_a_packet_with_no_seeds_has_nothing_unfalsified(self):
        self.assertEqual(seeds.unfalsified(_packet(), {}), [])

    def test_a_seed_that_falsified_is_not_reported(self):
        packet = _packet([_seed(seed_id="a")])
        self.assertEqual(seeds.unfalsified(packet, {"a": _red(GATE)}), [])

    def test_a_seed_that_did_not_falsify_is_reported(self):
        packet = _packet([_seed(seed_id="a")])
        self.assertEqual(seeds.unfalsified(packet, {"a": _green(GATE)}), ["a"])

    def test_a_seed_with_no_outcome_is_reported(self):
        packet = _packet([_seed(seed_id="a")])
        self.assertEqual(seeds.unfalsified(packet, {}), ["a"])

    def test_reporting_is_in_packet_order(self):
        packet = _packet([_seed(seed_id="b"), _seed(seed_id="a")])
        self.assertEqual(seeds.unfalsified(packet, {}), ["b", "a"])

    def test_only_the_failing_seeds_are_reported(self):
        packet = _packet([_seed(seed_id="a"), _seed(seed_id="b"), _seed(seed_id="c")])
        outcomes = {"a": _red(GATE), "b": _green(GATE), "c": _red(GATE)}
        self.assertEqual(seeds.unfalsified(packet, outcomes), ["b"])


if __name__ == "__main__":
    unittest.main()
