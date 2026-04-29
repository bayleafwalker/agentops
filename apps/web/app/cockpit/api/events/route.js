import { errorPayload, getSearchParams, ok, parseIntParam, parseRepoId } from "../../../../lib/cockpit/http.js";
import { listEvents } from "../../../../lib/cockpit/sprintctl.js";

export function createGetHandler(deps = { listEvents }) {
  return async function GET(request) {
    const repoId = parseRepoId(request);
    try {
      const sprintId = parseIntParam(request, "sprint_id", null);
      const limit = parseIntParam(request, "limit", 100);
      const cursor = getSearchParams(request).get("cursor");
      const payload = await deps.listEvents({ repoId, sprintId, limit, cursor });
      return ok({
        source: "pg://sprintctl",
        repo_id: repoId,
        sprint_id: sprintId,
        degraded: null,
        ...payload
      });
    } catch (error) {
      return ok({
        source: "pg://sprintctl",
        repo_id: repoId,
        sprint_id: getSearchParams(request).get("sprint_id"),
        events: [],
        next_cursor: null,
        degraded: errorPayload("Sprint data unavailable — pg://sprintctl unreachable", "pg://sprintctl", {
          detail: error.message
        })
      });
    }
  };
}

export const GET = createGetHandler();
