import fs from "node:fs/promises";
import path from "node:path";
import { getCached, setCached } from "./cache.js";
import { getConfig } from "./env.js";

const ADOPTION_LEVELS = new Set(["guidance-only", "observable", "dispatchable"]);
const HARNESSES = new Set(["claude", "codex", "opencode"]);
const ACTION_CLASSES = new Set(["plan", "build", "review", "release-ops", "meta-dispatch"]);
const SKILLS = new Set([
  "dispatch-plan",
  "dispatch-build",
  "dispatch-review",
  "code-change-verification",
  "pr-handoff-summary",
  "sprint-resume",
  "sprint-packet",
  "item-done",
  "sprint-snapshot",
  "kctl-extract",
  "sprint-close"
]);

export function validateDispatchManifest(manifest) {
  if (!manifest || typeof manifest !== "object" || Array.isArray(manifest)) {
    throw new Error("dispatch manifest must be an object");
  }
  if (manifest.schema_version !== 1) {
    throw new Error("schema_version must be 1");
  }
  if (typeof manifest.repo_id !== "string" || !/^[A-Za-z0-9._-]+$/.test(manifest.repo_id)) {
    throw new Error("repo_id must be a valid repo identifier");
  }
  if (!ADOPTION_LEVELS.has(manifest.adoption_level)) {
    throw new Error("adoption_level must be guidance-only, observable, or dispatchable");
  }
  if (manifest.dispatch_group_id != null && (typeof manifest.dispatch_group_id !== "string" || manifest.dispatch_group_id.length === 0)) {
    throw new Error("dispatch_group_id must be a non-empty string when present");
  }
  const routing = manifest.routing;
  if (!routing || typeof routing !== "object") {
    throw new Error("routing must be an object");
  }
  if (!HARNESSES.has(routing.default_harness)) {
    throw new Error("routing.default_harness is invalid");
  }
  if (typeof routing.default_model_alias !== "string" || routing.default_model_alias.length === 0) {
    throw new Error("routing.default_model_alias must be a non-empty string");
  }
  if (!routing.action_classes || Object.keys(routing.action_classes).length === 0) {
    throw new Error("routing.action_classes must not be empty");
  }
  for (const [name, actionClass] of Object.entries(routing.action_classes)) {
    if (!ACTION_CLASSES.has(name)) {
      throw new Error(`unknown action class: ${name}`);
    }
    if (typeof actionClass.enabled !== "boolean") {
      throw new Error(`action class ${name} missing enabled boolean`);
    }
    if (actionClass.harness != null && !HARNESSES.has(actionClass.harness)) {
      throw new Error(`action class ${name} has invalid harness`);
    }
  }
  const selected = manifest.skills?.selected;
  if (!Array.isArray(selected) || selected.length === 0) {
    throw new Error("skills.selected must not be empty");
  }
  for (const skill of selected) {
    if (!SKILLS.has(skill)) {
      throw new Error(`unknown selected skill: ${skill}`);
    }
  }
  if (!Array.isArray(manifest.verification?.command_families) || manifest.verification.command_families.length === 0) {
    throw new Error("verification.command_families must not be empty");
  }
  if (!manifest.hooks || !Array.isArray(manifest.hooks.publishers)) {
    throw new Error("hooks.publishers must be an array");
  }
  return manifest;
}

function summarizeManifest(manifest, sourcePath) {
  return {
    repo_id: manifest.repo_id,
    adoption_level: manifest.adoption_level,
    dispatch_group_id: manifest.dispatch_group_id || null,
    source: sourcePath,
    routing: {
      default_harness: manifest.routing.default_harness,
      default_model_alias: manifest.routing.default_model_alias,
      action_classes: manifest.routing.action_classes
    },
    skills: manifest.skills.selected,
    verification: manifest.verification,
    hooks: manifest.hooks
  };
}

async function readManifestFile(fullPath) {
  const raw = await fs.readFile(fullPath, "utf8");
  return summarizeManifest(validateDispatchManifest(JSON.parse(raw)), fullPath);
}

export async function listDispatchManifests({ root = getConfig().dispatchManifestRoot } = {}) {
  const config = getConfig();
  const stats = await fs.stat(root);
  const cacheKey = `dispatch-manifests:${root}:${stats.mtimeMs}:${stats.size}`;
  const cached = getCached(cacheKey);
  if (cached) {
    return cached;
  }

  const entries = await fs.readdir(root, { withFileTypes: true });
  const manifests = [];
  const warnings = [];
  for (const entry of entries.filter((item) => item.isFile() && item.name.endsWith(".dispatch.json"))) {
    const fullPath = path.join(root, entry.name);
    try {
      manifests.push(await readManifestFile(fullPath));
    } catch (error) {
      warnings.push({ file: fullPath, message: error.message });
    }
  }
  manifests.sort((a, b) => a.repo_id.localeCompare(b.repo_id));
  return setCached(cacheKey, { source: `dispatch-manifest:${root}`, manifests, warnings }, config.dispatchManifestCacheMs);
}

export async function getDispatchManifest(repoId, options = {}) {
  const payload = await listDispatchManifests(options);
  return {
    ...payload,
    manifests: payload.manifests.filter((manifest) => repoId === "ALL" || manifest.repo_id === repoId)
  };
}
