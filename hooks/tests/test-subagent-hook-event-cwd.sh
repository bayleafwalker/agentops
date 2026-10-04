#!/usr/bin/env bash
# Run the same temp-store routing oracle against SubagentStop's actual publisher.
set -euo pipefail
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
AGENTOPS_TEST_EVENT_CWD_HOOK=subagent-exit.sh AGENTOPS_TEST_EVENT_CWD_TYPE=dispatch.exit bash "$here/test-cost-hook-event-cwd.sh"
