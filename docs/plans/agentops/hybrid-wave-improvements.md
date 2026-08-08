# Hybrid wave improvements assessment and staged plan

Status: implementation started; lifecycle automation remains owner-staged.

## Assessment

| Intervention | Existing foundation | This change | Remaining owner work |
|---|---|---|---|
| Coherent batching | Immutable plan entries and exact work revisions | `dispatch-plan` wave mode and `dispatch-wave` skill | Measure packet-size/candidate-quality tradeoffs |
| Stratified verification | Worker command IDs, candidate verification, integration profile | Skills freeze attempt/focused/full stages | Compiler v2 may encode all three profile refs explicitly |
| Adversarial acceptance | Falsifying `acceptance_properties` | Plan/build/review guidance requires negative, ordering, mutation, real-layer, anti-vacuity evidence | Add repo-specific fixtures and mutation histories |
| Worker gate execution | OpenCode overlay already grants exact manifest commands | Skill makes inability to run a focused gate a blocker | Qualify each harness profile against exact command execution |
| Context churn | Cost and token receipts already exist | Packet adds bounded repeated-read/mutation-free/identical-context stop rules and early handoff | Harness-native mid-turn telemetry/interrupt enforcement |
| Observable waits | Vuoro resource reference, changes, and wait design exists | Portable contract requires one terminal wait and attached receipts/bundles/log refs | Actionq snapshot/cursor/long-poll owner proof, then Vuoro adapter/client |
| Dependent review | Actionq immutable candidate verification/review/integration contracts exist | Wave skill defines idempotent publication→review→approval→integration sequencing | Actionq owner implements explicit transition operation and recovery histories |
| Concurrent topology | `independent`, `stacked`, `wave-integrated`, `max_parallel` exist | Wave skill forbids shared mutable worktrees and requires merge-resolution actions | Stacked predecessor binding remains staged |
| Semantic ownership | Existing protected paths and coordinator-owned oracle | All wave skills retain coordinator-only semantic surfaces | Keep risk-surface gates current per repository |

## Contract direction

Do not create a second workflow engine in AgentOps or Vuoro. The compiler
freezes intent, Actionq owns action creation and terminal lifecycle, runners
consume exact commands and immutable artifacts, and Vuoro transports owner
references and observation.

The next versioned compiler contract should make three verification stages
explicit only after Actionq profile refs and transition operations are stable.
Until then, `command_id` is the worker falsifier,
`candidate-verification-spec/v1` supplies focused owner verification, and an
integration entry's `verification_profile` is the once-per-wave broad gate.

## Ordered implementation

1. Land and qualify the wave skill and packet churn controls.
2. Add repository-specific adversarial fixture histories to packets; do not
   put generic filter semantics in the shared schema.
3. Stabilize Actionq observable action/group snapshots, cursors, terminal
   attachments, and one idempotent transition that creates review from an exact
   publication and integration from an exact approval.
4. Add Vuoro generic `get`, `changes`, and bounded `wait` only against the
   proven Actionq owner contract.
5. Measure coherent batches against tiny packets using candidate success,
   review findings, repeated-context tokens, focused-gate latency, and one
   full-suite cost per accepted wave. Cheap cache writes are not a primary
   optimization target.
