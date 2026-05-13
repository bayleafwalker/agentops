export function validateActionSessionRow(row) {
  if (!row || typeof row !== "object") {
    throw new Error("session row must be an object");
  }
  for (const field of ["session_id", "status", "heartbeat_at", "ttl_seconds"]) {
    if (!(field in row)) {
      throw new Error(`session row missing ${field}`);
    }
  }
  if (typeof row.session_id !== "string" || row.session_id.length === 0) {
    throw new Error("session_id must be a non-empty string");
  }
  if (typeof row.status !== "string" || row.status.length === 0) {
    throw new Error("status must be a non-empty string");
  }
  if (typeof row.heartbeat_at !== "string" || !row.heartbeat_at.endsWith("Z")) {
    throw new Error("heartbeat_at must be an ISO UTC string");
  }
  if (typeof row.ttl_seconds !== "number") {
    throw new Error("ttl_seconds must be a number");
  }
  if (row.claim != null) {
    if (typeof row.claim !== "object") {
      throw new Error("claim must be an object when present");
    }
    if (row.claim.claim_id != null && typeof row.claim.claim_id !== "number") {
      throw new Error("claim.claim_id must be a number when present");
    }
  }
  return row;
}

export function validateActionSessionsPayload(payload) {
  if (!Array.isArray(payload)) {
    throw new Error("actionctl sessions output must be an array");
  }
  return payload.map(validateActionSessionRow);
}

export function validateDispatchRow(row) {
  if (!row || typeof row !== "object") {
    throw new Error("dispatch row must be an object");
  }
  for (const field of ["id", "action_type", "project", "status", "priority", "created_at"]) {
    if (!(field in row)) {
      throw new Error(`dispatch row missing ${field}`);
    }
  }
  if (typeof row.id !== "number") {
    throw new Error("dispatch id must be a number");
  }
  if (typeof row.action_type !== "string" || row.action_type.length === 0) {
    throw new Error("action_type must be a non-empty string");
  }
  if (row.project != null && typeof row.project !== "string") {
    throw new Error("project must be a string when present");
  }
  if (typeof row.status !== "string" || row.status.length === 0) {
    throw new Error("status must be a non-empty string");
  }
  if (typeof row.priority !== "number") {
    throw new Error("priority must be a number");
  }
  if (typeof row.created_at !== "string" || !row.created_at.endsWith("Z")) {
    throw new Error("created_at must be an ISO UTC string");
  }
  if (!Array.isArray(row.source_refs)) {
    throw new Error("source_refs must be an array");
  }
  return row;
}

export function validateDispatchesPayload(payload) {
  if (!Array.isArray(payload)) {
    throw new Error("actionq dispatches output must be an array");
  }
  return payload.map(validateDispatchRow);
}

const EVENT_ID_RE = /^ad:[0-9A-HJKMNP-TV-Z]{26}$/;
const VALID_REF_PREFIXES = ["wi:", "ka:", "ad:", "sha:", "pr:", "sprint:"];

export function validateAuditEvent(event) {
  const required = ["id", "ts", "type", "actor", "summary", "refs", "source", "metadata", "created_at"];
  for (const field of required) {
    if (!(field in event)) {
      throw new Error(`missing required field(s): ${field}`);
    }
  }
  if (!EVENT_ID_RE.test(String(event.id))) {
    throw new Error(`invalid audit event id: ${event.id}`);
  }
  for (const field of ["ts", "created_at"]) {
    if (typeof event[field] !== "string" || !event[field].endsWith("Z")) {
      throw new Error(`${field} must be an ISO UTC value ending in Z`);
    }
  }
  if (!Array.isArray(event.refs) || event.refs.some((ref) => typeof ref !== "string")) {
    throw new Error("refs must be a list of strings");
  }
  for (const ref of event.refs) {
    if (!VALID_REF_PREFIXES.some((prefix) => ref.startsWith(prefix))) {
      throw new Error(`invalid ref '${ref}'`);
    }
  }
  if (!event.metadata || typeof event.metadata !== "object" || Array.isArray(event.metadata)) {
    throw new Error("metadata must be an object");
  }
  return event;
}
