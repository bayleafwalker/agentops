#!/usr/bin/env bash
# The wrapper preserves event bytes, resolves CLI fallbacks and never denies a tool.
set -euo pipefail
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
task_tmp=$(mktemp -d)
trap 'rm -rf -- "$task_tmp"' EXIT
mkdir -p "$task_tmp/repo/hooks" "$task_tmp/repo/bin" "$task_tmp/path"
cp "$here/../session-skill.sh" "$task_tmp/repo/hooks/session-skill.sh"
chmod +x "$task_tmp/repo/hooks/session-skill.sh"
cat > "$task_tmp/path/agentops" <<'CLI'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$TASK_ARGS"
cat > "$TASK_EVENT"
exit "${TASK_EXIT:-0}"
CLI
chmod +x "$task_tmp/path/agentops"
export TASK_ARGS="$task_tmp/args" TASK_EVENT="$task_tmp/event"
printf '{"tool_name":"Skill","tool_input":{"skill":"sprint-resume"}}\n' > "$task_tmp/input"
PATH="$task_tmp/path:$PATH" "$task_tmp/repo/hooks/session-skill.sh" < "$task_tmp/input"
printf 'session-binding\n--record-skill\n' > "$task_tmp/expected-args"
cmp "$task_tmp/expected-args" "$TASK_ARGS"
cmp "$task_tmp/input" "$TASK_EVENT"
# A failed recorder remains observational.
TASK_EXIT=17 PATH="$task_tmp/path:$PATH" "$task_tmp/repo/hooks/session-skill.sh" < "$task_tmp/input"
# Isolate PATH while retaining the wrapper and stub's required system tools.
ln -s "$(command -v bash)" "$task_tmp/path/bash"
ln -s "$(command -v cat)" "$task_tmp/path/cat"
ln -s "$(command -v readlink)" "$task_tmp/path/readlink"
mv "$task_tmp/path/agentops" "$task_tmp/repo/bin/agentops"
PATH="$task_tmp/path" "$task_tmp/repo/hooks/session-skill.sh" < "$task_tmp/input"
cmp "$task_tmp/input" "$TASK_EVENT"
# A symlinked hook still finds its own repository CLI.
ln -s "$task_tmp/repo/hooks/session-skill.sh" "$task_tmp/path/skill-hook"
PATH="$task_tmp/path" "$task_tmp/path/skill-hook" < "$task_tmp/input"
cmp "$task_tmp/input" "$TASK_EVENT"
rm "$task_tmp/repo/bin/agentops" "$TASK_ARGS" "$TASK_EVENT"
PATH="$task_tmp/path" "$task_tmp/repo/hooks/session-skill.sh" < "$task_tmp/input"
[[ ! -e "$TASK_ARGS" && ! -e "$TASK_EVENT" ]]
printf 'session skill wrapper tests passed\n'
