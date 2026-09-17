#!/usr/bin/env bash
# Oracle for push-landed-check.sh: it checks the PUSHED repository against the canonical remote.
#
#   REQ-001 `git -C <worktree> push origin HEAD:main` that landed -> no warning
#   REQ-002 `cd <repo> && git push` that landed -> no warning
#   REQ-003 a genuinely unlanded push still warns
#   REQ-004 session cwd in a different (unlanded) repo does not override the pushed repo
#   REQ-005 `git -C <dir> push` from an unlanded repo warns (resolution is not a blanket pass)
#   REQ-006 a push naming a branch judges that branch, not a stale checked-out main in the event cwd
set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
hook="$(cd -- "$here/.." && pwd -P)/push-landed-check.sh"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

mkrepo() { # <name> -> repo at $tmp/<name> with bare canonical remote "canon" (origin is a decoy)
  local r="$tmp/$1"
  git init -q --bare "$tmp/$1.git"
  git init -q -b main "$r"
  git -C "$r" commit -q --allow-empty -m init
  git -C "$r" remote add origin "$tmp/$1-decoy.git"
  git -C "$r" remote add canon "$tmp/$1.git"
  git -C "$r" config claude.canonicalRemote canon
  git -C "$r" push -q canon main
}

run_hook() { # <cwd> <command>
  jq -cn --arg c "$2" --arg d "$1" '{tool_input:{command:$c}, cwd:$d}' | bash "$hook"
}
assert_quiet() { local o; o="$(run_hook "$1" "$2")"; [ -z "$o" ] || fail "$3: expected no warning, got: $o"; }
assert_warns() { local o; o="$(run_hook "$1" "$2")"; printf '%s' "$o" | grep -q 'WORK IS NOT LANDED' || fail "$3: expected warning, got: '$o'"; }

# pushed: a worktree on branch fix/x whose HEAD was pushed to canon main.
mkrepo pushed
git -C "$tmp/pushed" worktree add -q -b fix/x "$tmp/wt" main
git -C "$tmp/wt" commit -q --allow-empty -m change
git -C "$tmp/wt" push -q canon HEAD:main

mkrepo plain  # main checkout, pushed to canon main

# other: the session's repo, with an unpushed commit on a branch the remote lacks.
mkrepo other
git -C "$tmp/other" checkout -q -b handoff
git -C "$tmp/other" commit -q --allow-empty -m unpushed

assert_quiet "$tmp/other" "git -C $tmp/wt push canon HEAD:main" REQ-001
assert_quiet "$tmp/other" "git -C '$tmp/wt' push origin HEAD:main" REQ-001-quoted
assert_quiet "$tmp/other" "cd $tmp/wt && git push canon HEAD:main" REQ-002
assert_quiet "$tmp/other" "cd $tmp/plain && git push" REQ-002-main
assert_warns "$tmp/other" "git push origin handoff" REQ-003
assert_warns "$tmp" "cd $tmp/other && git push origin handoff" REQ-003-cd
assert_quiet "$tmp/other" "git -C $tmp/wt push" REQ-004
assert_warns "$tmp/wt" "git -C $tmp/other push origin handoff" REQ-005
# stale: main checkout behind canon (another clone advanced it); the push names a
# worktree branch this checkout does not have, or a landed branch it does have.
mkrepo stale
git clone -q -b main "$tmp/stale.git" "$tmp/stale-clone"
git -C "$tmp/stale-clone" commit -q --allow-empty -m ahead
git -C "$tmp/stale-clone" push -q origin main
git -C "$tmp/stale" fetch -q canon
git -C "$tmp/stale" branch -q feat canon/main
assert_quiet "$tmp/stale" "git push -u origin s2/not-here" REQ-006-foreign-ref
assert_quiet "$tmp/stale" "git push --force-with-lease canon feat" REQ-006-landed-ref
assert_warns "$tmp/stale" "git push canon main" REQ-006-stale-main
assert_quiet "$tmp/stale" "git push origin --delete feat" REQ-006-delete
# Non-push commands never trigger.
assert_quiet "$tmp/other" "git -C $tmp/other status" non-push

echo "PASS test-push-landed-check"
