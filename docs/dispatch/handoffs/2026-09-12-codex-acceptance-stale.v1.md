# Handoff 2026-09-12-codex-acceptance-stale.v1

<!-- Rendered from the canonical JSON beside this file. Do not hand-edit:
     `agentops handoff validate` and `ack` read the JSON, never this. -->

**Objective.** Record the Codex acceptance evidence line in the context-economy plan.

**Next action.** In /projects/dev/outctl/docs/CONTEXT_ECONOMY_PLAN_2026-09-12.md, append the line 'Codex acceptance evidence: docs/verification/handoff-v1-successor-isolation.md' immediately after the 'Codex acceptance: 2026-09-12.' line. Change nothing else. Do not commit.

## Predecessor

- harness: claude-code
- session: 75f65a35-f426-49bc-9638-b09003838075
- model: claude-opus-5
- context used: 48.0%
- transcript: /home/bayleaf/.claude/projects/-projects-dev/UNREADABLE-predecessor-transcript.jsonl

Read-only after transfer: once a successor acks, the predecessor makes no
edits and takes no external actions. It stays consultable.

## Constraints

- Do not push; commits stay local.
- Touch only docs/CONTEXT_ECONOMY_PLAN_2026-09-12.md in /projects/dev/outctl.
- If the repo-state check refuses, stop and report; do not adapt to the drift and do not edit the handoff.

## Decisions

- **The handoff JSON is canonical** — the rendered .md is never read by the ack guard

## Rejected

- **Re-deriving state from the tree when the digest disagrees** — the digest exists so a successor can prove the tree is the one the predecessor left

## Repo state

| path | branch | head | dirty | unpushed | diff_sha256 |
|---|---|---|---|---|---|
| `/projects/dev/outctl` | release/2026-08-11 | `a9392a0be0b2` | yes | 3 | `42ab277d03b0b6c7…` |

## Unresolved

- (none recorded)

## Evidence

- artifact: `/projects/dev/outctl/docs/CONTEXT_ECONOMY_PLAN_2026-09-12.md`

## sprintctl bundle

- none (sprintctl unavailable or produced no bundle)

## Successor

- session: 01a09578-1fb9-71d1-bbbf-6408a160b748
- acknowledged: 2026-09-12T11:54:42Z
