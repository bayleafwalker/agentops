import { getDispatchManifest, listDispatchManifests } from "../../../../lib/cockpit/dispatch-manifest.js";
import { errorPayload, ok, parseRepoId } from "../../../../lib/cockpit/http.js";

export const dynamic = "force-dynamic";

export function createGetHandler(deps = { getDispatchManifest, listDispatchManifests }) {
  return async function GET(request) {
    const repoId = parseRepoId(request);
    try {
      const payload = repoId === "ALL" ? await deps.listDispatchManifests() : await deps.getDispatchManifest(repoId);
      return ok({
        ...payload,
        repo_id: repoId,
        degraded: null
      });
    } catch (error) {
      return ok({
        source: "dispatch-manifest",
        repo_id: repoId,
        manifests: [],
        warnings: [],
        degraded: errorPayload("Dispatch manifests unavailable", "dispatch-manifest", {
          detail: error.message
        })
      });
    }
  };
}

export const GET = createGetHandler();
