import { errorPayload, ok, parseRepoId } from "../../../../lib/cockpit/http.js";
import { readKnowledgeArtifact } from "../../../../lib/cockpit/knowledge.js";

export const dynamic = "force-dynamic";

export function createGetHandler(deps = { readKnowledgeArtifact }) {
  return async function GET(request) {
    const repoId = parseRepoId(request);
    try {
      const payload = await deps.readKnowledgeArtifact({ repoId });
      return ok({
        ...payload,
        degraded: null
      });
    } catch (error) {
      return ok({
        source: "artifact:knowledge/" + repoId,
        repo_id: repoId,
        entries: [],
        warnings: [],
        artifact_path: null,
        updated_at: null,
        degraded: errorPayload(
          "Knowledge artifacts unavailable — artifact:knowledge/" + repoId + " unreachable",
          "artifact:knowledge/" + repoId,
          { detail: error.message }
        )
      });
    }
  };
}

export const GET = createGetHandler();
