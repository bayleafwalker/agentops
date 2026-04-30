import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { join } from "node:path";

const ROOT = join(process.cwd(), "../..");
const EXAMPLES_DIR = join(ROOT, "templates/dispatch/examples");
const TEMPLATE_SKILLS = new Set([
  "dispatch-plan",
  "dispatch-build",
  "dispatch-review",
  "code-change-verification",
  "pr-handoff-summary",
  "sprint-resume",
  "sprint-packet",
  "item-done",
  "sprint-snapshot",
  "kctl-extract"
]);
const ADOPTION_LEVELS = new Set(["guidance-only", "observable", "dispatchable"]);
const ROUTING_CLASSES = new Set(["plan", "build", "review", "release-ops", "meta-dispatch"]);

async function readJson(path) {
  return JSON.parse(await readFile(path, "utf8"));
}

function validateDispatchManifest(manifest) {
  assert.equal(manifest.schema_version, 1);
  assert.match(manifest.repo_id, /^[A-Za-z0-9._-]+$/);
  assert.ok(ADOPTION_LEVELS.has(manifest.adoption_level));

  assert.ok(manifest.routing.default_harness);
  assert.ok(manifest.routing.default_model_alias);
  assert.ok(Object.keys(manifest.routing.action_classes).length > 0);
  for (const [name, actionClass] of Object.entries(manifest.routing.action_classes)) {
    assert.ok(ROUTING_CLASSES.has(name), `${manifest.repo_id} has unknown action class ${name}`);
    assert.equal(typeof actionClass.enabled, "boolean");
  }

  assert.ok(manifest.skills.selected.length > 0);
  for (const skill of manifest.skills.selected) {
    assert.ok(TEMPLATE_SKILLS.has(skill), `${manifest.repo_id} selects unknown skill ${skill}`);
  }

  assert.ok(manifest.verification.command_families.length > 0);
  assert.equal(typeof manifest.hooks.level, "string");
  assert.ok(Array.isArray(manifest.hooks.publishers));
}

test("dispatch manifest examples satisfy routing contract invariants", async () => {
  for (const file of ["homelab-analytics.dispatch.json", "appservice.dispatch.json"]) {
    validateDispatchManifest(await readJson(join(EXAMPLES_DIR, file)));
  }
});

test("dispatchable repos include build routing and verification hooks", async () => {
  const manifest = await readJson(join(EXAMPLES_DIR, "homelab-analytics.dispatch.json"));

  assert.equal(manifest.adoption_level, "dispatchable");
  assert.equal(manifest.routing.action_classes.build.enabled, true);
  assert.equal(manifest.routing.action_classes.build.review_required, true);
  assert.ok(manifest.hooks.publishers.includes("dispatcher-gate"));
});
