# Cross-Repository Backlog — Clean-Room Findings × sprintctl #1164 Capstone

Status: draft backlog, 2026-07-24. Source review: the Vuoro clean-room
comparison record (`docs/assessments/vuoro-clean-room-comparison/`) read
against sprintctl item #1164 (sprint #407, projection-cutover track), and the
external critique in `docs/plans/assessment-review.md`.

## 0. Standing of the assessment-review critique

`assessment-review.md` argues the exercise performed a credible
migration-safety gate but stopped "immediately before the useful experiment":
it never built the integrated Beads+Restate composition, never compared
adapter vs fork, and never measured residual bespoke ownership. The record has
already absorbed most of this critique — the review's revised conclusion and
its Stage 1–4 program are incorporated into
`outputs/strategic-assessment.md`, and **Stage 1 is now complete** for the
pinned Beads revision (`outputs/beads-restate-source-analysis.md`).

Two consequences for this backlog:

- **The strategic work is the primary open question, not a slow-burn extra.**
  Per the critique, "Beads + Restate is not merely an R2 research curiosity;
  it is the primary unfinished buy/adapt hypothesis." The Stage 2 vertical
  slice is the next decisive engineering investment after the #1164 gates.
- **Stage 1 evidence supersedes the review's adapter-first ordering.** The
  review recommended trying a thin adapter before a fork; the source analysis
  has since rejected every adapter variant in the tested deployment (hooks
  fire post-mutation, proxied-server has no receipt seam, raw storage stays
  writable). Stage 2 therefore goes directly to a bounded fork feasibility
  slice or a Beads-as-projection slice. Record this as an evidence-driven
  deviation, not a skipped step.
- **Keep the paperwork-to-engineering ratio honest.** The critique's closing
  observation (452k tokens of audit before the comparison began) is a process
  finding: the next clean-room unit of work should be a locked engineering
  slice with a budget, not another study.

## 1. How the clean-room record relates to the #1164 capstone

#1164 ("Retire split backend mode only after cutover, recovery, and capability
gates pass") is the last pending item in sprint #407. It retires the split
backend and direct-database client code once the served Vuoro substrate has
demonstrably taken over authority and recovery responsibilities.

The clean-room comparison closed its **migration-safety gate** with a
no-migration decision: no tested external composition (Beads-native,
Beads→Restate bridge, Windmill, td control) may take Vuoro authority. The
operating decision is to retain the Vuoro claim/completion authority kernel
and run the reduced profile as a conservative direction.

Implications for the capstone:

- **The capstone is unblocked strategically.** Retiring the split backend
  deepens commitment to Vuoro as the served substrate; the clean-room record
  explicitly endorses operating Vuoro by default. Nothing in the open
  buy/adapt/fork assessment may grant an external candidate authority, so
  Stage 2+ strategic work must not gate or delay #1164.
- **The rollback invariants are compatible but must be sequenced.** The split
  backend is itself a fallback path. #1164's non-scope (retain
  standalone/recovery SQLite authority and retained exports) preserves the
  clean-room rollback invariant, but the export/recovery rehearsal must pass
  **before** removal so retained exports demonstrably substitute for the
  split-backend fallback.
- **#1164's removal diff is a Stage 4 input.** The residual-ownership
  criterion ("remove substantially more bespoke surface than you introduce")
  needs a measured Vuoro/sprintctl bespoke baseline. The split-backend code
  #1164 deletes shrinks that baseline regardless of the eventual
  retain/hybridize/fork outcome — capture the before/after module and line
  inventory as part of the removal PR, so the strategic comparison starts
  from the post-capstone surface rather than a stale count.
- **The reduced-profile finding cuts the other way too.** The sufficiency
  study shows the reduced profile is an invocation discipline, not an enforced
  deployment shape. Removing split-mode code is exactly the kind of
  structural reduction the study asks for — #1164 is evidence generation for
  the `keep-bespoke-reduced` hypothesis, and its removal diff should be
  recorded as such.
- **Execution-boundary design requirements are now written down.** The
  completion-callback contract (execution-ID dedupe, proof/revision rotation
  on transfer/recovery, verification failure as authoritative rejection) is a
  standing requirement on Vuoro for any future executor, independent of the
  capstone.

## 2. #1164 gate ledger (from item scope vs current evidence)

| Gate required by #1164 | Current status | Evidence / gap |
| --- | --- | --- |
| Selected-repo cutover | Done | #1163 dogfood with parity/lag/rollback evidence |
| Deployment-owned migrations, runtime DDL denial (client side) | Done | #1193 |
| Work adapter/catalog + legacy remote-command inventory | Done | #1194 |
| Endpoint/identity workstation cutover | Done | #1195 (project #1195 memory: COMPLETE 2026-07-23) |
| Catalog parity for legacy remote-relevant commands | To verify | Rerun the #1194 inventory against the current catalog |
| Runtime-role DDL denial (deployed) | To verify | Needs appservice-side evidence, not just client behavior |
| Direct credential removal | Open | Workstation and cluster credential sweep |
| vuoro-dev four-domain evidence | Open | No bundle recorded on #1164 yet |
| Export/recovery rehearsal (cross-backend) | Open | Must precede removal (see above) |
| Production promotion evidence | Open | — |
| Explicit operator gate | Open | Record as a decision event on #1164 before removal |

## 3. Backlog by repository

**Filed 2026-07-24.** Item IDs below are live sprintctl items: sprintctl
repo sprint #407 → #1218 (ledger, blocks #1221), #1219 (rehearsal), #1220
(old-client guidance), #1221 (operator gate); #1219/#1220/#1221 block #1164.
Vuoro sprint #427 → #1222 (four-domain evidence), #1223 (promotion evidence),
#1224 (completion-callback contract). Appservice sprint #384 → #1225
(migration job + DDL denial), #1226 (credential removal). Agentops sprint
#428 → #1227 (commit record), #1228 (Stage-4 sheet + baseline), #1229
(Stage-2 slice, blocked by #1227 and #1228), #1230 (reduced-profile
enforcement), #1231 (S-DORMANT), #1232 (resume observations). Cross-repo
dependencies are not representable in sprintctl, so vuoro/appservice items
name sprintctl #1164 in their descriptions; the #1218 ledger is the
cross-repo join point. The doc's item 4 (removal implementation) is #1164
itself, not a separate item.

### sprintctl (capstone execution)

1. **Gate-evidence audit for #1164.** Assemble the ledger above with links to
   concrete evidence for each row; attach it to #1164 as a ref. Identifies
   which of the remaining rows are already satisfied but unrecorded.
2. **Cross-backend export/recovery rehearsal.** Export from the served remote
   authority, restore into recovery SQLite, verify parity, and document the
   operator procedure. This replaces the split backend's fallback role and is
   the hard prerequisite for removal.
3. **Old-client failure guidance.** Verify that a pre-cutover client against
   the retired path fails closed with actionable guidance (the workstation
   `uv` tool at 0.2.0 already reports `schema-version-mismatch: remote schema
   3 vs expected 1` — confirm this is the intended guidance surface and
   upgrade path, and that stale installs cannot write).
4. **Removal implementation.** Delete remote-client bootstrap/mode/split
   backend code, run the full suite, rerun the catalog/CLI parity inventory,
   and update migration documentation. Record the removed-surface diff for the
   reduced-profile evidence stream (see agentops item 12).
5. **Operator gate + rollback record.** Explicit operator decision event on
   #1164; rollback documented as restoring the compatibility release plus
   retained exports.

### vuoro

6. **Four-domain evidence bundle on vuoro-dev.** Produce the evidence #1164
   names for all four served domains and attach it to the capstone.
7. **Production promotion evidence.** Promotion record for the served
   substrate serving sprintctl authority in production.
8. **Completion-callback contract as a Vuoro design requirement.** Encode the
   five execution-boundary requirements (opaque execution ID, pre-transition
   dedupe, proof/revision rotation, verification-failure rejection, executor
   loss changes no authoritative state) as a contract/test in Vuoro so any
   future executor integration starts claim-gated. Check for a
   coordination-mirror item before filing on both sides.

### appservice

9. **Deployment-owned migration job + role split, deployed.** #1193 scoped out
   the manifests; land the migration job, migration/runtime role separation,
   and runtime-role DDL denial in the cluster, and capture the denial evidence
   #1164 needs.
10. **Direct credential removal.** Rotate/remove direct database credentials
    from workstations and non-migration workloads; evidence feeds the gate
    ledger.

### agentops (clean-room continuation — parallel, non-blocking)

11. **Commit the assessment record.** The clean-room outputs, two new run
    directories, fork-map schema, and studies are currently uncommitted in the
    worktree. Commit them so the no-migration decision is durable (leave
    `docs/plans/evidence-needed.md` unstaged per the handover note).
12. **Reduced-profile enforcement and measurement.** Turn the reduced profile
    into an enforced shape (feature gates / absent surfaces with a
    command-level trace), and start scenario-segmented operator/setup/carrying
    cost records. Count any omitted surface that reappears as a background
    dependency as a reduction failure. #1164's removal diff is the first
    structural entry.
13. **S-DORMANT clock.** Seed the fourteen-day dormant observation for the
    retained/reduced Vuoro profile now if not already seeded; report only
    after the full horizon (no substitutes).
14. **H9/resume observations.** Execute `docs/plans/evidence-needed.md`: five
    qualifying resume observations including one multi-agent and one
    idle-gap resume, with a paired manual reconstruction.
15. **Stage 2 vertical slice (strategic assessment) — the decisive
    experiment.** One locked run of the chosen variant only — bounded Beads
    fork with a synchronous fail-closed authorization seam, or
    Beads-as-projection with a sole-writer adapter — per the source-analysis
    minimum design: workers denied raw storage and database credentials,
    bypass test across every transition family, then the full R2 pack, then
    the real-workflow sequence from the critique (import real corpus work,
    claim through Restate, reject stale claimant, dispatch, reject stale
    receipt, accept a verified one, crash and resume, prove no native bypass,
    produce Vuoro-equivalent audit output). Give it an explicit effort budget
    and a fresh locked run ID. It cannot grant authority and must not gate
    #1164. Note: the critique's adapter-first ordering is superseded by
    Stage 1 evidence (all adapter variants rejected at source level).
16. **Stage 4 residual-ownership framework + baseline.** Define the
    measurement sheet (bespoke surface removed vs added, authoritative
    databases, reconciliation loops, upstream patch burden, operator friction,
    segmented carrying cost) and take the current Vuoro/sprintctl bespoke
    baseline **before** the Stage 2 slice runs — incorporating the
    post-#1164 removal diff — so the slice's economics are captured rather
    than reconstructed. The harsh criterion stands: the composition must
    remove substantially more bespoke surface than it introduces while
    keeping exactly one authoritative mutation path.

## 4. Suggested sequencing

1. Now: items 1, 11 (audit + commit the record), and item 16's baseline
   sheet definition (cheap, and it must exist before Stage 2 or the #1164
   removal lands unmeasured).
2. Next: items 2, 9, 10, 6 (rehearsal + deployed-role/credential evidence +
   four-domain bundle) — these close the open gate rows.
3. Then: items 3, 4, 5, 7 (removal, guidance, operator gate, promotion
   evidence) — #1164 closes here; capture the removal diff for the Stage 4
   baseline as part of the removal PR.
4. Parallel slow-burn: items 13, 14 (dormant clock, resume observations).
5. Next major engineering investment after the gate rows close: item 15, the
   Stage 2 fork/projection vertical slice — this is the experiment the
   critique says the exercise stopped short of, budgeted and run-locked.
6. Deliberate, unhurried: items 8, 12 (contract hardening, reduced-profile
   measurement).
