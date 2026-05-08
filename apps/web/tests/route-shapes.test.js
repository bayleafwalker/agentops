import test from "node:test";
import assert from "node:assert/strict";
import { createGetHandler as createReposHandler } from "../app/cockpit/api/repos/route.js";
import { createGetHandler as createSprintsHandler } from "../app/cockpit/api/sprints/route.js";
import { createGetHandler as createTakeupHandler } from "../app/cockpit/api/takeup/route.js";
import { createGetHandler as createClaimsHandler } from "../app/cockpit/api/claims/route.js";
import { createGetHandler as createEventsHandler } from "../app/cockpit/api/events/route.js";
import { createGetHandler as createAuditHandler } from "../app/cockpit/api/audit/route.js";
import { createGetHandler as createDispatchManifestsHandler } from "../app/cockpit/api/dispatch-manifests/route.js";
import { createPostHandler as createDispatchHandler } from "../app/cockpit/api/dispatch/route.js";
import { dispatchViaActionctl, forwardDispatchToActionqServer } from "../lib/cockpit/dispatch.js";

function request(url) {
  return new Request(url);
}

function jsonRequest(url, body) {
  return new Request(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body)
  });
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

test("dispatch manifests route returns expected shape", async () => {
  const GET = createDispatchManifestsHandler({
    listDispatchManifests: async () => ({
      source: "dispatch-manifest:/tmp/manifests",
      manifests: [{ repo_id: "alpha", adoption_level: "dispatchable", routing: {}, skills: [], verification: {}, hooks: {} }],
      warnings: []
    }),
    getDispatchManifest: async () => {
      throw new Error("filter should not be called for ALL");
    }
  });
  const payload = await (await GET(request("http://localhost/cockpit/api/dispatch-manifests"))).json();
  assert.equal(payload.repo_id, "ALL");
  assert.equal(payload.manifests[0].repo_id, "alpha");
  assert.equal(payload.degraded, null);
});

test("dispatch route stays gated without actionq-server contract", async () => {
  const POST = createDispatchHandler({
    getDispatchGate: () => ({ enabled: false, source: "actionq-server", reason: "Dispatch disabled: no contract." }),
    getDispatchOperator: () => "operator:test",
    forwardDispatchToActionqServer: async () => {
      throw new Error("should not forward");
    }
  });
  const response = await POST(jsonRequest("http://localhost/cockpit/api/dispatch", {
    repo_id: "alpha",
    sprint_id: 12,
    kind: "implement",
    title: "Build alpha",
    harness: "codex"
  }));
  const payload = await response.json();
  assert.equal(response.status, 503);
  assert.equal(payload.accepted, false);
  assert.equal(payload.source, "actionq-server");
});

test("dispatch route forwards validated payload when gate is enabled", async () => {
  let forwarded = null;
  const POST = createDispatchHandler({
    getDispatchGate: () => ({ enabled: true, source: "actionq-server" }),
    getDispatchOperator: () => "operator:test",
    forwardDispatchToActionqServer: async (payload) => {
      forwarded = payload;
      return { action_id: "aq:12", status: "queued" };
    }
  });
  const response = await POST(jsonRequest("http://localhost/cockpit/api/dispatch", {
    repo_id: "alpha",
    sprint_id: 12,
    work_item_id: "wi:abc123",
    kind: "implement",
    title: "Build alpha",
    prompt: "Do the work",
    harness: "codex",
    model: "gpt-5.3-codex",
    priority: "high",
    refs: ["wi:abc123", "sprint:12"],
    requested_by: "operator:browser"
  }));
  const payload = await response.json();
  assert.equal(response.status, 200);
  assert.equal(payload.accepted, true);
  assert.equal(payload.action.action_id, "aq:12");
  assert.deepEqual(forwarded, {
    repo_id: "alpha",
    sprint_id: 12,
    work_item_id: "wi:abc123",
    kind: "implement",
    title: "Build alpha",
    prompt: "Do the work",
    harness: "codex",
    model: "gpt-5.3-codex",
    priority: "high",
    refs: ["wi:abc123", "sprint:12"],
    requested_by: "operator:test"
  });
});

test("dispatch forwarder preserves upstream status for non-json failures", async () => {
  await assert.rejects(
    () => forwardDispatchToActionqServer(
      {
        repo_id: "alpha",
        sprint_id: 12,
        work_item_id: null,
        kind: "implement",
        title: "Build alpha",
        prompt: "",
        harness: "codex",
        model: null,
        priority: "normal",
        refs: [],
        requested_by: "operator:test"
      },
      {
        config: {
          actionqServerUrl: "http://actionq-server",
          actionqDispatchContract: "v1"
        },
        fetchImpl: async () => new Response("bad gateway", { status: 502 })
      }
    ),
    /actionq-server dispatch failed with 502/
  );
});

test("dispatch route uses actionctl when gate method is actionctl", async () => {
  let dispatchedPayload = null;
  let dispatchedBin = null;
  const POST = createDispatchHandler({
    getDispatchGate: () => ({ enabled: true, source: "actionctl", method: "actionctl", bin: "/usr/local/bin/actionctl" }),
    getDispatchOperator: () => "operator:test",
    dispatchViaActionctl: async (payload, bin) => {
      dispatchedPayload = payload;
      dispatchedBin = bin;
      return { id: 42, type: "scope-iterate", status: "pending" };
    },
    forwardDispatchToActionqServer: async () => {
      throw new Error("should not forward to server");
    }
  });
  const response = await POST(jsonRequest("http://localhost/cockpit/api/dispatch", {
    repo_id: "alpha",
    sprint_id: 12,
    work_item_id: "wi:42",
    kind: "implement",
    title: "Build alpha",
    harness: "claude",
    priority: "high"
  }));
  const payload = await response.json();
  assert.equal(response.status, 200);
  assert.equal(payload.accepted, true);
  assert.equal(payload.source, "actionctl");
  assert.equal(payload.action.id, 42);
  assert.equal(dispatchedPayload.repo_id, "alpha");
  assert.equal(dispatchedPayload.priority, "high");
  assert.equal(dispatchedBin, "/usr/local/bin/actionctl");
});
