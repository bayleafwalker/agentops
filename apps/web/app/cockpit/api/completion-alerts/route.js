import { errorPayload, ok, parseIntParam, parseRepoId } from "../../../../lib/cockpit/http.js";
import { readCompletionAlertProjection, redactDiagnostic } from "../../../../lib/cockpit/completion-alerts.js";

export const dynamic = "force-dynamic";

export function createGetHandler(deps = { readCompletionAlertProjection }) {
  return async function GET(request) {
    const repoId = parseRepoId(request);
    try {
      const limit = parseIntParam(request, "limit", 50);
      return ok(await deps.readCompletionAlertProjection({ repoId, limit }));
    } catch (error) {
      return ok({
        source: "agentops://completion-alerts",
        repo_id: repoId,
        alerts: [],
        coalesced_events: [],
        outcomes: [],
        pending_deliveries: [],
        health: null,
        degraded: errorPayload(
          "Completion alerts unavailable — agentops://completion-alerts unreachable",
          "agentops://completion-alerts",
          { detail: redactDiagnostic(error.message) }
        )
      });
    }
  };
}

export const GET = createGetHandler();
