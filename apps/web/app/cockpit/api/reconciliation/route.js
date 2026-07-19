import { errorPayload, ok, parseRepoId } from "../../../../lib/cockpit/http.js";
import { readReconciliationState } from "../../../../lib/cockpit/reconciliation.js";

export const dynamic = "force-dynamic";

export function createGetHandler(deps = { readReconciliationState }) {
  return async function GET(request) {
    const repoId = parseRepoId(request);
    try {
      const payload = await deps.readReconciliationState({ repoId });
      return ok({
        ...payload,
        degraded: null
      });
    } catch (error) {
      return ok({
        source: `artifact:reconciliation/${repoId}`,
        repo_id: repoId,
        review_queue: [],
        executions: [],
        lag: null,
        watermark: null,
        dogfooding: null,
        warnings: [],
        degraded: errorPayload(
          `Reconciliation artifacts unavailable — artifact:reconciliation/${repoId} unreachable`,
          `artifact:reconciliation/${repoId}`,
          { detail: error.message }
        )
      });
    }
  };
}

export const GET = createGetHandler();
