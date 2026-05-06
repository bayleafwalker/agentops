import { getConfig } from "./env.js";

export const DISPATCH_CONTRACT_VERSION = "v1";

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

export function normalizeDispatchPayload(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("dispatch payload must be an object");
  }
  const repoId = String(payload.repo_id || "").trim();
  const actionType = String(payload.action_type || "").trim();
  const targetRef = String(payload.target_ref || "").trim();
  const sourceRefs = payload.source_refs == null ? [] : payload.source_refs;
  if (!repoId || repoId === "ALL") {
    throw new Error("repo_id must name one concrete repo");
  }
  if (!actionType) {
    throw new Error("action_type is required");
  }
  if (!targetRef) {
    throw new Error("target_ref is required");
  }
  if (!Array.isArray(sourceRefs) || sourceRefs.some((ref) => typeof ref !== "string")) {
    throw new Error("source_refs must be an array of strings");
  }
  return {
    repo_id: repoId,
    action_type: actionType,
    target_ref: targetRef,
    source_refs: sourceRefs,
    priority: Number.isInteger(payload.priority) ? payload.priority : 100,
    prompt: typeof payload.prompt === "string" ? payload.prompt : ""
  };
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
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.error || body?.message || `actionq-server dispatch failed with ${response.status}`);
  }
  return body;
}
