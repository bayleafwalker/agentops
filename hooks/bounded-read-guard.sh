#!/usr/bin/env bash
# PreToolUse/Bash. Refuses UNBOUNDED whole-file reads of large files.
#
# Written 2026-09-12 as lever B of outctl/docs/CONTEXT_ECONOMY_PLAN_2026-09-12.md.
# Measured over 220 transcripts: Bash results are 38% of top-level session
# content, 60% of those bytes are file reads, and the 242 results over 10 KB
# (22% of all Bash bytes) were dominated by whole-file `cat` of 20-29 KB
# configs and docs. The cost is not the tool -- `sed -n 1,60p` and Read with
# `limit` cost the same -- it is reading a whole file when a range, a grep, or
# a subagent would have answered the question.
#
# SCOPE, stated honestly. This is a guardrail against HABIT, not a control. It
# pattern-matches the command string; `python3 -c 'print(open(f).read())'`,
# `while read` loops, `xargs cat` and anything built from variables walk
# straight past it. It exists because the behaviour it addresses is reflexive,
# and reflexes match patterns.
#
# It DENIES and never rewrites. Lever D (silently rewriting `cat FILE` into
# `head -c 8000 FILE`) was rejected in the plan: truncation the model cannot
# see is worse than a refusal it can read.
#
# FAILS OPEN. Unlike secret-read-guard.sh, the harm here is wasted context, not
# leaked secrets. Anything it cannot parse -- missing python3, malformed JSON,
# quoting it does not understand, a path that does not exist -- is allowed.
set -uo pipefail

command -v python3 >/dev/null 2>&1 || exit 0

# The script is fed on fd 3 so that fd 0 stays the hook event JSON.
exec python3 /dev/fd/3 3<<'PYEOF'
import json, os, re, sys

try:
    event = json.load(sys.stdin)
except Exception:
    sys.exit(0)                      # unparseable event: allow

cmd = ((event or {}).get("tool_input") or {}).get("command") or ""
if not isinstance(cmd, str) or not cmd.strip():
    sys.exit(0)

# Heredocs are content the model is WRITING, not reading. Never touch them.
if "<<" in cmd:
    sys.exit(0)

# Explicit, auditable escape hatch, for the case where the whole file really is
# the answer (a 300-line file being rewritten wholesale, a diff of a config).
if "BOUNDED_READ_APPROVED=1" in cmd:
    sys.exit(0)

try:
    THRESHOLD = int(os.environ.get("BOUNDED_READ_MAX_LINES", "200"))
except ValueError:
    THRESHOLD = 200
if THRESHOLD <= 0:
    sys.exit(0)


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason}}))
    sys.exit(0)


# ---------------------------------------------------------------- tokenising
OPS = (";;", "&&", "||", ";", "|", "\n", "&")


def tokenise(s):
    """Shell-ish split into words and control operators. Quote-aware, and
    deliberately dumb about everything else -- on anything surprising we return
    None and the caller allows the command."""
    toks, cur, i, n = [], "", 0, len(s)
    quoted = False          # current word contained quotes (so: not a glob/op)
    while i < n:
        c = s[i]
        if c in "'\"":
            q, i, buf = c, i + 1, ""
            while i < n and s[i] != q:
                if q == '"' and s[i] == "\\" and i + 1 < n:
                    buf += s[i + 1]
                    i += 2
                    continue
                buf += s[i]
                i += 1
            if i >= n:
                return None          # unterminated quote: unparseable
            cur += buf
            quoted = True
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            cur += s[i + 1]
            i += 2
            continue
        if c in "$`(){}":
            # command substitution, subshells, brace expansion: give up.
            return None
        if c.isspace() and c != "\n":
            if cur or quoted:
                toks.append(("w", cur))
            cur, quoted = "", False
            i += 1
            continue
        op = next((o for o in OPS if s.startswith(o, i)), None)
        if op:
            if cur or quoted:
                toks.append(("w", cur))
            cur, quoted = "", False
            toks.append(("op", op))
            i += len(op)
            continue
        if c in "<>":
            if cur or quoted:
                toks.append(("w", cur))
            cur, quoted = "", False
            toks.append(("op", ">" if c == ">" else "<"))
            i += 1
            continue
        cur += c
        i += 1
    if cur or quoted:
        toks.append(("w", cur))
    return toks


toks = tokenise(cmd)
if toks is None:
    sys.exit(0)

# segments split on ; && || newline &   ; stages within a segment split on |
segments, seg = [], [[]]
for kind, val in toks:
    if kind == "op" and val in (";", "&&", "||", "\n", "&", ";;"):
        segments.append(seg)
        seg = [[]]
    elif kind == "op" and val == "|":
        seg.append([])
    else:
        seg[-1].append((kind, val))
segments.append(seg)

# Stages that merely pass bytes through: a pipe into one of these still dumps
# the whole file. Anything else downstream (head, grep, wc, jq, python, ...)
# bounds or consumes the output, and the command is allowed.
PASSTHROUGH = {"tee", "cat", "nl", "tr", "rev", "expand", "unexpand", "pv"}


def lines_of(path):
    try:
        p = os.path.expanduser(path)
        if not os.path.isfile(p):
            return None
        n = 0
        with open(p, "rb") as fh:
            for _ in fh:
                n += 1
        return n
    except Exception:
        return None


def hint(path, n, what):
    return (
        "BLOCKED: %s would read all %d lines of %s into the session transcript."
        "\n\nMeasured: file reads are 60%% of Bash result bytes and the largest "
        "single results in the corpus were whole-file cats of configs and docs. "
        "Read what the task needs, not the file.\n\n"
        "Instead:\n"
        "  sed -n 'START,ENDp' %s        # the range you actually need\n"
        "  grep -n 'PATTERN' %s          # find the range first\n"
        "  Read tool with offset/limit\n"
        "  an Explore subagent, if answering needs most of the file or several "
        "files -- it returns the conclusion and the parent keeps only that\n\n"
        "Threshold is %d lines (BOUNDED_READ_MAX_LINES). If the whole file "
        "genuinely is the answer, re-issue with BOUNDED_READ_APPROVED=1 prefixed."
        % (what, n, path, path, path, THRESHOLD))


def words(stage):
    return [v for k, v in stage if k == "w"]


def has_redirect(stage):
    return any(k == "op" and v in (">", "<") for k, v in stage)


def strip_env(w):
    """Drop leading VAR=value assignments and a `command`/`sudo` prefix."""
    i = 0
    while i < len(w) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w[i]):
        i += 1
    while i < len(w) and w[i] in ("command", "sudo", "time", "nice", "stdbuf"):
        i += 1
        while i < len(w) and w[i].startswith("-"):
            i += 1
    return w[i:]


for seg in segments:
    stages = [s for s in seg if words(s)]
    if not stages:
        continue
    if len(stages) > 1:
        downstream = [strip_env(words(s)) for s in stages[1:]]
        if any(d and os.path.basename(d[0]) not in PASSTHROUGH for d in downstream):
            continue                 # something downstream bounds/consumes it
    first = stages[0]
    if has_redirect(first):
        continue                     # output goes to a file, not the transcript
    w = strip_env(words(first))
    if not w:
        continue
    prog = os.path.basename(w[0])
    args = w[1:]

    # ---- cat / bat: any single target over the threshold ------------------
    if prog in ("cat", "bat", "batcat"):
        if any(a in ("-h", "--help", "--version") for a in args):
            continue
        files = [a for a in args if not a.startswith("-")]
        for f in files:
            n = lines_of(f)
            if n is not None and n > THRESHOLD:
                deny(hint(f, n, "`%s %s`" % (prog, f)))
        continue

    # ---- head -n NNN / head -NNN, where NNN covers the file ---------------
    if prog == "head":
        if any(a.startswith("-c") or a == "--bytes" for a in args):
            continue
        want, files, i = None, [], 0
        while i < len(args):
            a = args[i]
            if a in ("-n", "--lines"):
                i += 1
                if i < len(args) and re.fullmatch(r"[+-]?\d+", args[i]):
                    want = abs(int(args[i]))
                i += 1
                continue
            m = re.fullmatch(r"-n?(\d+)", a) or re.fullmatch(r"--lines=(\d+)", a)
            if m:
                want = int(m.group(1))
                i += 1
                continue
            if a.startswith("-"):
                i += 1
                continue
            files.append(a)
            i += 1
        if want is None:
            continue                 # bare `head` = 10 lines, bounded
        for f in files:
            n = lines_of(f)
            if n is not None and n > THRESHOLD and want >= n:
                deny(hint(f, n, "`head -n %d %s`" % (want, f)))
        continue

    # ---- sed -n '1,$p' / sed -n 1,NNNp, where the range covers the file ---
    if prog == "sed":
        if "-n" not in args and not any(
                re.fullmatch(r"-[a-zA-Z]*n[a-zA-Z]*", a) for a in args):
            continue
        script, files, i = None, [], 0
        while i < len(args):
            a = args[i]
            if a in ("-e", "--expression", "-f", "--file", "-i"):
                i += 1
                if script is None and i < len(args):
                    script = args[i]
                i += 1
                continue
            if a.startswith("-"):
                i += 1
                continue
            if script is None:
                script = a
            else:
                files.append(a)
            i += 1
        if script is None:
            continue
        m = re.fullmatch(r"\s*(\d+)?\s*,\s*(\$|\d+)\s*p\s*;?\s*", script)
        if not m:
            continue                 # not a plain range print: allow
        start = int(m.group(1)) if m.group(1) else 1
        if start > 1:
            continue                 # a genuine offset read
        for f in files:
            n = lines_of(f)
            if n is None or n <= THRESHOLD:
                continue
            end = n if m.group(2) == "$" else int(m.group(2))
            if end >= n:
                deny(hint(f, n, "`sed -n '%s' %s`" % (script.strip(), f)))
        continue

sys.exit(0)
PYEOF
