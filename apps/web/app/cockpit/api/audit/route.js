import { errorPayload, getSearchParams, ok, parseIntParam, parseRepoId } from "../../../../lib/cockpit/http.js";
import { readAuditFeed } from "../../../../lib/cockpit/audit.js";

export function createGetHandler(deps = { readAuditFeed }) {
  return async function GET(request) {
    const repoId = parseRepoId(request);
    try {
      const days = parseIntParam(request, "days", 3);
      const limit = parseIntParam(request, "limit", 100);
      const cursor = getSearchParams(request).get("cursor");
      const payload = await deps.readAuditFeed({ repoId, days, limit, cursor });
      return ok({
        ...payload,
        degraded: null
      });
    } catch (error) {
      return ok({
        source: `artifact:audit/${repoId}`,
        repo_id: repoId,
        events: [],
        warnings: [],
        next_cursor: null,
        degraded: errorPayload(`Audit data unavailable — artifact:audit/${repoId} unreachable`, `artifact:audit/${repoId}`, {
          detail: error.message
        })
      });
    }
  };
}

export const GET = createGetHandler();
