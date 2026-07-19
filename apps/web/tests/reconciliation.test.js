import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {
  decideProposal,
  ProposalDecisionError,
  ProposalNotFoundError,
  readReconciliationState,
  resolveMechanizationRoot
} from "../lib/cockpit/reconciliation.js";
import {
  commandRequestId,
  executeAcceptedProposal,
  normalizeProposalCommand
} from "../lib/cockpit/reconciliation-executor.js";
import { createGetHandler } from "../app/cockpit/api/reconciliation/route.js";
import { createPostHandler } from "../app/cockpit/api/reconciliation/decide/route.js";

const CAPSULE_A = "0f1e2d3c-4b5a-4978-8b6c-1a2b3c4d5e6f";
const CAPSULE_B = "1a2b3c4d-5e6f-4788-9a0b-1c2d3e4f5061";
const PROPOSAL_PENDING = "3c4d5e6f-7081-4920-9a0b-3d4e5f607182";
const PROPOSAL_REJECTED = "4d5e6f70-8192-4a31-9b0c-4e5f60718293";

function capsule(capsuleId, endedAt, target = null) {
  return {
    schema_version: "session-capsule/v1",
    capsule_id: capsuleId,
    runtime_session_id: `sess-${capsuleId.slice(0, 4)}`,
    ended_at: endedAt,
    target,
    starting_watermark: { ingest_offset: 42, age_seconds: 30 }
  };
}

function proposal(proposalId, lifecycleState, createdAt, overrides = {}) {
  const lifecycle =
    lifecycleState === "pending"
      ? { state: "pending", decided_at: null, decided_by: null, rejection_reason: null, superseded_by: null }
      : {
          state: lifecycleState,
          decided_at: "2026-07-14T20:00:00Z",
          decided_by: "operator:reviewer",
          rejection_reason: lifecycleState === "rejected" ? "not actually done" : null,
          superseded_by: null
        };
  return {
    schema_version: "reconciliation-proposal/v1",
    proposal_id: proposalId,
    dedup_key: `agentops:wi:1108:${proposalId.slice(0, 4)}`,
    created_at: createdAt,
    source_capsules: [
      {
        runtime_session_id: "sess-a",
        capsule_ref: {
          kind: "artifact",
          source: `agentops:_artifacts/agentops/session-capsules/${CAPSULE_A}.json`,
          revision: "sha256:" + "0".repeat(64)
        }
      }
    ],
    evidence_refs: [
      {
        kind: "git-commit",
        source: "repo:agentops",
        revision: "a".repeat(40)
      }
    ],
    basis: { observed_revision: "event:1", current_revision: "event:1" },
    target: { kind: "work-item", ref: "wi:1108" },
    classification: "mark-item-advanced",
    proposed_commands: [
      { command_type: "item.done", params: { item_id: 1108, evidence_event_id: 853 } }
    ],
    confidence: { level: "medium", rationale: "test" },
    lifecycle,
    ...overrides
  };
}

async function makeFixture() {
  const rootDir = await fs.mkdtemp(path.join(os.tmpdir(), "cockpit-reconciliation-"));
  const repoRoot = resolveMechanizationRoot(rootDir, "agentops");
  await fs.mkdir(path.join(repoRoot, "session-capsules"), { recursive: true });
  await fs.mkdir(path.join(repoRoot, "reconciliation-proposals"), { recursive: true });
  await fs.mkdir(path.join(repoRoot, "session-scribe"), { recursive: true });

  await fs.writeFile(
    path.join(repoRoot, "session-capsules", `${CAPSULE_A}.json`),
    JSON.stringify(capsule(CAPSULE_A, "2026-07-14T18:00:00Z", { rank: "explicit", ref: "wi:1108" }))
  );
  await fs.writeFile(
    path.join(repoRoot, "session-capsules", `${CAPSULE_B}.json`),
    JSON.stringify(capsule(CAPSULE_B, "2026-07-14T19:00:00Z"))
  );
  await fs.writeFile(
    path.join(repoRoot, "session-scribe", "cursor.json"),
    JSON.stringify({
      schema_version: "session-scribe-cursor/v1",
      consumed_capsule_ids: [CAPSULE_A],
      last_advanced_at: "2026-07-14T19:30:00Z"
    })
  );
  await fs.writeFile(
    path.join(repoRoot, "reconciliation-proposals", `${PROPOSAL_PENDING}.json`),
    JSON.stringify(proposal(PROPOSAL_PENDING, "pending", "2026-07-14T19:30:00Z"))
  );
  await fs.writeFile(
    path.join(repoRoot, "reconciliation-proposals", `${PROPOSAL_REJECTED}.json`),
    JSON.stringify(
      proposal(PROPOSAL_REJECTED, "rejected", "2026-07-14T18:30:00Z", {
        classification: "incidental-no-change",
        target: null,
        proposed_commands: []
      })
    )
  );
  return rootDir;
}

function executorConfig(rootDir, enabled = true) {
  return {
    auditRoot: rootDir,
    reconciliationStateRoot: rootDir,
    reconciliationExecutionEnabled: enabled,
    reconciliationExecutionTimeoutMs: 1000,
    sprintctlBin: "sprintctl",
    workspaceRoot: rootDir
  };
}

function acceptedResult(command, overrides = {}) {
  return {
    request_event_id: command.request_event_id,
    decision_event_id: "5e6f7081-92a3-4b42-8c0d-5f60718293a4",
    decision_ingest_offset: 17,
    decision_type: "item.transitioned",
    status: "accepted",
    duplicate: false,
    effect: { item_id: command.aggregate_id, status: "done" },
    ...overrides
  };
}

async function acceptFixtureProposal(rootDir) {
  await withArtifactsRoot(rootDir, () =>
    decideProposal({
      repoId: "agentops",
      proposalId: PROPOSAL_PENDING,
      decision: "accepted",
      decidedBy: "operator:reviewer"
    })
  );
}

function withArtifactsRoot(rootDir, fn) {
  const previousRoot = process.env.COCKPIT_ARTIFACTS_ROOT;
  const previousReconciliationRoot = process.env.COCKPIT_RECONCILIATION_ROOT;
  const previousReconciliationStateRoot = process.env.COCKPIT_RECONCILIATION_STATE_ROOT;
  const previousCache = process.env.COCKPIT_RECONCILIATION_CACHE_MS;
  process.env.COCKPIT_ARTIFACTS_ROOT = rootDir;
  delete process.env.COCKPIT_RECONCILIATION_ROOT;
  delete process.env.COCKPIT_RECONCILIATION_STATE_ROOT;
  process.env.COCKPIT_RECONCILIATION_CACHE_MS = "0";
  return fn().finally(() => {
    if (previousRoot === undefined) {
      delete process.env.COCKPIT_ARTIFACTS_ROOT;
    } else {
      process.env.COCKPIT_ARTIFACTS_ROOT = previousRoot;
    }
    if (previousReconciliationRoot === undefined) {
      delete process.env.COCKPIT_RECONCILIATION_ROOT;
    } else {
      process.env.COCKPIT_RECONCILIATION_ROOT = previousReconciliationRoot;
    }
    if (previousReconciliationStateRoot === undefined) {
      delete process.env.COCKPIT_RECONCILIATION_STATE_ROOT;
    } else {
      process.env.COCKPIT_RECONCILIATION_STATE_ROOT = previousReconciliationStateRoot;
    }
    if (previousCache === undefined) {
      delete process.env.COCKPIT_RECONCILIATION_CACHE_MS;
    } else {
      process.env.COCKPIT_RECONCILIATION_CACHE_MS = previousCache;
    }
  });
}

function withReconciliationRoot(artifactsRoot, reconciliationRoot, fn) {
  const previousArtifactsRoot = process.env.COCKPIT_ARTIFACTS_ROOT;
  const previousReconciliationRoot = process.env.COCKPIT_RECONCILIATION_ROOT;
  const previousReconciliationStateRoot = process.env.COCKPIT_RECONCILIATION_STATE_ROOT;
  const previousCache = process.env.COCKPIT_RECONCILIATION_CACHE_MS;
  process.env.COCKPIT_ARTIFACTS_ROOT = artifactsRoot;
  delete process.env.COCKPIT_RECONCILIATION_ROOT;
  process.env.COCKPIT_RECONCILIATION_STATE_ROOT = reconciliationRoot;
  process.env.COCKPIT_RECONCILIATION_CACHE_MS = "0";
  return fn().finally(() => {
    if (previousArtifactsRoot === undefined) delete process.env.COCKPIT_ARTIFACTS_ROOT;
    else process.env.COCKPIT_ARTIFACTS_ROOT = previousArtifactsRoot;
    if (previousReconciliationRoot === undefined) delete process.env.COCKPIT_RECONCILIATION_ROOT;
    else process.env.COCKPIT_RECONCILIATION_ROOT = previousReconciliationRoot;
    if (previousReconciliationStateRoot === undefined) delete process.env.COCKPIT_RECONCILIATION_STATE_ROOT;
    else process.env.COCKPIT_RECONCILIATION_STATE_ROOT = previousReconciliationStateRoot;
    if (previousCache === undefined) delete process.env.COCKPIT_RECONCILIATION_CACHE_MS;
    else process.env.COCKPIT_RECONCILIATION_CACHE_MS = previousCache;
  });
}

test("readReconciliationState reports queue, lag, watermark, and dogfooding", async () => {
  const rootDir = await makeFixture();
  await withArtifactsRoot(rootDir, async () => {
    const state = await readReconciliationState({ repoId: "agentops" });
    assert.equal(state.repo_id, "agentops");
    assert.equal(state.source, "artifact:reconciliation/agentops");

    assert.equal(state.review_queue.length, 1);
    assert.equal(state.review_queue[0].proposal_id, PROPOSAL_PENDING);
    assert.equal(state.review_queue[0].classification, "mark-item-advanced");
    assert.deepEqual(state.review_queue[0].source_sessions, ["sess-a"]);
    assert.equal(state.review_queue[0].proposed_commands.length, 1);

    assert.equal(state.lag.total_capsules, 2);
    assert.equal(state.lag.reconciled_count, 1);
    assert.equal(state.lag.unreconciled_count, 1);
    assert.equal(state.lag.unreconciled[0].capsule_id, CAPSULE_B);
    assert.ok(state.lag.oldest_unreconciled_age_seconds > 0);
    assert.equal(state.lag.cursor_last_advanced_at, "2026-07-14T19:30:00Z");

    assert.equal(state.watermark.latest_capsule_id, CAPSULE_B);
    assert.deepEqual(state.watermark.starting_watermark, { ingest_offset: 42, age_seconds: 30 });

    assert.equal(state.dogfooding.proposals_total, 2);
    assert.equal(state.dogfooding.proposals_by_state.pending, 1);
    assert.equal(state.dogfooding.proposals_by_state.rejected, 1);
    assert.equal(state.dogfooding.proposals_by_classification["incidental-no-change"], 1);
    assert.equal(state.dogfooding.no_change_rate, 0.5);
    assert.equal(state.dogfooding.rejected_rate, 1);
    assert.equal(state.dogfooding.pending_review_count, 1);
    assert.equal(state.dogfooding.executions_total, 0);
    assert.equal(state.dogfooding.accepted_without_execution_count, 0);
    assert.deepEqual(state.executions, []);
    assert.deepEqual(state.warnings, []);
  });
});

test("resolveMechanizationRoot accepts a direct artifact root", () => {
  assert.equal(
    resolveMechanizationRoot("/projects/dev/_artifacts", "agentops"),
    "/projects/dev/_artifacts/agentops"
  );
});

test("reconciliation state is independently rooted from read-only artifacts", async () => {
  const artifactsRoot = await makeFixture();
  const reconciliationRoot = await fs.mkdtemp(path.join(os.tmpdir(), "cockpit-reconciliation-state-"));
  await withReconciliationRoot(artifactsRoot, reconciliationRoot, async () => {
    const result = await decideProposal({
      repoId: "agentops",
      proposalId: PROPOSAL_PENDING,
      decision: "rejected",
      decidedBy: "operator:reviewer",
      rejectionReason: "separate durable state"
    });
    assert.equal(result.lifecycle.state, "rejected");
    const state = await readReconciliationState({ repoId: "agentops" });
    assert.equal(state.dogfooding.proposals_by_state.rejected, 2);
    const original = JSON.parse(await fs.readFile(
      path.join(resolveMechanizationRoot(artifactsRoot, "agentops"), "reconciliation-proposals", `${PROPOSAL_PENDING}.json`),
      "utf8"
    ));
    assert.equal(original.lifecycle.state, "pending");
    const sidecar = JSON.parse(await fs.readFile(
      path.join(resolveMechanizationRoot(reconciliationRoot, "agentops"), "reconciliation-lifecycles", `${PROPOSAL_PENDING}.json`),
      "utf8"
    ));
    assert.equal(sidecar.lifecycle.state, "rejected");
  });
});

test("readReconciliationState handles a repo with no artifacts", async () => {
  const rootDir = await fs.mkdtemp(path.join(os.tmpdir(), "cockpit-reconciliation-empty-"));
  await withArtifactsRoot(rootDir, async () => {
    const state = await readReconciliationState({ repoId: "agentops" });
    assert.equal(state.lag.total_capsules, 0);
    assert.equal(state.lag.unreconciled_count, 0);
    assert.equal(state.lag.oldest_unreconciled_age_seconds, null);
    assert.equal(state.watermark, null);
    assert.equal(state.review_queue.length, 0);
    assert.equal(state.dogfooding.proposals_total, 0);
  });
});

test("readReconciliationState surfaces unparseable artifacts as warnings", async () => {
  const rootDir = await makeFixture();
  await fs.writeFile(
    path.join(resolveMechanizationRoot(rootDir, "agentops"), "reconciliation-proposals", "broken.json"),
    "{not json"
  );
  await withArtifactsRoot(rootDir, async () => {
    const state = await readReconciliationState({ repoId: "agentops" });
    assert.equal(state.warnings.length, 1);
    assert.match(state.warnings[0].file, /broken\.json$/);
    assert.equal(state.review_queue.length, 1);
  });
});

test("decideProposal rejects a pending proposal durably", async () => {
  const rootDir = await makeFixture();
  await withArtifactsRoot(rootDir, async () => {
    const result = await decideProposal({
      repoId: "agentops",
      proposalId: PROPOSAL_PENDING,
      decision: "rejected",
      decidedBy: "operator:reviewer",
      rejectionReason: "diff does not match done criteria"
    });
    assert.equal(result.lifecycle.state, "rejected");
    assert.equal(result.lifecycle.rejection_reason, "diff does not match done criteria");
    const written = JSON.parse(
      await fs.readFile(
        path.join(resolveMechanizationRoot(rootDir, "agentops"), "reconciliation-lifecycles", `${PROPOSAL_PENDING}.json`),
        "utf8"
      )
    );
    assert.equal(written.schema_version, "reconciliation-lifecycle/v1");
    assert.equal(written.lifecycle.state, "rejected");
    assert.equal(written.lifecycle.decided_by, "operator:reviewer");
    assert.ok(written.lifecycle.decided_at);
  });
});

test("decideProposal accepts and returns proposed commands without executing them", async () => {
  const rootDir = await makeFixture();
  await withArtifactsRoot(rootDir, async () => {
    const result = await decideProposal({
      repoId: "agentops",
      proposalId: PROPOSAL_PENDING,
      decision: "accepted",
      decidedBy: "operator:reviewer"
    });
    assert.equal(result.lifecycle.state, "accepted");
    assert.deepEqual(result.proposed_commands, [
      { command_type: "item.done", params: { item_id: 1108, evidence_event_id: 853 } }
    ]);
  });
});

test("accepted proposal decisions are idempotent so execution can resume", async () => {
  const rootDir = await makeFixture();
  await withArtifactsRoot(rootDir, async () => {
    const first = await decideProposal({
      repoId: "agentops",
      proposalId: PROPOSAL_PENDING,
      decision: "accepted",
      decidedBy: "operator:reviewer"
    });
    const retried = await decideProposal({
      repoId: "agentops",
      proposalId: PROPOSAL_PENDING,
      decision: "accepted",
      decidedBy: "operator:reviewer"
    });
    assert.deepEqual(retried.lifecycle, first.lifecycle);
  });
});

test("proposal command normalization enforces the authority allowlist and target", () => {
  const value = proposal(PROPOSAL_PENDING, "accepted", "2026-07-14T19:30:00Z");
  const normalized = normalizeProposalCommand(value, value.proposed_commands[0], 0);
  assert.equal(normalized.command_type, "item.done");
  assert.equal(normalized.aggregate_id, 1108);
  assert.equal(normalized.basis_revision, "event:1");
  assert.deepEqual(normalized.payload, { to_status: "done" });
  assert.equal(normalized.request_event_id, commandRequestId(PROPOSAL_PENDING, 0));
  assert.throws(
    () => normalizeProposalCommand(
      value,
      { command_type: "work.completed", params: { item_id: 1108 } },
      0
    ),
    /not allowlisted/
  );
});

test("accepted authority decisions are correlated and persisted", async () => {
  const rootDir = await makeFixture();
  await acceptFixtureProposal(rootDir);
  const calls = [];
  const execution = await executeAcceptedProposal({
    repoId: "agentops",
    proposalId: PROPOSAL_PENDING,
    executedBy: "operator:reviewer",
    config: executorConfig(rootDir),
    runCommand: async (command) => {
      calls.push(command);
      return acceptedResult(command);
    }
  });
  assert.equal(execution.state, "succeeded");
  assert.equal(execution.commands[0].state, "accepted");
  assert.equal(execution.commands[0].decision.request_event_id, calls[0].request_event_id);
  const written = JSON.parse(
    await fs.readFile(
      path.join(
        resolveMechanizationRoot(rootDir, "agentops"),
        "reconciliation-executions",
        `${PROPOSAL_PENDING}.json`
      ),
      "utf8"
    )
  );
  assert.equal(written.state, "succeeded");
  await withArtifactsRoot(rootDir, async () => {
    const state = await readReconciliationState({ repoId: "agentops" });
    assert.equal(state.executions.length, 1);
    assert.equal(state.executions[0].state, "succeeded");
    assert.equal(state.dogfooding.executions_by_state.succeeded, 1);
    assert.equal(state.dogfooding.authority_decisions_by_outcome.accepted, 1);
    assert.equal(state.dogfooding.accepted_without_execution_count, 0);
  });
});

test("accepted execution reads immutable proposals and writes only the separate state root", async () => {
  const artifactsRoot = await makeFixture();
  const stateRoot = await fs.mkdtemp(path.join(os.tmpdir(), "cockpit-execution-state-"));
  await withReconciliationRoot(artifactsRoot, stateRoot, async () => {
    await decideProposal({
      repoId: "agentops",
      proposalId: PROPOSAL_PENDING,
      decision: "accepted",
      decidedBy: "operator:reviewer"
    });
    const execution = await executeAcceptedProposal({
      repoId: "agentops",
      proposalId: PROPOSAL_PENDING,
      executedBy: "operator:reviewer",
      config: {
        auditRoot: artifactsRoot,
        reconciliationStateRoot: stateRoot,
        reconciliationExecutionEnabled: true,
        reconciliationExecutionTimeoutMs: 1000,
        sprintctlBin: "sprintctl",
        workspaceRoot: artifactsRoot
      },
      runCommand: async (command) => acceptedResult(command)
    });
    assert.equal(execution.state, "succeeded");
    const original = JSON.parse(await fs.readFile(
      path.join(resolveMechanizationRoot(artifactsRoot, "agentops"), "reconciliation-proposals", `${PROPOSAL_PENDING}.json`),
      "utf8"
    ));
    assert.equal(original.lifecycle.state, "pending");
    const executionSidecar = JSON.parse(await fs.readFile(
      path.join(resolveMechanizationRoot(stateRoot, "agentops"), "reconciliation-executions", `${PROPOSAL_PENDING}.json`),
      "utf8"
    ));
    assert.equal(executionSidecar.state, "succeeded");
  });
});

test("remote authority rejection is durable and terminal", async () => {
  const rootDir = await makeFixture();
  await acceptFixtureProposal(rootDir);
  let calls = 0;
  const runCommand = async (command) => {
    calls += 1;
    return acceptedResult(command, {
      status: "rejected",
      decision_type: "command.rejected",
      reason_code: "invalid-transition",
      reason_detail: "item is already done",
      effect: {}
    });
  };
  const first = await executeAcceptedProposal({
    repoId: "agentops",
    proposalId: PROPOSAL_PENDING,
    executedBy: "operator:reviewer",
    config: executorConfig(rootDir),
    runCommand
  });
  const retry = await executeAcceptedProposal({
    repoId: "agentops",
    proposalId: PROPOSAL_PENDING,
    executedBy: "operator:reviewer",
    config: executorConfig(rootDir),
    runCommand
  });
  assert.equal(first.state, "rejected");
  assert.equal(first.commands[0].decision.reason_code, "invalid-transition");
  assert.equal(retry.state, "rejected");
  assert.equal(calls, 1);
});

test("uncorrelated terminal authority responses remain unavailable", async () => {
  const rootDir = await makeFixture();
  await acceptFixtureProposal(rootDir);
  const execution = await executeAcceptedProposal({
    repoId: "agentops",
    proposalId: PROPOSAL_PENDING,
    executedBy: "operator:reviewer",
    config: executorConfig(rootDir),
    runCommand: async () => ({ status: "accepted", effect: { status: "done" } })
  });
  assert.equal(execution.state, "unavailable");
  assert.match(execution.commands[0].error, /correlated request or decision identity/);
});

test("stale proposal basis is rejected before authority submission", async () => {
  const rootDir = await makeFixture();
  const artifactPath = path.join(
    resolveMechanizationRoot(rootDir, "agentops"),
    "reconciliation-proposals",
    `${PROPOSAL_PENDING}.json`
  );
  const value = JSON.parse(await fs.readFile(artifactPath, "utf8"));
  value.basis.current_revision = "event:2";
  await fs.writeFile(artifactPath, JSON.stringify(value));
  await acceptFixtureProposal(rootDir);
  let called = false;
  const execution = await executeAcceptedProposal({
    repoId: "agentops",
    proposalId: PROPOSAL_PENDING,
    executedBy: "operator:reviewer",
    config: executorConfig(rootDir),
    runCommand: async () => {
      called = true;
      return {};
    }
  });
  assert.equal(execution.state, "rejected");
  assert.equal(execution.error.code, "validation-failed");
  assert.match(execution.error.message, /already stale/);
  assert.equal(called, false);
});

test("unavailable authority retries the same stable request identity", async () => {
  const rootDir = await makeFixture();
  await acceptFixtureProposal(rootDir);
  const requestIds = [];
  let attempt = 0;
  const runCommand = async (command) => {
    requestIds.push(command.request_event_id);
    attempt += 1;
    if (attempt === 1) {
      return {
        status: "unavailable",
        reason_code: "authority-unavailable",
        reason_detail: "connection refused"
      };
    }
    return acceptedResult(command, { duplicate: true });
  };
  const unavailable = await executeAcceptedProposal({
    repoId: "agentops",
    proposalId: PROPOSAL_PENDING,
    executedBy: "operator:reviewer",
    config: executorConfig(rootDir),
    runCommand
  });
  const recovered = await executeAcceptedProposal({
    repoId: "agentops",
    proposalId: PROPOSAL_PENDING,
    executedBy: "operator:reviewer",
    config: executorConfig(rootDir),
    runCommand
  });
  assert.equal(unavailable.state, "unavailable");
  assert.equal(recovered.state, "succeeded");
  assert.equal(recovered.commands[0].decision.duplicate, true);
  assert.deepEqual(requestIds, [requestIds[0], requestIds[0]]);
});

test("duplicate retry after success does not resubmit a terminal command", async () => {
  const rootDir = await makeFixture();
  await acceptFixtureProposal(rootDir);
  let calls = 0;
  const runCommand = async (command) => {
    calls += 1;
    return acceptedResult(command);
  };
  await executeAcceptedProposal({
    repoId: "agentops",
    proposalId: PROPOSAL_PENDING,
    executedBy: "operator:reviewer",
    config: executorConfig(rootDir),
    runCommand
  });
  const retry = await executeAcceptedProposal({
    repoId: "agentops",
    proposalId: PROPOSAL_PENDING,
    executedBy: "operator:reviewer",
    config: executorConfig(rootDir),
    runCommand
  });
  assert.equal(retry.state, "succeeded");
  assert.equal(calls, 1);
});

test("partial failure preserves earlier decisions and stops ordered execution", async () => {
  const rootDir = await makeFixture();
  const artifactPath = path.join(
    resolveMechanizationRoot(rootDir, "agentops"),
    "reconciliation-proposals",
    `${PROPOSAL_PENDING}.json`
  );
  const value = JSON.parse(await fs.readFile(artifactPath, "utf8"));
  value.proposed_commands = [
    { command_type: "item.transition", params: { item_id: 1108, to_status: "active" } },
    { command_type: "item.done", params: { item_id: 1108, evidence_event_id: 853 } }
  ];
  await fs.writeFile(artifactPath, JSON.stringify(value));
  await acceptFixtureProposal(rootDir);
  const execution = await executeAcceptedProposal({
    repoId: "agentops",
    proposalId: PROPOSAL_PENDING,
    executedBy: "operator:reviewer",
    config: executorConfig(rootDir),
    runCommand: async (command) => command.index === 0
      ? acceptedResult(command, { effect: { item_id: 1108, status: "active" } })
      : acceptedResult(command, {
          status: "rejected",
          decision_type: "command.rejected",
          reason_code: "stale-basis",
          reason_detail: "aggregate advanced",
          effect: { current_revision: "item:x@status:active" }
        })
  });
  assert.equal(execution.state, "partial");
  assert.deepEqual(execution.commands.map((command) => command.state), ["accepted", "rejected"]);
});

test("execution feature flag defers work without losing acceptance", async () => {
  const rootDir = await makeFixture();
  await acceptFixtureProposal(rootDir);
  let called = false;
  const execution = await executeAcceptedProposal({
    repoId: "agentops",
    proposalId: PROPOSAL_PENDING,
    executedBy: "operator:reviewer",
    config: executorConfig(rootDir, false),
    runCommand: async () => {
      called = true;
      return {};
    }
  });
  assert.equal(execution.state, "deferred");
  assert.equal(execution.error.code, "execution-disabled");
  assert.equal(called, false);
});

test("decideProposal refuses non-pending proposals and missing proposals", async () => {
  const rootDir = await makeFixture();
  await withArtifactsRoot(rootDir, async () => {
    await assert.rejects(
      decideProposal({
        repoId: "agentops",
        proposalId: PROPOSAL_REJECTED,
        decision: "accepted",
        decidedBy: "operator:reviewer"
      }),
      ProposalDecisionError
    );
    await assert.rejects(
      decideProposal({
        repoId: "agentops",
        proposalId: "00000000-0000-4000-8000-000000000000",
        decision: "accepted",
        decidedBy: "operator:reviewer"
      }),
      ProposalNotFoundError
    );
    await assert.rejects(
      decideProposal({
        repoId: "agentops",
        proposalId: "../escape",
        decision: "accepted",
        decidedBy: "operator:reviewer"
      }),
      ProposalDecisionError
    );
  });
});

test("reconciliation route returns expected shape and degrades cleanly", async () => {
  const GET = createGetHandler({
    readReconciliationState: async ({ repoId }) => ({
      repo_id: repoId,
      source: `artifact:reconciliation/${repoId}`,
      review_queue: [],
      lag: { total_capsules: 0, unreconciled_count: 0 },
      watermark: null,
      dogfooding: { proposals_total: 0 },
      warnings: []
    })
  });
  const payload = await (await GET(new Request("http://localhost/cockpit/api/reconciliation?repo_id=agentops"))).json();
  assert.equal(payload.repo_id, "agentops");
  assert.equal(payload.degraded, null);

  const failing = createGetHandler({
    readReconciliationState: async () => {
      throw new Error("boom");
    }
  });
  const degraded = await (await failing(new Request("http://localhost/cockpit/api/reconciliation?repo_id=agentops"))).json();
  assert.ok(degraded.degraded);
  assert.equal(degraded.review_queue.length, 0);
});

test("decide route validates input and forwards decisions", async () => {
  const calls = [];
  const POST = createPostHandler({
    decideProposal: async (args) => {
      calls.push(args);
      return { proposal_id: args.proposalId, lifecycle: { state: args.decision }, classification: "mark-item-advanced", proposed_commands: [] };
    },
    executeAcceptedProposal: async (args) => ({
      proposal_id: args.proposalId,
      state: "succeeded",
      commands: []
    }),
    requireConfiguredWriteAuth: () => null
  });

  const badDecision = await POST(
    new Request("http://localhost/cockpit/api/reconciliation/decide", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ repo_id: "agentops", proposal_id: "x", decision: "maybe" })
    })
  );
  assert.equal(badDecision.status, 400);

  const missingReason = await POST(
    new Request("http://localhost/cockpit/api/reconciliation/decide", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ repo_id: "agentops", proposal_id: "x", decision: "rejected" })
    })
  );
  assert.equal(missingReason.status, 400);

  const accepted = await POST(
    new Request("http://localhost/cockpit/api/reconciliation/decide", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ repo_id: "agentops", proposal_id: PROPOSAL_PENDING, decision: "accepted", decided_by: "operator:me" })
    })
  );
  const payload = await accepted.json();
  assert.equal(payload.lifecycle.state, "accepted");
  assert.equal(payload.execution.state, "succeeded");
  assert.equal(calls[0].decidedBy, "operator:me");
});

test("decide route is disabled without a configured write token", async () => {
  const previous = process.env.COCKPIT_WRITE_TOKEN;
  delete process.env.COCKPIT_WRITE_TOKEN;
  try {
    const POST = createPostHandler({ decideProposal: async () => ({}) });
    const response = await POST(
      new Request("http://localhost/cockpit/api/reconciliation/decide", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ repo_id: "agentops", proposal_id: "x", decision: "accepted" })
      })
    );
    assert.equal(response.status, 503);
  } finally {
    if (previous !== undefined) {
      process.env.COCKPIT_WRITE_TOKEN = previous;
    }
  }
});
