import { errorPayload, ok } from "../../../../../lib/cockpit/http.js";
import {
  decideProposal,
  ProposalDecisionError,
  ProposalNotFoundError
} from "../../../../../lib/cockpit/reconciliation.js";
import { requireConfiguredWriteAuth } from "../../../../../lib/cockpit/auth.js";
import { getConfig } from "../../../../../lib/cockpit/env.js";

export const dynamic = "force-dynamic";

const SOURCE = "artifact:reconciliation";

// Records the accept/reject decision on the proposal artifact only. It never
// executes the proposal's sprintctl commands — acceptance is carried out
// through normal sprintctl authority commands per write-surface-policy.md,
// and the response echoes proposed_commands so the operator knows what to run.
export function createPostHandler(deps = { decideProposal }) {
  const checkAuth = deps.requireConfiguredWriteAuth ?? requireConfiguredWriteAuth;
  return async function POST(request) {
    const denied = checkAuth(request, SOURCE);
    if (denied) {
      return denied;
    }
    let body;
    try {
      body = await request.json();
    } catch (error) {
      return Response.json(
        { degraded: errorPayload(`Invalid JSON: ${error.message}`, SOURCE) },
        { status: 400 }
      );
    }
    const { repo_id, proposal_id, decision, rejection_reason } = body || {};
    if (!repo_id || !proposal_id || !decision) {
      return Response.json(
        { degraded: errorPayload("repo_id, proposal_id, and decision are required", SOURCE) },
        { status: 400 }
      );
    }
    if (!["accepted", "rejected"].includes(decision)) {
      return Response.json(
        { degraded: errorPayload("decision must be accepted or rejected", SOURCE) },
        { status: 400 }
      );
    }
    if (decision === "rejected" && !rejection_reason) {
      return Response.json(
        { degraded: errorPayload("rejection_reason is required when rejecting", SOURCE) },
        { status: 400 }
      );
    }
    const decidedBy =
      typeof body.decided_by === "string" && body.decided_by.trim()
        ? body.decided_by.trim()
        : getConfig().cockpitOperatorId;
    try {
      const result = await deps.decideProposal({
        repoId: repo_id,
        proposalId: proposal_id,
        decision,
        decidedBy,
        rejectionReason: rejection_reason ?? null
      });
      return ok({ source: SOURCE, repo_id, ...result, degraded: null });
    } catch (error) {
      const status = error instanceof ProposalNotFoundError
        ? 404
        : error instanceof ProposalDecisionError
          ? 409
          : 500;
      return Response.json(
        { degraded: errorPayload(`Decision failed: ${error.message}`, SOURCE) },
        { status }
      );
    }
  };
}

export const POST = createPostHandler();
