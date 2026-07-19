import { errorPayload, ok } from "../../../../../lib/cockpit/http.js";
import {
  decideProposal,
  ProposalDecisionError,
  ProposalNotFoundError
} from "../../../../../lib/cockpit/reconciliation.js";
import { requireConfiguredWriteAuth } from "../../../../../lib/cockpit/auth.js";
import { getConfig } from "../../../../../lib/cockpit/env.js";
import {
  executeAcceptedProposal,
  ProposalExecutionError
} from "../../../../../lib/cockpit/reconciliation-executor.js";

export const dynamic = "force-dynamic";

const SOURCE = "artifact:reconciliation";

// Rejections stop at the durable proposal lifecycle. Acceptances additionally
// invoke the bounded executor; its sidecar distinguishes the review decision
// from accepted/rejected/unavailable sprintctl authority outcomes.
export function createPostHandler(deps = { decideProposal, executeAcceptedProposal }) {
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
      let result = await deps.decideProposal({
        repoId: repo_id,
        proposalId: proposal_id,
        decision,
        decidedBy,
        rejectionReason: rejection_reason ?? null
      });
      if (decision === "accepted") {
        const execute = deps.executeAcceptedProposal ?? executeAcceptedProposal;
        const execution = await execute({
          repoId: repo_id,
          proposalId: proposal_id,
          executedBy: decidedBy
        });
        result = { ...result, execution };
      }
      return ok({ source: SOURCE, repo_id, ...result, degraded: null });
    } catch (error) {
      const status = error instanceof ProposalNotFoundError
        ? 404
        : error instanceof ProposalDecisionError || error instanceof ProposalExecutionError
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
