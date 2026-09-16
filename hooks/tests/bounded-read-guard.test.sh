#!/usr/bin/env bash
# Tests for bounded-read-guard.sh (lever B of the context economy plan).
# Each case feeds a PreToolUse event on stdin and asserts the decision.
#   ./bounded-read-guard.test.sh          # run all
set -uo pipefail

HOOK="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/bounded-read-guard.sh"
[ -x "$HOOK" ] || { echo "not executable: $HOOK"; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
BIG="$TMP/big.md"      ; seq 1 733  > "$BIG"      # 733 lines, over threshold
SMALL="$TMP/small.yaml"; seq 1 42   > "$SMALL"    # 42 lines, under threshold
EDGE="$TMP/edge.txt"   ; seq 1 200  > "$EDGE"     # exactly at threshold
BIG2="$TMP/big2.md"    ; seq 1 400  > "$BIG2"

pass=0; fail=0

run() {  # run <command> -> prints decision: "deny" or "allow"
  local out
  out="$(jq -n --arg c "$1" \
    '{hook_event_name:"PreToolUse",tool_name:"Bash",tool_input:{command:$c}}' \
    | "$HOOK" 2>/dev/null)"
  if printf '%s' "$out" | grep -q '"permissionDecision" *: *"deny"'; then
    printf 'deny\n%s' "$out"
  else
    printf 'allow\n'
  fi
}

check() {  # check <expected> <name> <command> [substring the reason must hold]
  local want="$1" name="$2" cmd="$3" needle="${4:-}"
  local got body
  body="$(run "$cmd")"
  got="$(printf '%s' "$body" | head -1)"
  if [ "$got" != "$want" ]; then
    printf 'FAIL %-46s want=%s got=%s\n     cmd: %s\n' "$name" "$want" "$got" "$cmd"
    fail=$((fail + 1)); return
  fi
  if [ -n "$needle" ] && ! printf '%s' "$body" | grep -q -- "$needle"; then
    printf 'FAIL %-46s reason missing %q\n     cmd: %s\n' "$name" "$needle" "$cmd"
    fail=$((fail + 1)); return
  fi
  printf 'ok   %-46s %s\n' "$name" "$got"
  pass=$((pass + 1))
}

# ---------------------------------------------------------------- DENY cases
check deny  "cat of a 733-line file"            "cat $BIG"                 "733 lines"
check deny  "cat -n of a large file"            "cat -n $BIG"              "733 lines"
check deny  "bat of a large file"               "bat $BIG"                 "733 lines"
check deny  "sed -n '1,\$p' whole file"         "sed -n '1,\$p' $BIG"      "733 lines"
check deny  "sed -n 1,733p covers the file"     "sed -n 1,733p $BIG"       "733 lines"
check deny  "sed -n 1,5000p overshoots"         "sed -n '1,5000p' $BIG"    "733 lines"
check deny  "head -n 800 >= line count"         "head -n 800 $BIG"         "733 lines"
check deny  "head -1000 (bare -N form)"         "head -1000 $BIG"          "733 lines"
check deny  "one big file among small ones"     "cat $SMALL $BIG2"         "400 lines"
check deny  "cat piped only into tee"           "cat $BIG | tee /dev/null" "733 lines"
check deny  "large cat in a && chain"           "cd /tmp && cat $BIG"      "733 lines"

# --------------------------------------------------------------- ALLOW cases
check allow "cat piped to head"                 "cat $BIG | head -150"
check allow "cat piped to grep"                 "cat $BIG | grep -n foo"
check allow "cat piped to wc -l"                "cat $BIG | wc -l"
check allow "cat piped to jq"                   "cat $BIG | jq .name"
check allow "bounded sed range"                 "sed -n 1,60p $BIG"
check allow "offset sed range"                  "sed -n '400,460p' $BIG"
check allow "head -n 50 under the count"        "head -n 50 $BIG"
check allow "bare head (defaults to 10)"        "head $BIG"
check allow "tail -n 40"                        "tail -n 40 $BIG"
check allow "small file"                        "cat $SMALL"
check allow "several small files"               "cat $SMALL $SMALL $SMALL"
check allow "file exactly at the threshold"     "cat $EDGE"
check allow "non-existent path"                 "cat $TMP/nope.md"
check allow "heredoc containing the word cat"   "cat > $TMP/x <<'EOF'
cat $BIG
EOF"
check allow "redirect to a file, not to context" "cat $BIG > $TMP/copy.md"
check allow "grep over a large file"            "grep -n TODO $BIG"
check allow "explicit approval escape hatch"    "BOUNDED_READ_APPROVED=1 cat $BIG"
check allow "unparseable: variable expansion"   "cat \$MYFILE"
check allow "unparseable: command substitution" "cat \$(ls $BIG)"
check allow "sed without -n is not a range read" "sed 's/a/b/' $BIG"
check allow "non-read command mentioning cat"   "echo cat $BIG"
check allow "cat of a directory path"           "cat $TMP"

# ------------------------------------------------------------- env threshold
out="$(BOUNDED_READ_MAX_LINES=10 bash -c "jq -n --arg c 'cat $SMALL' \
  '{tool_name:\"Bash\",tool_input:{command:\$c}}' | '$HOOK'")"
if printf '%s' "$out" | grep -q '"deny"'; then
  printf 'ok   %-46s deny\n' "BOUNDED_READ_MAX_LINES=10 lowers threshold"; pass=$((pass + 1))
else
  printf 'FAIL %-46s want=deny got=allow\n' "BOUNDED_READ_MAX_LINES=10 lowers threshold"; fail=$((fail + 1))
fi

echo
echo "passed: $pass   failed: $fail"
[ "$fail" -eq 0 ]
