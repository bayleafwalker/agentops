import test from "node:test";
import assert from "node:assert/strict";
import { createGetHandler as createReposHandler } from "../app/cockpit/api/repos/route.js";
import { createGetHandler as createSprintsHandler } from "../app/cockpit/api/sprints/route.js";
import { createGetHandler as createTakeupHandler } from "../app/cockpit/api/takeup/route.js";
import { createGetHandler as createClaimsHandler } from "../app/cockpit/api/claims/route.js";
import { createGetHandler as createEventsHandler } from "../app/cockpit/api/events/route.js";
import { createGetHandler as createAuditHandler } from "../app/cockpit/api/audit/route.js";

function request(url) {
  return new Request(url);
}

test("repos route returns expected shape", async () => {
  const GET = createReposHandler({
    listRepos: async () => [{ repo_id: "alpha", active_sprint_count: 1, active_sprints: [], latest_update_at: null, source_health: { status: "ok" } }]
  });
  const payload = await (await GET(request("http://localhost/cockpit/api/repos"))).json();
  assert.equal(payload.source, "pg://sprintctl");
  assert.equal(payload.repos[0].repo_id, "alpha");
  assert.equal(payload.degraded, null);
});

test("sprints route returns expected shape", async () => {
  let receivedArgs = null;
  const GET = createSprintsHandler({
    listSprints: async (repoId, mode) => {
      receivedArgs = { repoId, mode };
      return [{ repo_id: "alpha", id: 1, name: "Sprint", summary: { total_items: 0, done_items: 0 }, attention: { level: "ok", reasons: [] } }];
    }
  });
  const payload = await (await GET(request("http://localhost/cockpit/api/sprints?repo_id=alpha&mode=backlog"))).json();
  assert.equal(payload.repo_id, "alpha");
  assert.equal(payload.mode, "backlog");
  assert.equal(payload.sprints[0].id, 1);
  assert.deepEqual(receivedArgs, { repoId: "alpha", mode: "backlog" });
});

test("takeup route returns expected shape", async () => {
  const GET = createTakeupHandler({
    getTakeup: async () => ({ operation: "takeup_list", active_takeups: [{ actor: "dev" }], released_takeups: [], unmatched_releases: [] })
  });
  const payload = await (await GET(request("http://localhost/cockpit/api/takeup?repo_id=alpha&sprint_id=9"))).json();
  assert.equal(payload.operation, "takeup_list");
  assert.equal(payload.active_takeups[0].actor, "dev");
});

test("claims route joins claims and sessions", async () => {
  const GET = createClaimsHandler({
    listClaims: async () => [{ claim_id: 81, work_item_id: 95, actor: "codex", runtime_session_id: "aqs:1" }],
    getActionqSessions: async () => [{ session_id: "aqs:1", runtime_session_id: "aqs:1", status: "running", heartbeat_at: "2026-04-29T00:00:00Z", ttl_seconds: 120 }]
  });
  const payload = await (await GET(request("http://localhost/cockpit/api/claims?repo_id=alpha"))).json();
  assert.equal(payload.claims[0].claim.source, "pg://sprintctl");
  assert.equal(payload.claims[0].session.source, "actionq://sessions");
});

test("events route returns expected shape", async () => {
  const GET = createEventsHandler({
    listEvents: async () => ({ events: [{ id: 1, repo_id: "alpha", sprint_id: 9, event_type: "decision", created_at: "2026-04-29T00:00:00Z" }], next_cursor: null })
  });
  const payload = await (await GET(request("http://localhost/cockpit/api/events?repo_id=alpha&limit=10"))).json();
  assert.equal(payload.events[0].event_type, "decision");
});

test("audit route returns expected shape", async () => {
  const GET = createAuditHandler({
    readAuditFeed: async () => ({ repo_id: "alpha", source: "artifact:audit/alpha", events: [{ id: "ad:01ARZ3NDEKTSV4RRFFQ69G5FAV", ts: "2026-04-29T00:00:00Z", type: "decision", actor: "bayleaf", summary: "picked a path", refs: [], source: "git-hook", metadata: {}, created_at: "2026-04-29T00:00:00Z" }], warnings: [], next_cursor: null })
  });
  const payload = await (await GET(request("http://localhost/cockpit/api/audit?repo_id=alpha"))).json();
  assert.equal(payload.source, "artifact:audit/alpha");
  assert.equal(payload.events.length, 1);
});
