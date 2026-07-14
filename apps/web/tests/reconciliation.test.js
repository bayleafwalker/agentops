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
    evidence_refs: [],
    basis: { observed_revision: "event:1", current_revision: "event:1" },
    target: { kind: "work-item", ref: "wi:1108" },
    classification: "mark-item-advanced",
    proposed_commands: [{ command_type: "work.completed", params: { item_id: 1108 } }],
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

function withArtifactsRoot(rootDir, fn) {
  const previousRoot = process.env.COCKPIT_ARTIFACTS_ROOT;
  const previousCache = process.env.COCKPIT_RECONCILIATION_CACHE_MS;
  process.env.COCKPIT_ARTIFACTS_ROOT = rootDir;
  process.env.COCKPIT_RECONCILIATION_CACHE_MS = "0";
  return fn().finally(() => {
    if (previousRoot === undefined) {
      delete process.env.COCKPIT_ARTIFACTS_ROOT;
    } else {
      process.env.COCKPIT_ARTIFACTS_ROOT = previousRoot;
    }
    if (previousCache === undefined) {
      delete process.env.COCKPIT_RECONCILIATION_CACHE_MS;
    } else {
      process.env.COCKPIT_RECONCILIATION_CACHE_MS = previousCache;
    }
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
    assert.deepEqual(state.warnings, []);
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
        path.join(resolveMechanizationRoot(rootDir, "agentops"), "reconciliation-proposals", `${PROPOSAL_PENDING}.json`),
        "utf8"
      )
    );
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
    assert.deepEqual(result.proposed_commands, [{ command_type: "work.completed", params: { item_id: 1108 } }]);
  });
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
