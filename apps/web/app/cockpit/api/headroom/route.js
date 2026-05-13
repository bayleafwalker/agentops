import { getModelHeadroom } from "../../../../lib/cockpit/headroom.js";
import { errorPayload, ok } from "../../../../lib/cockpit/http.js";

export const dynamic = "force-dynamic";

export function createGetHandler(deps = { getModelHeadroom }) {
  return async function GET() {
    try {
      const snapshot = await deps.getModelHeadroom({ force: false });
      return ok({
        source: "model-headroom",
        snapshot,
        degraded: snapshot.degraded
      });
    } catch (error) {
      return ok({
        source: "model-headroom",
        snapshot: null,
        degraded: errorPayload("Model headroom unavailable", "model-headroom", { detail: error.message })
      });
    }
  };
}

export function createPostHandler(deps = { getModelHeadroom }) {
  return async function POST() {
    try {
      const snapshot = await deps.getModelHeadroom({ force: true });
      return ok({
        source: "model-headroom",
        snapshot,
        degraded: snapshot.degraded
      });
    } catch (error) {
      return ok({
        source: "model-headroom",
        snapshot: null,
        degraded: errorPayload("Model headroom refresh failed", "model-headroom", { detail: error.message })
      });
    }
  };
}

export const GET = createGetHandler();
export const POST = createPostHandler();
