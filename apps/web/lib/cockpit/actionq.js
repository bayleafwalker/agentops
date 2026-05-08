import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { getCached, setCached } from "./cache.js";
import { validateActionSessionsPayload } from "./contracts.js";
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
