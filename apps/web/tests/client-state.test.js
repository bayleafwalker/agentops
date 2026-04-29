import test from "node:test";
import assert from "node:assert/strict";
import { buildCommandPaletteEntries, DEFAULT_TWEAKS, getPollIntervalMs, getVisibilityBackoffMultiplier, pickSprintSelection } from "../lib/cockpit/client-state.js";

test("visibility backoff multiplies hidden polling by four", () => {
  assert.equal(getVisibilityBackoffMultiplier("visible"), 1);
  assert.equal(getVisibilityBackoffMultiplier("hidden"), 4);
  assert.equal(getPollIntervalMs("claims", "hidden"), 40000);
  assert.equal(getPollIntervalMs("primary", "visible"), 30000);
});

test("pickSprintSelection preserves valid sprint and falls back to first", () => {
  const sprints = [{ id: 7 }, { id: 9 }];
  assert.equal(pickSprintSelection(sprints, "9"), "9");
  assert.equal(pickSprintSelection(sprints, "44"), "7");
  assert.equal(pickSprintSelection([], "44"), "");
});

test("command palette entries include ALL, repos, and sprints", () => {
  const entries = buildCommandPaletteEntries({
    repos: [{ repo_id: "alpha", active_sprint_count: 2 }],
    sprints: [{ repo_id: "alpha", id: 11, name: "Forge" }],
    selectedRepo: "alpha"
  });
  assert.deepEqual(DEFAULT_TWEAKS, { compact: false, alwaysShowSources: true, eventLimit: 20 });
  assert.equal(entries[0].id, "repo:ALL");
  assert.equal(entries[1].meta, "2 active sprints");
  assert.equal(entries[2].id, "sprint:alpha:11");
  assert.equal(entries[2].meta, "selected repo");
});
