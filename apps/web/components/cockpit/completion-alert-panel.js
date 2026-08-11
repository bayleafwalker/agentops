"use client";

import { createElement } from "react";

const h = createElement;

function text(value, fallback = "unknown") {
  if (value == null || String(value).trim() === "") {
    return fallback;
  }
  return String(value).slice(0, 160);
}

function timestamp(value) {
  const parsed = Date.parse(value || "");
  return Number.isNaN(parsed) ? null : parsed;
}

export function formatCompletionAge(value, now = Date.now()) {
  const completed = timestamp(value);
  const current = now instanceof Date ? now.getTime() : Number(now);
  if (completed == null || !Number.isFinite(current)) {
    return "age unknown";
  }
  const seconds = Math.max(0, Math.round((current - completed) / 1000));
  if (seconds < 90) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 90) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export function normalizeCompletionAlerts(data) {
  const byId = new Map();
  for (const alert of Array.isArray(data?.alerts) ? data.alerts : []) {
    if (!alert || typeof alert !== "object") continue;
    const id = alert.alert_id || alert.event_id;
    if (!id) continue;
    const previous = byId.get(id);
    if (!previous || (timestamp(alert.completed_at) || 0) > (timestamp(previous.completed_at) || 0)) {
      byId.set(id, alert);
    }
  }
  return [...byId.values()]
    .sort((left, right) => (timestamp(right.completed_at) || 0) - (timestamp(left.completed_at) || 0));
}

function severityClass(alert) {
  if (alert?.severity === "critical" || ["timed-out", "usage-limited", "end-inferred"].includes(alert?.terminal?.kind)) {
    return "error";
  }
  if (alert?.severity === "warning" || alert?.terminal?.kind === "failed" || alert?.terminal?.kind === "cancelled") {
    return "warn";
  }
  return "ok";
}

function formatDuration(value) {
  if (!Number.isFinite(Number(value))) return null;
  const seconds = Math.max(0, Math.round(Number(value) / 1000));
  if (seconds < 90) return `${seconds}s`;
  const minutes = Math.round(seconds / 60);
  return minutes < 90 ? `${minutes}m` : `${Math.round(minutes / 60)}h`;
}

function formatHealthAge(value) {
  if (!Number.isFinite(Number(value))) return "unknown";
  const seconds = Math.max(0, Math.round(Number(value)));
  if (seconds < 90) return `${seconds}s`;
  const minutes = Math.round(seconds / 60);
  return minutes < 90 ? `${minutes}m` : `${Math.round(minutes / 60)}h`;
}

function healthSummary(health) {
  if (!health) {
    return { state: "warn", parts: ["health unavailable"] };
  }
  const parts = [];
  const server = health.server;
  const consumer = health.consumer;
  const cockpit = health.routes?.cockpit;
  if (server) {
    if (server.cursor_expired) {
      parts.push(`server cursor expired${server.recovery_floor == null ? "" : ` at ${server.recovery_floor}`}`);
    } else if (server.ingest_lag_seconds != null) {
      parts.push(`server lag ${formatHealthAge(server.ingest_lag_seconds)}`);
    } else {
      parts.push("server connected");
    }
  } else {
    parts.push("server health unknown");
  }
  if (consumer?.status === "cursor-expired" || consumer?.cursor_expired) {
    parts.push(`consumer recovery required${consumer.recovery_floor == null ? "" : ` from ${consumer.recovery_floor}`}`);
  } else if (consumer?.status === "degraded") {
    parts.push("consumer degraded");
  } else if (consumer?.status) {
    parts.push(`consumer ${text(consumer.status)}`);
  } else {
    parts.push("consumer health unknown");
  }
  if (cockpit?.dead_lettered) parts.push(`route dead-lettered ${cockpit.dead_lettered}`);
  if (cockpit?.pending) parts.push(`route pending ${cockpit.pending}`);
  return {
    state: server?.cursor_expired || consumer?.status === "cursor-expired" || consumer?.cursor_expired || cockpit?.dead_lettered ? "error" : cockpit?.pending || !server || !consumer ? "warn" : "ok",
    parts
  };
}

function AlertCard({ alert, now, acknowledging, onAcknowledge }) {
  const kind = text(alert.terminal?.kind, "terminal");
  const actionId = alert.action_id;
  const sessionId = alert.runtime_session_id;
  const duration = formatDuration(alert.duration_ms);
  const alertId = alert.alert_id || alert.event_id;
  const acknowledged = Boolean(alert.acknowledged);
  return h(
    "article",
    { className: `completion-alert completion-alert--${severityClass(alert)}${acknowledged ? " is-acknowledged" : ""}` },
    h(
      "div",
      { className: "completion-alert-heading" },
      h("div", { className: "completion-alert-title" }, text(alert.repo?.project, "unknown project")),
      h("span", { className: `status-chip ${severityClass(alert)}` }, kind)
    ),
    h(
      "div",
      { className: "completion-alert-meta small" },
      h("span", null, text(alert.harness, "unknown harness")),
      h("span", null, formatCompletionAge(alert.completed_at, now)),
      alert.model?.name ? h("span", null, text(alert.model.name)) : null,
      duration ? h("span", null, `duration ${duration}`) : null
    ),
    h(
      "div",
      { className: "completion-alert-details small muted" },
      actionId ? `action ${text(actionId)}` : sessionId ? `session ${text(sessionId)}` : "direct session"
    ),
    h(
      "div",
      { className: "completion-alert-actions" },
      h("a", { className: "completion-alert-link", href: actionId ? "#dispatches" : "#claims" }, actionId ? "view dispatches" : "view claims"),
      onAcknowledge && alertId
        ? h(
            "button",
            {
              className: "mode-button completion-alert-ack",
              type: "button",
              disabled: acknowledging || acknowledged,
              onClick: () => onAcknowledge(alertId)
            },
            acknowledged ? "Acknowledged" : acknowledging ? "Acknowledging…" : "Acknowledge"
          )
        : null,
      acknowledged && alert.acknowledged_by ? h("span", { className: "small muted" }, `by ${text(alert.acknowledged_by)}`) : null
    )
  );
}

export function CompletionAlertPanel({ data, now = Date.now(), acknowledgingAlertId = null, onAcknowledge, onRefresh, refreshing = false }) {
  const alerts = normalizeCompletionAlerts(data);
  const health = healthSummary(data?.health);
  const degradedMessage = data?.degraded?.message || data?.degraded?.detail;
  const pendingDeliveries = Array.isArray(data?.pending_deliveries) ? data.pending_deliveries.length : 0;
  const acknowledgedCount = alerts.filter((alert) => alert.acknowledged).length;
  return h(
    "section",
    { className: "cockpit-section completion-alert-panel", id: "completion-alerts", "aria-labelledby": "completion-alerts-title" },
    h(
      "div",
      { className: "title-row" },
      h("h3", { className: "section-title", id: "completion-alerts-title" }, "Session Completions"),
      h(
        "div",
        { className: "completion-alert-header-actions" },
        h("span", { className: "source-tag" }, "agentops://completion-alerts"),
        onRefresh ? h("button", { className: "mode-button completion-alert-refresh", type: "button", onClick: onRefresh, disabled: refreshing }, refreshing ? "…" : "↻") : null
      )
    ),
    degradedMessage ? h("div", { className: "completion-alert-degraded small" }, `projection unavailable — ${text(degradedMessage)}`) : null,
    h("div", { className: `completion-alert-health small ${health.state}` }, [
      ...health.parts,
      `pending deliveries ${pendingDeliveries}`,
      `acknowledged ${acknowledgedCount}/${alerts.length}`
    ].join(" · ")),
    alerts.length
      ? h("div", { className: "completion-alert-list" }, alerts.map((alert) => h(AlertCard, { key: alert.alert_id || alert.event_id, alert, now, acknowledging: acknowledgingAlertId === (alert.alert_id || alert.event_id), onAcknowledge })))
      : h("div", { className: "empty-state small muted" }, degradedMessage ? "No completion alerts available." : "No recent session completions require attention.")
  );
}
