import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { getConfig } from "./env.js";

const execFileAsync = promisify(execFile);

export const DISPATCH_CONTRACT_VERSION = "v1";
const DISPATCH_KINDS = new Set(["implement", "review", "test", "investigate", "document", "custom"]);
const DISPATCH_HARNESSES = new Set(["claude", "codex", "copilot-cli", "codestral"]);
const DISPATCH_PRIORITIES = new Set(["normal", "high"]);
const OUTPUT_EXPECTATIONS = new Set(["plan", "audit-event", "draft-work-items", "sprint-proposal", "implementation", "review"]);

const KIND_TO_ACTION_TYPE = {
  implement: "scope-iterate",
  review: "scope-iterate",
  test: "scope-iterate",
  investigate: "scope-iterate",
  document: "scope-iterate",
  custom: "scope-iterate"
};

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
    enabled: true,
    source: "actionctl",
    method: "actionctl",
    bin: config.actionctlBin
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
  const outputExpectation = trimString(payload.output_expectation || "implementation");
  const dispatchGroupId = optionalTrimmedString(payload.dispatch_group_id);
  const operatorId = String(requestedBy || "").trim();
  if (!repoId || repoId === "ALL") {
    throw new Error("repo_id must name one concrete repo");
  }
  if (payload.sprint_id != null && !Number.isInteger(payload.sprint_id)) {
    throw new Error("sprint_id must be an integer when present");
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
  if (!OUTPUT_EXPECTATIONS.has(outputExpectation)) {
    throw new Error(`output_expectation must be one of: ${[...OUTPUT_EXPECTATIONS].join(", ")}`);
  }
  if (!operatorId) {
    throw new Error("requested_by is required");
  }
  return {
    repo_id: repoId,
    sprint_id: payload.sprint_id ?? null,
    work_item_id: workItemId,
    kind,
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
  const type = KIND_TO_ACTION_TYPE[payload.kind] || "scope-iterate";
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
