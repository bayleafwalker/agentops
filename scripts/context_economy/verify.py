# Provenance: written for agentops#2437 (context-economy Phase 1 arm b).
"""Quote verifier: decompose the Bash-share gate's numerator by command class.

#2435 measured Phase 1 for the first time and the Bash-share gate failed
(docs/evidence/scorecards/context-economy-phase1.json). That scorecard
carries two caveats about what the failing number means, and #2437 forbids
building any intervention before answering the caveat (a) question first:

  (a) file_read_share counts the Read tool only, so file reads issued
      through Bash (`cat`, `sed -n`, `head`, ...) are inside the Bash
      numerator, not the file-read numerator. This host's CLAUDE.md
      instructs Bash-first file reading under bypass-permissions mode, so a
      large part of the Bash share may be file reading wearing a Bash
      label. This module answers "how much" by splitting the Bash
      tool-result numerator with `classes.cls()` (the same classifier
      `classes.py`/`waste.py` already use) and reporting, per class, its
      chars, its share of the Bash numerator, and its share of total
      context.

  (b) the corpus is live (it contains the measuring session's own
      transcript), so any number here is a snapshot, not reproducible to
      the digit. `build_attribution_scorecard` therefore carries both the
      Phase 1 scorecard's original snapshot (`phase1_reference_snapshot`,
      hardcoded from the committed context-economy-phase1.json) and this
      run's own snapshot (`this_run_snapshot`), rather than only the latter.

This is measurement, not intervention: it attributes bytes already counted
as Bash to what they look like they are for, under an `adjusted` view. It
does not change how Bash or Read tool results are counted, and it does not
touch CLAUDE.md or the harness's read guidance (out of scope per #2437).

Structured for import safety like measure.py/classes.py: pure functions plus
`build_argparser()`/`main(argv=None)`, no work at module scope beyond the
sibling-module loads below (mirroring measure.py's own load of classes.py,
since this directory has no __init__.py and is not an importable package).
"""
from __future__ import annotations

import argparse
import collections
import datetime
import importlib.util
import json
import os
import socket
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_HERE, filename))
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


measure = _load('context_economy_measure', 'measure.py')
classes = _load('context_economy_classes', 'classes.py')

# The Phase 1 scorecard's own snapshot (docs/evidence/scorecards/context-economy-phase1.json
# at agentops aa2a45c), restated here per caveat (b) so any run of this module states both
# snapshots rather than only its own. Do not update these to "correct" them: they are the
# historical Phase 1 measurement, not a value this module recomputes.
PHASE1_REFERENCE_SNAPSHOT = {
    "study": "context-economy-phase1",
    "measured_at_utc": "2026-09-19T12:36:51Z",
    "denominator_chars": 1877174,
    "bash_numerator_chars": 1095814,
    "bash_share": 0.5837572862185392,
}


def decompose_bash(sessions: list[dict]) -> dict:
    """Sum each session's `bash_by_class` (added to measure.scan_file for
    this item) into one Counter, keyed by classes.cls() class name."""
    by_class: collections.Counter = collections.Counter()
    for s in sessions:
        for k, v in s.get('bash_by_class', {}).items():
            by_class[k] += v
    return dict(by_class)


def build_attribution(sessions: list[dict]) -> dict:
    """Decompose the Bash numerator by class and build the `adjusted` view.

    The `adjusted` view answers caveat (a): what would bash_share and
    file_read_share be if the 'file-read' class of the Bash numerator were
    attributed to file reading instead of Bash. It is stated as an
    attribution (a re-labeling of bytes already counted), not a correction
    to the Phase 1 measurement, which stands as measured.
    """
    agg = measure.aggregate(sessions)
    denom = agg['context_chars']
    bash_total = agg['bash_chars']
    by_class = decompose_bash(sessions)
    # The decomposition must exhaust the Bash numerator: classes.cls() always
    # returns a class (falling back to 'other'), so every Bash tool-result
    # byte lands in exactly one bucket.
    assert sum(by_class.values()) == bash_total, (
        f"bash_by_class sums to {sum(by_class.values())}, expected {bash_total}"
    )
    decomposition = {}
    for name, chars in sorted(by_class.items(), key=lambda kv: -kv[1]):
        decomposition[name] = {
            "chars": chars,
            "share_of_bash_numerator": (chars / bash_total) if bash_total else 0.0,
            "share_of_context": (chars / denom) if denom else 0.0,
        }
    bash_file_read_chars = by_class.get('file-read', 0)
    adjusted_bash_chars = bash_total - bash_file_read_chars
    adjusted_read_chars = agg['read_chars'] + bash_file_read_chars
    adjusted = {
        "note": "Attribution, not correction: bash_share/file_read_share as measured if the "
                "'file-read' class of the Bash numerator (chars matching classes.cls() == "
                "'file-read', i.e. cat/sed -n/head/tail/less/bat/heredoc commands) were "
                "counted as file reading instead of Bash.",
        "bash_file_read_chars": bash_file_read_chars,
        "adjusted_bash_chars": adjusted_bash_chars,
        "adjusted_read_chars": adjusted_read_chars,
        "adjusted_bash_share": (adjusted_bash_chars / denom) if denom else 0.0,
        "adjusted_file_read_share": (adjusted_read_chars / denom) if denom else 0.0,
    }
    return {
        "denominator_chars": denom,
        "bash_numerator_chars": bash_total,
        "bash_numerator_decomposition": decomposition,
        "adjusted": adjusted,
    }


def build_scorecard(sessions: list[dict], root: str, days: int | None) -> dict:
    """Build the arm-b scorecard: Phase 1's study/provenance/transcripts
    conventions, plus the Bash-numerator decomposition and both snapshots
    caveat (b) requires."""
    agg = measure.aggregate(sessions)
    attribution = build_attribution(sessions)
    now = datetime.datetime.now(datetime.timezone.utc)
    this_run_snapshot = {
        "measured_at_utc": now.isoformat(),
        "denominator_chars": attribution["denominator_chars"],
        "bash_numerator_chars": attribution["bash_numerator_chars"],
        "bash_share": (attribution["bash_numerator_chars"] / attribution["denominator_chars"])
        if attribution["denominator_chars"] else 0.0,
    }
    file_read_share_of_bash = (
        attribution["adjusted"]["bash_file_read_chars"] / attribution["bash_numerator_chars"]
    ) if attribution["bash_numerator_chars"] else 0.0
    return {
        "study": "context-economy-phase1-bash-attribution",
        "arm": "b",
        "filed_because": "#2435 forbade building arm b except if a Phase 1 gate failed; the "
                          "Bash-share gate failed (58.4 percent against a below-28-percent "
                          "threshold). #2437 files and builds arm b.",
        "provenance": {
            "host": socket.gethostname(),
            "measured_at_utc": now.isoformat(),
            "agentops_commit": "aa2a45c",
            "source_path": "scripts/context_economy/{verify.py,measure.py,classes.py}",
        },
        "transcripts": {
            "root": root,
            "count": agg['n_sessions'],
            "days_filter": days,
            "date_range_utc": {
                "start": agg['date_min'],
                "end": agg['date_max'],
                "inclusive": True,
            },
        },
        "phase1_reference_snapshot": PHASE1_REFERENCE_SNAPSHOT,
        "this_run_snapshot": this_run_snapshot,
        "bash_numerator_chars": attribution["bash_numerator_chars"],
        "denominator_chars": attribution["denominator_chars"],
        "bash_numerator_decomposition": attribution["bash_numerator_decomposition"],
        "adjusted": attribution["adjusted"],
        "caveats": {
            "snapshots_are_two_live_reads_of_the_same_corpus": (
                "Per the Phase 1 scorecard's corpus_is_live caveat, this corpus contains the "
                "transcript of the session doing the measuring and grows during the run. "
                f"phase1_reference_snapshot (measured {PHASE1_REFERENCE_SNAPSHOT['measured_at_utc']}) "
                f"read denominator {PHASE1_REFERENCE_SNAPSHOT['denominator_chars']} and bash_share "
                f"{PHASE1_REFERENCE_SNAPSHOT['bash_share']:.6f}; this_run_snapshot (measured "
                f"{this_run_snapshot['measured_at_utc']}) read denominator "
                f"{this_run_snapshot['denominator_chars']} and bash_share "
                f"{this_run_snapshot['bash_share']:.6f}. Both are snapshots of the same live "
                "corpus, not the same read; do not diff them digit-for-digit."
            ),
            "bash_numerator_decomposition_answers_the_file_read_label_question": (
                "Per the Phase 1 scorecard's read_share_counts_the_Read_tool_only caveat, "
                "file_read_share counts the Read tool only, so Bash-issued file reads (cat, "
                "sed -n, head, ...) are inside the Bash numerator, not the file-read numerator. "
                "This run's decomposition attributes "
                f"{file_read_share_of_bash:.1%} of the Bash numerator "
                f"({attribution['adjusted']['bash_file_read_chars']} of "
                f"{attribution['bash_numerator_chars']} chars) to the 'file-read' class; that is "
                f"{attribution['bash_numerator_decomposition'].get('file-read', {}).get('share_of_context', 0.0):.1%} "
                "of total context. See `adjusted` for what bash_share/file_read_share would be "
                "if that attribution were made; the remaining classes (k8s/flux/infra, "
                "tests/lint/build, git, search/list, python/scripts, other) stay Bash-labeled "
                "and are not file reading by this classifier."
            ),
        },
    }


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog='verify.py',
        description="Quote verifier (context-economy Phase 1 arm b): decompose the Bash-share "
                    "gate's numerator by classes.cls() command class and report the file-read "
                    "attribution within it (agentops#2437).",
    )
    p.add_argument('--root', default=os.path.expanduser('~/.claude/projects'),
                    help='directory to scan for *.jsonl transcripts (default: ~/.claude/projects)')
    p.add_argument('--days', type=int, default=None,
                    help='restrict to transcripts modified in the last N days (default: all)')
    p.add_argument('--out', default=None,
                    help='write a JSON scorecard to this path instead of printing a summary')
    return p


def print_report(sessions: list[dict]) -> None:
    attribution = build_attribution(sessions)
    print(f"bash numerator: {attribution['bash_numerator_chars']} chars "
          f"of {attribution['denominator_chars']} context chars")
    print("decomposition by command class:")
    for name, row in attribution["bash_numerator_decomposition"].items():
        print(f"  {name:18} {row['chars']:>9} chars  "
              f"{row['share_of_bash_numerator']*100:5.1f}% of bash  "
              f"{row['share_of_context']*100:5.1f}% of context")
    a = attribution["adjusted"]
    print(f"adjusted (file-read class attributed to file reading): "
          f"bash_share={a['adjusted_bash_share']*100:.1f}% "
          f"file_read_share={a['adjusted_file_read_share']*100:.1f}%")


def main(argv=None) -> int:
    args = build_argparser().parse_args(argv)
    files = measure.find_transcripts(args.root, args.days)
    sessions = [measure.scan_file(f, args.root) for f in files]
    if args.out:
        scorecard = build_scorecard(sessions, args.root, args.days)
        os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
        with open(args.out, 'w') as fh:
            json.dump(scorecard, fh, indent=2, sort_keys=True)
            fh.write('\n')
        print(f"wrote scorecard: {args.out}")
    else:
        print_report(sessions)
    return 0


if __name__ == '__main__':
    sys.exit(main())
