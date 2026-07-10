import test from "node:test";
import assert from "node:assert/strict";
import { buildCommandPaletteEntries, DEFAULT_TWEAKS, getPollIntervalMs, getVisibilityBackoffMultiplier, pickSprintSelection, SPRINT_VIEW_MODES, summarizeReviewWorktrees } from "../lib/cockpit/client-state.js";

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
    selectedRepo: "alpha",
    sprintMode: "backlog"
  });
  assert.deepEqual(DEFAULT_TWEAKS, { compact: false, alwaysShowSources: true, eventLimit: 20, pollAll: false });
  assert.deepEqual(SPRINT_VIEW_MODES, ["active", "backlog", "history"]);
  assert.equal(entries[0].id, "repo:ALL");
  assert.equal(entries[1].meta, "2 active sprints");
  assert.equal(entries[2].id, "sprint:alpha:11");
  assert.equal(entries[2].meta, "backlog / selected repo");
});

test("review worktree summary includes only failed and rejected dispatches with worktrees", () => {
  const summary = summarizeReviewWorktrees([
    {
      id: 1,
      project: "alpha",
      status: "failed",
      completed_at: "2026-05-10T10:00:00Z",
      failure_reason: "tests failed",
      session: { worktree: "/tmp/wt/1", branch: "agent/1" }
    },
    {
      id: 2,
      project: "alpha",
      status: "rejected",
      completed_at: "2026-05-12T10:00:00Z",
      session: { worktree: "/tmp/wt/2" }
    },
    {
      id: 3,
      project: "alpha",
      status: "completed",
      completed_at: "2026-05-09T10:00:00Z",
      session: { worktree: "/tmp/wt/3" }
    },
    {
      id: 4,
      project: "alpha",
      status: "failed",
      completed_at: "2026-05-08T10:00:00Z",
      session: null
    }
  ], { now: new Date("2026-05-13T10:00:00Z") });

  assert.equal(summary.count, 2);
  assert.equal(summary.oldest_age_seconds, 259200);
  assert.deepEqual(summary.rows.map((row) => row.action_id), [1, 2]);
});
