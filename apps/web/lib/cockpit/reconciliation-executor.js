import { createHash, randomUUID } from "node:crypto";
import { execFile } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";
import { resolveArtifactRepoRoot } from "./artifacts.js";
import { getConfig } from "./env.js";

const execFileAsync = promisify(execFile);
const TERMINAL_COMMAND_STATES = new Set(["accepted", "rejected"]);
const ALLOWED_COMMANDS = new Set([
  "item.transition",
  "item.done",
  "sprint.activate",
  "sprint.close"
]);

export class ProposalExecutionError extends Error {}

function timestamp(now = new Date()) {
  return now.toISOString().replace(/\.\d{3}Z$/, "Z");
}

function positiveInteger(value, field) {
  if (!Number.isInteger(value) || value < 1) {
    throw new ProposalExecutionError(`${field} must be a positive integer`);
  }
  return value;
}

function object(value, field) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ProposalExecutionError(`${field} must be an object`);
  }
  return value;
}

function exactKeys(value, allowed, field) {
  const extras = Object.keys(value).filter((key) => !allowed.has(key));
  if (extras.length) {
    throw new ProposalExecutionError(`${field} has unsupported fields: ${extras.join(", ")}`);
  }
}

function targetId(target, expectedKind) {
  if (target?.kind !== expectedKind || typeof target.ref !== "string") {
    throw new ProposalExecutionError(`command requires a ${expectedKind} proposal target`);
  }
  const prefix = expectedKind === "work-item" ? "wi:" : "sprint:";
  if (!target.ref.startsWith(prefix)) {
    throw new ProposalExecutionError(`target.ref must use the ${prefix} prefix`);
  }
  const suffix = target.ref.slice(prefix.length);
  if (!/^[1-9][0-9]*$/.test(suffix)) {
    throw new ProposalExecutionError("target.ref id must be a positive integer");
  }
  const value = Number(suffix);
  return positiveInteger(value, "target.ref id");
}

// Stable request identities make a retry after a process crash return the
// original sprintctl decision instead of applying a second command.
export function commandRequestId(proposalId, index) {
  if (
    typeof proposalId !== "string" ||
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(proposalId)
  ) {
    throw new ProposalExecutionError("proposal_id must be a lowercase UUID");
  }
  const namespace = Buffer.from(proposalId.replaceAll("-", ""), "hex");
  if (namespace.length !== 16) {
    throw new ProposalExecutionError("proposal_id must be a lowercase UUID");
  }
  const digest = createHash("sha1")
    .update(namespace)
    .update(Buffer.from(`reconciliation-command:${index}`, "utf8"))
    .digest();
  const bytes = Buffer.from(digest.subarray(0, 16));
  bytes[6] = (bytes[6] & 0x0f) | 0x50;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = bytes.toString("hex");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function normalizeProposalCommand(proposal, command, index) {
  object(proposal, "proposal");
  object(command, `proposed_commands[${index}]`);
  if (!ALLOWED_COMMANDS.has(command.command_type)) {
    throw new ProposalExecutionError(
      `proposed_commands[${index}].command_type is not allowlisted: ${command.command_type}`
    );
  }
  const params = object(command.params, `proposed_commands[${index}].params`);
  const basis = object(proposal.basis, "basis");
  if (
    typeof basis.observed_revision !== "string" ||
    !basis.observed_revision ||
    typeof basis.current_revision !== "string" ||
    !basis.current_revision
  ) {
    throw new ProposalExecutionError("basis revisions must be non-empty strings");
  }
  if (basis.observed_revision !== basis.current_revision) {
    throw new ProposalExecutionError(
      "proposal basis is already stale: observed_revision differs from current_revision"
    );
  }

  let aggregateId;
  let payload;
  if (command.command_type === "item.transition") {
    exactKeys(params, new Set(["item_id", "to_status", "claim_id"]), `proposed_commands[${index}].params`);
    aggregateId = targetId(proposal.target, "work-item");
    if (positiveInteger(params.item_id, "params.item_id") !== aggregateId) {
      throw new ProposalExecutionError("params.item_id must match the proposal target");
    }
    if (!new Set(["pending", "active", "blocked"]).has(params.to_status)) {
      throw new ProposalExecutionError("params.to_status is not a recognized item status");
    }
    payload = { to_status: params.to_status };
    if (params.claim_id != null) {
      payload.claim_id = positiveInteger(params.claim_id, "params.claim_id");
    }
  } else if (command.command_type === "item.done") {
    exactKeys(
      params,
      new Set(["item_id", "claim_id", "evidence_event_id"]),
      `proposed_commands[${index}].params`
    );
    aggregateId = targetId(proposal.target, "work-item");
    if (positiveInteger(params.item_id, "params.item_id") !== aggregateId) {
      throw new ProposalExecutionError("params.item_id must match the proposal target");
    }
    if (!Array.isArray(proposal.evidence_refs) || proposal.evidence_refs.length === 0) {
      throw new ProposalExecutionError("item.done requires at least one immutable evidence_ref");
    }
    if (params.evidence_event_id != null) {
      positiveInteger(params.evidence_event_id, "params.evidence_event_id");
    }
    payload = { to_status: "done" };
    if (params.claim_id != null) {
      payload.claim_id = positiveInteger(params.claim_id, "params.claim_id");
    }
  } else {
    exactKeys(params, new Set(["sprint_id"]), `proposed_commands[${index}].params`);
    aggregateId = targetId(proposal.target, "sprint");
    if (positiveInteger(params.sprint_id, "params.sprint_id") !== aggregateId) {
      throw new ProposalExecutionError("params.sprint_id must match the proposal target");
    }
    payload = {};
  }

  return {
    index,
    request_event_id: commandRequestId(proposal.proposal_id, index),
    command_type: command.command_type,
    aggregate_id: aggregateId,
    basis_revision: basis.current_revision,
    payload
  };
}

function proposalPath(config, repoId, proposalId) {
  commandRequestId(proposalId, 0);
  const root = resolveArtifactRepoRoot(config.auditRoot, repoId);
  return path.join(root, "reconciliation-proposals", `${proposalId}.json`);
}

function executionPath(config, repoId, proposalId) {
  commandRequestId(proposalId, 0);
  const root = resolveArtifactRepoRoot(
    config.reconciliationStateRoot || config.reconciliationRoot || config.auditRoot,
    repoId
  );
  return path.join(root, "reconciliation-executions", `${proposalId}.json`);
}

function lifecyclePath(config, repoId, proposalId) {
  const root = resolveArtifactRepoRoot(
    config.reconciliationStateRoot || config.reconciliationRoot || config.auditRoot,
    repoId
  );
  return path.join(root, "reconciliation-lifecycles", `${proposalId}.json`);
}

async function readJson(filePath) {
  return JSON.parse(await fs.readFile(filePath, "utf8"));
}

async function writeJsonAtomic(filePath, value) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  const temporary = `${filePath}.${process.pid}.${randomUUID()}.tmp`;
  await fs.writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, "utf8");
  await fs.rename(temporary, filePath);
}

async function loadExecution(filePath) {
  try {
    return await readJson(filePath);
  } catch (error) {
    if (error.code === "ENOENT") {
      return null;
    }
    throw error;
  }
}

function initialExecution(proposal, commands, executedBy, now) {
  return {
    schema_version: "reconciliation-execution/v1",
    proposal_id: proposal.proposal_id,
    dedup_key: proposal.dedup_key,
    state: "pending",
    executed_by: executedBy,
    created_at: timestamp(now),
    updated_at: timestamp(now),
    attempts: 0,
    error: null,
    commands: commands.map((command) => ({
      ...command,
      state: "pending",
      attempts: 0,
      last_attempt_at: null,
      decision: null,
      error: null
    }))
  };
}

function assertExecutionMatches(execution, proposal, commands) {
  if (execution.proposal_id !== proposal.proposal_id || execution.dedup_key !== proposal.dedup_key) {
    throw new ProposalExecutionError("execution sidecar does not match the accepted proposal identity");
  }
  if (!Array.isArray(execution.commands) || execution.commands.length !== commands.length) {
    throw new ProposalExecutionError("accepted proposal commands changed after execution began");
  }
  commands.forEach((command, index) => {
    const existing = execution.commands[index];
    if (
      existing.request_event_id !== command.request_event_id ||
      existing.command_type !== command.command_type ||
      existing.aggregate_id !== command.aggregate_id ||
      existing.basis_revision !== command.basis_revision ||
      JSON.stringify(existing.payload) !== JSON.stringify(command.payload)
    ) {
      throw new ProposalExecutionError("accepted proposal commands changed after execution began");
    }
  });
}

function recomputeState(execution) {
  const states = execution.commands.map((command) => command.state);
  const accepted = states.filter((state) => state === "accepted").length;
  if (states.length > 0 && accepted === states.length) {
    return "succeeded";
  }
  if (states.includes("rejected")) {
    return accepted > 0 ? "partial" : "rejected";
  }
  if (accepted > 0) {
    return "partial";
  }
  if (states.includes("unavailable")) {
    return "unavailable";
  }
  return "pending";
}

function parseAuthorityPayload(text) {
  if (!text || !text.trim()) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export async function runSprintctlAuthorityCommand(command, { repoId, actor, config = getConfig() }) {
  const repoRoot = path.resolve(config.workspaceRoot, repoId);
  const workspaceRoot = path.resolve(config.workspaceRoot);
  if (repoRoot === workspaceRoot || !repoRoot.startsWith(`${workspaceRoot}${path.sep}`)) {
    throw new ProposalExecutionError("repository path escapes COCKPIT_WORKSPACE_ROOT");
  }
  const args = [
    "authority",
    "submit",
    "--type",
    command.command_type,
    "--aggregate-id",
    String(command.aggregate_id),
    "--payload",
    JSON.stringify(command.payload),
    "--basis-revision",
    command.basis_revision,
    "--event-id",
    command.request_event_id,
    "--actor",
    actor,
    "--json"
  ];
  const env = { ...process.env };
  // Proposal artifacts never carry secrets. Do not accidentally inherit a
  // claim proof into a browser-mediated command execution either.
  delete env.SPRINTCTL_AUTHORITY_CLAIM_TOKEN;
  delete env.SPRINTCTL_AUTHORITY_COORDINATE_CLAIM_TOKEN;
  delete env.SPRINTCTL_AUTHORITY_PROPOSED_CLAIM_TOKEN;
  try {
    const { stdout } = await execFileAsync(config.sprintctlBin, args, {
      cwd: repoRoot,
      env,
      encoding: "utf8",
      timeout: config.reconciliationExecutionTimeoutMs,
      maxBuffer: 1024 * 1024
    });
    return parseAuthorityPayload(stdout) || {
      status: "unavailable",
      reason_code: "invalid-authority-response",
      reason_detail: "sprintctl returned no JSON decision"
    };
  } catch (error) {
    const payload = parseAuthorityPayload(error.stdout);
    if (payload) {
      return payload;
    }
    return {
      status: "unavailable",
      reason_code: error.code === "ETIMEDOUT" ? "authority-timeout" : "authority-unavailable",
      reason_detail: error.message
    };
  }
}

function applyAuthorityResult(command, result) {
  if (
    ["accepted", "rejected"].includes(result.status) &&
    (
      result.request_event_id !== command.request_event_id ||
      typeof result.decision_event_id !== "string" ||
      !result.decision_event_id
    )
  ) {
    command.state = "unavailable";
    command.error = "authority terminal response was missing its correlated request or decision identity";
    return;
  }
  if (result.status === "accepted") {
    command.state = "accepted";
    command.decision = {
      request_event_id: result.request_event_id,
      decision_event_id: result.decision_event_id,
      decision_type: result.decision_type,
      decision_ingest_offset: result.decision_ingest_offset,
      outcome: "accepted",
      duplicate: Boolean(result.duplicate),
      effect: result.effect || {}
    };
    command.error = null;
    return;
  }
  if (result.status === "rejected") {
    command.state = "rejected";
    command.decision = {
      request_event_id: result.request_event_id,
      decision_event_id: result.decision_event_id,
      decision_type: result.decision_type,
      decision_ingest_offset: result.decision_ingest_offset,
      outcome: "rejected",
      reason_code: result.reason_code || null,
      reason_detail: result.reason_detail || null,
      duplicate: Boolean(result.duplicate),
      effect: result.effect || {}
    };
    command.error = null;
    return;
  }
  command.state = result.status === "pending-shadow" ? "pending" : "unavailable";
  command.decision = null;
  command.error = result.reason_detail || result.reason_code || "authority did not return a terminal decision";
}

export async function executeAcceptedProposal({
  repoId,
  proposalId,
  executedBy,
  config = getConfig(),
  runCommand = runSprintctlAuthorityCommand,
  now = () => new Date()
}) {
  const proposal = await readJson(proposalPath(config, repoId, proposalId));
  try {
    const lifecycle = await readJson(lifecyclePath(config, repoId, proposalId));
    if (
      lifecycle.schema_version !== "reconciliation-lifecycle/v1" ||
      lifecycle.proposal_id !== proposal.proposal_id ||
      lifecycle.dedup_key !== proposal.dedup_key
    ) {
      throw new ProposalExecutionError("proposal lifecycle sidecar does not match immutable proposal identity");
    }
    proposal.lifecycle = lifecycle.lifecycle;
  } catch (error) {
    if (error.code !== "ENOENT") {
      throw error;
    }
  }
  if (proposal?.lifecycle?.state !== "accepted") {
    throw new ProposalExecutionError("only accepted proposals can execute authority commands");
  }
  const outPath = executionPath(config, repoId, proposalId);
  let commands;
  try {
    commands = (proposal.proposed_commands || []).map((command, index) =>
      normalizeProposalCommand(proposal, command, index)
    );
    if (commands.length === 0) {
      throw new ProposalExecutionError("accepted proposal has no authority commands");
    }
  } catch (error) {
    const current = now();
    const failed = {
      schema_version: "reconciliation-execution/v1",
      proposal_id: proposal.proposal_id,
      dedup_key: proposal.dedup_key,
      state: "rejected",
      executed_by: executedBy,
      created_at: timestamp(current),
      updated_at: timestamp(current),
      attempts: 0,
      error: { code: "validation-failed", message: error.message },
      commands: []
    };
    await writeJsonAtomic(outPath, failed);
    return failed;
  }

  let execution = await loadExecution(outPath);
  if (execution) {
    assertExecutionMatches(execution, proposal, commands);
  } else {
    execution = initialExecution(proposal, commands, executedBy, now());
  }
  if (!config.reconciliationExecutionEnabled) {
    execution.state = "deferred";
    execution.updated_at = timestamp(now());
    execution.error = {
      code: "execution-disabled",
      message: "COCKPIT_RECONCILIATION_EXECUTION_ENABLED is not true"
    };
    await writeJsonAtomic(outPath, execution);
    return execution;
  }

  // A semantic rejection is terminal for the ordered proposal. Retrying may
  // resume unavailable work, but must never skip past a rejected command.
  if (execution.commands.some((command) => command.state === "rejected")) {
    execution.state = recomputeState(execution);
    execution.updated_at = timestamp(now());
    await writeJsonAtomic(outPath, execution);
    return execution;
  }

  execution.error = null;
  for (const command of execution.commands) {
    if (TERMINAL_COMMAND_STATES.has(command.state)) {
      continue;
    }
    command.attempts += 1;
    command.last_attempt_at = timestamp(now());
    command.state = "running";
    execution.attempts += 1;
    execution.state = recomputeState(execution);
    execution.updated_at = timestamp(now());
    await writeJsonAtomic(outPath, execution);

    let result;
    try {
      result = await runCommand(command, { repoId, actor: executedBy, config });
    } catch (error) {
      result = {
        status: "unavailable",
        reason_code: "authority-unavailable",
        reason_detail: error.message
      };
    }
    applyAuthorityResult(command, result || {});
    execution.state = recomputeState(execution);
    execution.updated_at = timestamp(now());
    await writeJsonAtomic(outPath, execution);
    if (!TERMINAL_COMMAND_STATES.has(command.state) || command.state === "rejected") {
      break;
    }
  }
  execution.state = recomputeState(execution);
  execution.updated_at = timestamp(now());
  await writeJsonAtomic(outPath, execution);
  return execution;
}
