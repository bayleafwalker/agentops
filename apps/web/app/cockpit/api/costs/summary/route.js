import { readCostSummary } from "../../../../../lib/cockpit/costs.js";
import { errorPayload, ok } from "../../../../../lib/cockpit/http.js";

export const dynamic = "force-dynamic";

export function createGetHandler(deps = { readCostSummary }) {
  return async function GET(request) {
    const params = request.nextUrl?.searchParams || new URL(request.url).searchParams;
    const day = params.get("day") || undefined;
    try {
      const summary = await deps.readCostSummary({ day });
      return ok({
        source: "workspace-cost:/projects/dev/.claude/session-costs.jsonl",
        summary,
        degraded: null
      });
    } catch (error) {
      return ok({
        source: "workspace-cost:/projects/dev/.claude/session-costs.jsonl",
        summary: null,
        degraded: errorPayload("Cost summary unavailable — workspace cost log unreadable", "workspace-cost", {
          detail: error.message
        })
      });
    }
  };
}

export const GET = createGetHandler();
