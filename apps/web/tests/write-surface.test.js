import test from "node:test";
import assert from "node:assert/strict";
import { getWriteAuthState, requireConfiguredWriteAuth, requireWriteAuth } from "../lib/cockpit/auth.js";
import { withWriteToken, WRITE_TOKEN_STORAGE_KEY } from "../lib/cockpit/write-token.js";
import { SprintNotFoundError, SprintTransitionError } from "../lib/cockpit/sprintctl.js";
import { createPostHandler as createActivateHandler } from "../app/cockpit/api/sprints/activate/route.js";
import { createPostHandler as createDispatchHandler } from "../app/cockpit/api/dispatch/route.js";
import { createPostHandler as createPauseHandler } from "../app/cockpit/api/dispatcher/pause/route.js";
import { createGetHandler as createMcpGetHandler, createPostHandler as createMcpHandler } from "../app/cockpit/api/mcp/route.js";

function jsonRequest(url, body, headers = {}) {
  return new Request(url, {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: JSON.stringify(body)
  });
}

function rpcRequest(body, headers = {}) {
  return jsonRequest("http://localhost/cockpit/api/mcp", body, headers);
}

const TOKEN_ENV = { COCKPIT_WRITE_TOKEN: "s3cret" };
const EMPTY_ENV = {};

test("write auth is not enforced when no token is configured", () => {
  assert.deepEqual(getWriteAuthState(EMPTY_ENV), { configured: false, token: "" });
  assert.equal(requireWriteAuth(new Request("http://x", { method: "POST" }), "pg://sprintctl", EMPTY_ENV), null);
});

test("write auth rejects missing or wrong token and accepts bearer and header forms", async () => {
  const denied = requireWriteAuth(jsonRequest("http://x", {}), "pg://sprintctl", TOKEN_ENV);
  assert.equal(denied.status, 401);
  const wrong = requireWriteAuth(jsonRequest("http://x", {}, { authorization: "Bearer nope" }), "pg://sprintctl", TOKEN_ENV);
  assert.equal(wrong.status, 401);
  assert.equal(requireWriteAuth(jsonRequest("http://x", {}, { authorization: "Bearer s3cret" }), "pg://sprintctl", TOKEN_ENV), null);
  assert.equal(requireWriteAuth(jsonRequest("http://x", {}, { "x-cockpit-write-token": "s3cret" }), "pg://sprintctl", TOKEN_ENV), null);
});

test("configured-only surfaces are disabled without a token", async () => {
  const disabled = requireConfiguredWriteAuth(jsonRequest("http://x", {}), "mcp://agent-cockpit", EMPTY_ENV);
  assert.equal(disabled.status, 503);
  assert.equal(requireConfiguredWriteAuth(jsonRequest("http://x", {}, { authorization: "Bearer s3cret" }), "mcp://agent-cockpit", TOKEN_ENV), null);
});

test("withWriteToken attaches the stored token header", () => {
  const storage = new Map([[WRITE_TOKEN_STORAGE_KEY, "tok"]]);
  storage.getItem = (key) => storage.get(key) ?? null;
  assert.deepEqual(withWriteToken({ "content-type": "application/json" }, storage), {
    "content-type": "application/json",
    "x-cockpit-write-token": "tok"
  });
  const empty = new Map();
  empty.getItem = () => null;
  assert.deepEqual(withWriteToken({}, empty), {});
});

test("activate route passes actor and returns sprint shape", async () => {
  let received = null;
  const POST = createActivateHandler({
    activateSprint: async (repoId, sprintId, opts) => {
      received = { repoId, sprintId, ...opts };
      return { id: sprintId, repo_id: repoId, status: "active", kind: "active_sprint", event_id: 7 };
    },
    requireWriteAuth: () => null
  });
  const response = await POST(jsonRequest("http://localhost/cockpit/api/sprints/activate", { repo_id: "alpha", sprint_id: 3, actor: "operator:test" }));
  const payload = await response.json();
  assert.equal(response.status, 200);
  assert.deepEqual(received, { repoId: "alpha", sprintId: 3, actor: "operator:test" });
  assert.equal(payload.sprint.event_id, 7);
});

test("activate route maps not-found to 404 and invalid transition to 409", async () => {
  const notFound = createActivateHandler({
    activateSprint: async () => { throw new SprintNotFoundError("Sprint 9 not found for repo alpha"); },
    requireWriteAuth: () => null
  });
  assert.equal((await notFound(jsonRequest("http://localhost/x", { repo_id: "alpha", sprint_id: 9 }))).status, 404);

  const conflict = createActivateHandler({
    activateSprint: async () => { throw new SprintTransitionError("cannot transition sprint closed -> active. Allowed: planned -> active"); },
    requireWriteAuth: () => null
  });
  const response = await conflict(jsonRequest("http://localhost/x", { repo_id: "alpha", sprint_id: 9 }));
  assert.equal(response.status, 409);
  assert.match((await response.json()).degraded.message, /planned -> active/);
});

test("write routes deny unauthenticated requests when a token is configured", async () => {
  const checkAuth = (request, source) => requireWriteAuth(request, source, TOKEN_ENV);
  const activate = createActivateHandler({ activateSprint: async () => ({}), requireWriteAuth: checkAuth });
  assert.equal((await activate(jsonRequest("http://localhost/x", { repo_id: "a", sprint_id: 1 }))).status, 401);

  const dispatch = createDispatchHandler({
    getDispatchGate: () => ({ enabled: true, method: "server", source: "actionq://dispatch" }),
    getDispatchOperator: () => "operator:test",
    dispatchViaActionctl: async () => ({}),
    forwardDispatchToActionqServer: async () => ({}),
    requireWriteAuth: checkAuth
  });
  assert.equal((await dispatch(jsonRequest("http://localhost/x", {}))).status, 401);

  const pause = createPauseHandler({ setDispatcherPause: async () => ({}), requireWriteAuth: checkAuth });
  assert.equal((await pause(jsonRequest("http://localhost/x", { paused: true }))).status, 401);
});

let mcpDispatched = null;

const mcpDeps = {
  listRepos: async () => [{ repo_id: "alpha" }],
  listSprints: async (repoId, mode) => [{ repo_id: repoId, mode }],
  listEvents: async (args) => ({ events: [args], next_cursor: null }),
  listClaims: async () => [],
  activateSprint: async (repoId, sprintId, opts) => ({ id: sprintId, repo_id: repoId, status: "active", ...opts }),
  getDispatchGate: () => ({ enabled: true, method: "server", source: "actionq://dispatch" }),
  getDispatchOperator: () => "operator:test",
  normalizeDispatchPayload: (payload, { requestedBy }) => ({ ...payload, requested_by: requestedBy }),
  dispatchViaActionctl: async () => ({}),
  forwardDispatchToActionqServer: async (payload) => {
    mcpDispatched = payload;
    return {
      action_id: 42,
      status: "pending",
      request_ref: "req:test",
      request_sha256: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    };
  },
  requireConfiguredWriteAuth: () => null
};

test("mcp endpoint handles initialize, tools/list, and notifications", async () => {
  const POST = createMcpHandler(mcpDeps);
  const init = await (await POST(rpcRequest({ jsonrpc: "2.0", id: 1, method: "initialize", params: {} }))).json();
  assert.equal(init.result.protocolVersion, "2025-06-18");
  assert.equal(init.result.serverInfo.name, "agent-cockpit");

  const list = await (await POST(rpcRequest({ jsonrpc: "2.0", id: 2, method: "tools/list" }))).json();
  assert.deepEqual(
    list.result.tools.map((tool) => tool.name),
    ["list_repos", "list_sprints", "list_events", "list_claims", "activate_sprint", "dispatch_action"]
  );

  const notification = await POST(rpcRequest({ jsonrpc: "2.0", method: "notifications/initialized" }));
  assert.equal(notification.status, 202);

  const unknown = await (await POST(rpcRequest({ jsonrpc: "2.0", id: 3, method: "resources/list" }))).json();
  assert.equal(unknown.error.code, -32601);
});

test("mcp tools/call routes reads and writes to lib functions", async () => {
  const POST = createMcpHandler(mcpDeps);
  const sprints = await (await POST(rpcRequest({
    jsonrpc: "2.0", id: 4, method: "tools/call",
    params: { name: "list_sprints", arguments: { repo_id: "alpha", mode: "backlog" } }
  }))).json();
  assert.deepEqual(JSON.parse(sprints.result.content[0].text), [{ repo_id: "alpha", mode: "backlog" }]);

  const activated = await (await POST(rpcRequest({
    jsonrpc: "2.0", id: 5, method: "tools/call",
    params: { name: "activate_sprint", arguments: { repo_id: "alpha", sprint_id: 3 } }
  }))).json();
  const sprint = JSON.parse(activated.result.content[0].text);
  assert.equal(sprint.actor, "mcp:agent-cockpit");
  assert.equal(sprint.status, "active");

  const dispatched = await (await POST(rpcRequest({
    jsonrpc: "2.0", id: 6, method: "tools/call",
    params: { name: "dispatch_action", arguments: { repo_id: "alpha", title: "t", prompt: "p" } }
  }))).json();
  const dispatchResult = JSON.parse(dispatched.result.content[0].text);
  assert.equal(dispatchResult.accepted, true);
  assert.equal(dispatchResult.action.action_id, 42);
  assert.equal(dispatchResult.action.request_ref, "req:test");
  assert.equal(mcpDispatched.requested_by, "operator:test");
});

test("mcp tool failures surface as isError results, not protocol errors", async () => {
  const POST = createMcpHandler({
    ...mcpDeps,
    activateSprint: async () => { throw new SprintTransitionError("cannot transition sprint closed -> active. Allowed: planned -> active"); }
  });
  const payload = await (await POST(rpcRequest({
    jsonrpc: "2.0", id: 7, method: "tools/call",
    params: { name: "activate_sprint", arguments: { repo_id: "alpha", sprint_id: 3 } }
  }))).json();
  assert.equal(payload.result.isError, true);
  assert.match(payload.result.content[0].text, /planned -> active/);

  const unknownTool = await (await POST(rpcRequest({
    jsonrpc: "2.0", id: 8, method: "tools/call",
    params: { name: "delete_everything", arguments: {} }
  }))).json();
  assert.equal(unknownTool.error.code, -32602);
});

test("mcp endpoint requires a configured token and rejects GET", async () => {
  const POST = createMcpHandler({
    ...mcpDeps,
    requireConfiguredWriteAuth: (request, source) => requireConfiguredWriteAuth(request, source, EMPTY_ENV)
  });
  assert.equal((await POST(rpcRequest({ jsonrpc: "2.0", id: 1, method: "initialize" }))).status, 503);

  const GET = createMcpGetHandler();
  assert.equal((await GET()).status, 405);
});
