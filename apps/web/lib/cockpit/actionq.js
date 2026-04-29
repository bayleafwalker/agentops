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

export async function getActionqSessions() {
  const config = getConfig();
  const cacheKey = `actionq:sessions:${config.actionctlBin}:${config.actionqLimit}`;
  const cached = getCached(cacheKey);
  if (cached) {
    return cached;
  }
  const payload = await runActionctlSessions(config.actionctlBin, config.actionqLimit);
  const validated = validateActionSessionsPayload(payload);
  return setCached(cacheKey, validated, config.actionqCacheMs);
}
