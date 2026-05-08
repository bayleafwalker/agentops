import fs from "node:fs";
import path from "node:path";

export function resolveActionctlBin(env = process.env) {
  if (env.COCKPIT_ACTIONCTL_BIN) {
    return env.COCKPIT_ACTIONCTL_BIN;
  }
  if (env.HOME) {
    const userLocal = path.join(env.HOME, ".local", "bin", "actionctl");
    if (fs.existsSync(userLocal)) {
      return userLocal;
    }
  }
  return "actionctl";
}

export function getConfig() {
  return {
    sprintctlUrl: process.env.SPRINTCTL_URL || "",
    actionctlBin: resolveActionctlBin(),
    actionqCacheMs: Number(process.env.COCKPIT_ACTIONQ_CACHE_MS || 5000),
    actionqLimit: Number(process.env.COCKPIT_ACTIONQ_LIMIT || 500),
    auditRoot: process.env.COCKPIT_ARTIFACTS_ROOT || "/projects/dev",
    auditLookbackDays: Number(process.env.COCKPIT_AUDIT_LOOKBACK_DAYS || 3),
    auditCacheMs: Number(process.env.COCKPIT_AUDIT_CACHE_MS || 5000),
    dispatchManifestRoot:
      process.env.COCKPIT_DISPATCH_MANIFEST_ROOT || "/projects/dev/agentops/templates/dispatch/examples",
    dispatchManifestCacheMs: Number(process.env.COCKPIT_DISPATCH_MANIFEST_CACHE_MS || 5000),
    actionqServerUrl: process.env.COCKPIT_ACTIONQ_SERVER_URL || "",
    actionqDispatchContract: process.env.COCKPIT_ACTIONQ_DISPATCH_CONTRACT || "",
    cockpitOperatorId: process.env.COCKPIT_OPERATOR_ID || "operator:cockpit"
  };
}
