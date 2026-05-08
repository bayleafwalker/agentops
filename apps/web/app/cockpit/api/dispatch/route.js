import { dispatchViaActionctl, forwardDispatchToActionqServer, getDispatchGate, getDispatchOperator, normalizeDispatchPayload } from "../../../../lib/cockpit/dispatch.js";
import { errorPayload, ok } from "../../../../lib/cockpit/http.js";

export const dynamic = "force-dynamic";

export function createPostHandler(deps = { dispatchViaActionctl, forwardDispatchToActionqServer, getDispatchGate, getDispatchOperator }) {
  return async function POST(request) {
    const gate = deps.getDispatchGate();
    if (!gate.enabled) {
      return Response.json(
        {
          source: gate.source,
          accepted: false,
          action: null,
          degraded: errorPayload(gate.reason, gate.source)
        },
        { status: 503 }
      );
    }

    try {
      const payload = normalizeDispatchPayload(await request.json(), {
        requestedBy: deps.getDispatchOperator()
      });
      const action = gate.method === "actionctl"
        ? await deps.dispatchViaActionctl(payload, gate.bin)
        : await deps.forwardDispatchToActionqServer(payload);
      return ok({
        source: gate.source,
        accepted: true,
        action,
        degraded: null
      });
    } catch (error) {
      return Response.json(
        {
          source: gate.source,
          accepted: false,
          action: null,
          degraded: errorPayload("Dispatch request rejected", gate.source, {
            detail: error.message
          })
        },
        { status: 400 }
      );
    }
  };
}

export const POST = createPostHandler();
