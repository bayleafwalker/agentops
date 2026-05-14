import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { getConfig } from "./env.js";

const execFileAsync = promisify(execFile);

let cachedSnapshot = null;
let cachedAtMs = 0;

function numberOrNull(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function textOrNull(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function normalizeWindow(raw = {}) {
  return {
    used_percent: numberOrNull(raw.used_percent ?? raw.percent_used ?? raw.used),
    limit_window_seconds: numberOrNull(raw.limit_window_seconds ?? raw.window_seconds),
    reset_at: textOrNull(raw.reset_at),
    remaining_seconds: numberOrNull(raw.remaining_seconds ?? raw.time_remaining_seconds)
  };
}

function unavailableProvider(provider, message) {
  return {
    provider,
    available: false,
    degraded: message,
    refreshed_at: null
  };
}

export function normalizeCodexHeadroom(raw = {}, refreshedAt = new Date().toISOString()) {
  return {
    provider: "codex",
    available: true,
    degraded: null,
    refreshed_at: refreshedAt,
    plan_type: textOrNull(raw.plan_type),
    model: textOrNull(raw.model),
    reasoning_level: textOrNull(raw.reasoning_level ?? raw.reasoning),
    cwd: textOrNull(raw.cwd ?? raw.working_directory),
    account_email: textOrNull(raw.account_email ?? raw.email),
    rate_limit: {
      primary_window: normalizeWindow(raw.rate_limit?.primary_window ?? raw.primary_window),
      secondary_window: normalizeWindow(raw.rate_limit?.secondary_window ?? raw.secondary_window)
    },
    credits: {
      has_credits: Boolean(raw.credits?.has_credits ?? raw.has_credits ?? false),
      unlimited: Boolean(raw.credits?.unlimited ?? raw.unlimited ?? false),
      balance: numberOrNull(raw.credits?.balance ?? raw.credit_balance)
    },
    code_review_rate_limit: normalizeWindow(raw.code_review_rate_limit ?? raw.review_rate_limit)
  };
}

export function normalizeClaudeHeadroom(raw = {}, refreshedAt = new Date().toISOString()) {
  const weekly = raw.weekly_limit ?? raw.weekly ?? {};
  return {
    provider: "claude",
    available: true,
    degraded: null,
    refreshed_at: refreshedAt,
    model: textOrNull(raw.model),
    cost_usd: numberOrNull(raw.cost_usd),
    projected_cost_usd: numberOrNull(raw.projected_cost_usd),
    current_window: normalizeWindow(raw.current_window ?? raw.current_5h_session ?? raw.session),
    weekly_limit: {
      opus: normalizeWindow(weekly.opus ?? raw.opus_weekly),
      other: normalizeWindow(weekly.other ?? weekly.non_opus ?? raw.other_weekly)
    }
  };
}

async function runJsonCommand(command, timeoutMs) {
  if (!command) {
    return { configured: false, payload: null, error: "refresh command not configured" };
  }
  try {
    const { stdout } = await execFileAsync("/bin/sh", ["-lc", command], {
      timeout: timeoutMs,
      maxBuffer: 1024 * 1024
    });
    return { configured: true, payload: JSON.parse(stdout), error: null };
  } catch (error) {
    return { configured: true, payload: null, error: error.message };
  }
}

export async function refreshModelHeadroom({ config = getConfig(), now = new Date() } = {}) {
  const refreshedAt = now.toISOString();
  const [codex, claude] = await Promise.all([
    runJsonCommand(config.codexHeadroomCommand, config.headroomCommandTimeoutMs),
    runJsonCommand(config.claudeHeadroomCommand, config.headroomCommandTimeoutMs)
  ]);

  const providers = {
    codex: codex.payload
      ? normalizeCodexHeadroom(codex.payload, refreshedAt)
      : unavailableProvider("codex", codex.error),
    claude: claude.payload
      ? normalizeClaudeHeadroom(claude.payload, refreshedAt)
      : unavailableProvider("claude", claude.error)
  };
  const warnings = Object.values(providers)
    .filter((provider) => !provider.available)
    .map((provider) => `${provider.provider}: ${provider.degraded}`);

  const snapshot = {
    source: "model-headroom",
    refreshed_at: refreshedAt,
    stale: false,
    providers,
    warnings,
    degraded: warnings.length ? { source: "model-headroom", message: warnings.join("; ") } : null
  };

  cachedSnapshot = snapshot;
  cachedAtMs = now.getTime();
  return snapshot;
}

export async function getModelHeadroom({ force = false, config = getConfig(), now = new Date() } = {}) {
  const ageMs = now.getTime() - cachedAtMs;
  if (!force && cachedSnapshot && ageMs >= 0 && ageMs < config.headroomCacheMs) {
    return cachedSnapshot;
  }
  const previousSnapshot = cachedSnapshot;
  const snapshot = await refreshModelHeadroom({ config, now });
  if (snapshot.degraded && previousSnapshot && previousSnapshot.refreshed_at !== snapshot.refreshed_at) {
    const staleSnapshot = {
      ...previousSnapshot,
      stale: true,
      last_refresh_error_at: snapshot.refreshed_at,
      degraded: snapshot.degraded,
      warnings: snapshot.warnings
    };
    cachedSnapshot = staleSnapshot;
    cachedAtMs = now.getTime();
    return staleSnapshot;
  }
  return snapshot;
}

export function resetModelHeadroomCache() {
  cachedSnapshot = null;
  cachedAtMs = 0;
}
