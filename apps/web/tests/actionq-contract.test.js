import test from "node:test";
import assert from "node:assert/strict";
import { validateActionSessionsPayload } from "../lib/cockpit/contracts.js";
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
