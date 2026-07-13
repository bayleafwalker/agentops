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
  assert.equal(validated.risk_surfaces[0].default_depth, 2);
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
