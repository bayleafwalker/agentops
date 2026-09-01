import fs from "node:fs/promises";
import { getCached, setCached } from "./cache.js";
import { getConfig } from "./env.js";

function dayKey(date = new Date()) {
  return date.toISOString().slice(0, 10);
}

function blankSummary(day = dayKey()) {
  return {
    day,
    sessions: 0,
    total_cost_usd: 0,
    by_session: {},
    by_model: {}
  };
}

function roundCurrency(value) {
  return Math.round(Number(value || 0) * 100) / 100;
}

// A cost row reports the cumulative spend of its session so far, so rows for one
// session supersede each other rather than accumulating. Same reduction as
// templates/dispatch/hooks/cost-summary.sh: sort_by([.ts, .cost_usd, .out]) | last.
function supersedes(row, current) {
  if (!current) {
    return true;
  }
  const a = [String(row.ts || ""), Number(row.cost_usd || 0), Number(row.out || 0)];
  const b = [String(current.ts || ""), Number(current.cost_usd || 0), Number(current.out || 0)];
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] > b[i]) {
      return true;
    }
    if (a[i] < b[i]) {
      return false;
    }
  }
  return false;
}

export function summarizeCostLines(lines, { day = dayKey() } = {}) {
  const summary = blankSummary(day);
  const newestBySession = new Map();
  for (const line of lines) {
    if (!line.trim()) {
      continue;
    }
    let row;
    try {
      row = JSON.parse(line);
    } catch {
      continue;
    }
    if (!String(row.ts || "").startsWith(day)) {
      continue;
    }
    const session = String(row.runtime_session_id || row.session || "unknown");
    if (supersedes(row, newestBySession.get(session))) {
      newestBySession.set(session, row);
    }
  }
  for (const [session, row] of newestBySession) {
    const model = String(row.model || "unknown");
    const cost = Number(row.cost_usd || 0);
    summary.by_session[session] = roundCurrency(cost);
    summary.by_model[model] = roundCurrency((summary.by_model[model] || 0) + cost);
    summary.total_cost_usd += cost;
  }
  summary.sessions = newestBySession.size;
  summary.total_cost_usd = roundCurrency(summary.total_cost_usd);
  return summary;
}

export async function readCostSummary({ path = getConfig().costLogPath, day = dayKey() } = {}) {
  const config = getConfig();
  const cacheKey = `costs:${path}:${day}`;
  const cached = getCached(cacheKey);
  if (cached) {
    return cached;
  }
  let content = "";
  try {
    content = await fs.readFile(path, "utf8");
  } catch (error) {
    if (error.code === "ENOENT") {
      return setCached(cacheKey, blankSummary(day), config.costCacheMs);
    }
    throw error;
  }
  return setCached(cacheKey, summarizeCostLines(content.split(/\r?\n/), { day }), config.costCacheMs);
}
