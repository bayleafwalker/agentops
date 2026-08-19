#!/usr/bin/env bash
set -euo pipefail

# The dispatcher owns these identifiers and exports them before starting the
# harness. Do not ask the agent to discover or rewrite them.
export VUORO_DISPATCH_ID="${DISPATCH_ID:?missing DISPATCH_ID}"
export VUORO_REPO_ID="${REPO_UUID:-}"
export VUORO_CONTEXT_ENDPOINT="${VUORO_CONTEXT_ENDPOINT:-http://127.0.0.1:8765}"

exec "$@"
