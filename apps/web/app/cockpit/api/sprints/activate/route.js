import { errorPayload, ok } from "../../../../../lib/cockpit/http.js";
import { activateSprint, SprintNotFoundError, SprintTransitionError } from "../../../../../lib/cockpit/sprintctl.js";
import { requireWriteAuth } from "../../../../../lib/cockpit/auth.js";
import { getConfig } from "../../../../../lib/cockpit/env.js";

export const dynamic = "force-dynamic";

export function createPostHandler(deps = { activateSprint }) {
  const checkAuth = deps.requireWriteAuth ?? requireWriteAuth;
  return async function POST(request) {
    const denied = checkAuth(request, "pg://sprintctl");
    if (denied) {
      return denied;
    }
    let body;
    try {
      body = await request.json();
    } catch (error) {
      return Response.json(
        { degraded: errorPayload(`Invalid JSON: ${error.message}`, "pg://sprintctl") },
        { status: 400 }
      );
    }
    const { repo_id, sprint_id } = body || {};
    if (!repo_id || !sprint_id) {
      return Response.json(
        { degraded: errorPayload("repo_id and sprint_id are required", "pg://sprintctl") },
        { status: 400 }
      );
    }
    const actor =
      typeof body.actor === "string" && body.actor.trim()
        ? body.actor.trim()
        : getConfig().cockpitOperatorId;
    try {
      const sprint = await deps.activateSprint(repo_id, Number(sprint_id), { actor });
      return ok({ source: "pg://sprintctl", sprint, degraded: null });
    } catch (error) {
      const status = error instanceof SprintNotFoundError
        ? 404
        : error instanceof SprintTransitionError
          ? 409
          : 500;
      return Response.json(
        { degraded: errorPayload(`Activation failed: ${error.message}`, "pg://sprintctl") },
        { status }
      );
    }
  };
}

export const POST = createPostHandler();
