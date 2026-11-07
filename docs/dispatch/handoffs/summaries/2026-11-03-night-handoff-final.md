# Agentops / Sovite night handoff — 2026-11-03

Prepared from the verified landing receipts and current coordination state. This is a current-only handoff; prior investigations remain in versioned checkpoints and receipts.

## Authority and operating limits

- User approval persists for independently reviewed source changes and merges after required exact-head CI passes. The user has standing approval for OpenCode Go for all development and other work. Preferred route: `opencode-go/deepseek-v4.1-flash`; Codex gpt-6-luna for integration/review, Terra for escalation. Current Go probes/drafts returned CLI output, but did not independently expose provider identity; they do not establish native qualification.
- Approval excludes deployment, production data changes, activation, and field clearance. No actual Root signing authority, live transport, production/shared database, real provider or native executor authority is established.
- Never retry or reroute the filtered adversarial Work31 task or the rejected private receipt-contract upload. Never disclose credentials or keys or resend the specifically rejected private payload. Generic/public draft work through Go remains authorized; do not broaden that specific rejection into a ban on all development.
- Development is stopped at the user's request. Root records the closing checkpoint and releases its advisory observation 484; the verified final state is in [nightstop-closeout-2026-11-03.json](nightstop-closeout-2026-11-03.json). Resume with fresh coordination, not reuse of the old observation.

## Canonical source and landed PRs

Canonical Sovite main is `546b170cbbc1589db9915c0b373adeb6696d154c`, tree `38ed250f2b3a3e6036b8b1e9a3e996966a871416`.

- PR61: reviewed head `3e7aece926d875e195d9a21ad5869bf8e69f2765`, merge `d7528fccc06545a5a88f4062d3a34a5ed74f7388`. Receipt: [unit4c-pr61-landing.json](unit4c-pr61-landing.json).
- PR62: reviewed head `3f3b82315bdff53e063d6776b8a9b695c36d1e5b`, merge `a827e9069e6bcc7f45892d48ede722ea55bd3c4a`. Exact eight CI checks passed; hosted PG16 fixture completed 59 starts / 177 phases with no skips or failures. Receipt: [sovite-luna-pr62-landing-verification-20261103.json](sovite-luna-pr62-landing-verification-20261103.json).
- PR63: reviewed head `16e886734f2eaf1b78f6995749fd3b024747b9dc`, merge `546b170cbbc1589db9915c0b373adeb6696d154c`; parents and tree verified, both PR and push runs passed all four jobs, exact remote branch removal read back, local worktrees preserved. Receipt: [sovite-luna-pr63-landing-receipt-20261103.json](sovite-luna-pr63-landing-receipt-20261103.json), SHA-256 `c7d23cbdbc99360fc32b557e2a4d55f18b9d62e1d17144647f02030b08daf7b6`.

## Stopped hand_back work

Work31 Luna owns the narrow `LeaseService.hand_back` source unit in `/tmp/sovite-hand-back-v2-20261103`, branch `codex/hand-back-v2-20261103`, based on canonical main. Finish, publication, renew, recovery, bulk cancellation, and other lease writers are outside this unit.

The reviewed design is [sovite-hand-back-design-v2-2026-11-03.md](../sovite-hand-back-design-v2-2026-11-03.md), SHA-256 `bc6971ac7b0db0d34e0dbacf7e361e652a0de4a152de5c6aaaf19eb6647ac0d4`. It requires exact no-projection proof across supported schema metadata, Job JSON, Work intents/legacy links, bindings, reservations, and slots; projected paths require the explicit captured fence; known settled evidence is preserved; unsettled possible dispatch stays UNKNOWN/held with gate inhibition; no refund or no-dispatch claim.

The prior frozen candidate `44e6f9579ed309ecd4f41cde82c761c8c8159650` (tree `7a1a2f73e720904c828967ebdcb096880d774a98`) is superseded. Current worktree HEAD is `46523712fc7b8736f9b110aaff209f3c8271e414`, tree `d8141cdbf040e2f2b21388c661a92c6a0c5fd6c7`, with two modified unstaged files and no untracked source. The exact HEAD previously passed a six-case SQLite selection; the current unstaged selector/regression delta is untested. Historical-link acceptance and unified current/historical lock closure remain unfinished. Primary's rule is to anchor locked targets and batch snapshots, retain unique history, and keep current identities disjoint; target binding alone is insufficient: reconcile retained source history and stored digests. These checks establish stored-row consistency, not external source authenticity. Confirm global lock closure before any new freeze.

No final PG evidence, immutable review snapshot, final pair of implementation reviews, or PR exists for the current WIP. After resumption: finish the bounded implementation, create a separate detached immutable snapshot, run scoped SQLite/PG validation on those exact bytes, then obtain both ordinary reviews. Do not treat the mutable author worktree as a frozen review target. No push/PR until those steps pass.

**Work31 WIP checkpoint:** [author night-stop handoff](../sovite-hand-back-wip-nightstop-2026-11-03/HANDOFF.md), SHA-256 `c7fc1eeee868f4a93d8cdfc4503694b4aa06ae9d826ee6b90e4c9a673c023a48`.

## Work31 boundary

Work31's inert source lane is complete, but live endpoint identity, Root-signed read authority/trusted keys, principal/RBAC, actual configuration and credential FD custody, live watch ownership, and cancellation/reap evidence remain external and UNBOUND. See [WORK31-LANE-HANDOFF-2026-11-03.md](../work31-continuation-2026-11-03/WORK31-LANE-HANDOFF-2026-11-03.md). No field authority or completion is inferred.

## Current served coordination

Event 6562 and the last active observation snapshot are historical. Consult [nightstop-closeout-2026-11-03.json](nightstop-closeout-2026-11-03.json) for the closing event and verified release of observation 484. This was source advisory only, never field clearance or programme completion. New work requires fresh coordination; the Nov2 no-hold answer is historical.

## Checkpoint pointers

- Current coordination pointer: [orchestrator-thin-state.json](orchestrator-thin-state.json), updated NOW/coordination fields.
- Frozen current-only authority/state source: [orchestrator-now-v4.json](orchestrator-now-v4.json), SHA-256 `2e8406f00c9be420fd29dc7c5e96d948b0afc93b9fea9713303c57dece0b1ab2`.
- PR63 landing checkpoint: [sovite-luna-checkpoint-20261103-v15.json](sovite-luna-checkpoint-20261103-v15.json), SHA-256 `76100d896f5e00fbc30bd737fe44926ac0c969468dd24ccdb97002ef062b3873`.

## Recovery and persistent boundaries

Root verified the complete two-file net source difference and saved-copy hashes. See [RECOVERY.md](../sovite-hand-back-wip-nightstop-2026-11-03/RECOVERY.md) before restoring: the unstaged patch alone is not the full change from canonical main. No hand-back test/review success applies to the current dirty delta.

PR2153 stays HOLDMERGE. Work31 B is permanently retired and B2 cleanup is done; do not repeat it. Preserve protected/dirty original copies and Source Secrets. No actual Root key/signer was launched. Contract27a and collection epoch1 remain the active source assumptions; the epoch amendment is unaccepted. Generic peer pause ACKs do not sign the newer source-identity/UID commitments. All seven real Work31 phases remain UNBOUND.

Agentops is public: keep private artifacts untracked and never commit this packet accidentally. `_artifacts` is host-persistent, not durable-authoritative; `/tmp` is ephemeral. Before reasoning about credentials run the state-only status/inventory hooks. A sandboxed empty network result means could-not-check; prefer packaged credctl where supported. No live source/shared application-ledger access, ledger migration, deployment, Root signing, source custody or field operation occurred; served coordination API notes and reservation updates are recorded separately. The broader programmes remain incomplete.

Earlier ecosystem state remains in `docs/dispatch/handoffs/2026-11-01-ecosystem-night-stop.v2.json`, the Nov2 artifact ledger and versioned Nov3 checkpoints; preserve changed trees rather than resetting them to satisfy an old digest. Resume with this final handoff and the exact WIP checkpoint.
