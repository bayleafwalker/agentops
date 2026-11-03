# Native coding runner comparison — 2026-11-03

## Setup

- Public repository: `https://github.com/bayleafwalker/agentops`
- Fetched ref: `origin/main`
- Pinned source SHA: `45c181b457c77030a499d547b3e2d9047b5fb09c`
- The original checkout had unrelated local changes and was not used for model edits.
- Four isolated checkouts under `/tmp/route-compare-20261103/` were exported from the pinned source: `kimi-task1`, `terra-task1`, `kimi-task2`, and `terra-task2`.
- Task prompts are `packet-task1.txt` and `packet-task2.txt`; their SHA-256 values are `8c1cc5782b2cc5f56dc1f2d149d96773210a3604264c41760f8eb16080a4034b` and `0fed66a7d44debe2b19f3aa934fcb31ae5c64478885cf7e1248424d90b`.
- Frozen independent oracles are `oracle-task1.py` and `oracle-task2.py`; SHA-256 values are `b1fe9d934252c4b8de4d41aa0eaeb3ffd1d2f02e6f150c5f06f92e618742deb4` and `440197c3e0fad2f729467620249353ca33fc956ad031b96d82c4aaf80e3c27b5`.
- Both oracles were run against the untouched baseline before model work and failed on their task-specific assertions, confirming they discriminate the requested changes.

Task 1 hardens native catalogue slug validation. Task 2 distinguishes an unconfigured primary model from a configured but unobserved one. Each packet limited edits to `scripts/audit_model_routing.py` and prohibited network commands.

## Runs and results

| Task | Runner / model | Session | Elapsed | Result and verification |
|---|---|---|---:|---|
| 1 | OpenCode / `opencode-go/kimi-k2.7-code` | `[redacted-session]` | 68.5 s | Implemented rejection of malformed, empty, and whitespace-only slugs in object catalogues. Existing audit tests: 5 passed, 6 pytest temporary-directory cleanup warnings. Independent task 1 oracle passed. |
| 1 | Codex / `gpt-6.1-terra` | `[redacted-thread]` | 16.7 s | Implemented the same behavior using a compact `any(...)` validation. Focused local checks and independent task 1 oracle passed. |
| 2 | OpenCode / `opencode-go/kimi-k2.7-code` | `[redacted-session]` | 32.1 s | Added `primary-unconfigured` for a missing, malformed, or whitespace-only primary; suppressed `primary-not-observed` in that case. Existing audit tests: 5 passed, 6 pytest temporary-directory cleanup warnings. Independent task 2 oracle passed. |
| 2 | Codex / `gpt-6.1-terra` | `[redacted-thread]` | 13.1 s | Implemented the same issue behavior. Focused local checks and independent task 2 oracle passed. |

All four checkouts passed `git diff --check`. Every candidate changed only `scripts/audit_model_routing.py`. Task 1 differences are stylistic; both implementations reject all malformed rows, including hidden ones, while preserving valid visible and probe-list behavior. Task 2 produced identical diffs for both models.

Full candidate diffs are saved as:

- `kimi-task1.diff` — SHA-256 `edbbcffb632d0a327f4e3fb2e26fc97ceeae4f5538fa94f13b20e6ba08b076f8`
- `terra-task1.diff` — SHA-256 `cb83b9906d43622b4122683d94efd8ae5eeecb812715a1bd32fbe85e8fbe696d`
- `kimi-task2.diff` and `terra-task2.diff` — identical; SHA-256 `baaba2a25a06974a4256ee6e746b389f258149429930b3cb9ee2cfa2234a4ae1`

## Native continuation

OpenCode successfully resumed both Kimi sessions with a no-edit request and returned the prior task outcomes. Codex runs used `--ephemeral`; a resume attempt for task 2 returned `no rollout found for thread id`, so Codex continuation was not available from those ephemeral runs.

## Interpretation and limits

Both models met the frozen acceptance checks on both tasks. Kimi ran the existing focused test file on both tasks; Terra ran focused inline checks, and all four candidates passed the independently frozen oracle. Task 1 implementations differ in style; task 2 implementations are identical. These two small tasks do not establish a general model ranking.

No model edit touched the real agentops checkout. No push or other external repository effect occurred. The harness fetched the public source ref and made hosted model-inference requests for the four runs and Kimi continuation checks. The frozen prompts prohibited network commands; the models used local file reads, edits, and checks only. No credential files were inspected or copied during the reruns.

## Credential incident

During initial setup, before the reruns, a local OpenCode service credential was accidentally included in a tool result while inspecting configuration. It was not intentionally used; downstream retention is unknown. The operator was notified and the local service password was rotated. No credential value is recorded here.

## Claude Sonnet extension

At the operator's direction, Claude Code ran the same frozen tasks in two new isolated checkouts exported from the exact same source SHA and using the same packet/oracle files. Each baseline oracle failed before the run for its task-specific assertion; both candidate oracles passed afterward.

| Task | Native runner / model | Session ID | CLI elapsed | Result |
|---|---|---|---:|---|
| 1 | Claude Code / `claude-sonnet-5-5` | `[redacted-thread]` | 17.6 s | Added rejection of empty and whitespace-only object-form catalogue slugs. Task 1 oracle and `git diff --check` passed. |
| 2 | Claude Code / `claude-sonnet-5-5` | `[redacted-thread]` | 11.1 s | Added `primary-unconfigured` for missing, malformed, or whitespace-only primary models. Task 2 oracle and `git diff --check` passed. |

The CLI was invoked with `--restricted` and only `Read`, `Edit`, `Glob`, and `Grep` tools. Shell and web tools were unavailable to the model; the returned metadata reported zero web requests and no permission denials. Claude stated it did not run additional tests; only the pre-frozen independent oracles were run against these candidates. The operator had verified the native Claude Code subscription login. This record makes no claim about billing beyond that authentication context.

Candidate diffs:

- `claude-task1.diff` — SHA-256 `aa90929acb842f4ec7af89875343287123860cac57d55a1972a710805c44b5a5`
- `claude-task2.diff` — SHA-256 `baaba2a25a06974a4256ee6e746b389f258149429930b3cb9ee2cfa2234a4ae1`; this matches both previous task 2 candidates byte for byte.

Claude's task 1 uses the same validation condition as the other candidates, expressed as a one-line addition. Its task 2 implementation is byte-identical to Kimi and Terra. Both Claude responses were successful; no runner or model failures occurred in these two Claude runs.
