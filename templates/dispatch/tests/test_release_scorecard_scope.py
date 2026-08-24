"""Coordinator-authored oracle for ``release_scorecard.py`` -- scoping the sink.

T-6a/T-6b/T-6c/T-6d pinned the reduction, the worker half, the assembly and the
I/O shell. #91 fixed the units defect: a cost figure that did not carry what
kind of number it was. This packet fixes the two remaining defects of the same
family, both about a scorecard not carrying what it was built FROM:

1. **The sink is global; the scorecard is not.**
   ``/projects/dev/.claude/session-costs.jsonl`` is written by the Claude Code
   Stop hook for EVERY repository on the machine -- homelab-analytics,
   sprintctl, actionq, agentops -- and each row carries a ``project`` field
   saying which. ``release_scorecard.py`` has no way to scope to one, so the
   frontier half of an agentops release counts whatever else happened to be
   running in the same window. On the live run that motivated this packet, four
   sessions fell inside the window and only some of them were agentops.

2. **A scorecard does not say what it counted.**
   It records ``release`` and ``recorded_at`` and nothing about the window or
   the project it was built from. Two scorecards built with different
   ``--since`` values are not comparable, and nothing in either one says so.

This file pins the two additions that close them::

    filter_by_project(rows, project) -> list
    build_scorecard(release, rows, receipts, escalations, recorded_at,
                    scope=None) -> dict   # gains a top-level "scope" key

Load-bearing properties, asserted directly:

* matching is EXACT. ``agentops`` must not match ``agentops-web`` and must not
  match ``Agentops``. The naive implementation is a substring or a case-folded
  compare, and either one silently rolls a sibling repository's spend into the
  release. ``test_a_substring_match_would_pull_in_the_sibling_repo`` is that
  trap.
* an UNATTRIBUTABLE row is excluded when a project is requested. A row with no
  ``project`` key cannot be counted for one. With ``project=None`` nothing is
  being attributed, so it is kept.
* scoping PARTITIONS rather than double-counts: over a corpus where every
  session belongs to exactly one project, the per-project frontier figures sum
  to the unscoped one.
* ``scope`` is carried VERBATIM, and is ``{}`` -- never ``None`` -- when
  omitted, so a reader never has to distinguish "absent" from "unbounded".
* the fifth-positional-argument call still works. Every existing caller passes
  five positional arguments; the new parameter is optional and trailing.

Written against the packet spec only. ``release_scorecard.py`` carries no
``filter_by_project`` and its ``build_scorecard`` takes no ``scope`` -- so this
oracle fails at attribute lookup and at the signature. That is the declared red.
"""
from __future__ import annotations

import copy
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
    if not path.exists():
        raise ModuleNotFoundError(f"no module to grade: {path} does not exist")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


scorecard = _load_module("release_scorecard_scope_subject",
                         SCRIPTS / "release_scorecard.py")


def _row(session, project, ts, cost_usd, **extra):
    """A sink row shaped the way ``hooks/log-session-cost.sh`` writes them.

    ``project`` is omitted entirely when it is ``None`` -- that is how a row
    written before the field existed actually looks on disk, and it is the case
    that must be excluded when scoping.
    """
    row = {
        "ts": ts,
        "session": session,
        "model": "claude-opus-5",
        "out": 100,
        "cost_usd": cost_usd,
        "turns": 1,
        "assistant_msgs": 2,
        "tool_calls": 1,
        "duration_s": 30,
        "rework_rounds": 0,
    }
    if project is not None:
        row["project"] = project
    row.update(extra)
    return row


#: The corpus for the substring trap. Four project names that a naive ``in``
#: check, or a case-folded compare, would over-match on: the exact name, the
#: sibling repo whose name CONTAINS it, the differently-cased spelling, and the
#: shorter name the exact one contains.
TRAP_ROWS: tuple[dict, ...] = (
    _row("s-exact-1", "agentops", "2026-08-24T10:00:00Z", 1.0),
    _row("s-web", "agentops-web", "2026-08-24T10:01:00Z", 2.0),
    _row("s-case", "Agentops", "2026-08-24T10:02:00Z", 4.0),
    _row("s-short", "agentop", "2026-08-24T10:03:00Z", 8.0),
    _row("s-exact-2", "agentops", "2026-08-24T10:04:00Z", 16.0),
)

#: The sessions in TRAP_ROWS whose project is EXACTLY "agentops".
TRAP_EXACT_SESSIONS = ["s-exact-1", "s-exact-2"]

#: A corpus carrying rows that cannot be attributed to any project: one with no
#: ``project`` key at all, and three whose ``project`` is present but not a
#: string. ``None``, a number and a list are all things a hand-edited or
#: half-migrated sink really contains.
UNATTRIBUTABLE_ROWS: tuple[dict, ...] = (
    _row("s-attributed", "agentops", "2026-08-24T10:00:00Z", 1.0),
    _row("s-missing", None, "2026-08-24T10:01:00Z", 2.0),
    dict(_row("s-null", None, "2026-08-24T10:02:00Z", 4.0), project=None),
    dict(_row("s-number", None, "2026-08-24T10:03:00Z", 8.0), project=17),
    dict(_row("s-list", None, "2026-08-24T10:04:00Z", 16.0),
         project=["agentops"]),
)

#: A partition corpus: every session belongs to exactly one project, and each
#: project has a session that stopped more than once so the reduction is
#: exercised inside each part rather than only across them. Session "a-loop"
#: contributes three cumulative snapshots (survivor 3.5), "a-one" one (0.25);
#: "b-loop" contributes two (survivor 6.0), "b-one" one (0.75). So the agentops
#: frontier cost is 3.75, the sprintctl one 6.75, and the unscoped one 10.5.
PARTITION_ROWS: tuple[dict, ...] = (
    _row("a-loop", "agentops", "2026-08-24T10:00:00Z", 0.5, turns=1,
         tool_calls=1, rework_rounds=0),
    _row("b-loop", "sprintctl", "2026-08-24T10:01:00Z", 1.5, turns=2,
         tool_calls=3, rework_rounds=1),
    _row("a-loop", "agentops", "2026-08-24T10:05:00Z", 2.0, turns=3,
         tool_calls=4, rework_rounds=1),
    _row("a-one", "agentops", "2026-08-24T10:06:00Z", 0.25, turns=1,
         tool_calls=0, rework_rounds=0),
    _row("b-loop", "sprintctl", "2026-08-24T10:08:00Z", 6.0, turns=9,
         tool_calls=11, rework_rounds=3),
    _row("a-loop", "agentops", "2026-08-24T10:11:00Z", 3.5, turns=6,
         tool_calls=7, rework_rounds=2),
    _row("b-one", "sprintctl", "2026-08-24T10:12:00Z", 0.75, turns=2,
         tool_calls=2, rework_rounds=0),
)

#: The three frontier costs the partition corpus must produce, by hand, so the
#: assertion does not depend on the subject agreeing with itself.
PARTITION_AGENTOPS_COST = 3.75
PARTITION_SPRINTCTL_COST = 6.75
PARTITION_TOTAL_COST = 10.5

#: The aggregate fields that must partition additively across projects.
#: ``cost_usd`` is compared separately because it is a float.
ADDITIVE_FIELDS = ("sessions", "turns", "assistant_msgs", "tool_calls",
                   "duration_s", "rework_rounds")


def _receipt(task_id, cost_usd, tokens):
    """A receipt shaped like docs/evidence/receipts/<task>/receipt.json."""
    return {
        "schema_version": "agentops-hybrid-receipt/v1",
        "task_id": task_id,
        "repo_id": "agentops",
        "attempt": 1,
        "recorded_at": "2026-08-24T10:07:00Z",
        "route": "mechanical_bulk",
        "harness_model": "opencode-go/deepseek-v4-flash",
        "driver_steps": [
            {"step": "run", "attempt": 1, "exit_code": 0, "stderr": "",
             "receipt": {"spend": {"cost_usd": cost_usd, "tokens": tokens,
                                   "cost_reported": True}}},
        ],
        "gate": {"evidence": {"gates": {"diff-nonempty": True},
                              "passed": True}},
    }


RECEIPTS: tuple[dict, ...] = (
    _receipt("V5-M20-scorecard", 0.011111, 140002),
    _receipt("V5-M21-doctor", 0.020864, 292309),
)

RECORDED_AT = "2026-08-24T10:30:00Z"

#: A realistic scope block: the one ``main`` builds from --project/--since
#: --until. All three keys always present, ``None`` where the flag was absent.
SCOPE = {
    "project": "agentops",
    "since": "2026-08-24T10:00:00Z",
    "until": "2026-08-24T11:00:00Z",
}


def _fresh(corpus):
    """A fresh deep copy, so no test can mutate a fixture for another."""
    return copy.deepcopy(list(corpus))


def _sessions(rows):
    return [row.get("session") for row in rows]


class FilterByProjectTests(unittest.TestCase):
    """``filter_by_project(rows, project)`` -- the scoping primitive."""

    def test_a_project_of_none_returns_every_row_in_order(self):
        rows = _fresh(TRAP_ROWS)
        kept = scorecard.filter_by_project(rows, None)
        self.assertEqual(
            _sessions(kept), _sessions(rows),
            "project=None did not return every row, in the order given -- "
            "None means 'no scoping', not 'the project named None'",
        )
        self.assertEqual(
            kept, rows,
            "project=None changed the rows it returned",
        )

    def test_a_substring_match_would_pull_in_the_sibling_repo(self):
        """The trap. Matching must be EXACT: not ``in``, not case-folded.

        The shared sink carries ``agentops`` beside ``agentops-web``. A
        substring check scopes an agentops release to both and bills it for a
        sibling repository's sessions; a case-folded check adds ``Agentops``.
        Neither failure announces itself -- the scorecard just reads high.
        """
        kept = scorecard.filter_by_project(_fresh(TRAP_ROWS), "agentops")
        self.assertEqual(
            _sessions(kept), TRAP_EXACT_SESSIONS,
            "scoping to 'agentops' did not return exactly the rows whose "
            "project IS 'agentops' -- 'agentops-web', 'Agentops' and "
            "'agentop' are four different repositories, not one",
        )
        for row in kept:
            self.assertEqual(
                row.get("project"), "agentops",
                f"a row whose project is {row.get('project')!r} survived "
                "scoping to 'agentops'",
            )

    def test_scoping_to_a_project_no_row_carries_returns_nothing(self):
        self.assertEqual(
            scorecard.filter_by_project(_fresh(TRAP_ROWS), "homelab-analytics"),
            [],
            "scoping to a project absent from the corpus returned rows",
        )

    def test_an_unattributable_row_is_excluded_when_scoping(self):
        """A row that cannot be attributed to a project cannot be counted for one."""
        kept = scorecard.filter_by_project(_fresh(UNATTRIBUTABLE_ROWS),
                                           "agentops")
        self.assertEqual(
            _sessions(kept), ["s-attributed"],
            "a row with no project key, or a non-string one, survived being "
            "scoped to a project -- an unattributable row was attributed",
        )

    def test_an_unattributable_row_is_kept_when_not_scoping(self):
        """With project=None nothing is being attributed, so nothing is dropped."""
        rows = _fresh(UNATTRIBUTABLE_ROWS)
        kept = scorecard.filter_by_project(rows, None)
        self.assertEqual(
            _sessions(kept), _sessions(rows),
            "project=None dropped the rows that carry no usable project -- "
            "an unscoped scorecard counts the whole sink",
        )

    def test_it_returns_a_list_it_is_safe_to_hold(self):
        kept = scorecard.filter_by_project(_fresh(TRAP_ROWS), "agentops")
        self.assertIsInstance(
            kept, list, "filter_by_project did not return a list",
        )

    def test_it_does_not_mutate_its_input(self):
        rows = _fresh(TRAP_ROWS)
        before = copy.deepcopy(rows)
        scorecard.filter_by_project(rows, "agentops")
        self.assertEqual(
            rows, before,
            "filter_by_project mutated the list it was handed",
        )
        rows = _fresh(UNATTRIBUTABLE_ROWS)
        before = copy.deepcopy(rows)
        scorecard.filter_by_project(rows, None)
        self.assertEqual(
            rows, before,
            "filter_by_project mutated the list it was handed on the "
            "unscoped path",
        )


class ScopedScorecardTests(unittest.TestCase):
    """``filter_by_project`` reaching the frontier half of a scorecard."""

    def _build(self, rows, scope=None):
        return scorecard.build_scorecard(
            "v5", _fresh(rows), _fresh(RECEIPTS), [], RECORDED_AT, scope,
        )

    def _frontier(self, project):
        rows = scorecard.filter_by_project(_fresh(PARTITION_ROWS), project)
        return self._build(rows)["frontier"]

    def test_two_projects_give_two_different_frontier_figures(self):
        agentops = self._frontier("agentops")
        sprintctl = self._frontier("sprintctl")
        self.assertNotEqual(
            agentops, sprintctl,
            "scoping to two different projects produced the same frontier "
            "half -- the scope was not applied",
        )
        self.assertAlmostEqual(
            agentops["cost_usd"], PARTITION_AGENTOPS_COST, places=6,
            msg="the agentops-scoped frontier cost is not the reduced "
                "survivors of the agentops sessions only (3.5 + 0.25)",
        )
        self.assertAlmostEqual(
            sprintctl["cost_usd"], PARTITION_SPRINTCTL_COST, places=6,
            msg="the sprintctl-scoped frontier cost is not the reduced "
                "survivors of the sprintctl sessions only (6.0 + 0.75)",
        )
        self.assertEqual(
            agentops["sessions"], 2,
            "the agentops scope did not reduce to its two sessions",
        )
        self.assertEqual(
            sprintctl["sessions"], 2,
            "the sprintctl scope did not reduce to its two sessions",
        )

    def test_the_parts_sum_to_the_whole_rather_than_double_counting(self):
        """Every session here belongs to exactly one project, so scoping partitions.

        If the two scoped figures do not add up to the unscoped one, either a
        session was counted for both projects or one was lost entirely.
        """
        agentops = self._frontier("agentops")
        sprintctl = self._frontier("sprintctl")
        whole = self._build(PARTITION_ROWS)["frontier"]
        self.assertAlmostEqual(
            whole["cost_usd"], PARTITION_TOTAL_COST, places=6,
            msg="the unscoped frontier cost is not the reduced survivors of "
                "the whole corpus",
        )
        self.assertAlmostEqual(
            agentops["cost_usd"] + sprintctl["cost_usd"], whole["cost_usd"],
            places=6,
            msg="the two per-project frontier costs do not add up to the "
                "unscoped one -- a session was double-counted or dropped",
        )
        for field in ADDITIVE_FIELDS:
            self.assertEqual(
                agentops[field] + sprintctl[field], whole[field],
                f"the per-project {field!r} figures do not partition the "
                "unscoped one",
            )

    def test_the_worker_half_is_untouched_by_scoping_the_sink(self):
        """The receipts are the release's own; scoping the sink must not move them."""
        scoped = self._build(
            scorecard.filter_by_project(_fresh(PARTITION_ROWS), "agentops"))
        whole = self._build(PARTITION_ROWS)
        self.assertEqual(
            scoped["worker"], whole["worker"],
            "scoping the sink to a project changed the worker half, which is "
            "read from the packet receipts and knows nothing about the sink",
        )


class ScopeKeyTests(unittest.TestCase):
    """``build_scorecard``'s new ``scope`` key -- what the number was built from."""

    def _build(self, *args, **kwargs):
        return scorecard.build_scorecard(*args, **kwargs)

    def test_the_scorecard_carries_a_scope_key(self):
        card = self._build("v5", _fresh(PARTITION_ROWS), _fresh(RECEIPTS), [],
                           RECORDED_AT, SCOPE)
        self.assertIn(
            "scope", card,
            "the scorecard carries no 'scope' key -- it records a number "
            "without recording what it was built from",
        )

    def test_scope_is_carried_through_verbatim(self):
        card = self._build("v5", _fresh(PARTITION_ROWS), _fresh(RECEIPTS), [],
                           RECORDED_AT, copy.deepcopy(SCOPE))
        self.assertEqual(
            card["scope"], SCOPE,
            "scope was not carried through verbatim -- it was rewritten, "
            "pruned or re-derived",
        )

    def test_a_scope_with_unbounded_sides_keeps_its_explicit_nones(self):
        """None means 'unbounded', and must survive as a key with a null value.

        Dropping the key would make a reader distinguish "absent" from
        "unbounded" -- exactly the ambiguity the scope block exists to remove.
        """
        unbounded = {"project": "agentops", "since": None, "until": None}
        card = self._build("v5", _fresh(PARTITION_ROWS), _fresh(RECEIPTS), [],
                           RECORDED_AT, copy.deepcopy(unbounded))
        self.assertEqual(
            card["scope"], unbounded,
            "a scope whose since/until are None did not survive verbatim",
        )
        self.assertEqual(
            sorted(card["scope"]), ["project", "since", "until"],
            "the carried scope lost one of its three keys",
        )

    def test_an_omitted_scope_is_an_empty_dict_not_none(self):
        card = self._build("v5", _fresh(PARTITION_ROWS), _fresh(RECEIPTS), [],
                           RECORDED_AT)
        self.assertEqual(
            card["scope"], {},
            "an omitted scope did not become {} -- a consumer reading "
            "card['scope'].get('project') would crash on a None",
        )

    def test_an_explicit_none_scope_is_an_empty_dict(self):
        card = self._build("v5", _fresh(PARTITION_ROWS), _fresh(RECEIPTS), [],
                           RECORDED_AT, None)
        self.assertEqual(
            card["scope"], {},
            "an explicit scope=None did not become {}",
        )

    def test_five_positional_arguments_still_work(self):
        """Every existing caller passes five. The new parameter is optional."""
        try:
            card = scorecard.build_scorecard(
                "v5", _fresh(PARTITION_ROWS), _fresh(RECEIPTS), [], RECORDED_AT,
            )
        except TypeError as exc:
            self.fail(
                "build_scorecard called with five positional arguments raised "
                f"TypeError: {exc} -- the new scope parameter is not optional, "
                "and every existing caller is broken",
            )
        self.assertEqual(
            card["scope"], {},
            "the five-argument call did not yield an empty scope",
        )

    def test_scope_can_be_passed_by_keyword(self):
        card = scorecard.build_scorecard(
            "v5", _fresh(PARTITION_ROWS), _fresh(RECEIPTS), [], RECORDED_AT,
            scope=copy.deepcopy(SCOPE),
        )
        self.assertEqual(
            card["scope"], SCOPE,
            "the scope parameter is not named 'scope', or is not accepted by "
            "keyword",
        )

    def test_scope_does_not_disturb_the_settled_keys(self):
        """Everything #91 and T-6c settled stays exactly as it was."""
        card = scorecard.build_scorecard(
            "v5", _fresh(PARTITION_ROWS), _fresh(RECEIPTS), [], RECORDED_AT,
            copy.deepcopy(SCOPE),
        )
        self.assertEqual(
            set(card),
            {"schema_version", "release", "recorded_at", "frontier", "worker",
             "escalations", "cost_usd", "scope"},
            "the top-level keys are not the seven settled ones plus 'scope'",
        )
        self.assertEqual(
            set(card["cost_usd"]),
            {"worker_billed_usd", "frontier_usage_equivalent_usd",
             "total_billed_usd", "commensurable", "total_reliable"},
            "the cost_usd block changed when scope was added",
        )
        self.assertEqual(
            card["frontier"], scorecard.frontier_totals(_fresh(PARTITION_ROWS)),
            "the frontier half no longer delegates to frontier_totals",
        )
        self.assertEqual(
            card["worker"], scorecard.worker_totals(_fresh(RECEIPTS)),
            "the worker half no longer delegates to worker_totals",
        )
        self.assertIs(
            card["cost_usd"]["commensurable"], False,
            "commensurable stopped being False",
        )

    def test_it_does_not_mutate_the_scope_it_was_handed(self):
        scope = copy.deepcopy(SCOPE)
        before = copy.deepcopy(scope)
        scorecard.build_scorecard("v5", _fresh(PARTITION_ROWS),
                                  _fresh(RECEIPTS), [], RECORDED_AT, scope)
        self.assertEqual(
            scope, before,
            "build_scorecard mutated the scope dict it was handed",
        )

    def test_two_scorecards_with_different_scopes_say_so(self):
        """The whole point: two incomparable scorecards must be distinguishable."""
        narrow = {"project": "agentops", "since": "2026-08-24T10:00:00Z",
                  "until": "2026-08-24T10:07:00Z"}
        wide = {"project": "agentops", "since": None, "until": None}
        rows = scorecard.filter_by_project(_fresh(PARTITION_ROWS), "agentops")
        first = scorecard.build_scorecard(
            "v5", _fresh(rows), _fresh(RECEIPTS), [], RECORDED_AT,
            copy.deepcopy(narrow))
        second = scorecard.build_scorecard(
            "v5", _fresh(rows), _fresh(RECEIPTS), [], RECORDED_AT,
            copy.deepcopy(wide))
        self.assertNotEqual(
            first["scope"], second["scope"],
            "two scorecards built over different windows carry the same "
            "scope -- nothing in either one says they are not comparable",
        )


if __name__ == "__main__":
    unittest.main()
