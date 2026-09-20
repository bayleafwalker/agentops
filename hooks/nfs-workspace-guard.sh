#!/usr/bin/env bash
# PreToolUse. Denies edits and git mutations against the legacy TrueNAS NFS
# workspace, /mnt/truenas/storage_layer/sealed/projects/<rest>, which looks
# like a canonical /projects/dev checkout but is a stale, months-old mirror --
# not a writable Git workspace. A Claude session committed into it on
# 2026-09-14 (see gitops-nixos docs/runbooks/workstation-projects-btrfs-migration.md).
#
# Scope:
#   - Edit / Write / MultiEdit / NotebookEdit whose target path (file_path or,
#     for NotebookEdit, notebook_path) resolves under the prefix.
#   - Bash commands that run a mutating git subcommand against a repo whose
#     effective path resolves under the prefix, via `git -C <path> ...`,
#     `cd <path> && git ...`, or a plain `git ...` when the event's own cwd is
#     under the prefix. Mutating: commit, push, merge, rebase, cherry-pick,
#     am, tag, stash, reset --hard, checkout -b, switch -c. Read-only git
#     (status, log, diff, show, fetch, ls-remote, and anything else not
#     listed above) is always allowed.
#
# Everything else is allowed, silently (exit 0), so normal sessions pay no
# cost. The headroom systemd writer is not a Claude tool and is unaffected.
#
# Operator override: AGENTOPS_ALLOW_NFS_WORKSPACE_WRITES=1 allows everything
# this hook would otherwise deny -- for a deliberate, operator-authorized
# write into the legacy workspace (e.g. recovering or inspecting it).
#
# FAILS OPEN. Anything this hook cannot parse -- missing python3, malformed
# event JSON, a command shape its conservative tokeniser does not understand
# -- is allowed, matching bounded-read-guard.sh and forge-sandbox-guard.sh.
set -uo pipefail

if [ "${AGENTOPS_ALLOW_NFS_WORKSPACE_WRITES:-}" = "1" ]; then
  exit 0
fi

command -v python3 >/dev/null 2>&1 || exit 0

# WL-D1: the event is captured here, rather than left for python to read
# directly off fd 0, so it survives after python exits and emit_decision
# (sourced below) can read .session_id from it for the gate log. The
# heredoc script is unchanged; it takes the same bytes over a pipe instead
# of inheriting fd 0 directly, and its own stdin-reading is identical
# either way.
EVENT="$(cat)"
_lib="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/lib/emit-decision.sh"
[ -r "$_lib" ] && . "$_lib"

# The script is fed on fd 3 so stdin (piped in below) stays the hook event JSON.
OUT="$(printf '%s' "$EVENT" | python3 /dev/fd/3 3<<'PYEOF'
import json
import os
import sys

PREFIX = "/mnt/truenas/storage_layer/sealed/projects"
CANONICAL = "/projects"

try:
    event = json.load(sys.stdin)
except Exception:
    sys.exit(0)                      # unparseable event: allow

if not isinstance(event, dict):
    sys.exit(0)

tool_name = event.get("tool_name")
tool_input = event.get("tool_input") or {}
if not isinstance(tool_input, dict):
    tool_input = {}


def under_prefix(path):
    """realpath -m equivalent: resolve symlinks, normalise, do not require
    the path to exist."""
    if not path or not isinstance(path, str):
        return None
    try:
        real = os.path.realpath(path)
    except Exception:
        return None
    if real == PREFIX or real.startswith(PREFIX + "/"):
        return real
    return None


def canonical_for(real_path):
    rest = real_path[len(PREFIX):].lstrip("/")
    return CANONICAL + ("/" + rest if rest else "")


def deny(target_real):
    canonical = canonical_for(target_real)
    reason = (
        "[nfs-workspace-guard.sh -- operator-configured PreToolUse hook, not "
        "agent-generated or third-party text]\n\n"
        f"Observation: the target ({target_real}) resolves under "
        f"{PREFIX}, the legacy TrueNAS NFS workspace. This holds "
        "months-stale repo checkouts that look like canonical /projects/dev "
        "but are recorded as not a writable Git workspace (source: "
        "gitops-nixos docs/runbooks/workstation-projects-btrfs-migration.md). "
        "A Claude session committed into it on 2026-09-14.\n\n"
        f"Use the canonical path instead: {canonical}\n\n"
        "Operator override: set AGENTOPS_ALLOW_NFS_WORKSPACE_WRITES=1 if this "
        "write into the legacy workspace is deliberate and authorized."
    )
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason}}))
    sys.exit(0)


# ------------------------------------------------------------- edit-family
EDIT_TOOLS = {"Edit", "Write", "MultiEdit"}
if tool_name in EDIT_TOOLS:
    real = under_prefix(tool_input.get("file_path"))
    if real:
        deny(real)
    sys.exit(0)

if tool_name == "NotebookEdit":
    real = under_prefix(tool_input.get("notebook_path"))
    if real:
        deny(real)
    sys.exit(0)

if tool_name != "Bash":
    sys.exit(0)

# ------------------------------------------------------------------- Bash
cmd = tool_input.get("command") or ""
if not isinstance(cmd, str) or not cmd.strip():
    sys.exit(0)

event_cwd = event.get("cwd")
if not isinstance(event_cwd, str):
    event_cwd = None

MUTATING_SIMPLE = {"commit", "push", "merge", "rebase", "cherry-pick", "am", "tag", "stash"}


def tokenise(s):
    """Shell-ish, quote-aware split into words and `&&`/`;`/`|`/`\\n`/`&`
    control operators. On anything surprising -- command substitution,
    subshells, brace expansion, an unterminated quote -- return None and the
    caller allows the command, same posture as bounded-read-guard.sh."""
    OPS = ("&&", "||", ";;", ";", "|", "\n", "&")
    toks, cur, i, n = [], "", 0, len(s)
    have_cur = False

    def flush():
        nonlocal cur, have_cur
        if have_cur:
            toks.append(("word", cur))
        cur, have_cur = "", False

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
            have_cur = True
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            cur += s[i + 1]
            i += 2
            continue
        if c in "$`(){}":
            return None               # command substitution / subshell / braces: give up
        matched_op = None
        for op in OPS:
            if s.startswith(op, i):
                matched_op = op
                break
        if matched_op:
            flush()
            toks.append(("op", matched_op))
            i += len(matched_op)
            continue
        if c.isspace():
            flush()
            i += 1
            continue
        cur += c
        have_cur = True
        i += 1
    flush()
    return toks


def split_commands(toks):
    """Split the token stream into individual simple commands (word lists),
    each tagged with the operator that preceded it (None for the first)."""
    commands, cur, preceding_op = [], [], None
    for kind, val in toks:
        if kind == "op":
            if cur:
                commands.append((preceding_op, cur))
            cur = []
            preceding_op = val
        else:
            cur.append(val)
    if cur:
        commands.append((preceding_op, cur))
    return commands


def parse_git(words):
    """words[0] == 'git'. Returns (dash_c_path, subcommand, rest_args)."""
    i, path, subcommand, rest = 1, None, None, []
    n = len(words)
    while i < n:
        w = words[i]
        if w == "-C" and i + 1 < n:
            path = words[i + 1]
            i += 2
            continue
        if w.startswith("-"):
            i += 1
            continue
        subcommand = w
        rest = words[i + 1:]
        break
    return path, subcommand, rest


def is_mutating(subcommand, args):
    if subcommand in MUTATING_SIMPLE:
        return True
    if subcommand == "reset" and "--hard" in args:
        return True
    if subcommand == "checkout" and "-b" in args:
        return True
    if subcommand == "switch" and "-c" in args:
        return True
    return False


toks = tokenise(cmd)
if toks is None:
    sys.exit(0)

commands = split_commands(toks)

cd_path = None  # tracks the most recent `cd <path>` in this command chain
for _op, words in commands:
    if not words:
        continue
    if words[0] == "cd" and len(words) >= 2:
        cd_path = words[1]
        continue
    if words[0] != "git":
        continue
    dash_c_path, subcommand, args = parse_git(words)
    if subcommand is None or not is_mutating(subcommand, args):
        continue
    effective_path = dash_c_path or cd_path or event_cwd
    real = under_prefix(effective_path)
    if real:
        deny(real)

sys.exit(0)
PYEOF
)"
RC=$?
[ -n "$OUT" ] && printf '%s\n' "$OUT"
if [ -n "$OUT" ] && printf '%s' "$OUT" | grep -q '"permissionDecision": "deny"' && command -v emit_decision >/dev/null 2>&1; then
  _tool="$(printf '%s' "$EVENT" | jq -r '.tool_name // "unknown"' 2>/dev/null || echo unknown)"
  emit_decision "nfs-workspace-guard.sh" "nfs-workspace" "$_tool" "deny"
fi
exit "$RC"
