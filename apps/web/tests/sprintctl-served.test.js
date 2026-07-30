import test from "node:test";
import assert from "node:assert/strict";
import {
  createSprintctlSource,
  SprintTransitionError
} from "../lib/cockpit/sprintctl.js";

const config = {
  sprintctlRepoRoot: "/workspace/agentops",
  workspaceRoot: "/workspace"
};

function fixtureRun(calls = []) {
  return async (args, options) => {
    calls.push({ args, options });
    const command = args.slice(0, 2).join(" ");
    if (command === "sprint list") {
      return [
        {
          repo_id: "alpha", id: 10, name: "Active", status: "active",
          kind: "active_sprint", created_at: "2026-07-30T10:00:00Z"
        },
        {
          repo_id: "beta", id: 11, name: "Backlog", status: "planned",
          kind: "backlog", created_at: "2026-07-29T10:00:00Z"
        }
      ];
    }
    if (command === "item list") {
      return [{
        repo_id: "alpha", id: 20, sprint_id: 10, title: "Work", status: "pending",
        track_name: "work", created_at: "2026-07-30T10:01:00Z",
        updated_at: "2026-07-30T10:02:00Z"
      }];
    }
    if (command === "claim list-sprint") {
      return [{
        claim_id: 30, work_item_id: 20, actor: "worker", claim_type: "execute",
        exclusive: true, heartbeat: "2026-07-30T10:03:00Z",
        expires_at: "2026-07-30T10:08:00Z"
      }];
    }
    if (command === "event list") {
      return [{
        repo_id: "alpha", id: 40, sprint_id: 10, actor: "worker",
        event_type: "decision", source_type: "actor", payload: { summary: "picked" },
        created_at: "2026-07-30T10:04:00Z"
      }];
    }
    if (command === "sprint status") return { sprint_id: 10, previous: "planned", status: "active" };
    throw new Error(`unexpected command: ${args.join(" ")}`);
  };
}

test("served source builds cockpit repository and sprint projections without SQL", async () => {
  const calls = [];
  const source = createSprintctlSource(fixtureRun(calls), config);

  const repos = await source.listRepos();
  const sprints = await source.listSprints("alpha", "active");

  assert.deepEqual(repos.map((repo) => repo.repo_id), ["alpha", "beta"]);
  assert.equal(repos[0].source_health.source, "served://vuoro/work");
  assert.equal(sprints.length, 1);
  assert.equal(sprints[0].work_items[0].id, 20);
  assert.equal(sprints[0].summary.pending_items, 1);
  assert.ok(calls.every((call) => call.options.cwd === "/workspace/agentops"));
});

test("served source reads claims and events from repository-scoped commands", async () => {
  const calls = [];
  const source = createSprintctlSource(fixtureRun(calls), config);

  const claims = await source.listClaims("alpha", 10);
  const events = await source.listEvents({ repoId: "alpha", sprintId: 10, limit: 10 });

  assert.equal(claims[0].claim_id, 30);
  assert.equal(events.events[0].id, 40);
  assert.ok(
    calls
      .filter((call) => ["claim", "event"].includes(call.args[0]))
      .every((call) => call.options.cwd === "/workspace/alpha")
  );
});

test("served activation uses the authority CLI and preserves transition errors", async () => {
  const calls = [];
  const source = createSprintctlSource(fixtureRun(calls), config);
  const activated = await source.activateSprint("alpha", 10, { actor: "operator:test" });

  assert.equal(activated.status, "active");
  assert.ok(calls.some((call) => call.args.join(" ").includes("sprint status --id alpha#10")));

  const rejected = createSprintctlSource(async (args) => {
    if (args[0] === "sprint" && args[1] === "list") {
      return [{ repo_id: "alpha", id: 10, status: "planned", kind: "backlog" }];
    }
    const error = new Error("command failed");
    error.stderr = "invalid-transition: cannot transition sprint closed -> active";
    throw error;
  }, config);
  await assert.rejects(
    rejected.activateSprint("alpha", 10),
    SprintTransitionError
  );
});
