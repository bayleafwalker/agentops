import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { getConfig } from "./env.js";

const execFileAsync = promisify(execFile);

export const DISPATCH_CONTRACT_VERSION = "v2";
const DISPATCH_KINDS = new Set(["implement", "review", "test", "investigate", "document", "custom"]);
const DISPATCH_HARNESSES = new Set(["claude", "codex", "copilot-cli", "codestral"]);
const DISPATCH_PRIORITIES = new Set(["normal", "high"]);
const OUTPUT_EXPECTATIONS = new Set(["plan", "audit-event", "draft-work-items", "sprint-proposal", "implementation", "review"]);

const V1_KIND_TO_EXPECTATION = {
  implement: "implementation",
  review: "review",
  test: "review",
  investigate: "plan",
  document: "plan"
};
const V2_PRODUCER_FIELDS = [
  "contract_version", "action_type", "output_expectation", "repo_id", "sprint_id", "work_item_id",
  "title", "prompt", "harness", "model", "priority", "refs", "dispatch_group_id"
];
const V2_PRODUCER_FIELD_SET = new Set(V2_PRODUCER_FIELDS);
const V2_ENQUEUE_RESULT_FIELDS = new Set(["action_id", "status", "request_ref", "request_sha256"]);

export function getDispatchGate(config = getConfig()) {
  if (config.actionqServerUrl) {
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
      method: "server",
      url: config.actionqServerUrl.replace(/\/+$/, "")
    };
  }
  return {
    enabled: false,
    source: "actionctl",
    reason: "Dispatch disabled: actionctl cannot yet persist the v2 immutable request snapshot, request_ref, and request_sha256."
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

function requireV2NonBlankString(payload, field) {
  if (typeof payload[field] !== "string" || !payload[field].trim()) {
    throw new Error(`${field} must be a non-blank string for v2`);
  }
}

function validateV2ProducerPayload(payload) {
  for (const field of V2_PRODUCER_FIELDS) {
    if (!Object.hasOwn(payload, field)) {
      throw new Error(`${field} is required for v2`);
    }
  }
  for (const field of Object.keys(payload)) {
    if (!V2_PRODUCER_FIELD_SET.has(field)) {
      throw new Error(`unknown v2 dispatch field: ${field}`);
    }
  }
  for (const field of ["contract_version", "action_type", "output_expectation", "repo_id", "title", "harness", "priority"]) {
    requireV2NonBlankString(payload, field);
  }
  if (payload.contract_version !== DISPATCH_CONTRACT_VERSION) {
    throw new Error("contract_version must be exactly v2");
  }
  if (payload.action_type !== "scope-iterate") {
    throw new Error("action_type must be exactly scope-iterate for v2");
  }
  if (!OUTPUT_EXPECTATIONS.has(payload.output_expectation)) {
    throw new Error("output_expectation must be an exact v2 enum value");
  }
  if (!DISPATCH_HARNESSES.has(payload.harness)) {
    throw new Error("harness must be an exact v2 enum value");
  }
  if (!DISPATCH_PRIORITIES.has(payload.priority)) {
    throw new Error("priority must be an exact v2 enum value");
  }
  if (typeof payload.prompt !== "string") {
    throw new Error("prompt must be a string for v2");
  }
  if (payload.sprint_id !== null && (!Number.isInteger(payload.sprint_id) || payload.sprint_id < 1)) {
    throw new Error("sprint_id must be a positive integer or null for v2");
  }
  for (const field of ["work_item_id", "model", "dispatch_group_id"]) {
    if (payload[field] !== null && (typeof payload[field] !== "string" || !payload[field].trim())) {
      throw new Error(`${field} must be null or a non-blank string for v2`);
    }
  }
  if (!Array.isArray(payload.refs) || payload.refs.some((ref) => typeof ref !== "string" || !ref.trim())) {
    throw new Error("refs must be an array of non-blank strings for v2");
  }
}

export function normalizeDispatchPayload(payload, { requestedBy = getDispatchOperator() } = {}) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("dispatch payload must be an object");
  }
  const inputVersion = payload.contract_version === undefined ? "v1" : payload.contract_version;
  if (inputVersion !== "v1" && inputVersion !== DISPATCH_CONTRACT_VERSION) {
    throw new Error("contract_version must be v1 or v2");
  }
  const repoId = trimString(payload.repo_id);
  const kind = trimString(payload.kind);
  const actionType = trimString(payload.action_type || "scope-iterate");
  const title = trimString(payload.title);
  const prompt = typeof payload.prompt === "string" ? payload.prompt : "";
  const harness = trimString(payload.harness);
  const model = optionalTrimmedString(payload.model);
  const priority = trimString(payload.priority || "normal");
  const refs = validateStringList(payload.refs, "refs");
  let workItemId = optionalTrimmedString(payload.work_item_id);
  if (workItemId && /^wi:/i.test(workItemId)) {
    workItemId = workItemId.slice(workItemId.indexOf(":") + 1).trim() || null;
  }
  let outputExpectation = trimString(payload.output_expectation);
  const dispatchGroupId = optionalTrimmedString(payload.dispatch_group_id);
  const operatorId = String(requestedBy || "").trim();
  if (!repoId || repoId === "ALL") {
    throw new Error("repo_id must name one concrete repo");
  }
  if (payload.sprint_id != null && !Number.isInteger(payload.sprint_id)) {
    throw new Error("sprint_id must be an integer when present");
  }
  if (inputVersion === DISPATCH_CONTRACT_VERSION) {
    validateV2ProducerPayload(payload);
    if (typeof payload.work_item_id === "string" && /^wi:/i.test(payload.work_item_id)) {
      throw new Error("work_item_id must be normalized without a wi: prefix for v2");
    }
    if (!trimString(payload.action_type)) {
      throw new Error("action_type is required for v2");
    }
    if (!outputExpectation) {
      throw new Error("output_expectation is required for v2");
    }
  } else {
    if (!DISPATCH_KINDS.has(kind)) {
      throw new Error(`kind must be one of: ${[...DISPATCH_KINDS].join(", ")}`);
    }
    const mappedExpectation = V1_KIND_TO_EXPECTATION[kind];
    if (!mappedExpectation) {
      throw new Error("v1 kind custom has no deterministic v2 compatibility mapping");
    }
    if (outputExpectation && outputExpectation !== mappedExpectation) {
      throw new Error(`v1 kind ${kind} conflicts with output_expectation ${outputExpectation}`);
    }
    outputExpectation = mappedExpectation;
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
  if (!OUTPUT_EXPECTATIONS.has(outputExpectation)) {
    throw new Error(`output_expectation must be one of: ${[...OUTPUT_EXPECTATIONS].join(", ")}`);
  }
  if (actionType !== "scope-iterate") {
    throw new Error("action_type must be scope-iterate");
  }
  if (!operatorId) {
    throw new Error("requested_by is required");
  }
  return {
    contract_version: DISPATCH_CONTRACT_VERSION,
    action_type: actionType,
    repo_id: repoId,
    sprint_id: payload.sprint_id ?? null,
    work_item_id: workItemId,
    output_expectation: outputExpectation,
    title,
    prompt,
    harness,
    model,
    priority,
    refs,
    dispatch_group_id: dispatchGroupId,
    requested_by: operatorId
  };
}

export async function dispatchViaActionctl(payload, bin = "actionctl") {
  const type = payload.action_type;
  const priority = payload.priority === "high" ? 50 : 100;
  const args = ["add", "--type", type, "--project", payload.repo_id, "--created-by", payload.requested_by || "operator:cockpit", "--priority", String(priority)];
  if (payload.work_item_id) {
    args.push("--target", payload.work_item_id);
  }
  if (payload.sprint_id != null) {
    args.push("--source", `sprint:${payload.sprint_id}`);
  }
  const { stdout } = await execFileAsync(bin, args, { encoding: "utf8", timeout: 10000 });
  return JSON.parse(stdout || "{}");
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

function validateEnqueuePersistence(body) {
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    throw new Error("actionq-server v2 dispatch response must be an object");
  }
  for (const field of V2_ENQUEUE_RESULT_FIELDS) {
    if (!Object.hasOwn(body, field)) {
      throw new Error(`actionq-server v2 dispatch response is missing ${field}`);
    }
  }
  for (const field of Object.keys(body)) {
    if (!V2_ENQUEUE_RESULT_FIELDS.has(field)) {
      throw new Error(`actionq-server v2 dispatch response has unknown field: ${field}`);
    }
  }
  if (!(Number.isInteger(body.action_id) || (typeof body.action_id === "string" && body.action_id.trim()))) {
    throw new Error("actionq-server v2 dispatch response is missing a valid action_id");
  }
  if (body.status !== "pending") {
    throw new Error("actionq-server v2 dispatch response must have status pending");
  }
  if (typeof body.request_ref !== "string" || !body.request_ref.trim()) {
    throw new Error("actionq-server v2 dispatch response is missing a valid request_ref");
  }
  if (typeof body.request_sha256 !== "string" || !/^[a-f0-9]{64}$/.test(body.request_sha256)) {
    throw new Error("actionq-server v2 dispatch response is missing a valid request_sha256");
  }
  return body;
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
  return validateEnqueuePersistence(body);
}
