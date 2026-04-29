import test from "node:test";
import assert from "node:assert/strict";
import { createGetHandler as createReposHandler } from "../app/cockpit/api/repos/route.js";
import { createGetHandler as createClaimsHandler } from "../app/cockpit/api/claims/route.js";
import { createGetHandler as createAuditHandler } from "../app/cockpit/api/audit/route.js";

function request(url) {
  return new Request(url);
}

test("repos route degrades when pg is unavailable", async () => {
  const GET = createReposHandler({
    listRepos: async () => {
      throw new Error("connect ECONNREFUSED");
    }
  });
  const payload = await (await GET(request("http://localhost/cockpit/api/repos"))).json();
  assert.equal(payload.repos.length, 0);
  assert.match(payload.degraded.message, /pg:\/\/sprintctl unreachable/);
});

test("claims route degrades when actionq is unavailable but retains sprintctl rows", async () => {
  const GET = createClaimsHandler({
    listClaims: async () => [{ claim_id: 10, work_item_id: 20, actor: "codex" }],
    getActionqSessions: async () => {
      throw new Error("actionctl failed");
    }
  });
  const payload = await (await GET(request("http://localhost/cockpit/api/claims?repo_id=alpha"))).json();
  assert.equal(payload.claims.length, 1);
  assert.equal(payload.claims[0].session, null);
  assert.match(payload.degraded.message, /actionq:\/\/sessions unreachable/);
});

test("audit route degrades when artifacts are unavailable", async () => {
  const GET = createAuditHandler({
    readAuditFeed: async () => {
      throw new Error("ENOENT");
    }
  });
  const payload = await (await GET(request("http://localhost/cockpit/api/audit?repo_id=alpha"))).json();
  assert.equal(payload.events.length, 0);
  assert.match(payload.degraded.message, /artifact:audit\/alpha unreachable/);
});
