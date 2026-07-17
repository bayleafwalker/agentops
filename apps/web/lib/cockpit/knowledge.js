import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { resolveArtifactRepoRoot } from "./artifacts.js";
import { getCached, setCached } from "./cache.js";
import { getConfig } from "./env.js";

const ARTIFACT_FILE = "knowledge-artifact-v1.ndjson";
const STREAMS = new Set(["durable", "coordination"]);
const CATEGORIES = new Set(["decision", "pattern", "lesson", "risk", "reference"]);
const RECORD_KEYS = [
  "body",
  "category",
  "content_digest",
  "entry_id",
  "published_at",
  "rendered_at",
  "repo_id",
  "schema_version",
  "source",
  "status",
  "stream",
  "superseded_by",
  "tags",
  "title"
];
const SOURCE_KEYS = ["event_id", "event_ref", "item_id", "sprint_id", "track"];
const UTC_TIMESTAMP_RE = /^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z$/;
const DIGEST_RE = /^sha256:[a-f0-9]{64}$/;

function sameKeys(actual, expected) {
  const sorted = [...actual].sort();
  return sorted.length === expected.length && sorted.every((key, index) => key === expected[index]);
}

function positiveInteger(value, field) {
  if (!Number.isInteger(value) || value < 1) {
    throw new Error(field + " must be a positive integer");
  }
  return value;
}

function nullablePositiveInteger(value, field) {
  if (value == null) {
    return null;
  }
  return positiveInteger(value, field);
}

function nullableText(value, field) {
  if (value == null) {
    return null;
  }
  if (typeof value !== "string" || !value) {
    throw new Error(field + " must be a non-empty string or null");
  }
  return value;
}

function timestamp(value, field) {
  if (typeof value !== "string" || !UTC_TIMESTAMP_RE.test(value)) {
    throw new Error(field + " must be an RFC 3339 UTC timestamp");
  }
  return value;
}

export function knowledgeContentDigest(title, body) {
  if (typeof title !== "string" || !title || typeof body !== "string" || !body) {
    throw new Error("title and body must be non-empty strings");
  }
  return "sha256:" + createHash("sha256")
    .update(JSON.stringify({ body, title }), "utf8")
    .digest("hex");
}

export function resolveKnowledgeArtifactPath(artifactsRoot, repoId) {
  return path.join(resolveArtifactRepoRoot(artifactsRoot, repoId), "knowledge", ARTIFACT_FILE);
}

export function validateKnowledgeArtifactRecord(value, expectedRepoId) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("record must be an object");
  }
  if (!sameKeys(Object.keys(value), RECORD_KEYS)) {
    throw new Error("record must match the knowledge-artifact/v1 field set");
  }
  if (value.schema_version !== "knowledge-artifact/v1") {
    throw new Error("schema_version must be knowledge-artifact/v1");
  }
  if (typeof value.repo_id !== "string" || !/^[A-Za-z0-9._-]+$/.test(value.repo_id)) {
    throw new Error("repo_id is invalid");
  }
  if (expectedRepoId && value.repo_id !== expectedRepoId) {
    throw new Error("record repo_id does not match the requested repository");
  }
  positiveInteger(value.entry_id, "entry_id");
  if (!STREAMS.has(value.stream)) {
    throw new Error("stream is invalid");
  }
  if (value.status !== "published") {
    throw new Error("status must be published");
  }
  if (typeof value.title !== "string" || !value.title || typeof value.body !== "string" || !value.body) {
    throw new Error("title and body must be non-empty strings");
  }
  if (!DIGEST_RE.test(value.content_digest) || value.content_digest !== knowledgeContentDigest(value.title, value.body)) {
    throw new Error("content_digest does not match published content");
  }
  if (!CATEGORIES.has(value.category)) {
    throw new Error("category is invalid");
  }
  if (!Array.isArray(value.tags) || value.tags.some((tag) => typeof tag !== "string" || !tag) || new Set(value.tags).size !== value.tags.length) {
    throw new Error("tags must be unique non-empty strings");
  }
  if (!value.source || typeof value.source !== "object" || Array.isArray(value.source) || !sameKeys(Object.keys(value.source), SOURCE_KEYS)) {
    throw new Error("source must match the knowledge-artifact/v1 field set");
  }
  const eventId = positiveInteger(value.source.event_id, "source.event_id");
  if (value.source.event_ref !== "sprintctl:event:" + eventId) {
    throw new Error("source.event_ref does not match source.event_id");
  }
  positiveInteger(value.source.sprint_id, "source.sprint_id");
  nullablePositiveInteger(value.source.item_id, "source.item_id");
  nullableText(value.source.track, "source.track");
  timestamp(value.published_at, "published_at");
  timestamp(value.rendered_at, "rendered_at");
  const supersededBy = nullablePositiveInteger(value.superseded_by, "superseded_by");
  if (supersededBy === value.entry_id) {
    throw new Error("superseded_by cannot equal entry_id");
  }
  return value;
}

async function loadArtifact(repoId, artifactPath, stats) {
  const config = getConfig();
  const cacheKey = ["knowledge", repoId, artifactPath, stats.mtimeMs, stats.size].join(":");
  const cached = getCached(cacheKey);
  if (cached) {
    return cached;
  }

  const content = await fs.readFile(artifactPath, "utf8");
  const entries = [];
  const warnings = [];
  const lines = content.split("\n");
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (!line.trim()) {
      if (index !== lines.length - 1) {
        warnings.push({ line: index + 1, message: "blank lines are not valid knowledge-artifact/v1 records" });
      }
      continue;
    }
    try {
      entries.push(validateKnowledgeArtifactRecord(JSON.parse(line), repoId));
    } catch (error) {
      warnings.push({ line: index + 1, message: error.message });
    }
  }
  return setCached(
    cacheKey,
    {
      repo_id: repoId,
      source: "artifact:knowledge/" + repoId,
      entries,
      warnings,
      artifact_path: artifactPath,
      updated_at: stats.mtime.toISOString()
    },
    config.knowledgeCacheMs
  );
}

export async function readKnowledgeArtifact({ repoId }) {
  const config = getConfig();
  const artifactPath = resolveKnowledgeArtifactPath(config.auditRoot, repoId);
  try {
    const stats = await fs.stat(artifactPath);
    return loadArtifact(repoId, artifactPath, stats);
  } catch (error) {
    if (error.code === "ENOENT") {
      return {
        repo_id: repoId,
        source: "artifact:knowledge/" + repoId,
        entries: [],
        warnings: [],
        artifact_path: artifactPath,
        updated_at: null
      };
    }
    throw error;
  }
}
