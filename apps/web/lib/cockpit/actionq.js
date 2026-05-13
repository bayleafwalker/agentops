import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { getCached, setCached } from "./cache.js";
import { validateActionSessionsPayload, validateDispatchesPayload } from "./contracts.js";
import { getConfig } from "./env.js";

const execFileAsync = promisify(execFile);

export async function runActionctlSessions(command = "actionctl", limit = 500) {
  const { stdout } = await execFileAsync(command, ["sessions", "--active", "--limit", String(limit)], {
    encoding: "utf8",
    timeout: 10000,
    maxBuffer: 1024 * 1024 * 5
  });
  return JSON.parse(stdout || "[]");
}

async function fetchServerSessions(serverUrl, limit) {
  const url = `${serverUrl.replace(/\/+$/, "")}/sessions?active_only=true&limit=${limit}`;
  const response = await fetch(url, { cache: "no-store" });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.error || `actionq-server sessions failed with ${response.status}`);
  }
  return body;
}

async function fetchServerDispatches(serverUrl, { limit, repoId = "ALL", status = null } = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (repoId && repoId !== "ALL") {
    params.set("project", repoId);
  }
  if (status) {
    params.set("status", status);
  }
  const url = `${serverUrl.replace(/\/+$/, "")}/dispatches?${params}`;
  const response = await fetch(url, { cache: "no-store" });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.error || `actionq-server dispatches failed with ${response.status}`);
  }
  return body;
}

export async function getActionqSessions() {
  const config = getConfig();
  const useServer = Boolean(config.actionqServerUrl);
  const cacheKey = useServer
    ? `actionq:sessions:server:${config.actionqServerUrl}:${config.actionqLimit}`
    : `actionq:sessions:cli:${config.actionctlBin}:${config.actionqLimit}`;
  const cached = getCached(cacheKey);
  if (cached) {
    return cached;
  }
  const payload = useServer
    ? await fetchServerSessions(config.actionqServerUrl, config.actionqLimit)
    : await runActionctlSessions(config.actionctlBin, config.actionqLimit);
  const validated = validateActionSessionsPayload(payload);
  return setCached(cacheKey, validated, config.actionqCacheMs);
}

export async function getActionqDispatches({ repoId = "ALL", status = null, limit = null } = {}) {
  const config = getConfig();
  if (!config.actionqServerUrl) {
    throw new Error("COCKPIT_ACTIONQ_SERVER_URL is required for dispatch lifecycle rows");
  }
  const rowLimit = limit || config.actionqLimit;
  const cacheKey = `actionq:dispatches:${config.actionqServerUrl}:${repoId}:${status || "all"}:${rowLimit}`;
  const cached = getCached(cacheKey);
  if (cached) {
    return cached;
  }
  const payload = await fetchServerDispatches(config.actionqServerUrl, {
    repoId,
    status,
    limit: rowLimit
  });
  const validated = validateDispatchesPayload(payload);
  return setCached(cacheKey, validated, config.actionqCacheMs);
}
