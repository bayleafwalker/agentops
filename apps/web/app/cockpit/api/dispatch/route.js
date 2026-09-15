import { getDispatchGate } from "../../../../lib/cockpit/dispatch.js";
import { errorPayload } from "../../../../lib/cockpit/http.js";
import { requireConfiguredWriteAuth } from "../../../../lib/cockpit/auth.js";

export const dynamic = "force-dynamic";

// agentops#2409 (D17): the dispatch write path is retired. actionq-server was
// deleted from the cluster on 2026-09-01 with no owner-source server or
// worker behind it (docs/ecosystem.md). This route always returns 410 and
// never makes an outbound call to actionq-server or any dispatch backend.
export function createPostHandler(deps = { getDispatchGate }) {
  const checkAuth = deps.requireConfiguredWriteAuth ?? requireConfiguredWriteAuth;
  return async function POST(request) {
    const denied = checkAuth(request, "cockpit://dispatch-retired");
    if (denied) {
      return denied;
    }
    const gate = deps.getDispatchGate();
    return Response.json(
      {
        source: gate.source,
        accepted: false,
        action: null,
        degraded: errorPayload(gate.reason, gate.source, { retired: true })
      },
      { status: 410 }
    );
  };
}

export const POST = createPostHandler();
