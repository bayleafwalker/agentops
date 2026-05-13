import { errorPayload, ok, parseIntParam, parseRepoId } from "../../../../lib/cockpit/http.js";
import { getActionqSessions } from "../../../../lib/cockpit/actionq.js";
import { listClaims } from "../../../../lib/cockpit/sprintctl.js";

function parseTime(value) {
  if (!value) {
    return null;
  }
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
}

export function annotateSessionLiveness(session, now = new Date()) {
  const heartbeatAt = session.last_heartbeat_at || session.heartbeat_at;
  const heartbeatMs = parseTime(heartbeatAt);
  const ttlSeconds = Number(session.ttl_seconds);
  if (heartbeatMs == null || !Number.isFinite(ttlSeconds)) {
    return {
      ...session,
      is_stale: false,
      deadline_at: session.deadline_at || null,
      ttl_remaining_seconds: null
    };
  }
  const deadlineMs = heartbeatMs + ttlSeconds * 1000;
  const remaining = Math.floor((deadlineMs - now.getTime()) / 1000);
  return {
    ...session,
    is_stale: remaining <= 0,
    deadline_at: session.deadline_at || new Date(deadlineMs).toISOString(),
    ttl_remaining_seconds: remaining
  };
}

export function joinSessions(claims, sessions, { now = new Date() } = {}) {
  const byRuntimeSession = new Map();
  const byClaimId = new Map();
  for (const session of sessions) {
    const annotated = annotateSessionLiveness(session, now);
    if (session.runtime_session_id) {
      byRuntimeSession.set(session.runtime_session_id, annotated);
    }
    if (session.claim?.claim_id != null) {
      byClaimId.set(session.claim.claim_id, annotated);
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
        const now = deps.now ? deps.now() : new Date();
        return ok({
          sources: ["pg://sprintctl", "actionq://sessions"],
          repo_id: repoId,
          sprint_id: sprintId,
          claims: joinSessions(claims, sessions, { now }),
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
