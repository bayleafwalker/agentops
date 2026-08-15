import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { getDispatchManifest, listDispatchManifests, validateDispatchManifest } from "../lib/cockpit/dispatch-manifest.js";

const ROOT = join(process.cwd(), "../..");
const EXAMPLES_DIR = join(ROOT, "templates/dispatch/examples");

async function readJson(path) {
  return JSON.parse(await readFile(path, "utf8"));
}

test("dispatch manifest examples satisfy routing contract invariants", async () => {
  for (const file of ["actionq.dispatch.json", "scribectl.dispatch.json", "homelab-analytics.dispatch.json", "appservice.dispatch.json"]) {
    assert.equal(validateDispatchManifest(await readJson(join(EXAMPLES_DIR, file))).schema_version, 1);
  }
});

test("v2 manifests retain v1 routing and validate the instruction source catalog", () => {
  const manifest = {
    schema_version: 2,
    repo_id: "fixture",
    adoption_level: "guidance-only",
    routing: {
      default_harness: "codex",
      default_model_alias: "fast-build",
      action_classes: { plan: { enabled: true } }
    },
    skills: { selected: ["dispatch-plan"] },
    verification: { command_families: ["unit"] },
    hooks: { level: "none", publishers: [] },
    instruction_set: {
      schema_version: 1,
      discovery: "native",
      sources: [{
        id: "agents",
        path: "AGENTS.md",
        kind: "AGENTS.md",
        digest: "0".repeat(64),
        source_rev: "git:fixture"
      }]
    }
  };
  assert.equal(validateDispatchManifest(manifest).schema_version, 2);
  assert.throws(() => validateDispatchManifest({ ...manifest, instruction_set: undefined }), /instruction_set must be an object/);
});

test("dispatchable repos include build routing and verification hooks", async () => {
  const manifest = await readJson(join(EXAMPLES_DIR, "homelab-analytics.dispatch.json"));

  assert.equal(manifest.adoption_level, "dispatchable");
  assert.equal(manifest.routing.action_classes.build.enabled, true);
  assert.equal(manifest.routing.action_classes.build.review_required, true);
  assert.ok(manifest.hooks.publishers.includes("dispatcher-gate"));
});

test("stateful manifests select protocol skills and bounded risk surfaces", async () => {
  const manifest = await readJson(join(EXAMPLES_DIR, "actionq.dispatch.json"));
  const validated = validateDispatchManifest(manifest);

  assert.equal(validated.routing.action_classes.verify.enabled, true);
  assert.ok(validated.skills.selected.includes("verify-state-protocols"));
  assert.deepEqual(validated.risk_surfaces[0].skills, ["verify-state-protocols", "reconcile-project-contracts"]);
  assert.deepEqual(validated.risk_surfaces[0].context_ids, ["actionq.action.claim-concurrency"]);
  assert.equal(validated.risk_surfaces[0].default_depth, 2);
});

test("stateful manifest rejects empty context ids", async () => {
  const manifest = await readJson(join(EXAMPLES_DIR, "actionq.dispatch.json"));
  manifest.risk_surfaces[0].context_ids = [];

  assert.throws(() => validateDispatchManifest(manifest), /context_ids must be non-empty strings/);
});

test("dispatch manifests may select the procedurally attested capability receipt skill", async () => {
  const manifest = await readJson(join(EXAMPLES_DIR, "actionq.dispatch.json"));
  manifest.skills.selected.push("capability-receipt");

  assert.ok(validateDispatchManifest(manifest).skills.selected.includes("capability-receipt"));
});

test("dispatch manifest loader lists and filters examples", async () => {
  const all = await listDispatchManifests({ root: EXAMPLES_DIR });
  assert.deepEqual(
    all.manifests.map((manifest) => manifest.repo_id),
    ["actionq", "appservice", "homelab-analytics", "scribectl"]
  );

  const filtered = await getDispatchManifest("appservice", { root: EXAMPLES_DIR });
  assert.equal(filtered.manifests.length, 1);
  assert.equal(filtered.manifests[0].routing.action_classes["release-ops"].enabled, true);
});
