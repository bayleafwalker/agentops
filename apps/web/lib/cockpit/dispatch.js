import { getConfig } from "./env.js";

export const DISPATCH_CONTRACT_VERSION = "v1";
const DISPATCH_KINDS = new Set(["implement", "review", "test", "investigate", "document", "custom"]);
const DISPATCH_HARNESSES = new Set(["claude", "codex", "copilot-cli", "codestral"]);
const DISPATCH_PRIORITIES = new Set(["normal", "high"]);

export function getDispatchGate(config = getConfig()) {
  if (!config.actionqServerUrl) {
    return {
      enabled: false,
      source: "actionq-server",
      reason: "Dispatch disabled: COCKPIT_ACTIONQ_SERVER_URL is not configured."
    };
  }
  if (config.actionqDispatchContract !== DISPATCH_CONTRACT_VERSION) {
    return {
      enabled: false,
      source: "actionq-server",
      reason: `Dispatch disabled: actionq-server dispatch contract must be ${DISPATCH_CONTRACT_VERSION}.`
    };
  }
  return {
    enabled: true,
    source: "actionq-server",
    url: config.actionqServerUrl.replace(/\/+$/, "")
  };
}

export function getDispatchOperator(config = getConfig()) {
  return String(config.cockpitOperatorId || "operator:cockpit").trim() || "operator:cockpit";
}

function trimString(value) {
  return typeof value === "string" ? value.trim() : "";
}

function optionalTrimmedString(value) {
  if (value == null || value === "") {
    return null;
  }
  if (typeof value !== "string") {
    throw new Error("optional string fields must be strings when present");
  }
  return value.trim();
}

function validateStringList(value, name) {
  const refs = value == null ? [] : value;
  if (!Array.isArray(refs) || refs.some((ref) => typeof ref !== "string")) {
    throw new Error(`${name} must be an array of strings`);
  }
  return refs.map((ref) => ref.trim()).filter(Boolean);
}

export function normalizeDispatchPayload(payload, { requestedBy = getDispatchOperator() } = {}) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("dispatch payload must be an object");
  }
  const repoId = trimString(payload.repo_id);
  const kind = trimString(payload.kind);
  const title = trimString(payload.title);
  const prompt = typeof payload.prompt === "string" ? payload.prompt : "";
  const harness = trimString(payload.harness);
  const model = optionalTrimmedString(payload.model);
  const priority = trimString(payload.priority || "normal");
  const refs = validateStringList(payload.refs, "refs");
  const workItemId = optionalTrimmedString(payload.work_item_id);
  const operatorId = String(requestedBy || "").trim();
  if (!repoId || repoId === "ALL") {
    throw new Error("repo_id must name one concrete repo");
  }
  if (!Number.isInteger(payload.sprint_id)) {
    throw new Error("sprint_id must be an integer");
  }
  if (!DISPATCH_KINDS.has(kind)) {
    throw new Error(`kind must be one of: ${[...DISPATCH_KINDS].join(", ")}`);
  }
  if (!title) {
    throw new Error("title is required");
  }
  if (!harness || !DISPATCH_HARNESSES.has(harness)) {
    throw new Error(`harness must be one of: ${[...DISPATCH_HARNESSES].join(", ")}`);
  }
  if (!DISPATCH_PRIORITIES.has(priority)) {
    throw new Error(`priority must be one of: ${[...DISPATCH_PRIORITIES].join(", ")}`);
  }
  if (!operatorId) {
    throw new Error("requested_by is required");
  }
  return {
    repo_id: repoId,
    sprint_id: payload.sprint_id,
    work_item_id: workItemId,
    kind,
    title,
    prompt,
    harness,
    model,
    priority,
    refs,
    requested_by: operatorId
  };
}

async function parseJsonResponse(response) {
  const text = await response.text();
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch (error) {
    if (!response.ok) {
      return null;
    }
    throw new Error("actionq-server returned invalid JSON");
  }
}

export async function forwardDispatchToActionqServer(payload, { config = getConfig(), fetchImpl = fetch } = {}) {
  const gate = getDispatchGate(config);
  if (!gate.enabled) {
    throw new Error(gate.reason);
  }
  const response = await fetchImpl(`${gate.url}/dispatch`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-actionq-dispatch-contract": DISPATCH_CONTRACT_VERSION
    },
    body: JSON.stringify({
      contract_version: DISPATCH_CONTRACT_VERSION,
      ...payload
    })
  });
  const body = await parseJsonResponse(response);
  if (!response.ok) {
    throw new Error(body?.error || body?.message || `actionq-server dispatch failed with ${response.status}`);
  }
  return body;
}
