import { errorPayload, ok } from "../../../../../lib/cockpit/http.js";
import { readDispatcherPause, setDispatcherPause } from "../../../../../lib/cockpit/dispatcher-pause.js";
import { requireWriteAuth } from "../../../../../lib/cockpit/auth.js";

export const dynamic = "force-dynamic";

export function createGetHandler(deps = { readDispatcherPause }) {
  return async function GET() {
    try {
      const status = await deps.readDispatcherPause();
      return ok({
        source: "fs://dispatcher-pause",
        ...status,
        degraded: null
      });
    } catch (error) {
      return ok({
        source: "fs://dispatcher-pause",
        paused: false,
        pause_file: null,
        updated_at: null,
        degraded: errorPayload("Dispatcher pause state unavailable", "fs://dispatcher-pause", {
          detail: error.message
        })
      });
    }
  };
}

export function createPostHandler(deps = { setDispatcherPause }) {
  const checkAuth = deps.requireWriteAuth ?? requireWriteAuth;
  return async function POST(request) {
    const denied = checkAuth(request, "fs://dispatcher-pause");
    if (denied) {
      return denied;
    }
    let body;
    try {
      body = await request.json();
    } catch (error) {
      return Response.json({
        source: "fs://dispatcher-pause",
        degraded: errorPayload(`Invalid JSON: ${error.message}`, "fs://dispatcher-pause")
      }, { status: 400 });
    }
    if (typeof body?.paused !== "boolean") {
      return Response.json({
        source: "fs://dispatcher-pause",
        degraded: errorPayload("paused must be a boolean", "fs://dispatcher-pause")
      }, { status: 400 });
    }
    try {
      const status = await deps.setDispatcherPause(body.paused);
      return ok({
        source: "fs://dispatcher-pause",
        ...status,
        degraded: null
      });
    } catch (error) {
      return Response.json({
        source: "fs://dispatcher-pause",
        degraded: errorPayload("Dispatcher pause update failed", "fs://dispatcher-pause", {
          detail: error.message
        })
      }, { status: 500 });
    }
  };
}

export const GET = createGetHandler();
export const POST = createPostHandler();
