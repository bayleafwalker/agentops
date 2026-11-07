---
status: active
owner: operator-designated coordinator (default-assigned 2026-11-07)
last_verified: 2026-11-07
---

# Programme status (rolling)

This is the rolling, tracked summary of programme state. It replaces reading
untracked `_artifacts/agentops/ecosystem-resume-*` folders to learn where the
programmes stand. It is a summary of the canonical records below, not a new
authority: the structured handoff JSON, Git, CI and served sprintctl/Vuoro owner
records stay authoritative, and a later handoff supersedes this page until the
page is refreshed.

Sources, newest first:

- [2026-11-06 full-track handoff](../handoffs/2026-11-06-full-track-handoff.v1.json)
  and its [summary](../handoffs/summaries/2026-11-06-full-track-handoff-summary.md),
  [progress](../handoffs/summaries/2026-11-06-progress.md),
  [service-mint chronology](../handoffs/summaries/2026-11-06-service-mint-progress.md)
- [2026-11-05 full-track handoff](../handoffs/2026-11-05-full-track-handoff.v1.json)
  and its [summary](../handoffs/summaries/2026-11-05-full-track-handoff-summary.md),
  [Sovite programme census](../handoffs/summaries/2026-11-05-sovite-programme-census.md)
- [2026-11-04 night stop](../handoffs/2026-11-04-full-track-night-stop.v1.json)
  and its [summary](../handoffs/summaries/2026-11-04-night-stop-summary.md)
- [2026-11-03 final night handoff](../handoffs/summaries/2026-11-03-night-handoff-final.md)
- vuoro-cloud migration plan: [plan](../../plans/2026-11-06-vuoro-cloud-migration-plan.md);
  PR state read from Forgejo on 2026-11-07

## Completion rule

From 2026-11-07 a programme completes at **source accepted**: its source slices
are merged on the canonical main with exact-head CI green and independent
review recorded, against the programme's original acceptance criteria.
Deployment, live signing, field execution and promotion are a **separate gate
item** per programme, carried as an operator command package
([schema](../../../schemas/operator-command-package.v1.schema.json),
[packages](../operator-gates/README.md)). A source-accepted programme with an
open gate item is reported as `source accepted; gate open`, never as done and
never as blocked on source.

## The seven 2026-10-24 programmes and integration

Status as of the 2026-11-06 handoff (acked 2026-11-07T06:08:16Z). No parent
outcome is closed or source-accepted yet.

| # | Programme | Work refs | Source state | Open source gaps | Gate items |
|---|---|---|---|---|---|
| 01 | [Contract foundation](2026-10-24/01-contract-foundation.md) | vuoro#2734, vuoro#2735, agentops#2736 | Vuoro PR311 declaration-v2 / directory-entry-v2 schemas merged; v1 unchanged | v2 adjunct capability (uncommitted, unreviewed; preserved in `_artifacts/agentops/preserve-2026-11-07/`); EC-00 #2734 reservation #405 held by another session | none until source accepted |
| 02 | [Cloud recovery](2026-10-24/02-cloud-recovery.md) | agentops#2599, #2863, #2646 | backup source children #2599/#2646 accepted | physical/field recovery not proven | staging rehearsal |
| 03 | [Cloud product, TUI, distribution](2026-10-24/03-cloud-product.md) | vuoro-cloud#2727, #2729, #2682-#2684, #2741, agentops#2626-#2636 | Cloud PR345/346/348 merged; Vuoro 0.1.104 published (wheel + GHCR) | Cloud TUI #2727 gated on OA-01/OA-02 and EC foundation; 0.1.104 not pinned in vuoro-cloud (pins 0.1.94) | 0.1.104 rollout; poc.N promotion |
| 04 | [Requests and continuation](2026-10-24/04-requests-continuation.md) | vuoro#2725, #2728, agentops#2726, #2730, #2554, #2623, #2638 | sprintctl PR217, PR219-222 merged (owner lookup, material catalog, requester adapter, schema33 ledger) | private authenticated transport, real admission mint, receiver; material-v2 all-writer gate, lock order, restore anti-fork, outbox recovery unproved | mint signing |
| 05 | [Sovite](2026-10-24/05-sovite.md) | agentops#2850, #2849, CL-K06 | Sovite PR67-80 merged (GitHub, read 2026-11-07); PR81 test-only open; external fairness v2 opt-in | three unexplained CI failures (PR70 `authority_unavailable`, PR71 1122 ms timeout, earlier push run); SV-PW1-5 qualification | Sovite field qualification |
| 06 | [Telemetry](2026-10-24/06-telemetry.md) | agentops#2398, #2833, #2835 | synthetic export seam (Cloud PR346) | native child probe (exactly one run taken; not to be repeated without specific authority); receipt-to-sink | none until source accepted |
| 07 | [Retention](2026-10-24/07-retention.md) | agentops#2828 | none accepted | upstream replay fence; authoritative deletion inventory | none until source accepted |
| 08 | [Integration](2026-10-24/08-integration.md) | all candidates | appservice PR2171/2172 merged | appservice PR2153 open: needs Work31 against live Work29 primary behind an enforced fence | Work31 appservice field execution |

## vuoro-cloud migration plan P0-P7

Plan: [2026-11-06 migration plan](../../plans/2026-11-06-vuoro-cloud-migration-plan.md).
Forgejo `bayleaf/vuoro-cloud`, main `f1159258` on 2026-11-07.

| Phase | PR | State 2026-11-07 |
|---|---|---|
| P0 principles | #349 | merged |
| P1-P4, P6, P7 | #350, #351, #352, #354, #355 via integration #356 | merged |
| P5 tenant verification and scripted rollback plan | #353 | **open** (CI was pending 2026-11-06 21:39Z; still open 2026-11-07) |

Not buildable from source: tenant schema-version mapping (contract owned by the
vuoro repo, see [owners](../operator-gates/README.md#owners)), staging
rehearsal with real owner wheels, live Talos proof, migration Job image rebuild
carrying the manifest. Fast-forward-only merges and one ~30 minute runner mean
reviewed work should land as one stacked linear branch.

## Sovite

Source: PR67-80 merged, PR81 (test-only diagnostic setup time) open. Last live observation 2026-10-19 (landscape research notes, 2026-11-07). The
standalone (bundled Garage and Ollama) versus workspace-hosted duality has no
recorded decision; the spec's "This release does not write to a Vuoro service"
conflicts with the shipped `vuoro-contracts` pin and Vuoro adapter. Both are
recorded as doc-correction items for the Sovite repo, not as reasons to change
intent. A bounded diagnostic outcome on the three unexplained CI failures
precedes further Sovite slices.

## At-risk work preserved outside Git

| Item | Where | Next step |
|---|---|---|
| sprintctl declaration-v2 adjunct (schema34, uncommitted, final `FOR SHARE` lock change untested) | `_artifacts/agentops/preserve-2026-11-07/` bundles and patches; `_artifacts/agentops/ecosystem-resume-2026-11-06/handoff-adjunct/SHA256SUMS` | verify hashes, reanchor on sprintctl `8df99b9`, test, push as a draft PR |
| Sovite expired-owner WIP | `_artifacts/agentops/preserve-2026-11-07/sovite-worktree-state.txt` | push as a draft PR from its worktree |

## Refresh rule

Refresh this page in the same change as each new structured handoff, and bump
`last_verified`. The plan register (`docs/plans/REGISTER.md`) lists it with the programme files.
