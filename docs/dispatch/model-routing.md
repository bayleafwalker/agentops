# Model Routing

`templates/dispatch/model-routing.json` is the machine-readable source of truth for dispatch model aliases. Repositories may use provider-qualified model strings in runtime configuration, but those values must resolve to an alias in this policy.

## Alias Policy

| Alias | Anthropic model | Codex model | Fallback / status |
|---|---|---|---|
| `frontier-default` | `claude-fable-5` | - | Fall back to `claude-opus-4-8` when Fable is unavailable to the API key or OpenCode provider. |
| `frontier-plan` | `claude-opus-4-8` | `gpt-5.6-sol` | Verified: GPT-5.6 GA 2026-07-09; ID confirmed via OpenAI docs. |
| `review-synthesis` | `claude-sonnet-5` | `gpt-5.6-terra` | Verified: GPT-5.6 GA 2026-07-09; ID confirmed via OpenAI docs. |
| `release-ops` | `claude-sonnet-5` | - | Verified Anthropic routing. |
| `fast-build` | `claude-haiku-4-5-20251001` | `gpt-5.6-luna` | Verified: GPT-5.6 GA 2026-07-09; ID confirmed via OpenAI docs. |

The `verified` field belongs to the concrete provider ID, not the alias. The gpt-5.6 tier IDs (`-sol`/`-terra`/`-luna`) were confirmed against OpenAI's GA announcement and Codex model docs on 2026-07-18; recent Codex CLI releases ship them in the built-in catalog, but tier access depends on the authenticated plan (free/Go accounts get Terra only) and older CLI builds (e.g. 0.144.x) may predate the catalog entries. An unverified ID must not become a required default until its provider CLI or official documentation confirms availability.

## Resolution

Dispatch routing resolves harness, model, and optional reasoning in this order:

1. Explicit action payload values.
2. Project defaults.
3. Action-class defaults.
4. A single configured harness fallback.

`frontier-default` is deliberately not a blanket hard-coded value: API-key and OpenCode surfaces that cannot access `claude-fable-5` use `claude-opus-4-8` instead.

## Reasoning Controls

`actionq-dispatcher` supports an optional reasoning value at the action, project, and harness levels using the same precedence as model resolution. The installed Claude CLI documents `--effort <level>`, so Claude-backed dispatches pass that value through. The Codex CLI documents generic `-c key=value` overrides, but `model_reasoning_effort` was not verified in the available reference; Codex reasoning is intentionally not emitted yet. OpenCode reasoning syntax was not available for verification and is also ignored.

## Refresh Procedure

1. Update `model-routing.json` only after verifying concrete IDs through a provider CLI or official provider documentation.
2. Inventory live configuration, examples, deployment manifests, and guidance with `rg`.
3. Update each live value to the matching alias policy and retain an explicit fallback where provider access differs.
4. Re-scan for retired IDs. Historical training or archival records may remain only when their historical status is clear.

The shared `model-routing-optimizer` skill carries the repeatable audit workflow.

## Historical Exceptions

The dated appservice training records
`docs/training/health-checks/cluster-health-check-2026-03-29.md` and
`docs/training/health-checks/cluster-health-remediation-2026-03-29.md` retain
their original `claude-sonnet-4-6` attribution. They are historical evidence,
not live routing configuration.