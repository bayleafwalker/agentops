import { errorPayload, ok, parseRepoId } from "../../../../lib/cockpit/http.js";
import { listSprints } from "../../../../lib/cockpit/sprintctl.js";

export function createGetHandler(deps = { listSprints }) {
  return async function GET(request) {
    const repoId = parseRepoId(request);
    try {
      const sprints = await deps.listSprints(repoId);
      return ok({
        source: "pg://sprintctl",
        repo_id: repoId,
        sprints,
        degraded: null
      });
    } catch (error) {
      return ok({
        source: "pg://sprintctl",
        repo_id: repoId,
        sprints: [],
        degraded: errorPayload("Sprint data unavailable — pg://sprintctl unreachable", "pg://sprintctl", {
          detail: error.message
        })
      });
    }
  };
}

export const GET = createGetHandler();
