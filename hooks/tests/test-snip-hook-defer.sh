#!/usr/bin/env bash
# REQ-005 no rewrite inside an isolated worktree cwd; REQ-006 snip still receives the hook input on stdin.
# REQ-001 no permissionDecision in output; REQ-002 updatedInput preserved; REQ-003 empty snip output stays empty; REQ-004 missing binary fails open.
set -u; d=$(dirname "$0"); hook="$d/../snip-hook-defer.sh"; fail=0
fake=$(mktemp); cat > "$fake" <<'F'
#!/usr/bin/env bash
echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"snip auto-rewrite","updatedInput":{"command":"snip run -- git push"}}}'
F
chmod +x "$fake"
o=$(echo '{"tool_name":"Bash","tool_input":{"command":"git push"}}' | SNIP_BIN="$fake" "$hook")
[ "$(jq -r '.hookSpecificOutput | has("permissionDecision")' <<<"$o")" = false ] || { echo "REQ-001 fail: $o"; fail=1; }
[ "$(jq -r .hookSpecificOutput.updatedInput.command <<<"$o")" = "snip run -- git push" ] || { echo "REQ-002 fail"; fail=1; }
o=$(echo '{"cwd":"/r/.claude/worktrees/wf-1","tool_name":"Bash","tool_input":{"command":"git status"}}' | SNIP_BIN="$fake" "$hook"); [ -z "$o" ] || { echo "REQ-005 fail: $o"; fail=1; }
o=$(echo '{"cwd":"/r/_wt/x","tool_name":"Bash","tool_input":{"command":"git push"}}' | SNIP_BIN="$fake" "$hook"); [ -n "$o" ] || { echo "REQ-005 control fail"; fail=1; }
printf '#!/usr/bin/env bash\ngrep -q marker-42 && echo "{\\"hookSpecificOutput\\":{\\"updatedInput\\":{\\"command\\":\\"ok\\"}}}"\n' > "$fake"
o=$(echo '{"tool_input":{"command":"marker-42"}}' | SNIP_BIN="$fake" "$hook"); [ "$(jq -r .hookSpecificOutput.updatedInput.command <<<"$o" 2>/dev/null)" = ok ] || { echo "REQ-006 fail: $o"; fail=1; }
printf '#!/usr/bin/env bash\nexit 0\n' > "$fake"
o=$(echo '{}' | SNIP_BIN="$fake" "$hook"); [ -z "$o" ] || { echo "REQ-003 fail: $o"; fail=1; }
o=$(echo '{}' | SNIP_BIN=/nonexistent "$hook"); [ -z "$o" ] || { echo "REQ-004 fail"; fail=1; }
rm -f "$fake"; [ $fail = 0 ] && echo "snip-hook-defer: 6/6 pass"; exit $fail
