import { getConfig } from "./env.js";

export const DISPATCH_CONTRACT_VERSION = "v2";

// actionq-server was deleted from the cluster on 2026-09-01 (see
// actionq/docs/plans/2026-08-20-execution-plane-deletion-order.md). There is
// no owner-source server behind either the actionq-server forwarding path or
// the actionctl CLI path any more, so the dispatch write surface is retired
// outright rather than gated on configuration. Dispatch is done by native
// harness sessions coordinated through sprintctl; see
// docs/runbooks/maintenance-lane.md for the current path.
export const DISPATCH_RETIRED_REASON =
  "Dispatch write path retired: actionq-server was removed from the cluster on 2026-09-01 " +
  "and no queue worker replaces it. Dispatch is done by native harness sessions coordinated " +
  "through sprintctl; see docs/runbooks/maintenance-lane.md.";
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

export function getDispatchGate() {
  return {
    enabled: false,
    source: "cockpit-dispatch-retired",
    reason: DISPATCH_RETIRED_REASON
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

// dispatchViaActionctl and forwardDispatchToActionqServer were removed with
// the dispatch write path retirement (agentops#2409 / D17). Neither
// owner-source (actionctl v2 persistence, actionq-server) exists any more, so
// the outbound call capability itself is gone, not merely gated off. See
// getDispatchGate above and docs/runbooks/maintenance-lane.md.
