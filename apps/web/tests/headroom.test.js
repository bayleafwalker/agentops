import test from "node:test";
import assert from "node:assert/strict";
import { getModelHeadroom, normalizeClaudeHeadroom, normalizeCodexHeadroom, resetModelHeadroomCache } from "../lib/cockpit/headroom.js";

test("codex headroom keeps reset timestamps, credits, and review limits", () => {
  const headroom = normalizeCodexHeadroom({
    plan_type: "pro",
    model: "gpt-5.3-codex",
    reasoning_level: "medium",
    account_email: "dev@example.com",
    rate_limit: {
      primary_window: { used_percent: 42, limit_window_seconds: 18000, reset_at: "2026-05-13T12:00:00Z" },
      secondary_window: { used_percent: 7, limit_window_seconds: 604800, reset_at: "2026-05-18T00:00:00Z" }
    },
    credits: { has_credits: true, unlimited: false, balance: 12.5 },
    code_review_rate_limit: { used_percent: 9, reset_at: "2026-05-13T13:00:00Z" }
  }, "2026-05-13T10:00:00Z");

  assert.equal(headroom.plan_type, "pro");
  assert.equal(headroom.rate_limit.primary_window.reset_at, "2026-05-13T12:00:00Z");
  assert.equal(headroom.credits.balance, 12.5);
  assert.equal(headroom.code_review_rate_limit.used_percent, 9);
});

test("claude headroom preserves opus and non-opus weekly split", () => {
  const headroom = normalizeClaudeHeadroom({
    model: "sonnet",
    current_window: { used_percent: 22, remaining_seconds: 3600 },
    weekly_limit: {
      opus: { used_percent: 80, reset_at: "2026-05-18T00:00:00Z" },
      other: { used_percent: 35, reset_at: "2026-05-18T00:00:00Z" }
    }
  }, "2026-05-13T10:00:00Z");

  assert.equal(headroom.current_window.used_percent, 22);
  assert.equal(headroom.weekly_limit.opus.used_percent, 80);
  assert.equal(headroom.weekly_limit.other.used_percent, 35);
});

test("model headroom returns stale cached snapshot after a failed refresh", async () => {
  resetModelHeadroomCache();
  const config = {
    codexHeadroomCommand: "printf '%s' '{\"plan_type\":\"pro\",\"rate_limit\":{\"primary_window\":{\"used_percent\":10}}}'",
    claudeHeadroomCommand: "",
    headroomCommandTimeoutMs: 1000,
    headroomCacheMs: 0
  };
  const first = await getModelHeadroom({ force: true, config, now: new Date("2026-05-13T10:00:00Z") });
  assert.equal(first.stale, false);
  assert.equal(first.providers.codex.rate_limit.primary_window.used_percent, 10);

  const stale = await getModelHeadroom({
    force: true,
    config: { ...config, codexHeadroomCommand: "exit 2" },
    now: new Date("2026-05-13T10:05:00Z")
  });
  assert.equal(stale.stale, true);
  assert.equal(stale.providers.codex.rate_limit.primary_window.used_percent, 10);
  assert.equal(stale.last_refresh_error_at, "2026-05-13T10:05:00.000Z");
});
