import test from "node:test";
import assert from "node:assert/strict";
import { validateActionSessionsPayload, validateDispatchesPayload } from "../lib/cockpit/contracts.js";
import { resolveActionctlBin } from "../lib/cockpit/env.js";

test("actionctl sessions payload validates documented v1 shape", () => {
  const payload = validateActionSessionsPayload([
    {
      session_id: "aqs:example",
      runtime_session_id: "aqs:example",
      status: "running",
      heartbeat_at: "2026-04-28T09:03:00Z",
      ttl_seconds: 120,
      claim: { claim_id: 81, work_item_id: 95, claim_type: "execute" }
    }
  ]);
  assert.equal(payload[0].claim.claim_id, 81);
});

test("actionctl sessions payload rejects missing heartbeat_at", () => {
  assert.throws(
    () => validateActionSessionsPayload([{ session_id: "aqs:example", status: "running", ttl_seconds: 120 }]),
    /heartbeat_at/
  );
});

test("resolveActionctlBin prefers explicit cockpit override", () => {
  assert.equal(
    resolveActionctlBin({
      COCKPIT_ACTIONCTL_BIN: "/custom/actionctl",
      HOME: "/home/dev"
    }),
    "/custom/actionctl"
  );
});

test("resolveActionctlBin falls back to user-local actionctl when present", () => {
  assert.equal(
    resolveActionctlBin({
      HOME: "/home/dev"
    }),
    "/home/dev/.local/bin/actionctl"
  );
});

test("actionq dispatches payload validates lifecycle row shape", () => {
  const payload = validateDispatchesPayload([
    {
      id: 12,
      action_type: "scope-iterate",
      kind: "investigate",
      output_expectation: "sprint-proposal",
      project: "agentops",
      target_ref: null,
      source_refs: [],
      status: "pending",
      priority: 100,
      created_at: "2026-05-13T08:00:00Z",
      claimed_at: null,
      completed_at: null,
      claimed_by: null,
      result_ref: null,
      failure_reason: null,
      parent_id: null,
      chain_depth: 0,
      dispatch_group_id: "dg:refine",
      session: null,
      audit_refs: []
    }
  ]);
  assert.equal(payload[0].dispatch_group_id, "dg:refine");
});
