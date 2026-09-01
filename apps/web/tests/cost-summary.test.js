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
  assert.equal(summary.total_cost_usd, 0.75);
  assert.equal(summary.by_session["aqs:1"], 0.75);
  assert.equal(summary.by_model.sonnet, 0.75);
});

test("cost rows supersede rather than accumulate within a session", () => {
  const summary = summarizeCostLines([
    JSON.stringify({ ts: "2026-05-13T08:00:00Z", session: "a", model: "opus", cost_usd: 1, out: 10 }),
    JSON.stringify({ ts: "2026-05-13T09:00:00Z", session: "a", model: "opus", cost_usd: 4, out: 40 }),
    JSON.stringify({ ts: "2026-05-13T08:30:00Z", session: "b", model: "opus", cost_usd: 2, out: 20 })
  ], { day: "2026-05-13" });

  // Summing raw rows would give 7; the newest row per session gives 4 + 2.
  assert.equal(summary.total_cost_usd, 6);
  assert.equal(summary.by_session.a, 4);
  assert.equal(summary.by_model.opus, 6);
});

test("equal timestamps fall back to cost then output tokens", () => {
  const summary = summarizeCostLines([
    JSON.stringify({ ts: "2026-05-13T08:00:00Z", session: "a", model: "opus", cost_usd: 3, out: 30 }),
    JSON.stringify({ ts: "2026-05-13T08:00:00Z", session: "a", model: "opus", cost_usd: 1, out: 10 })
  ], { day: "2026-05-13" });

  assert.equal(summary.total_cost_usd, 3);
});
