import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {
  CompletionAlertConsumer,
  DEFAULT_COMPLETION_ALERT_POLICY,
  DurableCompletionAlertStore,
  evaluateCompletionAlertPolicy,
  normalizeCompletionAlertPolicy,
  readCompletionAlertProjection,
  readCompletionPage,
  validateCompletionEvent
} from "../lib/cockpit/completion-alerts.js";

const EXAMPLE_PATH = path.resolve("../../templates/dispatch/session-mechanization/session-completion-observed.example.json");

async function fixture() {
  const event = JSON.parse(await fs.readFile(EXAMPLE_PATH, "utf8"));
  event.completed_at = "2026-08-11T12:04:12Z";
  event.observed_at = event.completed_at;
  event.started_at = "2026-08-11T12:00:00Z";
  event.duration_ms = 252000;
  return event;
}

async function failureFixture() {
  const event = await fixture();
  event.event_id = "4d5e6f70-8192-4a3b-8c0d-3e4f50617284";
  event.origin_sequence = 43;
  event.terminal = { kind: "failed", exit_code: 2, reason_code: "process-exit", retryable: true };
  return event;
}

async function stateRoot() {
  return fs.mkdtemp(path.join(os.tmpdir(), "agentops-completion-alerts-"));
}

function clock(value = "2026-08-11T12:05:00Z") {
  let current = new Date(value);
  return {
    now: () => new Date(current),
    set(next) { current = new Date(next); }
  };
}

test("completion validation rejects prohibited fields and inconsistent terminal facts", async () => {
  const event = await fixture();
  assert.doesNotThrow(() => validateCompletionEvent(event));
  assert.throws(() => validateCompletionEvent({ ...event, prompt: "never store this" }), /prohibited/);
  assert.throws(() => validateCompletionEvent({ ...event, terminal: { ...event.terminal, exit_code: 3 } }), /succeeded completion/);
  assert.throws(() => validateCompletionEvent({ ...event, terminal: { ...event.terminal, reason_code: "process-exit" } }), /reason_code/);
});

test("policy suppresses success by default and can explicitly alert every terminal", async () => {
  const event = await fixture();
  assert.equal(evaluateCompletionAlertPolicy(event).decision, "suppress");
  const all = normalizeCompletionAlertPolicy({ ...DEFAULT_COMPLETION_ALERT_POLICY, terminal_mode: "all" });
  assert.equal(evaluateCompletionAlertPolicy(event, all).decision, "deliver");
});

test("terminal-kind policy filtering is validated and preserves failed/cancelled/timed-out distinctions", async () => {
  const failed = await failureFixture();
  const failedOnly = normalizeCompletionAlertPolicy({ ...DEFAULT_COMPLETION_ALERT_POLICY, terminal_kinds: ["failed"] });
  assert.equal(evaluateCompletionAlertPolicy(failed, failedOnly).decision, "deliver");

  const cancelled = { ...structuredClone(failed), terminal: { kind: "cancelled", exit_code: null, reason_code: "cancelled", retryable: false } };
  const timedOut = { ...structuredClone(failed), terminal: { kind: "timed-out", exit_code: null, reason_code: "timeout", retryable: true } };
  assert.equal(evaluateCompletionAlertPolicy(cancelled, failedOnly).reason, "terminal-kind-filter");
  assert.equal(evaluateCompletionAlertPolicy(timedOut, failedOnly).reason, "terminal-kind-filter");
  assert.equal(evaluateCompletionAlertPolicy(cancelled, normalizeCompletionAlertPolicy({ ...DEFAULT_COMPLETION_ALERT_POLICY, terminal_kinds: ["cancelled"] })).decision, "deliver");
  assert.equal(evaluateCompletionAlertPolicy(timedOut, normalizeCompletionAlertPolicy({ ...DEFAULT_COMPLETION_ALERT_POLICY, terminal_kinds: ["timed-out"] })).decision, "deliver");
  assert.throws(() => normalizeCompletionAlertPolicy({ ...DEFAULT_COMPLETION_ALERT_POLICY, terminal_kinds: [] }), /terminal_kinds/);
  assert.throws(() => normalizeCompletionAlertPolicy({ ...DEFAULT_COMPLETION_ALERT_POLICY, terminal_kinds: ["failed", "unknown"] }), /terminal_kinds/);
});

test("duplicate pages and restart with a new consumer instance preserve one inbox fact, receipt, and projection", async () => {
  const root = await stateRoot();
  const event = await failureFixture();
  const pages = [
    { events: [event], next_cursor: "cursor-1" },
    { events: [structuredClone(event)], next_cursor: "cursor-2" }
  ];
  let deliveries = 0;
  const firstConsumer = new CompletionAlertConsumer({
    stateRoot: root,
    fetchPage: async () => pages.shift(),
    now: () => new Date("2026-08-11T12:05:00Z"),
    deliverRoute: async ({ event: received }) => { deliveries += 1; await new DurableCompletionAlertStore({ root }).writeProjection({ alert_id: received.event_id, event_id: received.event_id, repo: received.repo, completed_at: received.completed_at }); }
  });
  const first = await firstConsumer.pollOnce();
  const secondConsumer = new CompletionAlertConsumer({
    stateRoot: root,
    fetchPage: async () => pages.shift(),
    now: () => new Date("2026-08-11T12:05:00Z"),
    deliverRoute: async ({ event: received }) => { deliveries += 1; await new DurableCompletionAlertStore({ root }).writeProjection({ alert_id: received.event_id, event_id: received.event_id, repo: received.repo, completed_at: received.completed_at }); }
  });
  const second = await secondConsumer.pollOnce();
  assert.equal(first.status, "ok");
  assert.equal(second.status, "ok");
  assert.equal(deliveries, 1);
  const store = new DurableCompletionAlertStore({ root });
  assert.ok(await store.readInbox(event.event_id));
  assert.equal((await store.readOutcome(event.event_id)).outcome, "delivered");
  assert.equal((await store.readReceipt(event.event_id)).state, "delivered");
  assert.equal((await store.readCheckpoint()).server_cursor, "cursor-2");
});

test("expired served cursor is explicit and never advances the durable consumer checkpoint", async () => {
  const root = await stateRoot();
  const store = new DurableCompletionAlertStore({ root });
  await store.initialize();
  await store.writeCheckpoint({ server_cursor: 0, pages: 4, events_seen: 9 });
  let requests = 0;
  const consumer = new CompletionAlertConsumer({
    stateRoot: root,
    fetchPage: async () => {
      requests += 1;
      return {
        schema_version: "session-completion-cursor/v1",
        status: "cursor_expired",
        cursor: 0,
        events: [],
        next_cursor: 0,
        server_cursor: 9,
        recovery_floor: 4,
        advance_cursor: false,
        error: { code: "cursor_expired", message: "completion cursor is below the durable recovery floor" },
        health: { cursor_expired: true, recovery_floor: 4, ingest_lag_seconds: 7 }
      };
    }
  });
  const result = await consumer.pollOnce();
  assert.equal(result.status, "cursor-expired");
  assert.equal(result.cursor_expired, true);
  assert.equal(result.recovery_floor, 4);
  assert.equal(result.health.server.cursor_expired, true);
  assert.equal(result.health.server.recovery_floor, 4);
  assert.equal(requests, 1);
  assert.equal((await store.readCheckpoint()).server_cursor, 0);
});

test("readCompletionPage preserves the released ActionQ cursor-expired response", async () => {
  const page = await readCompletionPage({
    cursor: 0,
    config: { completionAlertActionqUrl: "https://actionq.example/session-completions", completionAlertReadToken: "read-secret", completionAlertPageSize: 10, completionAlertPollTimeoutMs: 1000 },
    fetchImpl: async () => new Response(JSON.stringify({
      schema_version: "session-completion-cursor/v1",
      status: "cursor_expired",
      error: { code: "cursor_expired", message: "completion cursor is below the durable recovery floor", recovery_floor: 4 },
      cursor: 0,
      recovery_floor: 4,
      server_cursor: 9,
      next_cursor: 0,
      events: [],
      advance_cursor: false,
      gap: false,
      requires_replay: false,
      health: {}
    }), { status: 409, headers: { "content-type": "application/json" } })
  });
  assert.equal(page.cursor_expired, true);
  assert.equal(page.advance_cursor, false);
  assert.equal(page.next_cursor, 0);
  assert.equal(page.recovery_floor, 4);
  assert.equal(page.server_cursor, 9);
});

test("ActionQ read failure marks server unavailable without discarding the last server health", async () => {
  const root = await stateRoot();
  const store = new DurableCompletionAlertStore({ root });
  await store.initialize();
  await store.writeHealth({ server: { cursor: 8, ingest_lag_seconds: 2 } });
  const consumer = new CompletionAlertConsumer({
    stateRoot: root,
    fetchPage: async () => { throw new Error("completion log read failed"); }
  });
  const result = await consumer.pollOnce();
  assert.equal(result.status, "degraded");
  const health = await consumer.health();
  assert.equal(health.consumer.server_unavailable, true);
  assert.equal(health.server.cursor, 8);
});

test("closed event identities reject traversal, absolute, and encoded path attacks before filesystem access", async () => {
  const root = await stateRoot();
  const store = new DurableCompletionAlertStore({ root });
  const maliciousIds = ["../neighbor", "/tmp/escape", "..%2fneighbor", "%2e%2e%2fneighbor", "C:\\escape"];
  for (const maliciousId of maliciousIds) {
    await assert.rejects(() => store.readInbox(maliciousId), /safe closed path identity|lowercase UUID/);
    await assert.rejects(() => store.readOutcome(maliciousId), /safe closed path identity|lowercase UUID/);
    await assert.rejects(() => store.readReceipt(maliciousId), /safe closed path identity|lowercase UUID/);
    await assert.rejects(() => store.readProjection(maliciousId), /safe closed path identity|lowercase UUID/);
  }
  const valid = await failureFixture();
  const poisonEvents = maliciousIds.map((event_id, index) => ({ ...structuredClone(valid), event_id, origin_sequence: 100 + index }));
  const consumer = new CompletionAlertConsumer({ stateRoot: root, fetchPage: async () => ({ events: [...poisonEvents, valid], next_cursor: "identity-safe" }) });
  const result = await consumer.pollOnce();
  assert.equal(result.results.filter((entry) => entry.outcome === "dead-lettered").length, maliciousIds.length);
  assert.equal((await new DurableCompletionAlertStore({ root }).readOutcome(valid.event_id)).outcome, "delivered");
  await assert.rejects(() => fs.stat(path.join(path.dirname(root), "neighbor")), { code: "ENOENT" });
  assert.equal((await fs.readdir(path.join(root, "quarantine"))).length, maliciousIds.length);
});

test("stream-position or event-id digest conflicts quarantine without rewriting the accepted outcome", async () => {
  const root = await stateRoot();
  const event = await failureFixture();
  const conflicting = { ...structuredClone(event), terminal: { ...event.terminal, exit_code: 3 } };
  const pages = [{ events: [event], next_cursor: "d1" }, { events: [conflicting], next_cursor: "d2" }];
  const consumer = new CompletionAlertConsumer({ stateRoot: root, fetchPage: async () => pages.shift() });
  await consumer.pollOnce();
  await consumer.pollOnce();
  const store = new DurableCompletionAlertStore({ root });
  assert.equal((await store.readOutcome(event.event_id)).outcome, "delivered");
  assert.equal((await consumer.health()).quarantine_count, 1);
});

test("server gap is repaired by replay before cursor advancement", async () => {
  const root = await stateRoot();
  const event = await fixture();
  const requests = [];
  const consumer = new CompletionAlertConsumer({
    stateRoot: root,
    fetchPage: async ({ replay }) => {
      requests.push(Boolean(replay));
      return replay ? { events: [event], next_cursor: "repaired-1" } : { events: [], next_cursor: "gap-1", gap: true };
    }
  });
  await consumer.pollOnce();
  assert.deepEqual(requests, [false, true]);
  assert.equal((await new DurableCompletionAlertStore({ root }).readCheckpoint()).server_cursor, "repaired-1");
});

test("a route outage remains pending, retries with the same idempotency key, and then delivers", async () => {
  const root = await stateRoot();
  const event = await failureFixture();
  const pages = [{ events: [event], next_cursor: "c1" }, { events: [], next_cursor: "c1" }];
  let attempts = 0;
  const consumer = new CompletionAlertConsumer({
    stateRoot: root,
    fetchPage: async () => pages.shift(),
    retryBaseMs: 50,
    retryMaxMs: 50,
    deliverRoute: async () => { attempts += 1; if (attempts === 1) throw new Error("cockpit offline"); }
  });
  await consumer.pollOnce();
  assert.equal((await new DurableCompletionAlertStore({ root }).readOutcome(event.event_id)).outcome, "pending");
  const receipt = await new DurableCompletionAlertStore({ root }).readReceipt(event.event_id);
  assert.equal(receipt.attempts, 1);
  receipt.next_attempt_at = "2020-01-01T00:00:00Z";
  await new DurableCompletionAlertStore({ root }).writeReceipt(receipt);
  await consumer.pollOnce();
  assert.equal(attempts, 2);
  assert.equal((await new DurableCompletionAlertStore({ root }).readOutcome(event.event_id)).outcome, "delivered");
  assert.equal((await new DurableCompletionAlertStore({ root }).readReceipt(event.event_id)).attempts, 2);
});

test("local route processing failure is persisted without becoming server unavailable", async () => {
  const root = await stateRoot();
  const event = await failureFixture();
  const consumer = new CompletionAlertConsumer({
    stateRoot: root,
    fetchPage: async () => ({ events: [event], next_cursor: "route-local-1" }),
    deliverRoute: async () => { throw new Error("cockpit projection write failed"); }
  });
  const result = await consumer.pollOnce();
  assert.equal(result.status, "degraded");
  assert.equal(result.failure_origin, "local-route");
  assert.equal(result.server_unavailable, false);
  const health = await consumer.health();
  assert.equal(health.consumer.failure_origin, "local-route");
  assert.equal(health.consumer.server_unavailable, false);
  assert.equal(health.routes.cockpit.pending, 1);
});

test("production default delivery projects cockpit only and fails unsupported routes honestly", async () => {
  const root = await stateRoot();
  const event = await failureFixture();
  const consumer = new CompletionAlertConsumer({
    stateRoot: root,
    policy: { ...DEFAULT_COMPLETION_ALERT_POLICY, routes: ["cockpit", "pager"] },
    maxAttempts: 1,
    fetchPage: async () => ({ events: [event], next_cursor: "default-routes-1" })
  });
  await consumer.pollOnce();
  const store = new DurableCompletionAlertStore({ root });
  assert.ok(await store.readProjection(event.event_id));
  assert.equal((await store.readReceipt(event.event_id, "cockpit")).state, "delivered");
  const unsupported = await store.readReceipt(event.event_id, "pager");
  assert.equal(unsupported.state, "dead-lettered");
  assert.match(unsupported.last_error, /not implemented/);
  assert.equal((await store.readOutcome(event.event_id)).outcome, "dead-lettered");
});

test("multi-route delivery isolates one failing route and retries only its receipt", async () => {
  const root = await stateRoot();
  const event = await failureFixture();
  const pages = [{ events: [event], next_cursor: "routes-1" }, { events: [], next_cursor: "routes-1" }];
  const attempts = { cockpit: 0, pager: 0 };
  const consumer = new CompletionAlertConsumer({
    stateRoot: root,
    policy: { ...DEFAULT_COMPLETION_ALERT_POLICY, routes: ["cockpit", "pager"] },
    fetchPage: async () => pages.shift(),
    deliverRoute: async ({ routeId }) => {
      attempts[routeId] += 1;
      if (routeId === "pager" && attempts.pager === 1) throw new Error("pager offline");
    }
  });
  await consumer.pollOnce();
  const store = new DurableCompletionAlertStore({ root });
  const pager = await store.readReceipt(event.event_id, "pager");
  pager.next_attempt_at = "2020-01-01T00:00:00Z";
  await store.writeReceipt(pager);
  assert.equal((await store.readReceipt(event.event_id, "cockpit")).state, "delivered");
  assert.equal(pager.state, "pending");
  assert.equal((await store.readOutcome(event.event_id)).outcome, "pending");
  await consumer.pollOnce();
  assert.deepEqual(attempts, { cockpit: 1, pager: 2 });
  assert.equal((await store.readOutcome(event.event_id)).outcome, "delivered");
});

test("repeated failures coalesce into one operator delivery while retaining each event history", async () => {
  const root = await stateRoot();
  const first = await failureFixture();
  const second = { ...structuredClone(first), event_id: "4d5e6f70-8192-4a3b-8c0d-3e4f50617285", origin_sequence: 44, completed_at: "2026-08-11T12:04:13Z", observed_at: "2026-08-11T12:04:13Z" };
  const pages = [{ events: [first], next_cursor: "coalesce-1" }, { events: [second], next_cursor: "coalesce-2" }];
  const consumer = new CompletionAlertConsumer({ stateRoot: root, policy: { ...DEFAULT_COMPLETION_ALERT_POLICY, coalesce_window_seconds: 60 }, fetchPage: async () => pages.shift(), now: () => new Date("2026-08-11T12:05:00Z") });
  await consumer.pollOnce();
  await consumer.pollOnce();
  const store = new DurableCompletionAlertStore({ root });
  assert.equal((await store.readReceipt(first.event_id)).state, "delivered");
  assert.equal((await store.readReceipt(second.event_id)).state, "suppressed");
  assert.equal((await store.readOutcome(second.event_id)).reason, "coalesced");
  assert.equal((await store.readProjection(first.event_id)).coalesced_event_count, 2);
  const projection = await readCompletionAlertProjection({ stateRoot: root });
  assert.equal(projection.alerts.length, 1);
  assert.equal(projection.coalesced_events.length, 1);
  assert.equal(projection.outcomes.find((outcome) => outcome.event_id === second.event_id).outcome, "suppressed");
});

test("quiet-hour deferral releases from the durable inbox without losing the event", async () => {
  const root = await stateRoot();
  const event = await fixture();
  const clockState = clock();
  const policy = { ...DEFAULT_COMPLETION_ALERT_POLICY, terminal_mode: "all", quiet_hours: { start: "00:00", end: "13:00", behavior: "defer" } };
  const pages = [{ events: [event], next_cursor: "quiet-1" }, { events: [], next_cursor: "quiet-1" }];
  const consumer = new CompletionAlertConsumer({ stateRoot: root, policy, fetchPage: async () => pages.shift(), now: clockState.now });
  await consumer.pollOnce();
  assert.equal((await new DurableCompletionAlertStore({ root }).readOutcome(event.event_id)).outcome, "pending");
  clockState.set("2026-08-11T14:00:00Z");
  await consumer.pollOnce();
  assert.equal((await new DurableCompletionAlertStore({ root }).readOutcome(event.event_id)).outcome, "delivered");
});

test("quiet-hour suppression records a named terminal outcome without delivering", async () => {
  const root = await stateRoot();
  const event = await fixture();
  const consumer = new CompletionAlertConsumer({
    stateRoot: root,
    policy: { ...DEFAULT_COMPLETION_ALERT_POLICY, terminal_mode: "all", quiet_hours: { start: "00:00", end: "23:59", behavior: "suppress" } },
    fetchPage: async () => ({ events: [event], next_cursor: "quiet-suppress" }),
    now: () => new Date("2026-08-11T12:05:00Z")
  });
  await consumer.pollOnce();
  const store = new DurableCompletionAlertStore({ root });
  assert.equal((await store.readOutcome(event.event_id)).reason, "quiet-hours");
  assert.equal(await store.readProjection(event.event_id), null);
  assert.equal((await store.listHealth()).routes.cockpit, undefined);
});

test("poison input is quarantined while a valid event in the same page is delivered", async () => {
  const root = await stateRoot();
  const valid = await failureFixture();
  const poison = { ...structuredClone(valid), event_id: "4d5e6f70-8192-4a3b-8c0d-3e4f50617283", origin_sequence: 44, terminal: { ...valid.terminal, kind: "failed", reason_code: "process-exit", exit_code: 0 } };
  const consumer = new CompletionAlertConsumer({ stateRoot: root, fetchPage: async () => ({ events: [poison, valid], next_cursor: "poison-1" }) });
  const result = await consumer.pollOnce();
  assert.equal(result.results[0].outcome, "dead-lettered");
  assert.equal(result.results[1].outcome, "delivered");
  const health = await consumer.health();
  assert.equal(health.quarantine_count, 1);
  assert.equal(health.outcomes["dead-lettered"], 1);
});

test("policy changes are prospective until an explicit replay", async () => {
  const root = await stateRoot();
  const event = await fixture();
  const pages = [{ events: [event], next_cursor: "p1" }, { events: [], next_cursor: "p1" }];
  const consumer = new CompletionAlertConsumer({ stateRoot: root, fetchPage: async () => pages.shift() });
  await consumer.pollOnce();
  consumer.policy = normalizeCompletionAlertPolicy({ ...DEFAULT_COMPLETION_ALERT_POLICY, terminal_mode: "all" });
  await consumer.pollOnce();
  assert.equal((await new DurableCompletionAlertStore({ root }).readOutcome(event.event_id)).outcome, "suppressed");
  await consumer.replayEvent(event.event_id);
  assert.equal((await new DurableCompletionAlertStore({ root }).readOutcome(event.event_id)).outcome, "delivered");
});

test("projection reads are non-mutating on a fresh read-only state root", async () => {
  const parent = await fs.mkdtemp(path.join(os.tmpdir(), "agentops-alert-read-"));
  const root = path.join(parent, "fresh-read-only-root");
  const projection = await readCompletionAlertProjection({ stateRoot: root });
  assert.deepEqual(projection.alerts, []);
  assert.deepEqual(projection.outcomes, []);
  await assert.rejects(() => fs.stat(root), { code: "ENOENT" });

  await fs.mkdir(root);
  await fs.chmod(root, 0o555);
  try {
    const readOnlyProjection = await readCompletionAlertProjection({ stateRoot: root });
    assert.deepEqual(readOnlyProjection.alerts, []);
    assert.deepEqual(readOnlyProjection.outcomes, []);
  } finally {
    await fs.chmod(root, 0o755);
  }
});

test("acknowledgement changes only the AgentOps cockpit projection", async () => {
  const root = await stateRoot();
  const event = await failureFixture();
  const store = new DurableCompletionAlertStore({ root, now: () => new Date("2026-08-11T12:06:00Z") });
  await store.initialize();
  await store.writeProjection({
    alert_id: event.event_id,
    event_id: event.event_id,
    acknowledged: false,
    acknowledged_at: null,
    acknowledged_by: null,
    completed_at: event.completed_at,
    repo: event.repo,
    terminal: event.terminal
  });
  const acknowledged = await store.acknowledgeProjection(event.event_id, "operator:test");
  assert.equal(acknowledged.acknowledged, true);
  assert.equal(acknowledged.acknowledged_by, "operator:test");
  assert.equal(acknowledged.acknowledged_at, "2026-08-11T12:06:00.000Z");
  assert.equal((await store.readProjection(event.event_id)).acknowledged, true);
  await assert.rejects(() => store.acknowledgeProjection("00000000-0000-0000-0000-000000000000", "operator:test"), /not found/);
});

test("served read credentials and route diagnostics never enter durable histories", async () => {
  const event = await failureFixture();
  let requestHeaders;
  const page = await readCompletionPage({
    config: { completionAlertActionqUrl: "https://actionq.example/session-completions", completionAlertReadToken: "read-secret", completionAlertPageSize: 10, completionAlertPollTimeoutMs: 1000 },
    fetchImpl: async (_url, options) => {
      requestHeaders = options.headers;
      return new Response(JSON.stringify({ events: [event], next_cursor: "redaction-1" }), { status: 200, headers: { "content-type": "application/json" } });
    }
  });
  assert.equal(requestHeaders.authorization, "Bearer read-secret");
  assert.equal(page.events[0].event_id, event.event_id);
  const root = await stateRoot();
  const consumer = new CompletionAlertConsumer({
    stateRoot: root,
    fetchPage: async () => ({ events: [event], next_cursor: "redaction-1" }),
    deliverRoute: async () => { throw new Error("Authorization: Bearer route-secret /projects/dev/private-token"); }
  });
  await consumer.pollOnce();
  const stateText = JSON.stringify(await Promise.all([
    (await new DurableCompletionAlertStore({ root }).readReceipt(event.event_id)),
    (await new DurableCompletionAlertStore({ root }).readOutcome(event.event_id)),
    (await new DurableCompletionAlertStore({ root }).readHealth())
  ]));
  assert.doesNotMatch(stateText, /route-secret|private-token|\/projects\/dev/);
});
