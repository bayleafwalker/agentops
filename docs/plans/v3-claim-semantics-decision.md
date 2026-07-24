# Decision record: claims demoted to advisory reservations (v3 tract opened)

Date: 2026-07-24. Operator decision following the #1233 pre-commit review
escalation; supersedes the capability-lease framing of sprintctl claims as a
target state. This is a cross-repo coordination record; the engineering
source of truth is sprintctl `docs/plans/v3-reservation-model-plan.md`.

## Decision

The sprintctl/vuoro claim model is demoted from a capability-style lease
(bearer token, rotation, proof-gated mutations, heartbeat TTL discipline,
lease_epoch) to an **advisory reservation with conflict detection**. Mutation
safety moves to expected-revision compare-and-swap, command idempotency,
transactions, and served-authority serialization. Execution ownership stays
with the dispatcher/runtime (actionq execution IDs, git worktrees). Recovery
is invalidate-and-reacquire. This is a deliberate "v3 clean-sweep" shift:
migration workload and backward compatibility are explicitly not weighted
heavily; machinery is deleted, not preserved.

Rationale (from the review escalation): the claim protocol itself documents
that it is not fencing and that `lease_epoch` has no enforcement; a claim
token only gates sprintctl mutations and cannot stop a former owner from
editing files or calling external systems — too weak to be true ownership,
too expensive to be merely advisory. The recovery review made this concrete:
preserving tokens through recovery would have manufactured split-brain
continuity and turned every recovery export into a secrets-bearing artifact.

## Executed 2026-07-24 (current semantics, pre-v3)

- sprintctl `b38937e`: #1233 `db recover-from-remote` committed with
  ownership-invalidating semantics (tokens stripped, active claims closed),
  fail-closed schema-drift assertion, atomic provenance. CI green.
- sprintctl `49efa09`: #1219 cross-backend recovery rehearsal completed
  against the live served authority (full parity, doctor/integrity clean,
  invalidation verified live); #1164 gate-evidence ledger row 9 is green.
  Bonus fix: doctor's stale SQLite schema-version pin (11 vs 14) — now
  derived from `db.CURRENT_SCHEMA_VERSION` as single source of truth.
- sprintctl `733394f`: v3 reservation-model plan committed; tract placed.

## Backlog placement

- sprintctl #1235–#1241 (track `v3-reservations`, sprint #407): revision CAS
  → proof-gate removal → credential-free catalog v2 → schema demotion train
  (#1238 gated on #1164 retirement completing on current semantics) →
  heartbeat removal → handoff/recovery deletion → protocol/guide rewrite.
- sprintctl #1234 re-scoped as V3-7: repo-level atomic recovery record
  (dual-backend schema), reservations close as `interrupted`.
- agentops #1242 (sprint #428): cross-repo guidance mirrors — agentops
  dispatch skills + sprintctl-bootstrap-template docs drop token/heartbeat
  ceremony once sprintctl #1241 lands.
- **Filed 2026-07-24:** the V3-3 vuoro twin is vuoro #1243 (sprint 429,
  track `v3-reservations`), created by bootstrapping `.sprintctl/backend.json`
  in the vuoro checkout (repo_id `vuoro` was already registered in remote
  postgres — only the local marker was missing). Q5 resolved as **retire**:
  invocation/v2's transient-credential carrier existed only to transport
  `claim_token` proofs (#1195 Group A) and has no consumer once v3 removes
  `claim_token`. #1243 also covers vuoro's composition/client-discovery
  refresh for the catalog v2 cutover, sequenced after sprintctl #1237. Per
  the coordination-mirror convention this is not duplicated as a separate
  item on this side.

## Open operator questions

Q1–Q4, Q7 open in sprintctl `docs/plans/v3-reservation-model-plan.md` §4
(reserve conflict policy, claim-type taxonomy, activity tracking, stale
sweep, catalog cutover window). Q5 (vuoro credential carrier) resolved
2026-07-24 as retire — see filing note above. Q6 (retirement interleaving)
was resolved by placement.

## Relationship to the retained-Vuoro assessment

`assessment-review.md` (this directory) keeps the build-vs-buy question open
(Beads+Restate adaptation unmeasured, #1228/#1229). The v3 tract narrows the
bespoke surface that any future migration would have to reproduce: advisory
reservations + revision CAS is a far smaller contract than the lease
protocol, which lowers the adaptation bar for external substrates and makes
the Stage-4 residual-ownership measurement (#1228) cleaner. The tracts are
complementary, not competing.
