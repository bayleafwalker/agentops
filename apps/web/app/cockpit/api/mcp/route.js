import { requireConfiguredWriteAuth } from "../../../../lib/cockpit/auth.js";
import {
  dispatchViaActionctl,
  forwardDispatchToActionqServer,
  getDispatchGate,
  getDispatchOperator,
  normalizeDispatchPayload
} from "../../../../lib/cockpit/dispatch.js";
import {
  activateSprint,
  listClaims,
  listEvents,
  listRepos,
  listSprints
} from "../../../../lib/cockpit/sprintctl.js";

export const dynamic = "force-dynamic";

const PROTOCOL_VERSION = "2025-06-18";
const SERVER_INFO = { name: "agent-cockpit", version: "0.1.0" };
const INSTRUCTIONS =
  "Read and operate on agentops sprint state. Reads come from sprintctl postgres. " +
  "activate_sprint is the only direct write (planned -> active, recorded in the event ledger). " +
  "All other mutations must go through dispatch_action, which queues work for an agent that runs " +
  "the sprintctl CLI with its evidence gates intact.";

const TOOLS = [
  {
    name: "list_repos",
    description: "List repos tracked in sprintctl with active sprint counts and source health.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false }
  },
  {
    name: "list_sprints",
    description: "List sprints with work items, summaries, and attention flags.",
    inputSchema: {
      type: "object",
      properties: {
        repo_id: { type: "string", description: "Repo id, or ALL (default)" },
        mode: { type: "string", enum: ["active", "backlog", "history"], description: "Sprint view mode (default active)" }
      },
      additionalProperties: false
    }
  },
  {
    name: "list_events",
    description: "List sprint events (decisions, claims, transitions) newest first.",
    inputSchema: {
      type: "object",
      properties: {
        repo_id: { type: "string", description: "Repo id, or ALL (default)" },
        sprint_id: { type: "integer", description: "Restrict to one sprint" },
        limit: { type: "integer", description: "Max events (default 50)" }
      },
      additionalProperties: false
    }
  },
  {
    name: "list_claims",
    description: "List active claims with actor, item, and heartbeat state.",
    inputSchema: {
      type: "object",
      properties: {
        repo_id: { type: "string", description: "Repo id, or ALL (default)" },
        sprint_id: { type: "integer", description: "Restrict to one sprint" }
      },
      additionalProperties: false
    }
  },
  {
    name: "activate_sprint",
    description:
      "Activate a planned sprint (planned -> active, kind becomes active_sprint). " +
      "Enforces sprintctl transition rules and records a sprint-activated event.",
    inputSchema: {
      type: "object",
      properties: {
        repo_id: { type: "string" },
        sprint_id: { type: "integer" },
        actor: { type: "string", description: "Provenance actor recorded on the event (default operator id)" }
      },
      required: ["repo_id", "sprint_id"],
      additionalProperties: false
    }
  },
  {
    name: "dispatch_action",
    description:
      "Queue an agent action via actionq. Use this for any sprint mutation that needs evidence " +
      "(tests, review) — the dispatched agent runs the sprintctl CLI inside a worktree.",
    inputSchema: {
      type: "object",
      properties: {
        contract_version: { const: "v2" },
        action_type: { const: "scope-iterate" },
        repo_id: { type: "string" },
        sprint_id: { type: ["integer", "null"] },
        work_item_id: { type: ["string", "null"] },
        title: { type: "string" },
        prompt: { type: "string" },
        output_expectation: { type: "string", enum: ["plan", "audit-event", "draft-work-items", "sprint-proposal", "implementation", "review"] },
        harness: { type: "string" },
        model: { type: ["string", "null"] },
        priority: { type: "string" },
        refs: { type: "array", items: { type: "string" } },
        dispatch_group_id: { type: ["string", "null"] }
      },
      required: ["contract_version", "action_type", "repo_id", "sprint_id", "work_item_id", "title", "prompt", "output_expectation", "harness", "model", "priority", "refs", "dispatch_group_id"],
      additionalProperties: false
    }
  }
];

function rpcResult(id, result) {
  return Response.json({ jsonrpc: "2.0", id, result });
}

function rpcError(id, code, message) {
  return Response.json({ jsonrpc: "2.0", id: id ?? null, error: { code, message } });
}

function toolText(value) {
  return { content: [{ type: "text", text: JSON.stringify(value, null, 2) }] };
}

function toolError(message) {
  return { content: [{ type: "text", text: message }], isError: true };
}

async function callTool(name, args, deps) {
  if (name === "list_repos") {
    return toolText(await deps.listRepos());
  }
  if (name === "list_sprints") {
    return toolText(await deps.listSprints(args.repo_id || "ALL", args.mode || "active"));
  }
  if (name === "list_events") {
    return toolText(
      await deps.listEvents({
        repoId: args.repo_id || "ALL",
        sprintId: args.sprint_id ?? null,
        limit: args.limit || 50,
        cursor: null
      })
    );
  }
  if (name === "list_claims") {
    return toolText(await deps.listClaims(args.repo_id || "ALL", args.sprint_id ?? null));
  }
  if (name === "activate_sprint") {
    if (!args.repo_id || !args.sprint_id) {
      return toolError("repo_id and sprint_id are required");
    }
    const actor =
      typeof args.actor === "string" && args.actor.trim() ? args.actor.trim() : "mcp:agent-cockpit";
    return toolText(await deps.activateSprint(args.repo_id, Number(args.sprint_id), { actor }));
  }
  if (name === "dispatch_action") {
    const gate = deps.getDispatchGate();
    if (!gate.enabled) {
      return toolError(`Dispatch disabled: ${gate.reason}`);
    }
    const payload = deps.normalizeDispatchPayload(args, {
      requestedBy: deps.getDispatchOperator()
    });
    const action = gate.method === "actionctl"
      ? await deps.dispatchViaActionctl(payload, gate.bin)
      : await deps.forwardDispatchToActionqServer(payload);
    return toolText({ accepted: true, source: gate.source, action });
  }
  return null;
}

export function createPostHandler(deps = {
  listRepos,
  listSprints,
  listEvents,
  listClaims,
  activateSprint,
  getDispatchGate,
  getDispatchOperator,
  normalizeDispatchPayload,
  dispatchViaActionctl,
  forwardDispatchToActionqServer
}) {
  const checkAuth = deps.requireConfiguredWriteAuth ?? requireConfiguredWriteAuth;
  return async function POST(request) {
    const denied = checkAuth(request, "mcp://agent-cockpit");
    if (denied) {
      return denied;
    }
    let message;
    try {
      message = await request.json();
    } catch {
      return rpcError(null, -32700, "Parse error");
    }
    if (Array.isArray(message) || typeof message !== "object" || message === null || message.jsonrpc !== "2.0") {
      return rpcError(null, -32600, "Invalid Request");
    }
    const { id, method, params } = message;
    if (typeof method !== "string") {
      return rpcError(id, -32600, "Invalid Request");
    }
    if (method.startsWith("notifications/")) {
      return new Response(null, { status: 202 });
    }
    if (method === "initialize") {
      return rpcResult(id, {
        protocolVersion: PROTOCOL_VERSION,
        capabilities: { tools: {} },
        serverInfo: SERVER_INFO,
        instructions: INSTRUCTIONS
      });
    }
    if (method === "ping") {
      return rpcResult(id, {});
    }
    if (method === "tools/list") {
      return rpcResult(id, { tools: TOOLS });
    }
    if (method === "tools/call") {
      const name = params?.name;
      const args = params?.arguments || {};
      if (!TOOLS.some((tool) => tool.name === name)) {
        return rpcError(id, -32602, `Unknown tool: ${name}`);
      }
      try {
        return rpcResult(id, await callTool(name, args, deps));
      } catch (error) {
        return rpcResult(id, toolError(`${name} failed: ${error.message}`));
      }
    }
    return rpcError(id, -32601, `Method not found: ${method}`);
  };
}

export function createGetHandler() {
  return async function GET() {
    return new Response(null, { status: 405, headers: { allow: "POST" } });
  };
}

export const POST = createPostHandler();
export const GET = createGetHandler();
