import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { getConfig } from "./env.js";

export const COMPLETION_SCHEMA_VERSION = "session.completion-observed/v1";
export const COMPLETION_ALERT_POLICY_VERSION = "completion-alert-policy/v1";
export const COCKPIT_ROUTE_ID = "cockpit";
export const COMPLETION_OUTCOMES = ["delivered", "suppressed", "pending", "dead-lettered"];
export const RECEIPT_STATES = ["pending", "delivered", "suppressed", "dead-lettered"];

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const ROUTE_RE = /^[a-z][a-z0-9-]{0,63}$/;
const TERMINAL_KINDS = new Set(["succeeded", "failed", "cancelled", "timed-out", "usage-limited", "end-inferred"]);
const TERMINAL_REASONS = {
  succeeded: new Set(["completed"]),
  failed: new Set(["process-exit", "start-failed"]),
  cancelled: new Set(["cancelled"]),
  "timed-out": new Set(["timeout"]),
  "usage-limited": new Set(["usage-limit"]),
  "end-inferred": new Set(["crash-inferred"])
};
const PROHIBITED_KEYS = new Set([
  "prompt", "transcript", "rawoutput", "rawoutputref", "environment", "env",
  "token", "secret", "secrets", "credential", "credentials", "password", "claimproof", "claimtoken",
  "accesstoken", "clientsecret", "apikey", "worktree", "commandoutput", "failuredetails",
  "failuredetail", "requestsnapshot", "requestbody", "headers", "provenance", "stdout", "stderr", "stacktrace"
]);
const SECRET_VALUE_RE = /(?:-----BEGIN [A-Z ]*PRIVATE KEY-----|\bBearer\s+[A-Za-z0-9._~+/=-]{8,}|\b(?:sk|ghp|github_pat)_[A-Za-z0-9_-]{8,})/i;
const ABSOLUTE_PATH_RE = /^(?:\/|[A-Za-z]:[\\/]|\\\\)/;
const DIAGNOSTIC_SECRET_RE = /((?:authorization|bearer|token|secret|password|credential|api[_-]?key)\s*[:=]?\s*)\S+/gi;

function normalizedKey(key) {
  return String(key).toLowerCase().replace(/[._\s-]/g, "");
}

function assertSafeComponent(value, name) {
  if (typeof value !== "string" || !value || value.includes("\0") || value.includes("%") || value.includes("/") || value.includes("\\") || value === "." || value === ".." || path.isAbsolute(value)) {
    throw new Error(`${name} is not a safe closed path identity`);
  }
  let decoded;
  try {
    decoded = decodeURIComponent(value);
  } catch {
    throw new Error(`${name} contains malformed encoding`);
  }
  if (decoded !== value || decoded.includes("/") || decoded.includes("\\") || path.isAbsolute(decoded)) {
    throw new Error(`${name} contains an encoded path separator`);
  }
  return value;
}

function assertEventId(value, name = "event_id") {
  if (typeof value !== "string" || !UUID_RE.test(value)) {
    throw new CompletionValidationError(`${name} must be a lowercase UUID safe for filesystem identity`);
  }
  return assertSafeComponent(value, name);
}

export function redactDiagnostic(value) {
  return String(value || "error")
    .replace(/Bearer\s+\S+/gi, "Bearer [REDACTED]")
    .replace(DIAGNOSTIC_SECRET_RE, "$1[REDACTED]")
    .replace(/(?:^|\s)(?:\/|[A-Za-z]:[\\/]|\\\\)\S+/g, " [PATH_REDACTED]")
    .slice(0, 500);
}

function safeServerHealth(value, cursor) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const safe = { cursor: typeof cursor === "string" ? cursor : null };
  for (const field of ["producer_backlog_age_seconds", "ingest_lag_seconds", "stream_lag_seconds", "retry_age_seconds", "quarantine_count", "oldest_event_age_seconds"]) {
    if (Number.isFinite(Number(value[field]))) safe[field] = Number(value[field]);
  }
  return safe;
}

function rejectProhibited(value, location = "event") {
  if (Array.isArray(value)) {
    value.forEach((item, index) => rejectProhibited(item, `${location}[${index}]`));
    return;
  }
  if (!value || typeof value !== "object") {
    if (typeof value === "string" && (SECRET_VALUE_RE.test(value) || ABSOLUTE_PATH_RE.test(value))) {
      throw new CompletionValidationError(`${location} contains prohibited secret or absolute path content`);
    }
    return;
  }
  for (const [key, child] of Object.entries(value)) {
    if (PROHIBITED_KEYS.has(normalizedKey(key))) {
      throw new CompletionValidationError(`${location}.${key} is prohibited in a completion alert`);
    }
    rejectProhibited(child, `${location}.${key}`);
  }
}

function requireObject(value, name) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new CompletionValidationError(`${name} must be an object`);
  }
}

function requireString(value, name, { uuid = false } = {}) {
  if (typeof value !== "string" || !value.trim()) {
    throw new CompletionValidationError(`${name} must be a non-empty string`);
  }
  if (uuid && !UUID_RE.test(value)) {
    throw new CompletionValidationError(`${name} must be a lowercase UUID`);
  }
}

function requireUtc(value, name) {
  requireString(value, name);
  if (!value.endsWith("Z") || Number.isNaN(Date.parse(value))) {
    throw new CompletionValidationError(`${name} must be an ISO UTC timestamp`);
  }
}

function requireNullableString(value, name) {
  if (value !== null) {
    requireString(value, name);
  }
}

export class CompletionValidationError extends Error {
  constructor(message) {
    super(message);
    this.name = "CompletionValidationError";
  }
}

export class CompletionConflictError extends Error {
  constructor(message) {
    super(message);
    this.name = "CompletionConflictError";
  }
}

export function validateCompletionEvent(event) {
  requireObject(event, "completion event");
  rejectProhibited(event);
  const required = [
    "schema_version", "event_id", "origin_stream_id", "origin_sequence", "runtime_session_id",
    "attempt_id", "action_id", "repo", "harness", "model", "terminal", "started_at",
    "completed_at", "observed_at", "duration_ms", "refs", "evidence", "privacy"
  ];
  for (const field of required) {
    if (!(field in event)) {
      throw new CompletionValidationError(`completion event missing ${field}`);
    }
  }
  if (event.schema_version !== COMPLETION_SCHEMA_VERSION) {
    throw new CompletionValidationError(`schema_version must be ${COMPLETION_SCHEMA_VERSION}`);
  }
  requireString(event.event_id, "event_id", { uuid: true });
  requireString(event.origin_stream_id, "origin_stream_id", { uuid: true });
  if (!Number.isInteger(event.origin_sequence) || event.origin_sequence < 1) {
    throw new CompletionValidationError("origin_sequence must be a positive integer");
  }
  requireString(event.runtime_session_id, "runtime_session_id");
  requireNullableString(event.attempt_id, "attempt_id");
  requireNullableString(event.action_id, "action_id");
  if ((event.attempt_id === null) !== (event.action_id === null)) {
    throw new CompletionValidationError("attempt_id and action_id must both be present or both be null");
  }

  requireObject(event.repo, "repo");
  requireString(event.repo.project, "repo.project");
  if (event.repo.repo_id != null) {
    requireString(event.repo.repo_id, "repo.repo_id", { uuid: true });
  }
  requireString(event.harness, "harness");
  if (event.actor != null) requireString(event.actor, "actor");
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(event.repo.project)) {
    throw new CompletionValidationError("repo.project must be a portable identifier");
  }
  if (event.model !== null) {
    requireObject(event.model, "model");
    requireString(event.model.name, "model.name");
    if (event.model.version != null && typeof event.model.version !== "string") {
      throw new CompletionValidationError("model.version must be a string when present");
    }
  }

  requireObject(event.terminal, "terminal");
  if (!TERMINAL_KINDS.has(event.terminal.kind)) {
    throw new CompletionValidationError(`terminal.kind is not recognized: ${event.terminal.kind}`);
  }
  if (!TERMINAL_REASONS[event.terminal.kind].has(event.terminal.reason_code)) {
    throw new CompletionValidationError(`terminal.reason_code does not match terminal.kind`);
  }
  if (event.terminal.exit_code !== null && !Number.isInteger(event.terminal.exit_code)) {
    throw new CompletionValidationError("terminal.exit_code must be an integer or null");
  }
  if (typeof event.terminal.retryable !== "boolean") {
    throw new CompletionValidationError("terminal.retryable must be boolean");
  }
  if (event.terminal.kind === "succeeded" && (event.terminal.exit_code !== 0 || event.terminal.retryable)) {
    throw new CompletionValidationError("succeeded completion must have exit_code 0 and retryable false");
  }
  if (event.terminal.reason_code === "process-exit" && (event.terminal.exit_code === null || event.terminal.exit_code === 0)) {
    throw new CompletionValidationError("process-exit must have a non-zero exit code");
  }
  if (["cancelled", "timed-out", "usage-limited", "end-inferred"].includes(event.terminal.kind) && event.terminal.exit_code !== null) {
    throw new CompletionValidationError(`${event.terminal.kind} must have a null exit code`);
  }
  for (const field of ["started_at", "completed_at", "observed_at"]) {
    requireUtc(event[field], field);
  }
  if (Date.parse(event.completed_at) < Date.parse(event.started_at)) {
    throw new CompletionValidationError("completed_at cannot precede started_at");
  }
  if (Date.parse(event.observed_at) < Date.parse(event.completed_at)) {
    throw new CompletionValidationError("observed_at cannot precede completed_at");
  }
  if (event.duration_ms !== null && (!Number.isInteger(event.duration_ms) || event.duration_ms < 0)) {
    throw new CompletionValidationError("duration_ms must be a non-negative integer or null");
  }
  if (!Array.isArray(event.refs)) {
    throw new CompletionValidationError("refs must be an array");
  }
  for (const ref of event.refs) {
    requireObject(ref, "refs entry");
    for (const field of ["kind", "source", "revision"]) {
      requireString(ref[field], `refs[].${field}`);
    }
  }
  requireObject(event.evidence, "evidence");
  if (typeof event.evidence.dirty !== "boolean" || !Number.isInteger(event.evidence.commit_count) || event.evidence.commit_count < 0) {
    throw new CompletionValidationError("evidence dirty/commit_count is invalid");
  }
  requireObject(event.evidence.verification, "evidence.verification");
  for (const field of ["pass", "fail", "error"]) {
    if (!Number.isInteger(event.evidence.verification[field]) || event.evidence.verification[field] < 0) {
      throw new CompletionValidationError(`evidence.verification.${field} must be a non-negative integer`);
    }
  }
  requireObject(event.privacy, "privacy");
  for (const field of ["prompt_absent", "transcript_absent", "raw_output_absent", "environment_absent", "credentials_absent", "absolute_paths_absent", "claim_proofs_absent"]) {
    if (event.privacy[field] !== true) {
      throw new CompletionValidationError(`privacy.${field} must be true`);
    }
  }
  return event;
}

function stableStringify(value) {
  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).join(",")}]`;
  }
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

export function completionDigest(event) {
  return `sha256:${createHash("sha256").update(stableStringify(event)).digest("hex")}`;
}

export const DEFAULT_COMPLETION_ALERT_POLICY = {
  schema_version: COMPLETION_ALERT_POLICY_VERSION,
  policy_id: "cockpit-terminal-v1",
  version: 1,
  // Operators may opt into all terminal sessions with the same policy
  // evaluator. The safe default is non-success sessions so normal work does
  // not turn the cockpit into a success toast stream.
  terminal_mode: "non-success",
  // When present, this closed set is authoritative over terminal_mode.
  // It permits policies such as failed-only or cancelled-only while keeping
  // the event model's terminal distinctions explicit.
  terminal_kinds: null,
  routes: [COCKPIT_ROUTE_ID],
  severity_by_terminal: {
    succeeded: "info",
    failed: "warning",
    cancelled: "warning",
    "timed-out": "critical",
    "usage-limited": "critical",
    "end-inferred": "critical"
  },
  projects: null,
  harnesses: null,
  actors: null,
  dispatch_modes: ["direct", "dispatch"],
  quiet_hours: null,
  coalesce_window_seconds: 0
};

function listOrNull(value, name) {
  if (value == null) return null;
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string" || !item.trim())) {
    throw new Error(`${name} must be an array of non-empty strings or null`);
  }
  return [...new Set(value)];
}

export function normalizeCompletionAlertPolicy(policy = DEFAULT_COMPLETION_ALERT_POLICY) {
  const merged = { ...DEFAULT_COMPLETION_ALERT_POLICY, ...policy };
  if (merged.schema_version !== COMPLETION_ALERT_POLICY_VERSION) throw new Error("unsupported completion alert policy schema");
  if (typeof merged.policy_id !== "string" || !merged.policy_id.trim()) throw new Error("policy_id is required");
  if (!Number.isInteger(merged.version) || merged.version < 1) throw new Error("policy version must be positive");
  if (!["all", "non-success"].includes(merged.terminal_mode)) throw new Error("terminal_mode must be all or non-success");
  if (merged.terminal_kinds != null) {
    if (!Array.isArray(merged.terminal_kinds) || merged.terminal_kinds.length === 0 || merged.terminal_kinds.some((kind) => !TERMINAL_KINDS.has(kind))) {
      throw new Error("terminal_kinds must be a non-empty array of recognized terminal kinds");
    }
    merged.terminal_kinds = [...new Set(merged.terminal_kinds)];
  }
  if (!Array.isArray(merged.routes) || merged.routes.length === 0 || merged.routes.some((route) => !ROUTE_RE.test(route))) throw new Error("routes must contain valid route IDs");
  merged.projects = listOrNull(merged.projects, "projects");
  merged.harnesses = listOrNull(merged.harnesses, "harnesses");
  merged.actors = listOrNull(merged.actors, "actors");
  if (!Array.isArray(merged.dispatch_modes) || merged.dispatch_modes.some((mode) => !["direct", "dispatch"].includes(mode))) throw new Error("dispatch_modes is invalid");
  if (!Number.isInteger(merged.coalesce_window_seconds) || merged.coalesce_window_seconds < 0) throw new Error("coalesce_window_seconds must be non-negative");
  if (!merged.severity_by_terminal || typeof merged.severity_by_terminal !== "object" || Array.isArray(merged.severity_by_terminal)) throw new Error("severity_by_terminal must be an object");
  for (const [kind, severity] of Object.entries(merged.severity_by_terminal)) {
    if (!TERMINAL_KINDS.has(kind) || !["info", "warning", "critical"].includes(severity)) throw new Error("severity_by_terminal contains an invalid terminal kind or severity");
  }
  if (merged.quiet_hours != null) {
    if (!merged.quiet_hours || typeof merged.quiet_hours !== "object") throw new Error("quiet_hours must be an object or null");
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(merged.quiet_hours.start) || !/^([01]\d|2[0-3]):[0-5]\d$/.test(merged.quiet_hours.end)) throw new Error("quiet hours must use HH:MM");
    if (!["defer", "suppress"].includes(merged.quiet_hours.behavior || "defer")) throw new Error("quiet hour behavior must be defer or suppress");
    if ((merged.quiet_hours.timezone || "UTC") !== "UTC") throw new Error("v1 quiet hours only support UTC");
  }
  return {
    ...merged,
    severity_by_terminal: { ...DEFAULT_COMPLETION_ALERT_POLICY.severity_by_terminal, ...(merged.severity_by_terminal || {}) },
    terminal_kinds: merged.terminal_kinds ? [...merged.terminal_kinds] : null,
    quiet_hours: merged.quiet_hours ? { timezone: "UTC", behavior: "defer", ...merged.quiet_hours } : null,
    routes: [...merged.routes],
    dispatch_modes: [...merged.dispatch_modes]
  };
}

function inQuietHours(now, quietHours) {
  if (!quietHours) return false;
  const hhmm = new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", hour: "2-digit", minute: "2-digit", hour12: false, hourCycle: "h23" }).format(now);
  const current = Number(hhmm.replace(":", ""));
  const start = Number(quietHours.start.replace(":", ""));
  const end = Number(quietHours.end.replace(":", ""));
  return start === end ? true : start < end ? current >= start && current < end : current >= start || current < end;
}

export function evaluateCompletionAlertPolicy(event, policy = DEFAULT_COMPLETION_ALERT_POLICY, now = new Date()) {
  validateCompletionEvent(event);
  const normalized = normalizeCompletionAlertPolicy(policy);
  const mode = event.attempt_id === null ? "direct" : "dispatch";
  const terminalAllowed = normalized.terminal_kinds
    ? normalized.terminal_kinds.includes(event.terminal.kind)
    : normalized.terminal_mode === "all" || event.terminal.kind !== "succeeded";
  const matches = [
    [terminalAllowed, terminalAllowed ? null : normalized.terminal_kinds ? "terminal-kind-filter" : "success-terminal"],
    [!normalized.projects || normalized.projects.includes(event.repo.project), "project-filter"],
    [!normalized.harnesses || normalized.harnesses.includes(event.harness), "harness-filter"],
    [!normalized.actors || normalized.actors.includes(event.actor), "actor-filter"],
    [normalized.dispatch_modes.includes(mode), "dispatch-mode-filter"]
  ];
  const rejected = matches.find(([matched]) => !matched);
  if (rejected) {
    return { decision: "suppress", reason: rejected[1], severity: normalized.severity_by_terminal[event.terminal.kind] || "info", routes: [] };
  }
  if (inQuietHours(now, normalized.quiet_hours)) {
    if (normalized.quiet_hours.behavior === "suppress") {
      return { decision: "suppress", reason: "quiet-hours", severity: normalized.severity_by_terminal[event.terminal.kind] || "info", routes: [] };
    }
    return { decision: "defer", reason: "quiet-hours", severity: normalized.severity_by_terminal[event.terminal.kind] || "info", routes: normalized.routes };
  }
  return { decision: "deliver", reason: "policy-match", severity: normalized.severity_by_terminal[event.terminal.kind] || "info", routes: normalized.routes };
}

function safeAlertProjection(event, evaluation, receivedAt, coalescedInto = null) {
  return {
    schema_version: "completion-alert/v1",
    alert_id: event.event_id,
    event_id: event.event_id,
    route_id: COCKPIT_ROUTE_ID,
    source: "actionq://session-completion-log",
    received_at: receivedAt,
    severity: evaluation.severity,
    terminal: { ...event.terminal },
    repo: { project: event.repo.project, ...(event.repo.repo_id ? { repo_id: event.repo.repo_id } : {}) },
    harness: event.harness,
    model: event.model ? { name: event.model.name, ...(event.model.version ? { version: event.model.version } : {}) } : null,
    runtime_session_id: event.runtime_session_id,
    attempt_id: event.attempt_id,
    action_id: event.action_id,
    started_at: event.started_at,
    completed_at: event.completed_at,
    observed_at: event.observed_at,
    duration_ms: event.duration_ms,
    refs: event.refs.map((ref) => ({ kind: ref.kind, source: ref.source, revision: ref.revision })),
    evidence: {
      dirty: event.evidence.dirty,
      commit_count: event.evidence.commit_count,
      verification: { ...event.evidence.verification }
    },
    coalesce_key: `${event.repo.project}:${event.harness}:${event.terminal.kind}`,
    coalesced: Boolean(coalescedInto),
    coalesced_event_count: 1,
    coalesced_into: coalescedInto,
    acknowledged: false,
    acknowledged_at: null,
    acknowledged_by: null
  };
}

function nowIso(now) {
  return (now instanceof Date ? now : new Date(now)).toISOString();
}

function safeId(value, name) {
  return encodeURIComponent(assertSafeComponent(value, name));
}

function statePath(root, ...parts) {
  const base = path.resolve(root);
  const target = path.resolve(base, ...parts);
  if (target !== base && !target.startsWith(`${base}${path.sep}`)) {
    throw new Error("completion alert state path escaped its configured root");
  }
  return target;
}

async function readJson(filePath) {
  try {
    return JSON.parse(await fs.readFile(filePath, "utf8"));
  } catch (error) {
    if (error.code === "ENOENT") return null;
    throw error;
  }
}

async function writeJsonAtomic(filePath, value) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  const temporary = `${filePath}.${process.pid}.${Date.now()}.tmp`;
  await fs.writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, { encoding: "utf8", flag: "wx" });
  await fs.rename(temporary, filePath);
}

async function listJson(directory) {
  let entries;
  try {
    entries = await fs.readdir(directory, { withFileTypes: true });
  } catch (error) {
    if (error.code === "ENOENT") return [];
    throw error;
  }
  const values = [];
  for (const entry of entries) {
    if (!entry.isFile() || !entry.name.endsWith(".json")) continue;
    const filePath = path.join(directory, entry.name);
    try {
      values.push({ filePath, value: JSON.parse(await fs.readFile(filePath, "utf8")) });
    } catch {
      // A partial/corrupt state record is never allowed to stop cursor repair.
    }
  }
  return values;
}

export class DurableCompletionAlertStore {
  constructor({ root, now = () => new Date(), retention = {} } = {}) {
    if (!root) throw new Error("completion alert state root is required");
    this.root = path.resolve(root);
    this.now = now;
    this.retention = {
      inboxMs: retention.inboxMs ?? 30 * 24 * 60 * 60 * 1000,
      outcomeMs: retention.outcomeMs ?? 90 * 24 * 60 * 60 * 1000,
      receiptMs: retention.receiptMs ?? 90 * 24 * 60 * 60 * 1000,
      projectionMs: retention.projectionMs ?? 30 * 24 * 60 * 60 * 1000
    };
  }

  directory(name) { return statePath(this.root, assertSafeComponent(name, "state directory")); }
  file(name, id) { return statePath(this.root, assertSafeComponent(name, "state directory"), `${safeId(id, name)}.json`); }
  receiptFile(eventId, routeId) { return statePath(this.root, "receipts", `${safeId(eventId, "event_id")}--${safeId(routeId, "route_id")}.json`); }
  positionFile(streamId, sequence) { return statePath(this.root, "positions", `${safeId(streamId, "origin_stream_id")}--${sequence}.json`); }

  async initialize() {
    await Promise.all(["inbox", "outcomes", "receipts", "projections", "quarantine", "positions"].map((name) => fs.mkdir(this.directory(name), { recursive: true })));
  }

  async readCheckpoint() {
    return (await readJson(statePath(this.root, "checkpoint.json"))) || {
      schema_version: "completion-alert-checkpoint/v1",
      server_cursor: null,
      last_advanced_at: null,
      pages: 0,
      events_seen: 0
    };
  }

  async writeCheckpoint(checkpoint) {
    await writeJsonAtomic(statePath(this.root, "checkpoint.json"), {
      schema_version: "completion-alert-checkpoint/v1",
      server_cursor: checkpoint.server_cursor ?? null,
      last_advanced_at: checkpoint.last_advanced_at || nowIso(this.now()),
      pages: Number(checkpoint.pages || 0),
      events_seen: Number(checkpoint.events_seen || 0)
    });
  }

  async readInbox(eventId) { assertEventId(eventId); return readJson(this.file("inbox", eventId)); }
  async listInbox() { return listJson(this.directory("inbox")); }
  async readOutcome(eventId) { assertEventId(eventId); return readJson(this.file("outcomes", eventId)); }
  async readReceipt(eventId, routeId = COCKPIT_ROUTE_ID) { assertEventId(eventId); assertSafeComponent(routeId, "route_id"); return readJson(this.receiptFile(eventId, routeId)); }
  async readProjection(eventId) { assertEventId(eventId); return readJson(this.file("projections", eventId)); }
  async listProjections() { return listJson(this.directory("projections")); }

  async putInbox(event, { serverCursor = null, receivedAt = nowIso(this.now()) } = {}) {
    validateCompletionEvent(event);
    const digest = completionDigest(event);
    const existing = await this.readInbox(event.event_id);
    if (existing && existing.event_digest !== digest) throw new CompletionConflictError(`event_id ${event.event_id} was received with a different digest`);
    const positionPath = this.positionFile(event.origin_stream_id, event.origin_sequence);
    const position = await readJson(positionPath);
    if (position && (position.event_id !== event.event_id || position.event_digest !== digest)) {
      throw new CompletionConflictError(`origin stream position ${event.origin_stream_id}/${event.origin_sequence} was reused with a different digest`);
    }
    if (!existing) {
      await writeJsonAtomic(this.file("inbox", event.event_id), {
        schema_version: "completion-alert-inbox/v1",
        event_id: event.event_id,
        event_digest: digest,
        received_at: receivedAt,
        server_cursor: serverCursor,
        event
      });
    }
    if (!position) await writeJsonAtomic(positionPath, { event_id: event.event_id, event_digest: digest });
    return existing || await this.readInbox(event.event_id);
  }

  async writeOutcome(outcome) { assertEventId(outcome.event_id); await writeJsonAtomic(this.file("outcomes", outcome.event_id), outcome); return outcome; }
  async writeReceipt(receipt) { assertEventId(receipt.event_id); assertSafeComponent(receipt.route_id, "route_id"); await writeJsonAtomic(this.receiptFile(receipt.event_id, receipt.route_id), receipt); return receipt; }
  async writeProjection(projection) { assertEventId(projection.event_id); await writeJsonAtomic(this.file("projections", projection.event_id), projection); return projection; }

  async quarantine(event, error, metadata = {}) {
    const rawIdentity = event?.event_id;
    const eventId = UUID_RE.test(rawIdentity || "") ? rawIdentity : null;
    const quarantineDigest = createHash("sha256").update(JSON.stringify(event ?? null)).digest("hex").slice(0, 32);
    const recordId = `invalid-${quarantineDigest}-${metadata.quarantine_id ? Date.now() : "event"}`;
    const summary = event && typeof event === "object" ? {
      ...(event.schema_version === COMPLETION_SCHEMA_VERSION ? { schema_version: event.schema_version } : {}),
      ...(eventId ? { event_id: eventId } : {}),
      ...(UUID_RE.test(event.origin_stream_id || "") ? { origin_stream_id: event.origin_stream_id } : {}),
      ...(Number.isInteger(event.origin_sequence) && event.origin_sequence > 0 ? { origin_sequence: event.origin_sequence } : {}),
      ...(TERMINAL_KINDS.has(event.terminal?.kind) ? { terminal_kind: event.terminal.kind } : {}),
      ...(TERMINAL_REASONS[event.terminal?.kind]?.has(event.terminal?.reason_code) ? { terminal_reason_code: event.terminal.reason_code } : {})
    } : null;
    const record = {
      schema_version: "completion-alert-quarantine/v1",
      event_id: eventId,
      quarantined_at: nowIso(this.now()),
      error: "completion-event-quarantined",
      error_class: ["CompletionValidationError", "CompletionConflictError"].includes(error?.name) ? error.name : "Error",
      metadata: { server_cursor: metadata.serverCursor == null ? null : "present" },
      event: summary
    };
    await writeJsonAtomic(this.file("quarantine", recordId), record);
    return record;
  }

  async writeHealth(health) { await writeJsonAtomic(statePath(this.root, "health.json"), health); return health; }
  async readHealth() { return readJson(statePath(this.root, "health.json")); }

  async compact({ now = this.now() } = {}) {
    const nowMs = (now instanceof Date ? now : new Date(now)).getTime();
    const removed = { inbox: 0, outcomes: 0, receipts: 0, projections: 0 };
    const rules = [
      ["inbox", this.retention.inboxMs, (value) => value.received_at],
      ["outcomes", this.retention.outcomeMs, (value) => value.updated_at || value.decided_at],
      ["receipts", this.retention.receiptMs, (value) => value.updated_at || value.created_at],
      ["projections", this.retention.projectionMs, (value) => value.received_at]
    ];
    for (const [name, ageMs, timestamp] of rules) {
      for (const { filePath, value } of await listJson(this.directory(name))) {
        if (["pending", "dead-lettered"].includes(value.outcome) || ["pending", "dead-lettered"].includes(value.state)) continue;
        const ts = Date.parse(timestamp(value) || "");
        if (!Number.isNaN(ts) && nowMs - ts > ageMs) {
          await fs.unlink(filePath);
          removed[name] += 1;
        }
      }
    }
    return removed;
  }

  async listHealth({ now = this.now() } = {}) {
    const [inbox, outcomes, receipts, projections, quarantine, checkpoint, health] = await Promise.all([
      listJson(this.directory("inbox")), listJson(this.directory("outcomes")), listJson(this.directory("receipts")),
      listJson(this.directory("projections")), listJson(this.directory("quarantine")), this.readCheckpoint(), this.readHealth()
    ]);
    const pendingReceipts = receipts.filter(({ value }) => value.state === "pending");
    const oldest = pendingReceipts.map(({ value }) => Date.parse(value.created_at || "")).filter(Number.isFinite).sort((a, b) => a - b)[0];
    const routeHealth = {};
    for (const { value } of receipts) {
      const route = routeHealth[value.route_id] || { pending: 0, delivered: 0, suppressed: 0, dead_lettered: 0, oldest_pending_at: null };
      if (value.state === "pending") route.pending += 1;
      if (value.state === "delivered") route.delivered += 1;
      if (value.state === "suppressed") route.suppressed = (route.suppressed || 0) + 1;
      if (value.state === "dead-lettered") route.dead_lettered += 1;
      if (value.state === "pending" && (!route.oldest_pending_at || value.created_at < route.oldest_pending_at)) route.oldest_pending_at = value.created_at;
      routeHealth[value.route_id] = route;
    }
    return {
      schema_version: "completion-alert-health/v1",
      source: "agentops://completion-alerts",
      checkpoint: checkpoint.server_cursor,
      inbox_count: inbox.length,
      outcomes: Object.fromEntries(COMPLETION_OUTCOMES.map((outcome) => [outcome, outcomes.filter(({ value }) => value.outcome === outcome).length])),
      projection_count: projections.length,
      quarantine_count: quarantine.length,
      oldest_pending_age_seconds: oldest == null ? null : Math.max(0, ((now instanceof Date ? now : new Date(now)).getTime() - oldest) / 1000),
      routes: routeHealth,
      server: health?.server || null,
      lag: {
        consumer_cursor: checkpoint.server_cursor,
        server_cursor: health?.server?.cursor || null,
        server_ingest_lag_seconds: health?.server?.ingest_lag_seconds ?? null
      },
      consumer: health?.consumer || null,
      updated_at: health?.updated_at || null
    };
  }
}

async function fetchWithTimeout(url, options, timeoutMs, fetchImpl = fetch) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetchImpl(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

export async function readCompletionPage({ cursor = null, limit = null, replay = false, fetchImpl = fetch, config = getConfig() } = {}) {
  if (!config.completionAlertActionqUrl) throw new Error("completion alert served read URL is not configured");
  const url = new URL(config.completionAlertActionqUrl);
  if (cursor != null) url.searchParams.set("cursor", String(cursor));
  url.searchParams.set("limit", String(Math.max(1, Math.min(Number(limit || config.completionAlertPageSize || 100), 500))));
  if (replay) url.searchParams.set("replay", "true");
  const headers = { accept: "application/json" };
  if (config.completionAlertReadToken) headers.authorization = `Bearer ${config.completionAlertReadToken}`;
  const response = await fetchWithTimeout(url, { headers, cache: "no-store" }, config.completionAlertPollTimeoutMs || 3000, fetchImpl);
  let body;
  try { body = await response.json(); } catch { body = null; }
  if (!response.ok) throw new Error(`completion log read failed with HTTP ${response.status}`);
  const rows = body?.events || body?.completions || body?.items || [];
  if (!Array.isArray(rows)) throw new Error("completion log response events must be an array");
  return {
    events: rows.map((row) => row?.event || row?.payload || row),
    next_cursor: body?.next_cursor ?? body?.nextCursor ?? body?.cursor?.next ?? null,
    server_cursor: body?.server_cursor ?? body?.cursor?.current ?? null,
    gap: Boolean(body?.gap || body?.cursor_gap || body?.requires_replay),
    health: body?.health || null
  };
}

function retryDelay(attempts, baseMs, maxMs) {
  return Math.min(maxMs, baseMs * (2 ** Math.max(0, attempts - 1)));
}

export class CompletionAlertConsumer {
  constructor({
    store = null,
    stateRoot = null,
    policy = null,
    fetchPage = null,
    deliverRoute = null,
    now = () => new Date(),
    pollIntervalMs = null,
    pollTimeoutMs = null,
    pageSize = null,
    maxAttempts = null,
    retryBaseMs = null,
    retryMaxMs = null
  } = {}) {
    const config = getConfig();
    this.config = config;
    this.store = store || new DurableCompletionAlertStore({ root: stateRoot || config.completionAlertStateRoot, now });
    let configuredPolicy = policy;
    if (!configuredPolicy && config.completionAlertPolicyJson) configuredPolicy = JSON.parse(config.completionAlertPolicyJson);
    this.policy = normalizeCompletionAlertPolicy(configuredPolicy || DEFAULT_COMPLETION_ALERT_POLICY);
    this.fetchPage = fetchPage || ((args) => readCompletionPage({ ...args, config, limit: args.limit || pageSize }));
    this.deliverRoute = deliverRoute || (async ({ routeId, event, evaluation, coalescedInto, receivedAt }) => {
      if (routeId === COCKPIT_ROUTE_ID) {
        const existing = await this.store.readProjection(event.event_id);
        return this.store.writeProjection(existing || safeAlertProjection(event, evaluation, receivedAt, coalescedInto));
      }
      throw new Error(`completion route ${routeId} is not implemented by the default AgentOps consumer`);
    });
    this.now = now;
    this.pollIntervalMs = Math.max(250, Math.min(30000, pollIntervalMs ?? config.completionAlertPollIntervalMs));
    this.pollTimeoutMs = Math.max(250, Math.min(30000, pollTimeoutMs ?? config.completionAlertPollTimeoutMs));
    this.pageSize = Math.max(1, Math.min(500, pageSize ?? config.completionAlertPageSize));
    this.maxAttempts = Math.max(1, maxAttempts ?? config.completionAlertMaxAttempts);
    this.retryBaseMs = Math.max(50, retryBaseMs ?? config.completionAlertRetryBaseMs);
    this.retryMaxMs = Math.max(this.retryBaseMs, retryMaxMs ?? config.completionAlertRetryMaxMs);
    this.running = false;
    this.timer = null;
    this.polling = false;
  }

  async _health(patch = {}) {
    const previous = await this.store.readHealth();
    const health = {
      ...(previous || {}),
      consumer: { ...(previous?.consumer || {}), ...patch },
      updated_at: nowIso(this.now())
    };
    await this.store.writeHealth(health);
    return health;
  }

  async _writeOutcome(event, evaluation, outcome, extra = {}) {
    const current = await this.store.readOutcome(event.event_id);
    return this.store.writeOutcome({
      schema_version: "completion-alert-outcome/v1",
      event_id: event.event_id,
      event_digest: completionDigest(event),
      ...current,
      outcome,
      policy_id: this.policy.policy_id,
      policy_version: this.policy.version,
      policy_decision: evaluation,
      ...extra,
      event_id: event.event_id,
      updated_at: nowIso(this.now())
    });
  }

  async _coalescingRoot(event) {
    if (this.policy.coalesce_window_seconds <= 0) return null;
    const cutoff = (this.now() instanceof Date ? this.now() : new Date(this.now())).getTime() - this.policy.coalesce_window_seconds * 1000;
    const key = `${event.repo.project}:${event.harness}:${event.terminal.kind}`;
    const recent = (await this.store.listProjections())
      .map(({ value }) => value)
      .filter((projection) => projection.coalesce_key === key && !projection.coalesced_into && Date.parse(projection.completed_at || "") >= cutoff)
      .sort((a, b) => String(b.completed_at).localeCompare(String(a.completed_at)))[0];
    return recent || null;
  }

  async _coalesceEvent(event, evaluation, root) {
    const child = safeAlertProjection(event, evaluation, (await this.store.readInbox(event.event_id)).received_at, root.event_id);
    await this.store.writeProjection(child);
    const aggregate = {
      ...root,
      coalesced_event_count: Number(root.coalesced_event_count || 1) + 1,
      last_coalesced_at: nowIso(this.now()),
      last_coalesced_event_id: event.event_id
    };
    await this.store.writeProjection(aggregate);
    const routeReceipts = [];
    for (const routeId of evaluation.routes) {
      const receipt = (await this.store.readReceipt(event.event_id, routeId)) || {
        schema_version: "completion-alert-receipt/v1",
        event_id: event.event_id,
        route_id: routeId,
        attempts: 0,
        created_at: nowIso(this.now())
      };
      receipt.state = "suppressed";
      receipt.reason = "coalesced";
      receipt.coalesced_into = root.event_id;
      receipt.next_attempt_at = null;
      receipt.updated_at = nowIso(this.now());
      routeReceipts.push(await this.store.writeReceipt(receipt));
    }
    await this._writeOutcome(event, evaluation, "suppressed", {
      reason: "coalesced",
      coalesced_into: root.event_id,
      route_receipts: routeReceipts.map((receipt) => ({ route_id: receipt.route_id, state: receipt.state, coalesced_into: root.event_id }))
    });
    return { outcome: "suppressed", reason: "coalesced", coalesced_into: root.event_id };
  }

  async _processEvent(rawEvent, serverCursor, { replay = false } = {}) {
    let event;
    try {
      event = validateCompletionEvent(rawEvent);
    } catch (error) {
      await this.store.quarantine(rawEvent, error, { serverCursor });
      if (rawEvent?.event_id && UUID_RE.test(rawEvent.event_id)) {
        await this.store.writeOutcome({ schema_version: "completion-alert-outcome/v1", event_id: rawEvent.event_id, outcome: "dead-lettered", reason: "invalid-event", error: redactDiagnostic(error.message), updated_at: nowIso(this.now()) });
      }
      return { outcome: "dead-lettered", reason: "invalid-event" };
    }
    try {
      await this.store.putInbox(event, { serverCursor, receivedAt: nowIso(this.now()) });
    } catch (error) {
      await this.store.quarantine(event, error, { serverCursor, quarantine_id: `${event.event_id}-${Date.now()}` });
      if (!(await this.store.readOutcome(event.event_id))) {
        await this.store.writeOutcome({ schema_version: "completion-alert-outcome/v1", event_id: event.event_id, outcome: "dead-lettered", reason: "identity-conflict", error: redactDiagnostic(error.message), updated_at: nowIso(this.now()) });
      }
      return { outcome: "dead-lettered", reason: "identity-conflict" };
    }
    const existingOutcome = replay ? null : await this.store.readOutcome(event.event_id);
    if (existingOutcome && ["delivered", "suppressed", "dead-lettered"].includes(existingOutcome.outcome)) return { outcome: existingOutcome.outcome, duplicate: true };
    let evaluation = existingOutcome?.policy_decision;
    if (!evaluation || existingOutcome?.reason === "quiet-hours") evaluation = evaluateCompletionAlertPolicy(event, this.policy, this.now());
    if (evaluation.decision === "suppress") {
      await this._writeOutcome(event, evaluation, "suppressed", { reason: evaluation.reason, route_receipts: [] });
    return { outcome: "suppressed", reason: evaluation.reason };
    }
    if (evaluation.decision === "defer") {
      const receipts = [];
      for (const routeId of evaluation.routes) {
        const existing = await this.store.readReceipt(event.event_id, routeId);
        const receipt = existing || { schema_version: "completion-alert-receipt/v1", event_id: event.event_id, route_id: routeId, state: "pending", attempts: 0, created_at: nowIso(this.now()) };
        receipt.state = "pending";
        receipt.reason = evaluation.reason;
        receipt.next_attempt_at = nowIso(new Date((this.now() instanceof Date ? this.now() : new Date(this.now())).getTime() + this.pollIntervalMs));
        receipt.updated_at = nowIso(this.now());
        receipts.push(await this.store.writeReceipt(receipt));
      }
      await this._writeOutcome(event, evaluation, "pending", { reason: evaluation.reason, route_receipts: receipts.map((receipt) => ({ route_id: receipt.route_id, state: receipt.state })) });
      return { outcome: "pending", reason: evaluation.reason };
    }

    const coalescingRoot = await this._coalescingRoot(event);
    if (coalescingRoot) return this._coalesceEvent(event, evaluation, coalescingRoot);
    const routeReceipts = [];
    for (const routeId of evaluation.routes) {
      const existing = await this.store.readReceipt(event.event_id, routeId);
      if (existing?.state === "delivered" && !replay) {
        routeReceipts.push(existing);
        continue;
      }
      if (existing?.state === "pending" && existing.next_attempt_at && Date.parse(existing.next_attempt_at) > (this.now() instanceof Date ? this.now() : new Date(this.now())).getTime() && !replay) {
        routeReceipts.push(existing);
        continue;
      }
      const receipt = existing || { schema_version: "completion-alert-receipt/v1", event_id: event.event_id, route_id: routeId, attempts: 0, created_at: nowIso(this.now()) };
      receipt.attempts += 1;
      receipt.updated_at = nowIso(this.now());
      try {
        await this.deliverRoute({ routeId, event, evaluation, coalescedInto: null, receivedAt: (await this.store.readInbox(event.event_id)).received_at });
        receipt.state = "delivered";
        receipt.delivered_at = nowIso(this.now());
        receipt.next_attempt_at = null;
        receipt.last_error = null;
      } catch (error) {
        receipt.last_error = redactDiagnostic(error?.message || error);
        if (receipt.attempts >= this.maxAttempts) {
          receipt.state = "dead-lettered";
          receipt.next_attempt_at = null;
        } else {
          receipt.state = "pending";
          receipt.next_attempt_at = nowIso(new Date((this.now() instanceof Date ? this.now() : new Date(this.now())).getTime() + retryDelay(receipt.attempts, this.retryBaseMs, this.retryMaxMs)));
        }
      }
      routeReceipts.push(await this.store.writeReceipt(receipt));
    }
    const hasPending = routeReceipts.some((receipt) => receipt.state === "pending");
    const hasDead = routeReceipts.some((receipt) => receipt.state === "dead-lettered");
    const outcome = hasDead ? "dead-lettered" : hasPending ? "pending" : "delivered";
    await this._writeOutcome(event, evaluation, outcome, {
      reason: outcome === "delivered" ? "route-delivered" : outcome === "pending" ? "route-retry" : "route-exhausted",
      route_receipts: routeReceipts.map((receipt) => ({ route_id: receipt.route_id, state: receipt.state, attempts: receipt.attempts, last_error: receipt.last_error || null }))
    });
    return { outcome, route_receipts: routeReceipts };
  }

  async pollOnce({ replay = false } = {}) {
    if (this.polling) return { status: "busy" };
    this.polling = true;
    await this.store.initialize();
    const startedAt = nowIso(this.now());
    const checkpoint = await this.store.readCheckpoint();
    await this._health({ status: "polling", last_poll_started_at: startedAt, last_error: null });
    try {
      let page = await this.fetchPage({ cursor: checkpoint.server_cursor, limit: this.pageSize, replay, timeoutMs: this.pollTimeoutMs });
      let gapRepaired = false;
      if (page.gap && !replay) {
        // A notification or a server page hint is not a correctness record.
        // Re-read the same durable cursor in replay mode before advancing it.
        page = await this.fetchPage({ cursor: checkpoint.server_cursor, limit: this.pageSize, replay: true, timeoutMs: this.pollTimeoutMs });
        gapRepaired = true;
      }
      const results = [];
      for (const event of page.events || []) results.push(await this._processEvent(event, page.server_cursor ?? page.next_cursor ?? checkpoint.server_cursor, { replay }));
      // A page can be empty while a route is still backing off. Retry those
      // receipts from the durable inbox; the server cursor must never be held
      // hostage by one unavailable route.
      if (!replay) {
        for (const { value } of await this.store.listInbox()) {
          const outcome = await this.store.readOutcome(value.event_id);
          if (outcome?.outcome === "pending") {
            results.push(await this._processEvent(value.event, value.server_cursor, { replay: false }));
          }
        }
      }
      await this.store.writeCheckpoint({
        server_cursor: page.next_cursor ?? checkpoint.server_cursor,
        last_advanced_at: nowIso(this.now()),
        pages: checkpoint.pages + 1,
        events_seen: checkpoint.events_seen + results.length
      });
      await this._health({
        status: "healthy",
        last_poll_completed_at: nowIso(this.now()),
        last_server_cursor: page.next_cursor ?? checkpoint.server_cursor,
        last_page_size: (page.events || []).length,
        last_gap_repaired: gapRepaired,
        last_error: null
      });
      if (page.health) {
        await this._health({ server: safeServerHealth(page.health, page.server_cursor ?? page.next_cursor ?? null) });
      }
      const health = await this.store.listHealth({ now: this.now() });
      return { status: "ok", events: results.length, results, next_cursor: page.next_cursor ?? checkpoint.server_cursor, health };
    } catch (error) {
      const safeError = redactDiagnostic(error?.message || error);
      await this._health({ status: "degraded", last_poll_completed_at: nowIso(this.now()), last_error: safeError });
      return { status: "degraded", events: 0, error: safeError };
    } finally {
      this.polling = false;
    }
  }

  async replayEvent(eventId) {
    const inbox = await this.store.readInbox(eventId);
    if (!inbox) throw new Error(`completion event ${eventId} is not in the durable inbox`);
    return this._processEvent(inbox.event, inbox.server_cursor, { replay: true });
  }

  async health() { await this.store.initialize(); return this.store.listHealth({ now: this.now() }); }

  start() {
    if (this.running) return;
    this.running = true;
    const tick = async () => {
      if (!this.running) return;
      const result = await this.pollOnce();
      const delay = result.status === "degraded" ? Math.min(this.retryMaxMs, Math.max(this.pollIntervalMs, this.retryBaseMs)) : this.pollIntervalMs;
      this.timer = setTimeout(tick, delay);
    };
    void tick();
  }

  stop() {
    this.running = false;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
  }
}

export async function readCompletionAlertProjection({ repoId = "ALL", limit = 50, stateRoot = null, now = () => new Date() } = {}) {
  const config = getConfig();
  const store = new DurableCompletionAlertStore({ root: stateRoot || config.completionAlertStateRoot, now });
  const entries = await listJson(store.directory("projections"));
  const allProjections = entries.map(({ value }) => value);
  const alerts = allProjections
    .filter((alert) => !alert.coalesced_into)
    .filter((alert) => repoId === "ALL" || alert.repo?.project === repoId)
    .sort((a, b) => String(b.completed_at).localeCompare(String(a.completed_at)))
    .slice(0, Math.max(1, Math.min(Number(limit) || 50, 200)));
  const coalescedEvents = allProjections
    .filter((alert) => alert.coalesced_into)
    .filter((alert) => repoId === "ALL" || alert.repo?.project === repoId)
    .sort((a, b) => String(b.completed_at).localeCompare(String(a.completed_at)))
    .slice(0, 200);
  const health = await store.listHealth({ now: now() });
  const outcomes = (await listJson(store.directory("outcomes"))).map(({ value }) => value)
    .filter((outcome) => repoId === "ALL" || allProjections.find((entry) => entry.event_id === outcome.event_id)?.repo?.project === repoId)
    .sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)))
    .slice(0, 200);
  return { source: "agentops://completion-alerts", repo_id: repoId, alerts, coalesced_events: coalescedEvents, outcomes, pending_deliveries: outcomes.filter((outcome) => outcome.outcome === "pending"), health, degraded: null };
}

export { safeAlertProjection };
