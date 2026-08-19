import fs from "node:fs/promises";
import path from "node:path";
import { getCached, setCached } from "./cache.js";
import { getConfig } from "./env.js";

const ADOPTION_LEVELS = new Set(["guidance-only", "observable", "dispatchable"]);
const MANIFEST_SCHEMA_VERSIONS = new Set([1, 2]);
const HARNESSES = new Set(["claude", "codex", "opencode"]);
const ACTION_CLASSES = new Set(["plan", "build", "review", "verify", "reconcile", "release-ops", "meta-dispatch"]);
const SKILLS = new Set([
  "dispatch-plan",
  "dispatch-build",
  "dispatch-review",
  "code-change-verification",
  "backlog-refinement",
  "sprint-maintenance",
  "task-pickup",
  "plan-review",
  "model-routing-optimizer",
  "pr-handoff-summary",
  "sprint-resume",
  "sprint-packet",
  "item-done",
  "sprint-snapshot",
  "kctl-extract",
  "sprint-close",
  "capability-receipt",
  "domain-impact-scan",
  "workflow-artifact-capture",
  "golden-child",
  "session-reconciler",
  "session-scribe",
  "verify-state-protocols",
  "reconcile-project-contracts"
]);
const RISK_SKILLS = new Set(["verify-state-protocols", "reconcile-project-contracts"]);
const INSTRUCTION_KINDS = new Set(["AGENTS.md", "CLAUDE.md", "overlay", "generated", "other"]);
const ROLE_PRESETS = new Set(["planner", "worker", "reviewer"]);

function validateInstructionSet(instructionSet) {
  if (!instructionSet || typeof instructionSet !== "object" || Array.isArray(instructionSet)) {
    throw new Error("instruction_set must be an object");
  }
  if (instructionSet.schema_version !== 1) {
    throw new Error("instruction_set.schema_version must be 1");
  }
  if (instructionSet.discovery !== "native") {
    throw new Error("instruction_set.discovery must be native");
  }
  for (const field of ["applicability", "entrypoints"]) {
    if (instructionSet[field] != null && (!instructionSet[field] || typeof instructionSet[field] !== "object" || Array.isArray(instructionSet[field]))) {
      throw new Error(`instruction_set.${field} must be an object`);
    }
  }
  if (instructionSet.role_presets != null) {
    if (typeof instructionSet.role_presets !== "object" || Array.isArray(instructionSet.role_presets)) throw new Error("instruction_set.role_presets must be an object");
    for (const [role, preset] of Object.entries(instructionSet.role_presets)) {
      if (!ROLE_PRESETS.has(role) || !preset || typeof preset !== "object" || Array.isArray(preset) || !["Sol", "Luna"].includes(preset.model) || !["high", "xhigh"].includes(preset.behavior) || !["read-only", "write"].includes(preset.tool_mode)) {
        throw new Error(`instruction_set.role_presets.${role} is invalid`);
      }
      if (Object.keys(preset).some((key) => !["model", "behavior", "tool_mode"].includes(key))) throw new Error(`instruction_set.role_presets.${role} contains unsupported authority fields`);
    }
  }
  if (instructionSet.provider_adapters != null) {
    if (!Array.isArray(instructionSet.provider_adapters)) throw new Error("instruction_set.provider_adapters must be an array");
    const providers = new Set();
    for (const adapter of instructionSet.provider_adapters) {
      if (!adapter || typeof adapter.provider !== "string" || typeof adapter.path !== "string" || providers.has(adapter.provider)) throw new Error("instruction_set.provider_adapters must have unique providers");
      providers.add(adapter.provider);
      if (adapter.digest != null && (typeof adapter.digest !== "string" || !/^[0-9a-f]{64}$/.test(adapter.digest))) throw new Error("provider adapter digest must be sha256");
    }
  }
  if (instructionSet.skill_lock != null) {
    const lock = Array.isArray(instructionSet.skill_lock) ? instructionSet.skill_lock : Object.entries(instructionSet.skill_lock).map(([id, digest]) => ({ id, digest }));
    if (!lock.every((item) => item && typeof item.id === "string" && typeof item.digest === "string" && /^[0-9a-f]{64}$/.test(item.digest))) throw new Error("instruction_set.skill_lock digests must be sha256");
  }
  if (!Array.isArray(instructionSet.sources)) {
    throw new Error("instruction_set.sources must be an array");
  }
  const allowedFields = new Set(["schema_version", "discovery", "sources", "applicability", "entrypoints", "role_presets", "provider_adapters", "skill_lock", "skill_lock_ref"]);
  if (Object.keys(instructionSet).some((field) => !allowedFields.has(field))) {
    throw new Error("instruction_set contains unsupported fields");
  }
  const ids = new Set();
  for (const source of instructionSet.sources) {
    if (!source || typeof source !== "object" || Array.isArray(source)) {
      throw new Error("instruction source must be an object");
    }
    if (typeof source.id !== "string" || !/^[A-Za-z0-9._-]+$/.test(source.id) || ids.has(source.id)) {
      throw new Error("instruction source id must be unique and valid");
    }
    ids.add(source.id);
    if (typeof source.path !== "string" || source.path.length === 0 || source.path.startsWith("/") || source.path.includes("..")) {
      throw new Error(`instruction source ${source.id} path must be relative`);
    }
    if (!INSTRUCTION_KINDS.has(source.kind)) {
      throw new Error(`instruction source ${source.id} kind is invalid`);
    }
    if (typeof source.digest !== "string" || !/^[0-9a-f]{64}$/.test(source.digest)) {
      throw new Error(`instruction source ${source.id} digest must be sha256`);
    }
    if (typeof source.source_rev !== "string" || source.source_rev.length === 0) {
      throw new Error(`instruction source ${source.id} source_rev is required`);
    }
    for (const field of ["refs", "hooks"]) {
      if (source[field] != null && (!Array.isArray(source[field]) || source[field].some((item) => typeof item !== "string" || item.length === 0))) {
        throw new Error(`instruction source ${source.id} ${field} must contain non-empty strings`);
      }
    }
    if (source.rules != null && (!Array.isArray(source.rules) || source.rules.some((rule) => !rule || typeof rule.rule_id !== "string" || !/^[A-Za-z0-9._-]+$/.test(rule.rule_id) || typeof rule.scope !== "string" || rule.scope.length === 0))) {
      throw new Error(`instruction source ${source.id} rules are invalid`);
    }
    if (source.line_budget != null && (!Number.isInteger(source.line_budget) || source.line_budget < 1)) {
      throw new Error(`instruction source ${source.id} line_budget must be positive`);
    }
  }
  if (instructionSet.skill_lock_ref != null) {
    const ref = instructionSet.skill_lock_ref;
    if (!ref || typeof ref !== "object" || Array.isArray(ref) || Object.keys(ref).sort().join(",") !== "digest,mandatory,path" || typeof ref.path !== "string" || ref.path.startsWith("/") || ref.path.includes("..") || !/^[0-9a-f]{64}$/.test(ref.digest) || typeof ref.mandatory !== "boolean") {
      throw new Error("instruction_set.skill_lock_ref is invalid");
    }
  }
  return instructionSet;
}

export function validateDispatchManifest(manifest) {
  if (!manifest || typeof manifest !== "object" || Array.isArray(manifest)) {
    throw new Error("dispatch manifest must be an object");
  }
  if (!MANIFEST_SCHEMA_VERSIONS.has(manifest.schema_version)) {
    throw new Error("schema_version must be 1 or 2");
  }
  if (manifest.schema_version === 2) validateInstructionSet(manifest.instruction_set);
  if (manifest.schema_version === 1 && manifest.instruction_set != null) {
    throw new Error("instruction_set requires schema_version 2");
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
  if (manifest.risk_surfaces != null && !Array.isArray(manifest.risk_surfaces)) {
    throw new Error("risk_surfaces must be an array when present");
  }
  for (const surface of manifest.risk_surfaces || []) {
    if (!surface || typeof surface !== "object" || !/^[A-Za-z0-9._-]+$/.test(surface.id || "")) {
      throw new Error("risk surface id must be a valid identifier");
    }
    if (!Array.isArray(surface.paths) || surface.paths.length === 0) {
      throw new Error(`risk surface ${surface.id} must include paths`);
    }
    if (!Array.isArray(surface.skills) || surface.skills.length === 0 || surface.skills.some((skill) => !RISK_SKILLS.has(skill))) {
      throw new Error(`risk surface ${surface.id} has invalid skills`);
    }
    if (surface.context_ids != null && (!Array.isArray(surface.context_ids) || surface.context_ids.length === 0 || surface.context_ids.some((id) => typeof id !== "string" || id.length === 0))) {
      throw new Error(`risk surface ${surface.id} context_ids must be non-empty strings`);
    }
    if (surface.default_depth != null && (!Number.isInteger(surface.default_depth) || surface.default_depth < 0 || surface.default_depth > 3)) {
      throw new Error(`risk surface ${surface.id} default_depth must be 0..3`);
    }
    if (surface.required_on_change != null && typeof surface.required_on_change !== "boolean") {
      throw new Error(`risk surface ${surface.id} required_on_change must be boolean`);
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
    risk_surfaces: manifest.risk_surfaces || [],
    verification: manifest.verification,
    hooks: manifest.hooks,
    instruction_set: manifest.instruction_set || null
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
