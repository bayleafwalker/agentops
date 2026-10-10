#!/usr/bin/env bash
# Register this explicit adapter in Codex SessionStart; event fields are data.
set -uo pipefail
_hook_src="${BASH_SOURCE[0]}"
[[ ! -L "$_hook_src" ]] || _hook_src="$(readlink -f -- "$_hook_src")"
exec bash "${_hook_src%/*}/session-binding.sh" codex
