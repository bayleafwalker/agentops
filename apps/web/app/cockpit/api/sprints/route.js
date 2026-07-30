import { errorPayload, ok, parseEnumParam, parseRepoId } from "../../../../lib/cockpit/http.js";
import { listSprints } from "../../../../lib/cockpit/sprintctl.js";

export function createGetHandler(deps = { listSprints }) {
  return async function GET(request) {
    const repoId = parseRepoId(request);
    let mode = "active";
    try {
      mode = parseEnumParam(request, "mode", ["active", "backlog", "history"], "active");
      const sprints = await deps.listSprints(repoId, mode);
      return ok({
        source: "served://vuoro/work",
        repo_id: repoId,
        mode,
        sprints,
        degraded: null
      });
    } catch (error) {
      return ok({
        source: "served://vuoro/work",
        repo_id: repoId,
        mode,
        sprints: [],
        degraded: errorPayload("Sprint data unavailable — served://vuoro/work unreachable", "served://vuoro/work", {
          detail: error.message
        })
      });
    }
  };
}

export const GET = createGetHandler();
