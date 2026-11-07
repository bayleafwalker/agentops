# Handoff 2026-11-03-routing-estate-investigation.v2

<!-- Rendered from the canonical JSON beside this file. Do not hand-edit:
     `agentops handoff validate` and `ack` read the JSON, never this. -->

**Objective.** Continue the broad investigation of model routing and practical execution across workstation, devbox and cloud, including native sessions, OpenCode, Claude, subscriptions, API, Jev, plans, implemented and market tools; use GPT-6 Luna explorers and GPT-6.1 Sol guidance as requested.

**Next action.** After acknowledging this handoff, read agentops#2874 notes #6563-#6564 and the linked v2 plan, inspect /tmp/vuoro-release-composition-20261103-sol if it survives, then ask GPT-6.1 Sol to reprioritize the broad estate and staged qualification; preserve all existing dirty state.

## Predecessor

- harness: claude-code
- session: 86b3f016-4d86-4987-bc47-37c90acc9add
- model: GPT-6 Codex
- context used: unknown%
- transcript: unknown
- origin: `workstation:/projects/dev/agentops/docs/dispatch/handoffs/2026-11-03-routing-estate-investigation.v2.json` (authoritative copy; an ack from another host goes through it)

Read-only after transfer: once a successor acks, the predecessor makes no
edits and takes no external actions. It stays consultable.

## Constraints

- The operator is closing for the night; do not continue work until a successor is launched.
- Follow /projects/dev/AGENTS.md and repository instructions. Preserve pre-existing dirty agentops files and unrelated worktrees; do not delete unknown work.
- Routine reviewed implementation and deployment need no invented operator gate, but claims must reflect actual evidence. Network checks need sandbox escalation, and empty sandboxed output is not evidence of absence.
- Never expose credentials; the workstation OpenCode local service password was rotated after it appeared in a tool output, potentially invalidating paired local clients. Provider keys were not exposed in that incident.
- Distinguish requested model, harness-reported configuration and backend/billing attribution; distinguish synthetic fixture, real owner and deployed service. Do not revive retired ActionQ or legacy route-decision producers.

## Decisions

- **Keep native lanes provisional and specify model explicitly on Codex resume** — Devbox ordinary resume selected configured Sol despite earlier Luna; explicit Luna worked. Catalog listings do not prove service entitlement or billed model.
- **Keep Jev offline/advisory** — October evaluation measured weak agreement with historical decisions, not independent accepted outcomes; costs and repair effort remain unknown.
- **Merge fixture-only OpenCode v2 terminal and running cancellation code** — Agentops PRs #483 and #484 passed CI; #484 had 392 targeted tests and two isolated exact 2.0.32 fixture runs. Production selection remains off and real owner/session exclusivity remain unqualified.
- **Disable queued deletion in cancellation orchestration** — A sole queued input was not reproducible on exact binary; 204 or an empty queue does not prove deletion. No DELETE was sent in the latest exact fixture.
- **Set devbox canonical remote keys** — Verified identical remote identities to workstation, then set claude.canonicalRemote=origin for clean agentops, sprintctl and gitops-nixos clones; readback confirmed.

## Rejected

- **Treat the live devbox OpenCode inbox as healthy because units run** — Installed adapter pin speaks v1 while service 2.0.32 returns HTML for v1 health endpoints. Health gate defers launches, potentially after owner acceptance/registration.
- **Switch devbox Nix generation immediately to fix default** — GitOps PR #82 fixes invalid DeepSeek Flash default in source but candidate closure also changes other packages and reloads system services; deployed impact and owner integration are not yet qualified.
- **Infer cancellation from an interrupt acknowledgement, empty active map, or wrong-session DELETE 204** — Exact-binary tests show ambiguous or misleading responses and pagination is not snapshot-isolated. Repeated observation is non-atomic and may defer indefinitely.
- **Create another generic offline coverage replayer** — Open PR #429 already implements fixture-only counting. Review found its exact-redelivery fingerprint ignores observed_at; fix or explicitly define that contract before refreshing CI. It does not implement real capture or OpenCode metadata extraction.
- **Treat source-pinned wheel as deployed image identity** — Live Vuoro service image digest was observed, but the disposable 0.1.101 wheel was locally built and cannot prove image byte equivalence.

## Repo state

Digest definition: v5 (see the handoffs README).

| path | branch | head | dirty | unpushed | diff_sha256 |
|---|---|---|---|---|---|
| `/projects/dev/agentops` | main | `b3e9241e4775` | yes | 0 | `ad01e661af4d737f…` |
| `/projects/dev/gitops-nixos` | main | `bf9a0857b7ea` | yes | 0 | `b8c6b2f09a005f49…` |
| `/projects/dev/vuoro` | main | `7dfa23483773` | yes | 0 | `1c752604c580c5df…` |
| `/projects/dev/sprintctl` | main | `32bc4e6b3b1f` | yes | 0 | `a24b3fa1f08288ea…` |

**Running:**

- No agent processes or tests remain running; source-pinned Vuoro temporary worktree and wheel, disposable composition and PR #429 review worktree remain under /tmp and are ephemeral.

## Unresolved

- Finish broad estate disposition: host defaults and overrides, billing/entitlement and account identity, cloud continuation, Jev accepted-outcome measurement, real telemetry and market tools. Native cloud marker succeeded but serving model, workstation-off execution and new Cloud continuation remain unproven.
- Complete disposable real packaged owner/CLI/adapter qualification: /tmp/vuoro-release-composition-20261103-sol has a built noneditable service 0.1.101, pinned owner Sprintctl 0.26.0 and 50 compatible packages; release composition attestation passed. First independently verify import origins and force attestation failure, then private guarded PostgreSQL, real loopback HTTP, immutable CLI and exact OpenCode integration with synthetic identities. No DB/server was started. /tmp is ephemeral.
- Deployed Vuoro shared image release 0.1.101 is ghcr.io/bayleafwalker/vuoro-service@sha256:b4efdf41bad0ffc199ee647c3c8c8a84982a47bd1f19db3e58f4c95172c662b3; release source 2909daa57b60f9967195e65e00b5d484526c0edd pins owner Sprintctl 0.26.0. Immutable workstation CLI candidate is 0.21.0, a distinct client; do not silently substitute its owner implementation.
- For OpenCode v2: sole queued deletion, broader effective permissions/MCP, actual owner RPC, exclusive writers, installed service, Nix rollout and rollback/legacy rows remain unqualified. Production v2 enablement is absent. Full state is in served item agentops#2874 notes through #6564 and committed traces.
- PR #429 offline coverage replay: local merged-tree focused tests passed 55; duplicate with changed observed_at was still treated as exact. Fix or formally specify timestamp semantics, define cross-case origin sequencing, review and rerun current CI. /tmp/agentops-pr429-review has a no-commit merge on review/pr429-merge; it is disposable and was created by this session. Do not mistake it for clean main.
- Source telemetry: Claude Stop has a best-effort cost export path; Codex Stop supplies session/turn/project but not effective model; OpenCode v1 adapter records requested model but not separately durable assistant provider/model/usage. C1 plan requires pinned real sources and owner/storage choices; no real-source exit established.
- Host drift: workstation/devbox OpenCode 2.2.1/2.0.32, sprintctl 0.20.0/0.28.0, Claude 2.1.310/2.1.316, Codex 0.166.0 both. Shared routing JSON matches. Workstation Claude reports subscriptionType pro after login; previous Max observation unresolved. Native auth and marker success do not establish billing or account equivalence.
- Market research points to OpenCode for local/multi-provider use, Claude Code web for subscription-hosted continuation, OpenAI Agents API for programmatic API-billed hosted workflows. Verify current official sources and actual account availability before recommendations.

## Evidence

- sprintctl: `agentops#2874 notes #6551-#6564`
- artifact: `/projects/dev/agentops/docs/evidence/2026-11-03-routing-estate.md`
- artifact: `/projects/dev/agentops/docs/dispatch/model-routing.md`
- artifact: `/projects/dev/agentops/docs/plans/2026-11-03-opencode-v2-host-adapter.md`
- artifact: `/projects/dev/agentops/verification/traces/opencode-v2-fixture-cancel-2032/README.md`
- artifact: `/projects/dev/agentops/docs/evidence/2026-11-03-routing-comparison/README.md`
- artifact: `/projects/dev/agentops/docs/evidence/2026-11-03-routing-local-clerical/README.md`

## sprintctl bundle

- none (sprintctl unavailable or produced no bundle)

## Successor

- session: (unacknowledged)
- acknowledged: —
