import crypto from "node:crypto";
import { errorPayload } from "./http.js";

export function getWriteAuthState(env = process.env) {
  const token = (env.COCKPIT_WRITE_TOKEN || "").trim();
  return { configured: Boolean(token), token };
}

function presentedToken(request) {
  const authorization = request.headers.get("authorization") || "";
  if (/^bearer\s/i.test(authorization)) {
    return authorization.replace(/^bearer\s+/i, "").trim();
  }
  return (request.headers.get("x-cockpit-write-token") || "").trim();
}

function tokensMatch(presented, expected) {
  const a = Buffer.from(presented, "utf8");
  const b = Buffer.from(expected, "utf8");
  if (a.length !== b.length) {
    return false;
  }
  return crypto.timingSafeEqual(a, b);
}

// Returns null when the request may proceed, otherwise a 401 Response.
// Enforcement is opt-in: without COCKPIT_WRITE_TOKEN the write routes keep
// their pre-token behavior so existing deployments do not break on rollout.
export function requireWriteAuth(request, source, env = process.env) {
  const { configured, token } = getWriteAuthState(env);
  if (!configured) {
    return null;
  }
  const presented = presentedToken(request);
  if (presented && tokensMatch(presented, token)) {
    return null;
  }
  return Response.json(
    { degraded: errorPayload("Write token missing or invalid", source) },
    { status: 401 }
  );
}

// Stricter variant for surfaces that did not exist before token support:
// disabled outright until a token is configured.
export function requireConfiguredWriteAuth(request, source, env = process.env) {
  const { configured } = getWriteAuthState(env);
  if (!configured) {
    return Response.json(
      { degraded: errorPayload("Disabled: COCKPIT_WRITE_TOKEN is not configured", source) },
      { status: 503 }
    );
  }
  return requireWriteAuth(request, source, env);
}
