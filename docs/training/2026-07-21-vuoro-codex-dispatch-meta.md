# Workflow Artifact: Codex-led Vuoro served-substrate dispatch

- **Date:** 2026-07-21
- **Source session note(s):** [raw redacted journal](../../.agents/sessions/2026-07-21-vuoro-served-substrate-codex-dispatch.md)
- **Workflow(s) used:** Codex root implementation plus fresh read-only verifier `/root/verify_vuoro_1203`; saved Claude workflows were hardened and published but were not callable from this Codex surface
- **Repos touched:** agentops, new local vuoro; derived project worktrees were relocated without authored changes

## Scenario

The run converted a ratified multi-repository direction into executable
dispatch infrastructure, a new public-runtime repository bootstrap, owner-local
backlog state, and the first protocol implementation. It also treated the run
itself as an evaluation of current dispatch topology, evidence quality, rework,
and cost visibility.

## Suitability assessment

One accountable owner was a good fit for the client/service protocol unit:
catalog revisioning, compatibility errors, identity derivation, and dynamic
invocation changed together. Splitting those files among builders would have
created interface negotiation inside an uncommitted unit. A fresh verifier was
appropriate after the commit because independence mattered more than parallel
implementation.

The saved workflow's new safety rules transferred well even though this Codex
surface could not invoke the Claude `Workflow(...)` primitive: live backlog was
re-read, claim proof stayed private, changes were committed before cold review,
publication was gated, and external permission failure did not become a false
pass. The main process gap is portability: workflow policy exists as a Claude
script, while Codex had to reproduce its stages manually.

## Item-level outcomes

| Item | Tier | Build tokens/calls | Verify tokens/calls | Verdict | Closed? | Rework? |
| --- | --- | --- | --- | --- | --- | --- |
| agentops workflow hardening | standard | aggregate root telemetry | local 82-test gate | confirmed and pushed | n/a | preserved and validated a pre-existing dirty change set |
| agentops #1185 | standard | aggregate root telemetry | 8 tests + render/sync gates | implementation complete locally; delivery blocked | blocked | CI path fix; GitHub credential lacks repository creation |
| vuoro #1203 | standard | aggregate root telemetry | first pass: 19/19 tests but four findings; recheck: 24/24 plus adversarial probes | pass after correction | blocked on remote | input/result split, safe refs, domain rejection, then request/basis, invalid-envelope, schema-feature, and adapter-context corrections |
| actionq #1196 | hard | 46.3M total tokens / 220 calls | four independent gates; final 74 focused and 162 full passes, zero skips | pass | pushed/done | skipped PG gate, false legacy/shape checks, transaction rollback, role authority, structured fingerprints |
| auditctl #1201 | hard | 33.2M total tokens / 120 calls | two gates plus doc recheck; final 54 full passes and 100 independent race histories | pass | pushed/done | Nix harness, event race, manifest roots, evidence ref, lock-order docs |

## What required rework

The useful rework was semantic, not cosmetic. Self-review caught that invalid
adapter output was being blamed on client input and that internal handler
failures could escape the generic result envelope. The corrected design uses
distinct caller, intentional-domain-rejection, adapter-result, and internal
handler paths. A standalone-CI path error and one temp cleanup command defect
were also corrected. More importantly, the independent verifier found four
contract gaps after the full 19-test suite passed: request-body validation
escaped the envelope, request/basis correlation fields were absent, schema
dialect/feature declarations were under-enforced, and adapters did not receive
the idempotency requirement. The correction added five regression tests and a
separate rework commit. The raw journal records prompts, commands, and sequence.
The re-verifier passed the correction with no findings. A separate operational
lesson came from evidence handling: redacting only top-level JSON keys exposed
a nested claim token in tool output. The claim was immediately released and
the proof deleted, but the workflow should provide a canonical recursive
redactor rather than relying on ad hoc `jq` filters.

The actionq pass demonstrates why skipped integration gates and structural
fixtures need separate visibility. One hundred passing tests did not catch
that a forged-but-checksummed ledger could authorize startup without queue
tables, and the migration adoption test recreated the new asset instead of the
real predecessor. The independent verifier rejected both. Auditctl paid more
harness setup cost but reached seven real PostgreSQL histories before review;
that harness pattern was then routed into actionq rework.
Auditctl's real PostgreSQL suite still missed a cross-stream race because the
concurrency test serialized migration, not conflicting event admission. A
fresh adversarial probe found it. This is evidence that merely eliminating
skips is insufficient: acceptance-driven fault selection matters as much as
the presence of a real database.

Actionq required four verifier rounds. This was expensive but materially
productive: each rejected green suite exposed a different class of authority
defect—missing live shape, transaction nesting, permissive SQL normalization,
incomplete FK metadata, and residual owner authority. The final correction
replaced ad hoc equivalence assumptions with structured PostgreSQL catalog
fingerprints and explicit owner-role rejection. The repeated defects also show
that the initial “standard” framing was optimistic; migration compatibility is
a hard reasoning unit and should route that way from the start.

## What was validated vs. not

Locally validated: independent wheels, no client database/migration/domain
assets, manifest and skill synchronization, deterministic catalog revision,
ETag caching, protocol incompatibility, safe JSON Schema references,
identity/environment/authority checks, idempotency enforcement and context,
client request/basis propagation, stale catalog, dynamic new-operation
invocation, schema dialect/feature declarations, and non-leaking error
envelopes.

Also validated and published: actionq deployment migration/runtime role
compatibility and auditctl central ingest/migration ownership contracts.

Not validated: Vuoro public GitHub visibility, GitHub Actions, Vuoro package or
OCI publication, the four-domain service adapter composition, the remaining
work/kctl migrations and adapters, Compose/Kustomize, and appservice runtimes.
Those are not silently treated as passes. Vuoro delivery is blocked
specifically on repository-creation permission.

## Cost summary

Ten Codex sessions reported 322,612,145 cumulative tokens and 942 tool/function
calls at the 19:45+03 snapshot. Of the input, 315,625,216 tokens were reported
as cached. Output was 1,256,422 tokens, including 468,576 reasoning-output
tokens. Root wall time at that snapshot was about 2h24m.

These are session telemetry counters, not a currency estimate. Forked agents
repeated large inherited contexts, which dominates the reported/cached input.
The actionq builder alone reported 46.3M total tokens and its four verifier
sessions another 138.9M; this makes context-fork size and repeated hard-gate
rounds the clearest cost target. Auditctl builder plus its two verifier sessions
reported 90.9M. The Vuoro verifier reported 2.35M because its scope and prompt
history were much smaller.

The local Codex telemetry exposes token counts and tool-call counts but no
session currency charge. The artifact reports the former and marks the latter
unavailable rather than applying API prices to a subscription-backed Codex
session.

## Follow-up changes named

- Create `bayleafwalker/vuoro` with an account credential allowed to create
  repositories, then push `fbcebfb..d025498` and publish agentops `0187bfb`.
- Close #1185 and #1203 only after the exact commits are remotely durable and
  re-run CI evidence is attached.
- Add a Codex-callable wrapper for the saved dispatch workflow or define a
  provider-neutral orchestration surface; manual semantic parity is useful but
  not ideal process evidence.
- Route deployment schema-compatibility units as `hard`; seed verifier prompts
  with semantic counterexamples for defaults, predicates, index NULL ordering,
  FK namespace/actions/deferrability, relation ownership, and transaction
  boundaries before the first gate.
- Add a provider-neutral compact context capsule for fresh verifiers. Forking
  the full root conversation made cached input dominate total telemetry.
- Add canonical claim-proof handling that never rewrites a credential record
  from a redacted response and never prints proof JSON; safe inspection should
  expose only allowlisted scalar metadata.
- Keep #1191 in dispatch-plan until signature scheme, ratifier registry,
  transition detection, and hook integration are decided.
