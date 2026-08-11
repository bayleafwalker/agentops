import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import { CompletionAlertPanel, formatCompletionAge, normalizeCompletionAlerts } from "../components/cockpit/completion-alert-panel.js";
import { getPollIntervalMs } from "../lib/cockpit/client-state.js";

const h = createElement;

const failedAlert = {
  alert_id: "alert-failed",
  event_id: "alert-failed",
  severity: "warning",
  terminal: { kind: "failed" },
  repo: { project: "alpha" },
  harness: "codex",
  model: { name: "gpt-5" },
  runtime_session_id: "session-1",
  action_id: "action-7",
  completed_at: "2026-08-11T12:04:00Z",
  duration_ms: 42000,
  acknowledged: false
};

test("completion panel data is deduplicated and newest-first", () => {
  const alerts = normalizeCompletionAlerts({
    alerts: [
      { ...failedAlert, completed_at: "2026-08-11T12:00:00Z" },
      { ...failedAlert, completed_at: "2026-08-11T12:04:00Z" },
      { ...failedAlert, alert_id: "alert-old", event_id: "alert-old", completed_at: "2026-08-11T11:00:00Z" }
    ]
  });
  assert.deepEqual(alerts.map((alert) => alert.alert_id), ["alert-failed", "alert-old"]);
  assert.equal(alerts[0].completed_at, "2026-08-11T12:04:00Z");
  assert.equal(formatCompletionAge("2026-08-11T12:04:00Z", new Date("2026-08-11T12:05:00Z")), "60s ago");
  assert.equal(getPollIntervalMs("completion-alerts", "visible"), 5000);
  assert.equal(getPollIntervalMs("completion-alerts", "hidden"), 20000);
});

test("completion panel renders bounded alert facts, safe detail links, and acknowledgement control", () => {
  let acknowledged = null;
  const html = renderToStaticMarkup(h(CompletionAlertPanel, {
    data: {
      alerts: [failedAlert, { ...failedAlert, alert_id: "alert-success", event_id: "alert-success", terminal: { kind: "succeeded" }, severity: "info", repo: { project: "beta" }, completed_at: "2026-08-11T11:00:00Z" }],
      health: {
        server: { ingest_lag_seconds: 2 },
        consumer: { status: "healthy" },
        routes: { cockpit: { pending: 0, dead_lettered: 0 } }
      },
      pending_deliveries: [{ event_id: "pending-1" }]
    },
    now: new Date("2026-08-11T12:05:00Z"),
    onAcknowledge: (alertId) => { acknowledged = alertId; }
  }));

  assert.match(html, /Session Completions/);
  assert.match(html, /alpha/);
  assert.match(html, /codex/);
  assert.match(html, /60s ago/);
  assert.match(html, /href="#dispatches"/);
  assert.match(html, /Acknowledge/);
  assert.match(html, /pending deliveries 1/);
  assert.doesNotMatch(html, /prompt|transcript|secret|worktree/);
  assert.equal(acknowledged, null);
});

test("completion panel makes cursor expiry and projection failures explicit", () => {
  const html = renderToStaticMarkup(h(CompletionAlertPanel, {
    data: {
      alerts: [],
      degraded: { message: "Completion alerts unavailable — projection unreachable" },
      health: {
        server: { cursor_expired: true, recovery_floor: 42, producer_backlog_age_seconds: 121 },
        consumer: { status: "cursor-expired", recovery_floor: 42 },
        routes: { cockpit: { pending: 2, dead_lettered: 1 } },
        lag: { consumer_cursor: 40, server_cursor: 42 },
        oldest_pending_age_seconds: 63
      }
    }
  }));

  assert.match(html, /projection unavailable/);
  assert.match(html, /server cursor expired at 42/);
  assert.match(html, /consumer recovery required from 42/);
  assert.match(html, /route dead-lettered 1/);
  assert.match(html, /route pending 2/);
  assert.match(html, /producer backlog 2m/);
  assert.match(html, /consumer lag 2 cursors/);
  assert.match(html, /oldest pending 63s/);
  assert.match(html, /No completion alerts available/);
});

test("projection outage names server unavailability instead of hiding the source state", () => {
  const html = renderToStaticMarkup(h(CompletionAlertPanel, {
    data: { alerts: [], degraded: { message: "projection unavailable" }, health: null }
  }));
  assert.match(html, /server unavailable/);
});

test("ActionQ read failure stays distinct from a generic consumer status", () => {
  const html = renderToStaticMarkup(h(CompletionAlertPanel, {
    data: {
      alerts: [],
      degraded: { message: "completion log read failed" },
      health: {
        server: { ingest_lag_seconds: null },
        consumer: { status: "degraded" },
        routes: { cockpit: { pending: 3, dead_lettered: 1 } }
      }
    }
  }));
  assert.match(html, /server unavailable/);
  assert.match(html, /consumer retrying/);
  assert.match(html, /route pending 3/);
  assert.match(html, /route dead-lettered 1/);
  assert.doesNotMatch(html, /consumer degraded/);
});
