import test from "node:test";
import assert from "node:assert/strict";
import { createGetHandler as createReposHandler } from "../app/cockpit/api/repos/route.js";
import { createGetHandler as createSprintsHandler } from "../app/cockpit/api/sprints/route.js";
import { createGetHandler as createTakeupHandler } from "../app/cockpit/api/takeup/route.js";
import { createGetHandler as createClaimsHandler } from "../app/cockpit/api/claims/route.js";
import { createGetHandler as createDispatchesHandler } from "../app/cockpit/api/dispatches/route.js";
import { createGetHandler as createEventsHandler } from "../app/cockpit/api/events/route.js";
import { createGetHandler as createAuditHandler } from "../app/cockpit/api/audit/route.js";
import { createGetHandler as createCostSummaryHandler } from "../app/cockpit/api/costs/summary/route.js";
import { createGetHandler as createHeadroomGetHandler, createPostHandler as createHeadroomPostHandler } from "../app/cockpit/api/headroom/route.js";
import { createGetHandler as createDispatchManifestsHandler } from "../app/cockpit/api/dispatch-manifests/route.js";
import { createGetHandler as createCompletionAlertsHandler, createPostHandler as createCompletionAlertAckHandler } from "../app/cockpit/api/completion-alerts/route.js";
import { createPostHandler as createDispatchHandler } from "../app/cockpit/api/dispatch/route.js";
import { dispatchViaActionctl, forwardDispatchToActionqServer, normalizeDispatchPayload } from "../lib/cockpit/dispatch.js";

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
  assert.equal(payload.source, "served://vuoro/work");
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
    getActionqSessions: async () => [{ session_id: "aqs:1", runtime_session_id: "aqs:1", status: "running", heartbeat_at: "2026-04-29T00:00:00Z", ttl_seconds: 120 }],
    now: () => new Date("2026-04-29T00:01:00Z")
  });
  const payload = await (await GET(request("http://localhost/cockpit/api/claims?repo_id=alpha"))).json();
  assert.equal(payload.claims[0].claim.source, "served://vuoro/work");
  assert.equal(payload.claims[0].session.source, "actionq://sessions");
  assert.equal(payload.claims[0].session.is_stale, false);
  assert.equal(payload.claims[0].session.ttl_remaining_seconds, 60);
});

test("claims route marks sessions stale after heartbeat ttl expires", async () => {
  const GET = createClaimsHandler({
    listClaims: async () => [{ claim_id: 81, work_item_id: 95, actor: "codex", runtime_session_id: "aqs:1" }],
    getActionqSessions: async () => [{ session_id: "aqs:1", runtime_session_id: "aqs:1", status: "running", heartbeat_at: "2026-04-29T00:00:00Z", ttl_seconds: 120 }],
    now: () => new Date("2026-04-29T00:03:00Z")
  });
  const payload = await (await GET(request("http://localhost/cockpit/api/claims?repo_id=alpha"))).json();
  assert.equal(payload.claims[0].session.is_stale, true);
  assert.equal(payload.claims[0].session.deadline_at, "2026-04-29T00:02:00.000Z");
});

test("dispatches route returns actionq lifecycle rows", async () => {
  let args = null;
  const GET = createDispatchesHandler({
    getActionqDispatches: async (received) => {
      args = received;
      return [{ id: 7, action_type: "scope-iterate", project: "alpha", status: "pending", priority: 100, created_at: "2026-05-13T00:00:00Z", source_refs: [] }];
    }
  });
  const payload = await (await GET(request("http://localhost/cockpit/api/dispatches?repo_id=alpha&limit=25"))).json();
  assert.equal(payload.source, "actionq://dispatches");
  assert.equal(payload.dispatches[0].id, 7);
  assert.deepEqual(args, { repoId: "alpha", status: null, limit: 25 });
});

test("cost summary route returns workspace cost shape", async () => {
  const GET = createCostSummaryHandler({
    readCostSummary: async () => ({ day: "2026-05-13", sessions: 2, total_cost_usd: 1.25, by_session: {}, by_model: {} })
  });
  const payload = await (await GET(request("http://localhost/cockpit/api/costs/summary"))).json();
  assert.equal(payload.summary.sessions, 2);
  assert.equal(payload.summary.total_cost_usd, 1.25);
});

test("headroom route returns cached and forced model quota shape", async () => {
  const snapshot = {
    source: "model-headroom",
    refreshed_at: "2026-05-13T10:00:00Z",
    stale: false,
    providers: { codex: { available: true }, claude: { available: false } },
    warnings: [],
    degraded: null
  };
  let forced = false;
  const deps = {
    getModelHeadroom: async ({ force }) => {
      forced = force;
      return snapshot;
    }
  };
  const GET = createHeadroomGetHandler(deps);
  const getPayload = await (await GET(request("http://localhost/cockpit/api/headroom"))).json();
  assert.equal(getPayload.snapshot.refreshed_at, "2026-05-13T10:00:00Z");
  assert.equal(forced, false);

  const POST = createHeadroomPostHandler(deps);
  await POST(request("http://localhost/cockpit/api/headroom"));
  assert.equal(forced, true);
});

test("dispatches route degrades independently when actionq is unavailable", async () => {
  const GET = createDispatchesHandler({
    getActionqDispatches: async () => {
      throw new Error("boom");
    }
  });
  const payload = await (await GET(request("http://localhost/cockpit/api/dispatches?repo_id=alpha"))).json();
  assert.equal(payload.dispatches.length, 0);
  assert.equal(payload.degraded.source, "actionq://dispatches");
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

test("completion alerts route returns the AgentOps projection shape", async () => {
  const GET = createCompletionAlertsHandler({
    readCompletionAlertProjection: async ({ repoId, limit }) => ({
      source: "agentops://completion-alerts",
      repo_id: repoId,
      limit,
      alerts: [{ event_id: "event-1", terminal: { kind: "failed" } }],
      outcomes: [{ event_id: "event-1", outcome: "delivered" }],
      pending_deliveries: [],
      health: { checkpoint: "c1" },
      degraded: null
    })
  });
  const payload = await (await GET(request("http://localhost/cockpit/api/completion-alerts?repo_id=alpha&limit=10"))).json();
  assert.equal(payload.source, "agentops://completion-alerts");
  assert.equal(payload.repo_id, "alpha");
  assert.equal(payload.alerts[0].event_id, "event-1");
  assert.equal(payload.health.checkpoint, "c1");
});

test("completion alert acknowledgement route writes only the AgentOps operator projection", async () => {
  let received = null;
  const POST = createCompletionAlertAckHandler({
    requireConfiguredWriteAuth: () => null,
    acknowledgeCompletionAlert: async (input) => {
      received = input;
      return { source: "agentops://completion-alerts", alert: { alert_id: input.alertId, acknowledged: true }, degraded: null };
    }
  });
  const payload = await (await POST(jsonRequest("http://localhost/cockpit/api/completion-alerts", { alert_id: "4d5e6f70-8192-4a3b-8c0d-3e4f50617284", acknowledged_by: "operator:test" }))).json();
  assert.deepEqual(received, { alertId: "4d5e6f70-8192-4a3b-8c0d-3e4f50617284", acknowledgedBy: "operator:test" });
  assert.equal(payload.alert.acknowledged, true);
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
      return {
        action_id: "aq:12", status: "pending", request_ref: "req:12",
        request_sha256: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
      };
    }
  });
  const response = await POST(jsonRequest("http://localhost/cockpit/api/dispatch", {
    contract_version: "v2",
    action_type: "scope-iterate",
    repo_id: "alpha",
    sprint_id: 12,
    work_item_id: "abc123",
    output_expectation: "implementation",
    title: "Build alpha",
    prompt: "Do the work",
    harness: "codex",
    model: "gpt-5.3-codex",
    priority: "high",
    refs: ["wi:abc123", "sprint:12"],
    dispatch_group_id: null
  }));
  const payload = await response.json();
  assert.equal(response.status, 200);
  assert.equal(payload.accepted, true);
  assert.equal(payload.action.action_id, "aq:12");
  assert.deepEqual(forwarded, {
    contract_version: "v2",
    action_type: "scope-iterate",
    repo_id: "alpha",
    sprint_id: 12,
    work_item_id: "abc123",
    output_expectation: "implementation",
    title: "Build alpha",
    prompt: "Do the work",
    harness: "codex",
    model: "gpt-5.3-codex",
    priority: "high",
    refs: ["wi:abc123", "sprint:12"],
    dispatch_group_id: null,
    requested_by: "operator:test"
  });
});

test("dispatch route accepts no-sprint refinement payload", async () => {
  let forwarded = null;
  const POST = createDispatchHandler({
    getDispatchGate: () => ({ enabled: true, source: "actionq-server" }),
    getDispatchOperator: () => "operator:test",
    forwardDispatchToActionqServer: async (payload) => {
      forwarded = payload;
      return {
        action_id: 13, status: "pending", request_ref: "req:13",
        request_sha256: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
      };
    }
  });
  const response = await POST(jsonRequest("http://localhost/cockpit/api/dispatch", {
    contract_version: "v2",
    action_type: "scope-iterate",
    repo_id: "alpha",
    sprint_id: null,
    work_item_id: null,
    output_expectation: "sprint-proposal",
    title: "Refine backlog",
    prompt: "",
    harness: "codex",
    model: null,
    priority: "normal",
    refs: [],
    dispatch_group_id: "dg:refine"
  }));
  const payload = await response.json();
  assert.equal(response.status, 200);
  assert.equal(payload.accepted, true);
  assert.equal(forwarded.sprint_id, null);
  assert.equal(forwarded.output_expectation, "sprint-proposal");
  assert.equal(forwarded.dispatch_group_id, "dg:refine");
});

test("dispatch forwarder preserves upstream status for non-json failures", async () => {
  await assert.rejects(
    () => forwardDispatchToActionqServer(
      {
        contract_version: "v2",
        action_type: "scope-iterate",
        repo_id: "alpha",
        sprint_id: 12,
        work_item_id: null,
        output_expectation: "implementation",
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
          actionqDispatchContract: "v2"
        },
        fetchImpl: async () => new Response("bad gateway", { status: 502 })
      }
    ),
    /actionq-server dispatch failed with 502/
  );
});

test("dispatch route rejects v2 kind and normalizes an explicit v1 alias", async () => {
  const POST = createDispatchHandler({
    getDispatchGate: () => ({ enabled: true, source: "actionq-server" }),
    getDispatchOperator: () => "operator:test",
    forwardDispatchToActionqServer: async (payload) => payload
  });
  const rejected = await POST(jsonRequest("http://localhost/cockpit/api/dispatch", {
    contract_version: "v2", action_type: "scope-iterate", repo_id: "alpha", sprint_id: null,
    work_item_id: null, kind: "implement", output_expectation: "implementation", title: "t",
    prompt: "", harness: "codex", model: null, priority: "normal", refs: [], dispatch_group_id: null
  }));
  assert.equal(rejected.status, 400);

  const accepted = await POST(jsonRequest("http://localhost/cockpit/api/dispatch", {
    contract_version: "v1", repo_id: "alpha", kind: "review", title: "t", prompt: "",
    harness: "codex", priority: "normal", refs: []
  }));
  const body = await accepted.json();
  assert.equal(accepted.status, 200);
  assert.equal(body.action.contract_version, "v2");
  assert.equal(body.action.action_type, "scope-iterate");
  assert.equal(body.action.output_expectation, "review");
  assert.equal(Object.hasOwn(body.action, "kind"), false);
});

test("dispatch route rejects omitted v2 fields instead of applying v1 defaults", async () => {
  const POST = createDispatchHandler({
    getDispatchGate: () => ({ enabled: true, source: "actionq-server" }),
    getDispatchOperator: () => "operator:test",
    forwardDispatchToActionqServer: async () => ({})
  });
  const response = await POST(jsonRequest("http://localhost/cockpit/api/dispatch", {
    contract_version: "v2", action_type: "scope-iterate", output_expectation: "plan",
    repo_id: "alpha", title: "Incomplete", prompt: "", harness: "codex", priority: "normal"
  }));
  assert.equal(response.status, 400);
  assert.match((await response.json()).degraded.detail, /sprint_id is required/);
});

test("v2 normalizer rejects unknown fields, wrong types, and blank nullable values", () => {
  const valid = {
    contract_version: "v2", action_type: "scope-iterate", output_expectation: "plan", repo_id: "alpha",
    sprint_id: null, work_item_id: null, title: "t", prompt: "", harness: "codex", model: null,
    priority: "normal", refs: [], dispatch_group_id: null
  };
  assert.throws(() => normalizeDispatchPayload({ ...valid, unexpected: true }, { requestedBy: "operator:test" }), /unknown v2 dispatch field/);
  assert.throws(() => normalizeDispatchPayload({ ...valid, refs: null }, { requestedBy: "operator:test" }), /refs must be an array/);
  assert.throws(() => normalizeDispatchPayload({ ...valid, model: " " }, { requestedBy: "operator:test" }), /model must be null or a non-blank string/);
  assert.throws(() => normalizeDispatchPayload({ ...valid, work_item_id: "wi:" }, { requestedBy: "operator:test" }), /must be normalized without a wi: prefix/);
  assert.throws(() => normalizeDispatchPayload({ ...valid, prompt: null }, { requestedBy: "operator:test" }), /prompt must be a string/);

  for (const [field, value, message] of [
    ["sprint_id", 0, /positive integer/],
    ["sprint_id", -1, /positive integer/],
    ["action_type", " scope-iterate ", /exactly scope-iterate/],
    ["output_expectation", " plan ", /exact v2 enum/],
    ["harness", " codex ", /exact v2 enum/],
    ["priority", " normal ", /exact v2 enum/]
  ]) {
    assert.throws(() => normalizeDispatchPayload({ ...valid, [field]: value }, { requestedBy: "operator:test" }), message);
  }
});

test("dispatch forwarder requires the exact ActionQ enqueue result schema on success", async () => {
  const payload = {
    contract_version: "v2", action_type: "scope-iterate", output_expectation: "plan", repo_id: "alpha",
    sprint_id: null, work_item_id: null, title: "t", prompt: "", harness: "codex", model: null,
    priority: "normal", refs: [], dispatch_group_id: null, requested_by: "operator:test"
  };
  const validResult = {
    action_id: "aq:1", status: "pending", request_ref: "req:opaque",
    request_sha256: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  };
  const options = {
    config: { actionqServerUrl: "http://actionq-server", actionqDispatchContract: "v2" },
    fetchImpl: async () => Response.json({ action_id: "aq:1", status: "pending" })
  };
  await assert.rejects(() => forwardDispatchToActionqServer(payload, options), /missing request_ref/);
  await assert.rejects(() => forwardDispatchToActionqServer(payload, {
    ...options, fetchImpl: async () => Response.json({ ...validResult, status: "completed" })
  }), /must have status pending/);
  await assert.rejects(() => forwardDispatchToActionqServer(payload, {
    ...options, fetchImpl: async () => Response.json({ ...validResult, action_id: "" })
  }), /valid action_id/);
  await assert.rejects(() => forwardDispatchToActionqServer(payload, {
    ...options,
    fetchImpl: async () => {
      const { action_id, ...withoutActionId } = validResult;
      return Response.json(withoutActionId);
    }
  }), /missing action_id/);
  await assert.rejects(() => forwardDispatchToActionqServer(payload, {
    ...options, fetchImpl: async () => Response.json({ ...validResult, extra: true })
  }), /unknown field/);
  const accepted = await forwardDispatchToActionqServer(payload, {
    ...options,
    fetchImpl: async () => Response.json(validResult)
  });
  assert.equal(accepted.request_ref, "req:opaque");
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
