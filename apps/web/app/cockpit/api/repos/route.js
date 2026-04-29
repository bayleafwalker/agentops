import { errorPayload, ok } from "../../../../lib/cockpit/http.js";
import { listRepos } from "../../../../lib/cockpit/sprintctl.js";

export function createGetHandler(deps = { listRepos }) {
  return async function GET() {
    try {
      const repos = await deps.listRepos();
      return ok({
        source: "pg://sprintctl",
        repos,
        degraded: null
      });
    } catch (error) {
      return ok({
        source: "pg://sprintctl",
        repos: [],
        degraded: errorPayload("Sprint data unavailable — pg://sprintctl unreachable", "pg://sprintctl", {
          detail: error.message
        })
      });
    }
  };
}

export const GET = createGetHandler();
