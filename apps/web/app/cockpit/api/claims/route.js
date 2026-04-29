import { errorPayload, ok, parseIntParam, parseRepoId } from "../../../../lib/cockpit/http.js";
import { getActionqSessions } from "../../../../lib/cockpit/actionq.js";
import { listClaims } from "../../../../lib/cockpit/sprintctl.js";

function joinSessions(claims, sessions) {
  const byRuntimeSession = new Map();
  const byClaimId = new Map();
  for (const session of sessions) {
    if (session.runtime_session_id) {
      byRuntimeSession.set(session.runtime_session_id, session);
    }
    if (session.claim?.claim_id != null) {
      byClaimId.set(session.claim.claim_id, session);
    }
  }
  return claims.map((claim) => {
    let session = null;
    if (claim.runtime_session_id && byRuntimeSession.has(claim.runtime_session_id)) {
      session = byRuntimeSession.get(claim.runtime_session_id);
    } else if (byClaimId.has(claim.claim_id)) {
      session = byClaimId.get(claim.claim_id);
    }
    return {
      claim: { ...claim, source: "pg://sprintctl" },
      session: session ? { ...session, source: "actionq://sessions" } : null
    };
  });
}

export function createGetHandler(deps = { listClaims, getActionqSessions }) {
  return async function GET(request) {
    const repoId = parseRepoId(request);
    let sprintId = null;
    try {
      sprintId = parseIntParam(request, "sprint_id", null);
      const claims = await deps.listClaims(repoId, sprintId);
      try {
        const sessions = await deps.getActionqSessions();
        return ok({
          sources: ["pg://sprintctl", "actionq://sessions"],
          repo_id: repoId,
          sprint_id: sprintId,
          claims: joinSessions(claims, sessions),
          degraded: null
        });
      } catch (error) {
        return ok({
          sources: ["pg://sprintctl", "actionq://sessions"],
          repo_id: repoId,
          sprint_id: sprintId,
          claims: claims.map((claim) => ({
            claim: { ...claim, source: "pg://sprintctl" },
            session: null
          })),
          degraded: errorPayload("Session data unavailable — actionq://sessions unreachable", "actionq://sessions", {
            detail: error.message
          })
        });
      }
    } catch (error) {
      return ok({
        sources: ["pg://sprintctl", "actionq://sessions"],
        repo_id: repoId,
        sprint_id: sprintId,
        claims: [],
        degraded: errorPayload("Claim data unavailable — pg://sprintctl unreachable", "pg://sprintctl", {
          detail: error.message
        })
      });
    }
  };
}

export const GET = createGetHandler();
