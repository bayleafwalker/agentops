# Vuoro Ecosystem Remediation Preflight Checklist

**Created:** 2026-07-25  
**Reworked:** 2026-07-26  
**Mode:** execution planning helper; no implicit operational authorization

## Global preflight

- [ ] Select one implementation-plan unit and confirm all dependency gates.
- [ ] Name the decision owner, builder, primary verifier, and fresh Spark-class secondary reviewer.
- [ ] Confirm repository ownership and separate authorization for every repository to be changed.
- [ ] Record input revision SHAs and expected branches without modifying unrelated dirty work.
- [ ] Inspect declared `risk_surfaces` for queue, claim, lease, retry, recovery, projection, publication, reconciliation, and backend-parity work.
- [ ] Record the approved contract or policy decision; do not build from an unresolved hypothesis.
- [ ] Define validation commands, fixtures, backends, fault schedule, and expected observable results before editing.
- [ ] Define rollback/forward-recovery behavior. Claim lifecycle rollback must account for schema and mixed-version clients.
- [ ] Choose the protected verification-record location and redaction rules.
- [ ] Confirm no claim tokens, credentials, direct connection strings, or unredacted environment output will enter Markdown or workflow args/results.
- [ ] Confirm no overlapping manual dispatch or closeout touches the same reasoning unit.
- [ ] Obtain separate authorization for any deployment, Kubernetes, Flux, image, or live-data action.

## Secondary implementation review preflight

- [ ] Reviewer did not implement the unit and starts from a fresh context.
- [ ] Review input names exact output revision SHAs, not a moving branch.
- [ ] Reviewer receives the approved contract, affected public surfaces, diff, and required fault/fixture matrix.
- [ ] Reviewer can access primary evidence but must reproduce critical assertions independently.
- [ ] Gate defines objective failure conditions and requires `PASS`, `FAIL`, or `BLOCKED`.
- [ ] Publication and closure are blocked until `PASS`.

## S0-S3 claim safety

- [ ] S0 defines execution authority, coordination authority, and opaque claim-incarnation proof.
- [ ] Renewal order and every partial-success/unknown-outcome state are specified.
- [ ] Ownership loss stops or terminates work and prohibits all settlement.
- [ ] One-shot supervision or an explicit TTL bound is decided.
- [ ] Cross-tool terminal partial commits have idempotent recovery behavior.
- [ ] S1 migration and mixed-version compatibility are defined before changing terminal APIs.
- [ ] S2 inventory covers daemon, one-shot, shutdown, exception, retry, and settlement paths.
- [ ] Session heartbeat is not counted as authority renewal.
- [ ] Fault histories include execution beyond TTL, wrong owner, response loss, sweep/reclaim, each renewal failing independently, shutdown during renewal, and each settlement write failing after the other succeeds.
- [ ] Integrated S3 review uses the combined pinned revisions.

## P1-P2 served policy and cutover

- [ ] Choose literal-only or approved-sourced `.envrc` policy before editing consumers.
- [ ] Confirm the validator's explicit eight-repository scope with owners; do not add `vuoro` implicitly.
- [ ] Checker fixtures distinguish active wiring, comments, sourced configuration, local-only rollback, missing profile, and override.
- [ ] Use the absolute profile path:

```bash
python /projects/dev/agentops/templates/dispatch/scripts/validate_vuoro_workstation_cutover.py \
  --root /projects/dev \
  --profile /projects/dev/agentops/templates/dispatch/environment-record/profiles/workstation-vuoro-shared.json
```

- [ ] Run smoke checks from the actual repository cwd with `direnv exec .`.
- [ ] Assert effective repo identity and tenant-specific data; do not accept HTTP success under wildcard credentials as proof.
- [ ] Smoke work remains read-only.

## I1 repository identity

- [ ] Keep tenant slug, committed marker, path fallback, and authority UUID as explicitly mapped identity types.
- [ ] Define behavior for rename, linked worktree, nested cwd, missing marker, and disagreement.
- [ ] Verify the entire dataflow through served facade, envelope, Vuoro authorization, and work store.
- [ ] Include unauthorized and wildcard-credential cases.
- [ ] Secondary reviewer performs tenant-distinguishing read-only smoke from two real repository directories.

## L1 lease capability

- [ ] Inventory every consumer of `lease_epoch` before calling backend divergence a defect.
- [ ] Decide token-only versus epoch fencing policy.
- [ ] If epoch fencing is selected, specify expected-epoch inputs and downstream rejection behavior before implementation.
- [ ] Compare SQLite, Postgres, and served histories and document accepted capability differences.

## H1 handoff portability

- [ ] Capture versioned local and served request/response shapes.
- [ ] Name stable common fields and intentional capability differences.
- [ ] Test positive and negative fixtures in both modes.
- [ ] Do not normalize away semantic differences such as unsupported legacy adoption.

## C0-C3 dispatch contracts

- [ ] Approve separate canonical manifest and dispatch-request contracts.
- [ ] Decide whether UI is a full projection or documented subset.
- [ ] Decide whether `kind` and `harness` are required or defaulted.
- [ ] Inventory action classes, skills, kinds, harnesses, priorities, outputs, required fields, and output-to-kind mappings.
- [ ] Test schema, runtime, HTTP, MCP tools/list, MCP execution, and UI projection from one fixture matrix.
- [ ] Reject duplicate literal enum sources outside declared/generated projections.
- [ ] From `apps/web`, run `npm test` and `npm run build` when implementation is ready and authorized.
- [ ] Secondary reviewer independently extracts and compares all sets and subset relations.

## O1-O2 operational CLI

- [ ] Classify each command as implemented, intentionally unavailable, or owner-CLI-only by environment.
- [ ] Prove there is exactly one migration authority per domain.
- [ ] Compatibility inspection does not require construction of an already-compatible ready app.
- [ ] Unavailable operations return truthful, stable machine-readable results.
- [ ] Migration, if approved, uses closed domains, pinned entrypoints, separate credentials, environment confirmation, and no automatic run on serve.
- [ ] Admin, if approved, uses a closed authorized action registry rather than an arbitrary string.
- [ ] Secondary review starts from docs/help and compares parser, exit codes, JSON shapes, environment availability, and implementation.
- [ ] Migration/admin secondary tests use fake adapters and no real database.

## Evidence and closeout

- [ ] Record input/output revisions, commands, cwd, versions, exit status, redacted summaries, fixtures, and fault schedules.
- [ ] Record minimized counterexamples and residual risks.
- [ ] Primary verification passed.
- [ ] Fresh secondary implementation review returned `PASS`.
- [ ] Owning domains accepted residual risks.
- [ ] Dependent units were cleared explicitly; independent units were not blocked by obsolete blanket wave gates.
- [ ] Publication or closeout occurred only after all preceding checks.
