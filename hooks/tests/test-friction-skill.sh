#!/usr/bin/env bash
# T-5 oracle, written from the handoff-doc rows (T-5, and T-4's CLI corrections
# that bound it) and nothing else:
#
#   REQ-001 the /friction skill's command records the note as
#           `auditctl add --type workflow.friction --summary "<note>"`
#           (argv asserted exactly for those tokens; --actor is allowed because
#           the CLI requires it, T-4)
#   REQ-002 the command passes no `session:` ref -- auditctl rejects that prefix
#           outright and the note would be lost
#   REQ-003 the command succeeds against the CLI (stub exits 0 only when argv
#           is well-formed: every flag has a value)
#
# The skill is a SKILL.md, so "its command" is the bash fenced block it tells
# the caller to run. The oracle extracts that block, fills the placeholders the
# way a caller would, and runs it with a stub auditctl on PATH that logs argv.
set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
skill="$(cd -- "$here/../.." && pwd -P)/skills/friction/SKILL.md"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
assert_eq() { [[ "$2" == "$3" ]] || fail "$1: expected '$3', got '$2'"; }

[[ -f "$skill" ]] || fail "skill not found at $skill"

# Stub auditctl: one argv element per line, then a minimal sanity check.
mkdir -p "$tmp/bin"
argv_log="$tmp/auditctl.argv"
cat > "$tmp/bin/auditctl" <<STUB
#!/usr/bin/env bash
: > "$argv_log"
for a in "\$@"; do printf '%s\n' "\$a" >> "$argv_log"; done
prev=""
for a in "\$@"; do
  if [[ "\$prev" == --* && "\$a" == --* ]]; then echo "auditctl: \$prev needs a value" >&2; exit 2; fi
  prev="\$a"
done
[[ "\$prev" == --* ]] && { echo "auditctl: \$prev needs a value" >&2; exit 2; }
echo "ad:STUB0000000000000000000000"
STUB
chmod +x "$tmp/bin/auditctl"
export PATH="$tmp/bin:$PATH"

# Extract the first bash fenced block from the skill.
block="$(awk '/^[[:space:]]*```bash[[:space:]]*$/{on=1; next} /^[[:space:]]*```[[:space:]]*$/{if(on) exit} on' "$skill")"
[[ -n "$block" ]] || fail "SKILL.md has no bash fenced block to run"
printf '%s\n' "$block" | grep -q 'auditctl' || fail "the skill's command does not invoke auditctl"

note="The untracked-file guard failed the packet because settings.local.json is untracked"
session_id="sess-t5-oracle"

# Fill placeholders the way a caller would: <one sentence> is the note, the
# session placeholder is the id, any other <...> placeholder is free text.
script="$(printf '%s\n' "$block" \
  | sed -e "s|<one sentence>|$note|g" \
        -e "s|<session id[^>]*>|$session_id|g" \
        -e "s|<[^>]*>|placeholder text|g")"

printf '%s\n' "$script" > "$tmp/friction.sh"
if ! (cd "$tmp" && USER="t5-oracle" bash "$tmp/friction.sh" >"$tmp/out" 2>"$tmp/err"); then
  fail "the skill's command failed: $(cat "$tmp/err")"
fi
[[ -f "$argv_log" ]] || fail "auditctl was never invoked"

mapfile -t argv < "$argv_log"

# REQ-001: exact tokens.
assert_eq "argv[0]" "${argv[0]:-}" "add"
type_value=""; summary_value=""; actor_seen=0
for ((i = 0; i < ${#argv[@]}; i++)); do
  case "${argv[$i]}" in
    --type) type_value="${argv[$((i + 1))]:-}" ;;
    --summary) summary_value="${argv[$((i + 1))]:-}" ;;
    --actor) actor_seen=1 ;;
  esac
done
assert_eq "--type" "$type_value" "workflow.friction"
assert_eq "--summary" "$summary_value" "$note"
[[ "$actor_seen" -eq 1 ]] || fail "--actor missing: the CLI requires it (T-4), so the note would be lost"

# REQ-002: no session: ref, in any spelling.
for ((i = 0; i < ${#argv[@]}; i++)); do
  a="${argv[$i]}"
  [[ "$a" == session:* ]] && fail "argv carries a session: ref ('$a'); auditctl rejects it"
  ref_flag="--ref"
  if [[ "$a" == "$ref_flag" || "$a" == "$ref_flag="* ]]; then
    v="${a#"$ref_flag="}"; [[ "$a" == "$ref_flag" ]] && v="${argv[$((i + 1))]:-}"
    [[ "$v" == session:* ]] && fail "a ref with the session prefix is passed; auditctl rejects it"
    case "$v" in wi:*|ka:*|ad:*|sha:*|pr:*|sprint:*|capsule:*) ;; *) fail "ref '$v' uses a prefix auditctl rejects";; esac
  fi
done

# The session id must still be recorded somewhere the CLI accepts (metadata),
# since the ref path is closed.
grep -q "$session_id" "$argv_log" || fail "the session id is not carried anywhere in the auditctl call"

printf 'PASS: friction skill oracle (T-5): %s argv tokens, type=workflow.friction, summary exact, no session: ref\n' "${#argv[@]}"
