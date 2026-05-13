import test from "node:test";
import assert from "node:assert/strict";
import { summarizeCostLines } from "../lib/cockpit/costs.js";

test("cost summary groups today's entries by runtime session when present", () => {
  const summary = summarizeCostLines([
    JSON.stringify({ ts: "2026-05-13T08:00:00Z", session: "claude:1", runtime_session_id: "aqs:1", model: "sonnet", cost_usd: 0.5 }),
    JSON.stringify({ ts: "2026-05-13T09:00:00Z", session: "claude:1", runtime_session_id: "aqs:1", model: "sonnet", cost_usd: 0.75 }),
    JSON.stringify({ ts: "2026-05-12T09:00:00Z", session: "old", model: "sonnet", cost_usd: 9 }),
    "not-json"
  ], { day: "2026-05-13" });

  assert.equal(summary.sessions, 1);
  assert.equal(summary.total_cost_usd, 1.25);
  assert.equal(summary.by_session["aqs:1"], 1.25);
  assert.equal(summary.by_model.sonnet, 1.25);
});
