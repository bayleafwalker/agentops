import { getActionqDispatches } from "../../../../lib/cockpit/actionq.js";
import { errorPayload, ok, parseIntParam, parseRepoId } from "../../../../lib/cockpit/http.js";

export const dynamic = "force-dynamic";

export function createGetHandler(deps = { getActionqDispatches }) {
  return async function GET(request) {
    const repoId = parseRepoId(request);
    const params = request.nextUrl?.searchParams || new URL(request.url).searchParams;
    try {
      const limit = parseIntParam(request, "limit", 100);
      const status = params.get("status") || null;
      const dispatches = await deps.getActionqDispatches({ repoId, status, limit });
      return ok({
        source: "actionq://dispatches",
        repo_id: repoId,
        status,
        dispatches,
        degraded: null
      });
    } catch (error) {
      return ok({
        source: "actionq://dispatches",
        repo_id: repoId,
        status: null,
        dispatches: [],
        degraded: errorPayload("Dispatch lifecycle unavailable — actionq://dispatches unreachable", "actionq://dispatches", {
          detail: error.message
        })
      });
    }
  };
}

export const GET = createGetHandler();
