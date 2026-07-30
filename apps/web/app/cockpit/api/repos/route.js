import { errorPayload, ok } from "../../../../lib/cockpit/http.js";
import { listRepos } from "../../../../lib/cockpit/sprintctl.js";

export const dynamic = "force-dynamic";

export function createGetHandler(deps = { listRepos }) {
  return async function GET() {
    try {
      const repos = await deps.listRepos();
      return ok({
        source: "served://vuoro/work",
        repos,
        degraded: null
      });
    } catch (error) {
      return ok({
        source: "served://vuoro/work",
        repos: [],
        degraded: errorPayload("Sprint data unavailable — served://vuoro/work unreachable", "served://vuoro/work", {
          detail: error.message
        })
      });
    }
  };
}

export const GET = createGetHandler();
