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

export function summarizeCostLines(lines, { day = dayKey() } = {}) {
  const summary = blankSummary(day);
  const sessions = new Set();
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
    const model = String(row.model || "unknown");
    const cost = Number(row.cost_usd || 0);
    sessions.add(session);
    summary.by_session[session] = roundCurrency((summary.by_session[session] || 0) + cost);
    summary.by_model[model] = roundCurrency((summary.by_model[model] || 0) + cost);
    summary.total_cost_usd += cost;
  }
  summary.sessions = sessions.size;
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
