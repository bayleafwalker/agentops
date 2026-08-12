import fs from "node:fs";
import path from "node:path";

export function resolveActionctlBin(env = process.env) {
  if (env.COCKPIT_ACTIONCTL_BIN) {
    return env.COCKPIT_ACTIONCTL_BIN;
  }
  if (env.HOME) {
    const userLocal = path.join(env.HOME, ".local", "bin", "actionctl");
    if (env.HOME === "/home/dev") {
      return userLocal;
    }
    if (fs.existsSync(userLocal)) {
      return userLocal;
    }
  }
  return "actionctl";
}

export function getConfig() {
  const dispatcherPauseFile =
    process.env.COCKPIT_DISPATCHER_PAUSE_FILE ||
    (process.env.HOME ? path.join(process.env.HOME, ".local", "state", "actionq-dispatcher", "PAUSED") : "~/.local/state/actionq-dispatcher/PAUSED");
  return {
    sprintctlRepoRoot:
      process.env.COCKPIT_SPRINTCTL_REPO_ROOT ||
      path.join(process.env.COCKPIT_WORKSPACE_ROOT || "/projects/dev", "agentops"),
    sprintctlTimeoutMs: Number(process.env.COCKPIT_SPRINTCTL_TIMEOUT_MS || 30000),
    actionctlBin: resolveActionctlBin(),
    actionqCacheMs: Number(process.env.COCKPIT_ACTIONQ_CACHE_MS || 5000),
    actionqLimit: Number(process.env.COCKPIT_ACTIONQ_LIMIT || 500),
    auditRoot: process.env.COCKPIT_ARTIFACTS_ROOT || "/projects/dev",
    auditLookbackDays: Number(process.env.COCKPIT_AUDIT_LOOKBACK_DAYS || 3),
    auditCacheMs: Number(process.env.COCKPIT_AUDIT_CACHE_MS || 5000),
    knowledgeCacheMs: Number(process.env.COCKPIT_KNOWLEDGE_CACHE_MS || 5000),
    reconciliationCacheMs: Number(process.env.COCKPIT_RECONCILIATION_CACHE_MS || 5000),
    // Proposals and capsules remain immutable input from auditRoot. Cockpit
    // lifecycle/execution sidecars use their own durable state root. The
    // legacy name is accepted during rollout for local compatibility.
    reconciliationStateRoot:
      process.env.COCKPIT_RECONCILIATION_STATE_ROOT ||
      process.env.COCKPIT_RECONCILIATION_ROOT ||
      process.env.COCKPIT_ARTIFACTS_ROOT ||
      "/projects/dev",
    reconciliationExecutionEnabled:
      process.env.COCKPIT_RECONCILIATION_EXECUTION_ENABLED === "true",
    reconciliationExecutionTimeoutMs: Number(
      process.env.COCKPIT_RECONCILIATION_EXECUTION_TIMEOUT_MS || 15000
    ),
    sprintctlBin: process.env.COCKPIT_SPRINTCTL_BIN || "sprintctl",
    workspaceRoot: process.env.COCKPIT_WORKSPACE_ROOT || "/projects/dev",
    dispatchManifestRoot:
      process.env.COCKPIT_DISPATCH_MANIFEST_ROOT || "/projects/dev/agentops/templates/dispatch/examples",
    dispatchManifestCacheMs: Number(process.env.COCKPIT_DISPATCH_MANIFEST_CACHE_MS || 5000),
    actionqServerUrl: process.env.COCKPIT_ACTIONQ_SERVER_URL || "",
    // Completion alerts consume the narrow served completion-log operation.
    // This is intentionally separate from the ActionQ dispatch endpoint and
    // never carries queue/claim/settlement authority.
    completionAlertActionqUrl:
      process.env.COCKPIT_ACTIONQ_COMPLETION_URL ||
      (process.env.COCKPIT_ACTIONQ_SERVER_URL
        ? `${process.env.COCKPIT_ACTIONQ_SERVER_URL.replace(/\/+$/, "")}/session-completions`
        : ""),
    completionAlertReadToken: process.env.COCKPIT_ACTIONQ_COMPLETION_READ_TOKEN || "",
    completionAlertStateRoot:
      process.env.COCKPIT_COMPLETION_ALERT_STATE_ROOT ||
      path.join(process.env.COCKPIT_ARTIFACTS_ROOT || "/projects/dev", "_agentops", "completion-alerts"),
    completionAlertPollIntervalMs: Number(process.env.COCKPIT_COMPLETION_ALERT_POLL_MS || 1000),
    completionAlertPollTimeoutMs: Number(process.env.COCKPIT_COMPLETION_ALERT_POLL_TIMEOUT_MS || 3000),
    completionAlertPageSize: Number(process.env.COCKPIT_COMPLETION_ALERT_PAGE_SIZE || 100),
    completionAlertMaxAttempts: Number(process.env.COCKPIT_COMPLETION_ALERT_MAX_ATTEMPTS || 8),
    completionAlertRetryBaseMs: Number(process.env.COCKPIT_COMPLETION_ALERT_RETRY_BASE_MS || 500),
    completionAlertRetryMaxMs: Number(process.env.COCKPIT_COMPLETION_ALERT_RETRY_MAX_MS || 30000),
    completionAlertPolicyJson: process.env.COCKPIT_COMPLETION_ALERT_POLICY_JSON || "",
    actionqDispatchContract: process.env.COCKPIT_ACTIONQ_DISPATCH_CONTRACT || "",
    cockpitOperatorId: process.env.COCKPIT_OPERATOR_ID || "operator:cockpit",
    costLogPath: process.env.COCKPIT_COST_LOG_PATH || "/projects/dev/.claude/session-costs.jsonl",
    costCacheMs: Number(process.env.COCKPIT_COST_CACHE_MS || 5000),
    codexHeadroomCommand: process.env.COCKPIT_CODEX_HEADROOM_COMMAND || "",
    claudeHeadroomCommand: process.env.COCKPIT_CLAUDE_HEADROOM_COMMAND || "",
    headroomCacheMs: Number(process.env.COCKPIT_HEADROOM_CACHE_MS || 60000),
    headroomCommandTimeoutMs: Number(process.env.COCKPIT_HEADROOM_COMMAND_TIMEOUT_MS || 10000),
    headroomFile: process.env.COCKPIT_CLAUDE_HEADROOM_FILE || "",
    headroomTriggerPath: process.env.COCKPIT_HEADROOM_TRIGGER_PATH || "",
    headroomTriggerTimeoutMs: Number(process.env.COCKPIT_HEADROOM_TRIGGER_TIMEOUT_MS || 15000),
    dispatcherPauseFile,
    dispatcherPauseFileExplicit: Boolean(process.env.COCKPIT_DISPATCHER_PAUSE_FILE)
  };
}
