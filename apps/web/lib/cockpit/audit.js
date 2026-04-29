import fs from "node:fs/promises";
import path from "node:path";
import { getCached, setCached } from "./cache.js";
import { validateAuditEvent } from "./contracts.js";
import { getConfig } from "./env.js";
import { decodeCursor, encodeCursor } from "./http.js";

const SHARD_NAME_RE = /^events-(\d{4}-\d{2}-\d{2})\.ndjson$/;

export function parseAuditShardName(fileName) {
  const match = SHARD_NAME_RE.exec(fileName);
  if (!match) {
    return null;
  }
  return match[1];
}

async function loadShard(repoId, fullPath, fileName) {
  const stats = await fs.stat(fullPath);
  const cacheKey = `audit:${repoId}:${fileName}:${stats.mtimeMs}:${stats.size}`;
  const cached = getCached(cacheKey);
  if (cached) {
    return cached;
  }

  const content = await fs.readFile(fullPath, "utf8");
  const warnings = [];
  const events = [];
  let offset = 0;
  for (const line of content.split("\n")) {
    const byteOffset = offset;
    offset += Buffer.byteLength(line, "utf8") + 1;
    if (!line.trim()) {
      continue;
    }
    try {
      const event = validateAuditEvent(JSON.parse(line));
      events.push({
        ...event,
        shard_date: parseAuditShardName(fileName),
        shard_path: fullPath,
        shard_offset: byteOffset
      });
    } catch (error) {
      warnings.push({ file: fullPath, offset: byteOffset, message: error.message });
    }
  }
  return setCached(cacheKey, { events, warnings, stats }, getConfig().auditCacheMs);
}

export async function readAuditFeed({ repoId, days = 3, limit = 100, cursor = null }) {
  const config = getConfig();
  const lookback = Math.max(1, Math.min(days, config.auditLookbackDays));
  const auditDir = path.join(config.auditRoot, repoId, "audit");
  const decodedCursor = decodeCursor(cursor);
  const entries = await fs.readdir(auditDir, { withFileTypes: true });
  const shardFiles = entries
    .filter((entry) => entry.isFile() && parseAuditShardName(entry.name))
    .map((entry) => entry.name)
    .sort()
    .reverse()
    .slice(0, lookback);

  const loaded = await Promise.all(
    shardFiles.map((fileName) => loadShard(repoId, path.join(auditDir, fileName), fileName))
  );
  const warnings = loaded.flatMap((shard) => shard.warnings);
  const events = loaded
    .flatMap((shard) => shard.events)
    .sort((a, b) => {
      if (a.ts !== b.ts) {
        return a.ts < b.ts ? 1 : -1;
      }
      return a.id < b.id ? 1 : -1;
    });

  let startIndex = 0;
  if (decodedCursor?.index != null) {
    startIndex = decodedCursor.index;
  }
  const page = events.slice(startIndex, startIndex + limit);
  const nextIndex = startIndex + page.length;
  return {
    repo_id: repoId,
    source: `artifact:audit/${repoId}`,
    events: page,
    warnings,
    next_cursor: nextIndex < events.length ? encodeCursor({ index: nextIndex }) : null
  };
}
