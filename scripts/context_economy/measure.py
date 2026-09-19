# Provenance: relocated from outctl@94840d7 studies/context-economy/measure.py (outctl retired; agentops#2435).
"""Measure Bash share and file-read share of Claude Code transcript context.

Phase 1/2 gate instrument for the context-economy study (see
docs/evidence/scorecards/context-economy-phase1.json). This reads local
`~/.claude/projects/**/*.jsonl` transcripts and reports, per session and in
aggregate:

  - Bash share: bytes of Bash tool_result content, as a fraction of total
    context bytes (message text + all tool_use input + all tool_result
    content).
  - file-read share: bytes of Read tool_result content, as the same fraction.

Refactored for import safety and CLI use: the original outctl study ran
entirely at module scope (glob, scan, print) as a side effect of
`import measure`, and had no CLI. Here the scan/aggregate logic is factored
into importable functions (`scan_file`, `aggregate`, `build_scorecard`) and an
argparse CLI is added so the module supports `--help`, `--root`, `--days`,
and `--out` (write a JSON scorecard instead of printing the diagnostic
report). The classification and byte-counting logic is unchanged from the
outctl original.

Extended for agentops#2437 (context-economy Phase 1 arm b, the quote
verifier): `scan_file` now also retains, per session, the Bash tool-result
bytes broken down by `classes.cls()` command class, under the new
`bash_by_class` key. This is additive: existing keys keep their prior
meaning and existing tests are unaffected. See verify.py for the consumer.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import glob
import importlib.util
import json
import os
import re
import socket
import sys

BOUND = re.compile(r'\|\s*(head|tail|grep|wc|cut|awk|sed -n|sort \| uniq|jq|rg)\b|--stat|--oneline|\bhead -|\btail -|\bgrep -c|-maxdepth|\b(limit|head|tail)\s*[:=]')
TRUNC = re.compile(r'\[?(output )?truncated|characters truncated|lines truncated|\.\.\. \[\d+ more|exceeds maximum', re.I)
ONLYYOU = 'Only you see that command'

GATE_BASH_SHARE = 0.28
GATE_FILE_READ_SHARE = 0.45

# Load classes.py by path rather than `import classes`: this directory has no
# __init__.py (matching the sibling modules' convention, see test_measure.py),
# so it is not an importable package from an arbitrary working directory.
_classes_spec = importlib.util.spec_from_file_location(
    'context_economy_classes', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'classes.py')
)
_classes = importlib.util.module_from_spec(_classes_spec)
assert _classes_spec.loader is not None
_classes_spec.loader.exec_module(_classes)


def find_transcripts(root: str, days: int | None = None) -> list[str]:
    """Return transcript paths under `root`, optionally restricted to files
    modified within the last `days` days (mtime, matching `find -mtime -N`)."""
    files = glob.glob(root + '/**/*.jsonl', recursive=True)
    if days is not None:
        cutoff = datetime.datetime.now().timestamp() - days * 86400
        files = [f for f in files if os.path.getmtime(f) >= cutoff]
    return files


def scan_file(path: str, root: str) -> dict:
    """Scan one transcript file and return its per-session counters."""
    is_sub = '/subagents/' in path
    name_of = {}
    cmd_of = {}
    tot_by_tool = collections.Counter()
    n_by_tool = collections.Counter()
    text_chars = 0
    n_bash = n_bash_bounded = n_trunc = n_onlyyou = 0
    bash_by_class = collections.Counter()
    compactions = 0
    last_usage = None
    first_ts = None
    n_msgs = 0
    for line in open(path, errors='replace'):
        try:
            d = json.loads(line)
        except Exception:
            continue
        ts = d.get('timestamp')
        if ts and not first_ts:
            first_ts = ts[:10]
        if d.get('isCompactSummary') or d.get('type') == 'summary':
            compactions += 1
        m = d.get('message')
        if not isinstance(m, dict):
            continue
        n_msgs += 1
        u = m.get('usage')
        if u and d.get('type') == 'assistant':
            last_usage = u
        c = m.get('content')
        if isinstance(c, str):
            text_chars += len(c)
            continue
        if not isinstance(c, list):
            continue
        for b in c:
            if not isinstance(b, dict):
                continue
            t = b.get('type')
            if t == 'text':
                text_chars += len(b.get('text', ''))
            elif t == 'thinking':
                text_chars += len(b.get('thinking', ''))
            elif t == 'tool_use':
                name_of[b.get('id')] = b.get('name')
                inp = b.get('input') or {}
                cmd_of[b.get('id')] = inp.get('command', '') if isinstance(inp, dict) else ''
                text_chars += len(json.dumps(inp))
                if b.get('name') == 'Bash':
                    n_bash += 1
                    if BOUND.search(inp.get('command', '') or ''):
                        n_bash_bounded += 1
            elif t == 'tool_result':
                cc = b.get('content')
                if isinstance(cc, list):
                    s = ''.join(x.get('text', '') for x in cc if isinstance(x, dict))
                else:
                    s = cc if isinstance(cc, str) else json.dumps(cc)
                tn = name_of.get(b.get('tool_use_id'), '?')
                L = len(s)
                tot_by_tool[tn] += L
                n_by_tool[tn] += 1
                if tn == 'Bash':
                    if TRUNC.search(s):
                        n_trunc += 1
                    if ONLYYOU in s:
                        n_onlyyou += 1
                    bash_by_class[_classes.cls(cmd_of.get(b.get('tool_use_id'), '') or '')] += L
    tool_total = sum(tot_by_tool.values())
    return dict(
        f=os.path.relpath(path, root), sub=is_sub, date=first_ts, msgs=n_msgs, text=text_chars, tools=tool_total,
        bash=tot_by_tool['Bash'], read=tot_by_tool['Read'], nbash=n_bash, nbound=n_bash_bounded, trunc=n_trunc,
        onlyyou=n_onlyyou, comp=compactions,
        ctx=(last_usage or {}).get('input_tokens', 0) + (last_usage or {}).get('cache_read_input_tokens', 0) + (last_usage or {}).get('cache_creation_input_tokens', 0),
        bytool=dict(tot_by_tool),
        bash_by_class=dict(bash_by_class),
    )


def scan_root(root: str, days: int | None = None) -> list[dict]:
    return [scan_file(f, root) for f in find_transcripts(root, days)]


def pct(a, q):
    a = sorted(a)
    return a[min(len(a) - 1, int(q * len(a)))] if a else 0


def aggregate(sessions: list[dict]) -> dict:
    """Sum context-share numerators/denominators across all sessions
    (top-level and subagents), matching the outctl study's 'ALL' grouping."""
    text_total = sum(s['text'] for s in sessions)
    tools_total = sum(s['tools'] for s in sessions)
    bash_total = sum(s['bash'] for s in sessions)
    read_total = sum(s['read'] for s in sessions)
    denom = text_total + tools_total
    dates = [s['date'] for s in sessions if s['date']]
    return dict(
        n_sessions=len(sessions),
        text_chars=text_total,
        tool_result_chars=tools_total,
        bash_chars=bash_total,
        read_chars=read_total,
        context_chars=denom,
        date_min=min(dates) if dates else None,
        date_max=max(dates) if dates else None,
    )


def build_scorecard(sessions: list[dict], root: str, days: int | None) -> dict:
    agg = aggregate(sessions)
    denom = agg['context_chars']
    bash_share = (agg['bash_chars'] / denom) if denom else 0.0
    read_share = (agg['read_chars'] / denom) if denom else 0.0
    now = datetime.datetime.now(datetime.timezone.utc)
    return {
        "study": "context-economy-phase1",
        "provenance": {
            "outctl_commit": "94840d7",
            "source_repo": "outctl (retired)",
            "source_path": "studies/context-economy/{measure.py,classes.py,waste.py}",
            "host": socket.gethostname(),
            "measured_at_utc": now.isoformat(),
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
        "bash_share": {
            "numerator_chars": agg['bash_chars'],
            "denominator_chars": agg['context_chars'],
            "value": bash_share,
            "gate_threshold": GATE_BASH_SHARE,
            "gate": "below 28 percent of context",
            "pass": bash_share < GATE_BASH_SHARE,
        },
        "file_read_share": {
            "numerator_chars": agg['read_chars'],
            "denominator_chars": agg['context_chars'],
            "value": read_share,
            "gate_threshold": GATE_FILE_READ_SHARE,
            "gate": "below 45 percent of context",
            "pass": read_share < GATE_FILE_READ_SHARE,
        },
    }


def print_report(sessions: list[dict], files_scanned: int) -> None:
    """Reproduce the outctl study's original diagnostic text report."""
    top = [s for s in sessions if not s['sub']]
    subs = [s for s in sessions if s['sub']]
    dated = [s['date'] for s in sessions if s['date']]
    if dated:
        print(f"files={files_scanned} top={len(top)} sub={len(subs)} dates={min(dated)}..{max(dated)}")
    else:
        print(f"files={files_scanned} top={len(top)} sub={len(subs)} dates=(none)")
    for label, grp in (('TOP-LEVEL', top), ('SUBAGENTS', subs), ('ALL', sessions)):
        T = sum(s['text'] for s in grp)
        TL = sum(s['tools'] for s in grp)
        B = sum(s['bash'] for s in grp)
        R = sum(s['read'] for s in grp)
        denom = max(T + TL, 1)
        print(f"\n== {label}: msg_text={T/1e6:.1f}M chars tool_results={TL/1e6:.1f}M bash={B/1e6:.1f}M read={R/1e6:.1f}M | "
              f"bash share of (text+tools)={B/denom*100:.1f}% read share of (text+tools)={R/denom*100:.1f}% of tool_results={B/max(TL,1)*100:.1f}%")
        nb = sum(s['nbash'] for s in grp)
        nbb = sum(s['nbound'] for s in grp)
        print(f"   bash calls={nb} self-bounded={nbb} ({nbb/max(nb,1)*100:.0f}%) trunc-marked results={sum(s['trunc'] for s in grp)} only-you-notes={sum(s['onlyyou'] for s in grp)} compactions={sum(s['comp'] for s in grp)}")
    agg = collections.Counter()
    for s in sessions:
        for k, v in s['bytool'].items():
            agg[k] += v
    print("\ntool_result chars by tool (all):", ', '.join(f"{k}={v/1e6:.2f}M" for k, v in agg.most_common(8)))


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog='measure.py',
        description="Measure Bash share and file-read share of local Claude Code transcript context "
                    "(context-economy Phase 1/2 gate instrument, relocated from outctl@94840d7).",
    )
    p.add_argument('--root', default=os.path.expanduser('~/.claude/projects'),
                    help='directory to scan for *.jsonl transcripts (default: ~/.claude/projects)')
    p.add_argument('--days', type=int, default=None,
                    help='restrict to transcripts modified in the last N days (default: all)')
    p.add_argument('--out', default=None,
                    help='write a JSON scorecard to this path instead of printing the diagnostic report')
    return p


def main(argv=None) -> int:
    args = build_argparser().parse_args(argv)
    files = find_transcripts(args.root, args.days)
    sessions = [scan_file(f, args.root) for f in files]
    if args.out:
        scorecard = build_scorecard(sessions, args.root, args.days)
        os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
        with open(args.out, 'w') as fh:
            json.dump(scorecard, fh, indent=2, sort_keys=True)
            fh.write('\n')
        print(f"wrote scorecard: {args.out}")
    else:
        print_report(sessions, len(files))
    return 0


if __name__ == '__main__':
    sys.exit(main())
