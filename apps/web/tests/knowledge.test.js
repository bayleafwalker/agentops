import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {
  knowledgeContentDigest,
  readKnowledgeArtifact,
  resolveKnowledgeArtifactPath
} from "../lib/cockpit/knowledge.js";
import { createGetHandler } from "../app/cockpit/api/knowledge/route.js";

function record(overrides = {}) {
  const value = {
    schema_version: "knowledge-artifact/v1",
    repo_id: "agentops",
    entry_id: 42,
    stream: "durable",
    status: "published",
    title: "Read knowledge artifacts",
    body: "The cockpit reads only published kctl records.",
    content_digest: "",
    category: "reference",
    tags: ["cockpit"],
    source: {
      event_id: 781,
      event_ref: "sprintctl:event:781",
      sprint_id: 380,
      item_id: 1165,
      track: "cockpit-v1"
    },
    published_at: "2026-07-17T18:00:00Z",
    rendered_at: "2026-07-17T18:01:00Z",
    superseded_by: null,
    ...overrides
  };
  if (!overrides.content_digest) {
    value.content_digest = knowledgeContentDigest(value.title, value.body);
  }
  return value;
}

async function writeArtifact(root, repoId, records) {
  const artifactPath = resolveKnowledgeArtifactPath(root, repoId);
  await fs.mkdir(path.dirname(artifactPath), { recursive: true });
  await fs.writeFile(artifactPath, records.map((value) => JSON.stringify(value)).join("\n") + (records.length ? "\n" : ""), "utf8");
  return artifactPath;
}

async function withArtifactsRoot(root, fn) {
  const priorRoot = process.env.COCKPIT_ARTIFACTS_ROOT;
  const priorCache = process.env.COCKPIT_KNOWLEDGE_CACHE_MS;
  process.env.COCKPIT_ARTIFACTS_ROOT = root;
  process.env.COCKPIT_KNOWLEDGE_CACHE_MS = "0";
  try {
    return await fn();
  } finally {
    if (priorRoot === undefined) {
      delete process.env.COCKPIT_ARTIFACTS_ROOT;
    } else {
      process.env.COCKPIT_ARTIFACTS_ROOT = priorRoot;
    }
    if (priorCache === undefined) {
      delete process.env.COCKPIT_KNOWLEDGE_CACHE_MS;
    } else {
      process.env.COCKPIT_KNOWLEDGE_CACHE_MS = priorCache;
    }
  }
}

test("readKnowledgeArtifact returns published records with stream and provenance", async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "cockpit-knowledge-"));
  const coordination = record({
    entry_id: 43,
    stream: "coordination",
    title: "Claim handoff lesson",
    body: "Use explicit proof rotation.",
    category: "lesson",
    tags: ["operations"],
    source: { event_id: 782, event_ref: "sprintctl:event:782", sprint_id: 380, item_id: null, track: null }
  });
  await writeArtifact(root, "agentops", [record(), coordination]);

  await withArtifactsRoot(root, async () => {
    const payload = await readKnowledgeArtifact({ repoId: "agentops" });
    assert.equal(payload.source, "artifact:knowledge/agentops");
    assert.equal(payload.entries.length, 2);
    assert.equal(payload.entries[1].stream, "coordination");
    assert.equal(payload.entries[0].source.event_ref, "sprintctl:event:781");
    assert.equal(payload.warnings.length, 0);
    assert.ok(payload.updated_at);
  });
});

test("resolveKnowledgeArtifactPath accepts a direct artifact root", () => {
  assert.equal(
    resolveKnowledgeArtifactPath("/projects/dev/_artifacts", "agentops"),
    "/projects/dev/_artifacts/agentops/knowledge/knowledge-artifact-v1.ndjson"
  );
});

test("readKnowledgeArtifact degrades to an empty read when no artifact exists", async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "cockpit-knowledge-empty-"));
  await withArtifactsRoot(root, async () => {
    const payload = await readKnowledgeArtifact({ repoId: "agentops" });
    assert.deepEqual(payload.entries, []);
    assert.deepEqual(payload.warnings, []);
    assert.equal(payload.updated_at, null);
  });
});

test("readKnowledgeArtifact keeps valid records and reports corrupt lines", async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "cockpit-knowledge-corrupt-"));
  const badDigest = record({ entry_id: 43, content_digest: "sha256:" + "0".repeat(64) });
  const artifactPath = await writeArtifact(root, "agentops", [record(), badDigest]);
  await fs.appendFile(artifactPath, "{not json}\n", "utf8");

  await withArtifactsRoot(root, async () => {
    const payload = await readKnowledgeArtifact({ repoId: "agentops" });
    assert.equal(payload.entries.length, 1);
    assert.equal(payload.warnings.length, 2);
    assert.match(payload.warnings[0].message, /content_digest/);
    assert.equal(payload.warnings[1].line, 3);
    assert.ok(payload.warnings[1].message);
  });
});

test("knowledge route returns its data shape and degrades on reader failure", async () => {
  const GET = createGetHandler({
    readKnowledgeArtifact: async ({ repoId }) => ({
      repo_id: repoId,
      source: "artifact:knowledge/" + repoId,
      entries: [record()],
      warnings: [],
      artifact_path: "/tmp/knowledge-artifact-v1.ndjson",
      updated_at: "2026-07-17T18:01:00Z"
    })
  });
  const payload = await (await GET(new Request("http://localhost/cockpit/api/knowledge?repo_id=agentops"))).json();
  assert.equal(payload.entries[0].status, "published");
  assert.equal(payload.degraded, null);

  const failing = createGetHandler({
    readKnowledgeArtifact: async () => {
      throw new Error("missing mount");
    }
  });
  const degraded = await (await failing(new Request("http://localhost/cockpit/api/knowledge?repo_id=agentops"))).json();
  assert.deepEqual(degraded.entries, []);
  assert.equal(degraded.degraded.source, "artifact:knowledge/agentops");
});
