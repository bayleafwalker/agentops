import path from "node:path";

// COCKPIT_ARTIFACTS_ROOT historically pointed at the workspace root while
// readers appended "_artifacts". The deployment handoff now configures the
// artifact directory itself. Accept both during rollout so an image and its
// GitOps environment can move independently.
export function resolveArtifactRepoRoot(artifactsRoot, repoId) {
  if (
    typeof repoId !== "string" ||
    !/^[A-Za-z0-9._-]+$/.test(repoId) ||
    repoId === "." ||
    repoId === ".."
  ) {
    throw new Error("repo_id is invalid");
  }
  const root = path.resolve(artifactsRoot);
  const artifactRoot = path.basename(root) === "_artifacts" ? root : path.join(root, "_artifacts");
  return path.join(artifactRoot, repoId);
}
