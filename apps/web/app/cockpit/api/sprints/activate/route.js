import { errorPayload, ok } from "../../../../../lib/cockpit/http.js";
import { activateSprint } from "../../../../../lib/cockpit/sprintctl.js";

export const dynamic = "force-dynamic";

export function createPostHandler(deps = { activateSprint }) {
  return async function POST(request) {
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
    try {
      const sprint = await deps.activateSprint(repo_id, Number(sprint_id));
      return ok({ source: "pg://sprintctl", sprint, degraded: null });
    } catch (error) {
      return Response.json(
        { degraded: errorPayload(`Activation failed: ${error.message}`, "pg://sprintctl") },
        { status: 500 }
      );
    }
  };
}

export const POST = createPostHandler();
