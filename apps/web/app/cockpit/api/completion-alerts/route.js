import { errorPayload, ok, parseIntParam, parseRepoId } from "../../../../lib/cockpit/http.js";
import { acknowledgeCompletionAlert, readCompletionAlertProjection, redactDiagnostic } from "../../../../lib/cockpit/completion-alerts.js";
import { getConfig } from "../../../../lib/cockpit/env.js";
import { requireConfiguredWriteAuth } from "../../../../lib/cockpit/auth.js";

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

export function createPostHandler(deps = { acknowledgeCompletionAlert }) {
  const checkAuth = deps.requireConfiguredWriteAuth ?? requireConfiguredWriteAuth;
  return async function POST(request) {
    const denied = checkAuth(request, "agentops://completion-alerts");
    if (denied) return denied;
    let body;
    try {
      body = await request.json();
    } catch (error) {
      return Response.json({ degraded: errorPayload(`Invalid JSON: ${error.message}`, "agentops://completion-alerts") }, { status: 400 });
    }
    const alertId = body?.alert_id || body?.event_id;
    if (typeof alertId !== "string" || !alertId.trim()) {
      return Response.json({ degraded: errorPayload("alert_id is required", "agentops://completion-alerts") }, { status: 400 });
    }
    const acknowledgedBy = typeof body?.acknowledged_by === "string" && body.acknowledged_by.trim()
      ? body.acknowledged_by.trim()
      : getConfig().cockpitOperatorId;
    try {
      return ok(await deps.acknowledgeCompletionAlert({ alertId, acknowledgedBy }));
    } catch (error) {
      const status = error?.code === "alert_not_found" ? 404 : 500;
      return Response.json({ degraded: errorPayload(`Completion alert acknowledgement failed: ${redactDiagnostic(error.message)}`, "agentops://completion-alerts") }, { status });
    }
  };
}

export const POST = createPostHandler();
