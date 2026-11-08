#!/usr/bin/env bash
# Synchronize shared agent assets from the workstation to the isolated devbox-vm.
set -euo pipefail

readonly DEFAULT_HOST="devbox-agent"
readonly DEFAULT_REMOTE_ROOT="/projects/dev"
readonly COST_LOG_RELATIVE_PATH=".claude/session-costs.jsonl"
readonly MAINTENANCE_HOOK=".claude/hooks/sprintctl-maintain-check.sh"
readonly COST_HOOK=".claude/hooks/log-session-cost.sh"

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
local_root="$(cd -- "$script_dir/../.." && pwd -P)"
host="$DEFAULT_HOST"
remote_root="$DEFAULT_REMOTE_ROOT"
apply_changes=false

usage() {
  cat <<'EOF'
Usage: sync-devbox.sh [--dry-run | --apply] [--host HOST] [--remote-root PATH]

Synchronize shared guidance, workspace templates, Claude hooks, and
known hook registrations from this workstation to an isolated devbox-vm clone.
The default is a read-only dry run. --apply is required for every remote or
local mutation.

The script intentionally does not run git pull, install tools, delete remote
files, reconcile infrastructure, or overwrite remote Claude permissions. It
backs up overwritten remote files, merges only known hook registrations, and
appends only unseen stable-session cost records.
EOF
}

die() {
  printf 'sync-devbox: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "required command is unavailable: $1"
}

validate_arguments() {
  [[ "$host" =~ ^[A-Za-z0-9._-]+$ ]] || die "host may contain only letters, digits, dots, underscores, and hyphens"
  [[ "$remote_root" == /* && "$remote_root" != *".."* ]] || die "remote root must be an absolute path without '..'"
}

remote_bash() {
  ssh -o BatchMode=yes "$host" bash -s -- "$@"
}

remote_preflight() {
  remote_bash "$remote_root" <<'REMOTE'
set -euo pipefail

remote_root="$1"
test -d "$remote_root"
test -d "$remote_root/agentops/.git"
command -v git >/dev/null
command -v jq >/dev/null
command -v rsync >/dev/null
printf 'Remote preflight passed for %s\n' "$remote_root"
REMOTE
}

template_drift_report() {
  local -a options=(
    --archive
    --itemize-changes
    --dry-run
    --exclude='__pycache__/'
    --exclude='*.pyc'
    --exclude='.pytest_cache/'
    --rsh "ssh -o BatchMode=yes"
  )

  rsync "${options[@]}" \
    "$local_root/agentops/templates/workspace/" \
    "$host:$remote_root/agentops/templates/workspace/"
}

inspect_remote_templates() {
  local inspection
  local template_drift

  if inspection="$(remote_bash "$remote_root" 2>&1 <<'REMOTE'
set -euo pipefail

remote_root="$1"
status="$(git -C "$remote_root/agentops" status --porcelain -- templates/workspace)"
if [[ -n "$status" ]]; then
  printf 'Remote agentops template paths are dirty:\n%s\n' "$status"
  exit 3
fi
printf 'Remote agentops template paths are clean.\n'
REMOTE
)"; then
    printf '%s\n' "$inspection"
    return
  fi

  if ! template_drift="$(template_drift_report)"; then
    die "could not compare local canonical templates with the remote tree"
  fi

  if [[ -z "$template_drift" ]]; then
    printf 'Remote template paths are dirty but match the local canonical source.\n'
    return
  fi

  printf '%s\n' "$inspection" >&2
  printf 'Remote template paths differ from the local canonical source:\n%s\n' "$template_drift" >&2
  if "$apply_changes"; then
    die "refusing to overwrite dirty remote agentops template paths"
  fi
  printf 'Dry run will report synchronization changes but cannot safely apply them until the remote paths are clean.\n' >&2
}

prepare_remote_apply() {
  local backup_root="$1"

  remote_bash "$remote_root" "$backup_root" <<'REMOTE'
set -euo pipefail

remote_root="$1"
backup_root="$2"
mkdir -p \
  "$remote_root/.claude/hooks" \
  "$remote_root/.claude/scripts" \
  "$remote_root/agentops/templates/workspace" \
  "$backup_root"
REMOTE
}

sync_file() {
  local source_path="$1"
  local destination_path="$2"
  local backup_root="$3"
  local -a options=(--archive --itemize-changes --rsh "ssh -o BatchMode=yes")

  [[ -f "$source_path" ]] || die "expected source file is missing: $source_path"

  if "$apply_changes"; then
    options+=(--backup --backup-dir="$backup_root")
  else
    options+=(--dry-run)
  fi

  rsync "${options[@]}" "$source_path" "$host:$destination_path"
}

sync_tree() {
  local source_path="$1"
  local destination_path="$2"
  local backup_root="$3"
  local -a options=(
    --archive
    --itemize-changes
    --exclude='__pycache__/'
    --exclude='*.pyc'
    --exclude='.pytest_cache/'
    --rsh "ssh -o BatchMode=yes"
  )

  [[ -d "$source_path" ]] || die "expected source directory is missing: $source_path"

  if "$apply_changes"; then
    options+=(--backup --backup-dir="$backup_root")
  else
    options+=(--dry-run)
  fi

  rsync "${options[@]}" "$source_path/" "$host:$destination_path/"
}

settings_payload() {
  local source_path="$1"

  jq -ce --arg remote_root "$remote_root" '
    def shared_hook:
      . == "/projects/dev/.claude/hooks/log-session-cost.sh"
      or . == "/projects/dev/.claude/hooks/sprintctl-maintain-check.sh";
    {
      hooks: (
        (.hooks // {})
        | with_entries(
            .value |= [
              .[]
              | select(
                  any((.hooks // [])[]?;
                    .type == "command" and (.command | shared_hook)
                  )
                )
            ]
          )
        | with_entries(select(.value | length > 0))
      )
    }
    | walk(
        if type == "object" and (.command? | type) == "string" then
          .command |= sub("^/projects/dev"; $remote_root)
        else
          .
        end
      )
  ' "$source_path"
}

merge_remote_settings() {
  local relative_path="$1"
  local source_path="$local_root/$relative_path"
  local target_path="$remote_root/$relative_path"
  local backup_root="$2"
  local mode="dry-run"
  local payload
  local encoded_payload

  [[ -f "$source_path" ]] || return
  payload="$(settings_payload "$source_path")"
  [[ "$(jq -r '.hooks | length' <<<"$payload")" != "0" ]] || return
  encoded_payload="$(printf '%s' "$payload" | base64 | tr -d '\n')"

  if "$apply_changes"; then
    mode="apply"
  fi

  remote_bash "$target_path" "$relative_path" "$mode" "$backup_root" "$encoded_payload" <<'REMOTE'
set -euo pipefail

target_path="$1"
relative_path="$2"
mode="$3"
backup_root="$4"
encoded_payload="$5"
current_file="$(mktemp)"
incoming_file="$(mktemp)"
merged_file="$(mktemp)"
trap 'rm -f -- "${current_file:-}" "${incoming_file:-}" "${merged_file:-}"' EXIT

if [[ -f "$target_path" ]]; then
  cp "$target_path" "$current_file"
else
  printf '{}\n' > "$current_file"
fi

printf '%s' "$encoded_payload" | base64 --decode > "$incoming_file"
jq -e . "$current_file" >/dev/null
jq -e . "$incoming_file" >/dev/null

jq --slurpfile incoming "$incoming_file" '
  def has_command($event_name; $command):
    [(.hooks[$event_name] // [])[]? | (.hooks // [])[]?
      | select(.type == "command") | .command]
    | index($command) != null;

  reduce (($incoming[0].hooks // {}) | to_entries[]) as $event
    (.;
      .hooks = (.hooks // {})
      | .hooks[$event.key] = (.hooks[$event.key] // [])
      | reduce $event.value[]? as $registration
          (.;
            [($registration.hooks // [])[]?
              | select(.type == "command" and (.command | type) == "string")
              | .command] as $commands
            | . as $current
            | if ($commands | length) == 0 then
                .
              elif all($commands[]; . as $command
                | ($current | has_command($event.key; $command))) then
                .
              else
                .hooks[$event.key] += [$registration]
              end
          )
    )
' "$current_file" > "$merged_file"

if [[ "$(jq -S -c . "$current_file")" == "$(jq -S -c . "$merged_file")" ]]; then
  printf 'Settings already contain shared hooks: %s\n' "$target_path"
  exit 0
fi

if [[ "$mode" != "apply" ]]; then
  printf 'Would merge shared hooks into: %s\n' "$target_path"
  exit 0
fi

mkdir -p "$(dirname "$target_path")" "$backup_root/$(dirname "$relative_path")"
if [[ -f "$target_path" ]]; then
  cp --preserve=mode,timestamps "$target_path" "$backup_root/$relative_path"
  chmod --reference="$target_path" "$merged_file"
else
  chmod 600 "$merged_file"
fi
mv "$merged_file" "$target_path"
printf 'Merged shared hooks into: %s\n' "$target_path"
REMOTE
}

read_remote_cost_log() {
  local target_path="$remote_root/$COST_LOG_RELATIVE_PATH"

  remote_bash "$target_path" <<'REMOTE'
set -euo pipefail

target_path="$1"
if [[ -r "$target_path" ]]; then
  cat "$target_path"
fi
REMOTE
}

sync_cost_log() {
  local local_log="$local_root/$COST_LOG_RELATIVE_PATH"
  local remote_log
  local pending_log
  local pending_count
  local unstable_count

  [[ -f "$local_log" ]] || die "expected local cost log is missing: $local_log"
  remote_log="$(mktemp)"
  pending_log="$(mktemp)"
  trap 'rm -f -- "$remote_log" "$pending_log"' RETURN

  read_remote_cost_log > "$remote_log"
  jq -e -s 'all(.[]; type == "object")' "$local_log" >/dev/null
  jq -e -s 'all(.[]; type == "object")' "$remote_log" >/dev/null

  jq -n -c --slurpfile local_entries "$local_log" --slurpfile remote_entries "$remote_log" '
    def stable_session:
      (.session? | type == "string" and length > 0 and . != "unknown");

    ([$local_entries[] | select(stable_session) | .session] | unique) as $local_sessions
    | (reduce $remote_entries[] as $entry
        ({};
          if ($entry | stable_session) then
            .[$entry.session] = $entry
          else
            .
          end
        )
        | [.[]]
        | sort_by(.ts // "")
      )
    | .[] as $entry
    | select(($local_sessions | index($entry.session)) | not)
    | $entry
  ' "$local_log" "$remote_log" > "$pending_log"

  pending_count="$(wc -l < "$pending_log" | tr -d '[:space:]')"
  unstable_count="$(jq -s '[.[] | select((.session? | type != "string" or . == "" or . == "unknown"))] | length' "$remote_log")"
  printf 'Cost records with unseen stable session IDs: %s\n' "$pending_count"
  if [[ "$unstable_count" != "0" ]]; then
    printf 'Remote cost records without a stable session ID were not imported: %s\n' "$unstable_count" >&2
  fi

  if "$apply_changes" && [[ "$pending_count" != "0" ]]; then
    cat "$pending_log" >> "$local_log"
    printf 'Appended %s deduplicated cost records to %s\n' "$pending_count" "$local_log"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply)
      apply_changes=true
      ;;
    --dry-run)
      apply_changes=false
      ;;
    --host)
      [[ $# -ge 2 ]] || die "--host requires a value"
      host="$2"
      shift
      ;;
    --remote-root)
      [[ $# -ge 2 ]] || die "--remote-root requires a value"
      remote_root="$2"
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
  shift
done

[[ "$USER" != "agent" ]] || die "run this workstation-to-devbox script from the workstation, not devbox-vm"
validate_arguments
require_command ssh
require_command rsync
require_command jq
require_command base64
require_command git

[[ -f "$local_root/AGENTS.md" ]] || die "cannot locate workspace guidance from $local_root"
[[ -f "$local_root/$MAINTENANCE_HOOK" ]] || die "cannot locate maintenance hook from $local_root"
[[ -f "$local_root/$COST_HOOK" ]] || die "cannot locate cost hook from $local_root"

printf 'Mode: %s\n' "$(if "$apply_changes"; then printf 'apply'; else printf 'dry-run'; fi)"
printf 'Target: %s:%s\n' "$host" "$remote_root"
remote_preflight
inspect_remote_templates

backup_timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
remote_backup_root="$remote_root/.claude/devbox-sync-backups/$backup_timestamp"
if "$apply_changes"; then
  prepare_remote_apply "$remote_backup_root"
fi

printf '\n== Shared guidance ==\n'
sync_file "$local_root/AGENTS.md" "$remote_root/AGENTS.md" "$remote_backup_root"
sync_file "$local_root/CLAUDE.md" "$remote_root/CLAUDE.md" "$remote_backup_root"

printf '\n== Claude hooks and scripts ==\n'
sync_tree "$local_root/.claude/hooks" "$remote_root/.claude/hooks" "$remote_backup_root"
sync_tree "$local_root/.claude/scripts" "$remote_root/.claude/scripts" "$remote_backup_root"

printf '\n== Workspace templates and project schemas ==\n'
sync_tree "$local_root/agentops/templates/workspace" "$remote_root/agentops/templates/workspace" "$remote_backup_root"
sync_tree "$local_root/agentops/docs/project/schemas" "$remote_root/agentops/docs/project/schemas" "$remote_backup_root"

printf '\n== Remote settings merges ==\n'
for relative_path in \
  ".claude/settings.local.json" \
  "sprintctl/.claude/settings.local.json" \
  "appservice/.claude/settings.local.json" \
  "homelab-analytics/.claude/settings.local.json" \
  "kctl/.claude/settings.local.json"; do
  merge_remote_settings "$relative_path" "$remote_backup_root"
done

printf '\n== Devbox cost log ==\n'
sync_cost_log

if "$apply_changes"; then
  printf '\nApply complete. Remote backups are under %s.\n' "$remote_backup_root"
else
  printf '\nDry run complete. Review the plan above, then rerun with --apply to make changes.\n'
fi
