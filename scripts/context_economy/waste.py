# Provenance: relocated from outctl@94840d7 studies/context-economy/waste.py (outctl retired; agentops#2435).
"""Measure wasted Bash tool-result bytes (duplicates, errors, spool hints) in a transcript.

Refactored for import safety: the original outctl study ran entirely at module
scope as a side effect of `import waste`. Here the logic is factored into
`cls()` and `scan_root()`/`main()`, which only run when invoked directly.
Classification and waste-detection logic is unchanged from the outctl original.
"""
from __future__ import annotations

import collections
import glob
import hashlib
import json
import os
import re

CLS = [
    ('file-read', re.compile(r'\b(cat|sed -n|head|tail|bat)\b|<<')),
    ('git', re.compile(r'\bgit\b|\bgh\b|\bfj\b')),
    ('infra', re.compile(r'\b(kubectl|flux|talosctl|helm|journalctl|systemctl|nixos-rebuild|nix |ssh |docker|zfs|zpool|restic)\b')),
    ('test/build', re.compile(r'\b(pytest|ruff|mypy|uv run|go test|cargo|npm|mise run|make)\b')),
    ('search', re.compile(r'\b(grep|rg|find|ls|tree|wc)\b')),
    ('py/curl', re.compile(r'\bpython3?\b|\bcurl\b|\bjq\b')),
]


def cls(c: str) -> str:
    for n, r in CLS:
        if r.search(c):
            return n
    return 'other'


def scan_root(root: str):
    """Scan every transcript under `root`. Returns (G, per) matching the
    original script's module-level `G` (global waste counters) and `per`
    (per-session Bash byte totals, keyed by truncated filename).
    """
    G = dict(dup_bytes=0, dup_n=0, tot=0, n=0, errbytes=0, errn=0, hint=0, hintbytes=0)
    per = {}
    for f in glob.glob(root + '/**/*.jsonl', recursive=True):
        seen = set()
        name = {}
        cmd = {}
        by = collections.Counter()
        tot = 0
        text = 0
        for line in open(f, errors='replace'):
            try:
                d = json.loads(line)
            except Exception:
                continue
            m = d.get('message')
            if not isinstance(m, dict):
                continue
            c = m.get('content')
            if isinstance(c, str):
                text += len(c)
                continue
            if not isinstance(c, list):
                continue
            for b in c:
                if not isinstance(b, dict):
                    continue
                t = b.get('type')
                if t in ('text', 'thinking'):
                    text += len(b.get(t, ''))
                elif t == 'tool_use':
                    name[b['id']] = b.get('name')
                    inp = b.get('input') or {}
                    text += len(json.dumps(inp))
                    if b.get('name') == 'Bash':
                        cmd[b['id']] = inp.get('command', '') or ''
                elif t == 'tool_result':
                    cc = b.get('content')
                    s = ''.join(x.get('text', '') for x in cc if isinstance(x, dict)) if isinstance(cc, list) else (cc if isinstance(cc, str) else '')
                    if name.get(b.get('tool_use_id')) != 'Bash':
                        text += len(s)
                        continue
                    L = len(s)
                    tot += L
                    G['tot'] += L
                    G['n'] += 1
                    h = hashlib.md5(s.encode()).hexdigest()
                    if L > 200 and h in seen:
                        G['dup_bytes'] += L
                        G['dup_n'] += 1
                    seen.add(h)
                    if b.get('is_error'):
                        G['errbytes'] += L
                        G['errn'] += 1
                    if 'Only you see that command' in s or "user's terminal shows" in s:
                        G['hint'] += 1
                        G['hintbytes'] += L
                    by[cls(cmd.get(b['tool_use_id'], ''))] += L
        if tot > 0 and '/subagents/' not in f:
            per[os.path.basename(f)[:8]] = (tot, text, by)
    return G, per


def main(root: str | None = None) -> None:
    root = root or os.path.expanduser('~/.claude/projects')
    G, per = scan_root(root)
    print(
        "Bash results total=%.1fM n=%d | exact-duplicate results(>200B): n=%d bytes=%.2fM (%.0f%%) | "
        "is_error: n=%d bytes=%.2fM | results carrying 'only you see' hint: %d (%.2fM)"
        % (G['tot']/1e6, G['n'], G['dup_n'], G['dup_bytes']/1e6, G['dup_bytes']/max(G['tot'], 1)*100,
           G['errn'], G['errbytes']/1e6, G['hint'], G['hintbytes']/1e6)
    )
    print("\nTop-level sessions with highest Bash share, class composition:")
    for k, (tot, text, by) in sorted(per.items(), key=lambda kv: -kv[1][0]/(kv[1][0]+kv[1][1]))[:8]:
        print(f"  {k} bash={tot//1000}K share={tot/(tot+text)*100:.0f}% :: " + ', '.join(f"{c}={v*100//tot}%" for c, v in by.most_common(4)))


if __name__ == '__main__':
    main()
