import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { parseAuditShardName, readAuditFeed, resolveAuditDir } from "../lib/cockpit/audit.js";

test("audit shard parser accepts daily shard names", () => {
  assert.equal(parseAuditShardName("events-2026-04-29.ndjson"), "2026-04-29");
  assert.equal(parseAuditShardName("notes.txt"), null);
});

test("audit directory resolves under workspace artifact root", () => {
  assert.equal(resolveAuditDir("/projects/dev", "alpha"), "/projects/dev/_artifacts/alpha/audit");
});

test("audit directory accepts direct artifact root during deployment rollout", () => {
  assert.equal(resolveAuditDir("/projects/dev/_artifacts", "alpha"), "/projects/dev/_artifacts/alpha/audit");
});

test("artifact readers reject traversal-shaped repository IDs", () => {
  assert.throws(() => resolveAuditDir("/projects/dev/_artifacts", "../secrets"), /repo_id is invalid/);
});

test("audit reader parses valid events and reports invalid lines", async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "agentops-audit-"));
  process.env.COCKPIT_ARTIFACTS_ROOT = root;
  const dir = path.join(root, "_artifacts", "alpha", "audit");
  await fs.mkdir(dir, { recursive: true });
  await fs.writeFile(
    path.join(dir, "events-2026-04-29.ndjson"),
    [
      JSON.stringify({
        id: "ad:01ARZ3NDEKTSV4RRFFQ69G5FAV",
        ts: "2026-04-29T00:00:00Z",
        type: "decision",
        actor: "bayleaf",
        summary: "valid event",
        refs: [],
        source: "git-hook",
        metadata: {},
        created_at: "2026-04-29T00:00:00Z"
      }),
      "{\"broken\": true}"
    ].join("\n"),
    "utf8"
  );

  const payload = await readAuditFeed({ repoId: "alpha", days: 1, limit: 10 });
  assert.equal(payload.events.length, 1);
  assert.equal(payload.warnings.length, 1);
});
