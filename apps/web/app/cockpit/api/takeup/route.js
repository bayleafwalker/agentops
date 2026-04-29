import { errorPayload, getSearchParams, ok, parseIntParam, parseRepoId } from "../../../../lib/cockpit/http.js";
import { getTakeup } from "../../../../lib/cockpit/sprintctl.js";

export function createGetHandler(deps = { getTakeup }) {
  return async function GET(request) {
    const repoId = parseRepoId(request);
    try {
      const sprintId = parseIntParam(request, "sprint_id");
      const payload = await deps.getTakeup(repoId, sprintId);
      return ok({
        source: "pg://sprintctl",
        repo_id: repoId,
        sprint_id: sprintId,
        ...payload,
        degraded: null
      });
    } catch (error) {
      return ok({
        source: "pg://sprintctl",
        repo_id: repoId,
        sprint_id: getSearchParams(request).get("sprint_id") || null,
        operation: "takeup_list",
        active_takeups: [],
        released_takeups: [],
        unmatched_releases: [],
        degraded: errorPayload("Takeup data unavailable — pg://sprintctl unreachable", "pg://sprintctl", {
          detail: error.message
        })
      });
    }
  };
}

export const GET = createGetHandler();
