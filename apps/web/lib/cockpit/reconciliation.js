import fs from "node:fs/promises";
import path from "node:path";
import { getCached, setCached } from "./cache.js";
import { getConfig } from "./env.js";

// Cockpit surfaces for the session-mechanization artifacts (item #1109):
// the review queue for reconciliation-proposal/v1, reconciliation-lag and
// watermark-age panels, and the dogfooding metrics named in
// docs/plans/agentops/session-mechanization-plan.md. Read side only — the
// artifacts are produced by the scribe/reconciler (items #1107/#1108), and
// decisions are recorded via decideProposal below, which never executes the
// proposed sprintctl commands (write-surface-policy.md).

const LIFECYCLE_STATES = ["pending", "accepted", "rejected", "superseded"];
const CLASSIFICATIONS = [
  "link-existing-item",
  "mark-item-advanced",
  "propose-completion",
  "flag-conflict-or-duplicate",
  "propose-new-item",
  "incidental-no-change"
];

export function resolveMechanizationRoot(artifactsRoot, repoId) {
  return path.join(artifactsRoot, "_artifacts", repoId);
}

async function readJsonDir(dirPath) {
  const values = [];
  const warnings = [];
  let entries;
  try {
    entries = await fs.readdir(dirPath, { withFileTypes: true });
  } catch (error) {
    if (error.code === "ENOENT") {
      return { values, warnings };
    }
    throw error;
  }
  for (const entry of entries) {
    if (!entry.isFile() || !entry.name.endsWith(".json")) {
      continue;
    }
    const fullPath = path.join(dirPath, entry.name);
    try {
      values.push({ path: fullPath, value: JSON.parse(await fs.readFile(fullPath, "utf8")) });
    } catch (error) {
      warnings.push({ file: fullPath, message: error.message });
    }
  }
  return { values, warnings };
}

async function readCursor(root) {
  try {
    return JSON.parse(await fs.readFile(path.join(root, "session-scribe", "cursor.json"), "utf8"));
  } catch (error) {
    if (error.code === "ENOENT") {
      return null;
    }
    throw error;
  }
}

function ageSeconds(iso, now) {
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) {
    return null;
  }
  return Math.max(0, (now - ts) / 1000);
}

function percentile(sortedValues, fraction) {
  if (sortedValues.length === 0) {
    return null;
  }
  const index = Math.min(sortedValues.length - 1, Math.ceil(fraction * sortedValues.length) - 1);
  return sortedValues[Math.max(0, index)];
}

function summarizeProposal(entry) {
  const proposal = entry.value;
  return {
    proposal_id: proposal.proposal_id,
    dedup_key: proposal.dedup_key,
    created_at: proposal.created_at,
    classification: proposal.classification,
    target: proposal.target ?? null,
    confidence: proposal.confidence ?? null,
    basis: proposal.basis ?? null,
    source_sessions: (proposal.source_capsules || []).map((capsule) => capsule.runtime_session_id),
    evidence_refs: proposal.evidence_refs || [],
    proposed_commands: proposal.proposed_commands || [],
    lifecycle: proposal.lifecycle,
    artifact_path: entry.path
  };
}

export async function readReconciliationState({ repoId, now = Date.now() }) {
  const config = getConfig();
  const root = resolveMechanizationRoot(config.auditRoot, repoId);
  const cacheKey = `reconciliation:${repoId}`;
  const cached = getCached(cacheKey);
  if (cached) {
    return cached;
  }

  const [capsules, proposals, cursor] = await Promise.all([
    readJsonDir(path.join(root, "session-capsules")),
    readJsonDir(path.join(root, "reconciliation-proposals")),
    readCursor(root)
  ]);
  const warnings = [...capsules.warnings, ...proposals.warnings];

  const consumed = new Set(cursor?.consumed_capsule_ids || []);
  const unreconciled = [];
  let latestCapsule = null;
  for (const { value: capsule } of capsules.values) {
    if (!capsule.capsule_id || !capsule.ended_at) {
      continue;
    }
    if (!latestCapsule || capsule.ended_at > latestCapsule.ended_at) {
      latestCapsule = capsule;
    }
    if (!consumed.has(capsule.capsule_id)) {
      unreconciled.push({
        capsule_id: capsule.capsule_id,
        runtime_session_id: capsule.runtime_session_id ?? null,
        target: capsule.target ?? null,
        ended_at: capsule.ended_at,
        age_seconds: ageSeconds(capsule.ended_at, now)
      });
    }
  }
  unreconciled.sort((a, b) => (b.age_seconds ?? 0) - (a.age_seconds ?? 0));
  const ages = unreconciled
    .map((entry) => entry.age_seconds)
    .filter((value) => value != null)
    .sort((a, b) => a - b);

  const byState = Object.fromEntries(LIFECYCLE_STATES.map((state) => [state, 0]));
  const byClassification = Object.fromEntries(CLASSIFICATIONS.map((name) => [name, 0]));
  const reviewQueue = [];
  for (const entry of proposals.values) {
    const proposal = entry.value;
    const state = proposal?.lifecycle?.state;
    if (!proposal?.proposal_id || !LIFECYCLE_STATES.includes(state)) {
      warnings.push({ file: entry.path, message: "proposal missing id or recognized lifecycle.state" });
      continue;
    }
    byState[state] += 1;
    if (CLASSIFICATIONS.includes(proposal.classification)) {
      byClassification[proposal.classification] += 1;
    }
    if (state === "pending") {
      reviewQueue.push(summarizeProposal(entry));
    }
  }
  reviewQueue.sort((a, b) => (a.created_at < b.created_at ? -1 : 1));

  const decidedCount = byState.accepted + byState.rejected + byState.superseded;
  const totalProposals = proposals.values.length;

  const state = {
    repo_id: repoId,
    source: `artifact:reconciliation/${repoId}`,
    review_queue: reviewQueue,
    lag: {
      total_capsules: capsules.values.length,
      reconciled_count: capsules.values.length - unreconciled.length,
      unreconciled_count: unreconciled.length,
      oldest_unreconciled_age_seconds: ages.length ? ages[ages.length - 1] : null,
      median_unreconciled_age_seconds: percentile(ages, 0.5),
      p95_unreconciled_age_seconds: percentile(ages, 0.95),
      unreconciled: unreconciled.slice(0, 50),
      cursor_last_advanced_at: cursor?.last_advanced_at ?? null
    },
    watermark: latestCapsule
      ? {
          latest_capsule_id: latestCapsule.capsule_id,
          latest_capsule_ended_at: latestCapsule.ended_at,
          starting_watermark: latestCapsule.starting_watermark ?? null,
          observed_age_seconds: ageSeconds(latestCapsule.ended_at, now)
        }
      : null,
    dogfooding: {
      proposals_total: totalProposals,
      proposals_by_state: byState,
      proposals_by_classification: byClassification,
      no_change_rate: totalProposals ? byClassification["incidental-no-change"] / totalProposals : null,
      accepted_rate: decidedCount ? byState.accepted / decidedCount : null,
      rejected_rate: decidedCount ? byState.rejected / decidedCount : null,
      pending_review_count: byState.pending
    },
    warnings
  };
  return setCached(cacheKey, state, config.reconciliationCacheMs);
}

export class ProposalNotFoundError extends Error {}
export class ProposalDecisionError extends Error {}

// Records an accept/reject decision on the proposal artifact's lifecycle.
// This is the durable decision record the scribe's dedup logic depends on
// (a rejected proposal is never rediscovered). It deliberately does NOT
// execute proposed_commands — acceptance runs through normal sprintctl
// authority commands per write-surface-policy.md.
export async function decideProposal({ repoId, proposalId, decision, decidedBy, rejectionReason = null }) {
  if (!["accepted", "rejected"].includes(decision)) {
    throw new ProposalDecisionError(`decision must be accepted or rejected, got ${decision}`);
  }
  if (decision === "rejected" && !rejectionReason) {
    throw new ProposalDecisionError("rejection_reason is required when rejecting a proposal");
  }
  const config = getConfig();
  const root = resolveMechanizationRoot(config.auditRoot, repoId);
  const artifactPath = path.join(root, "reconciliation-proposals", `${proposalId}.json`);
  let proposal;
  try {
    proposal = JSON.parse(await fs.readFile(artifactPath, "utf8"));
  } catch (error) {
    if (error.code === "ENOENT") {
      throw new ProposalNotFoundError(`Proposal ${proposalId} not found for repo ${repoId}`);
    }
    throw error;
  }
  const state = proposal?.lifecycle?.state;
  if (state !== "pending") {
    throw new ProposalDecisionError(`Proposal ${proposalId} is ${state}, only pending proposals can be decided`);
  }
  proposal.lifecycle = {
    state: decision,
    decided_at: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
    decided_by: decidedBy,
    rejection_reason: decision === "rejected" ? rejectionReason : null,
    superseded_by: null
  };
  const tmpPath = `${artifactPath}.tmp`;
  await fs.writeFile(tmpPath, `${JSON.stringify(proposal, null, 2)}\n`, "utf8");
  await fs.rename(tmpPath, artifactPath);
  return {
    proposal_id: proposal.proposal_id,
    lifecycle: proposal.lifecycle,
    classification: proposal.classification,
    // What acceptance is expected to run via sprintctl authority commands —
    // returned so the caller can act on them; never executed here.
    proposed_commands: proposal.proposed_commands || []
  };
}
