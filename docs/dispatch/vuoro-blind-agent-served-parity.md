# Vuoro blind-agent served parity matrix

Status: **historical source/deployment split, 2026-07-26**. This is the blind-agent
inventory required by the parity handoff. It records Sprintctl source that is
ready to ship separately from the currently deployed Vuoro adapter. It is
**not a claim of deployed parity**: production remains on the adapter assessed
in the handoff below, so its observed unsupported operations remain failures
until an immutable adapter release is pinned by Vuoro and deployed by the
operator.

**Current release clarification.** Vuoro v0.1.9 subsequently received
accepted evidence for its bounded served four-domain catalog. That acceptance
does not clear unattended ActionQ dispatch: claim-incarnation, supervised
renewal, and fault-recovery work are separate operational gates. See
[`vuoro-substrate-simplification-refactoring-assessment-2026-07-26.md`](../assessments/vuoro-substrate-simplification-refactoring-assessment-2026-07-26.md).

The contract is deliberately narrow. A command is **served** only when the
guidance can use it against the selected Vuoro profile without opening a
Sprintctl store. **Unsupported** means it is part of the blind-agent loop but
has no established served equivalent; it must be rejected before store
creation with `served-operation-unavailable`-class guidance. **Recovery-only**
means it deliberately needs local/direct state and must not be offered as the
normal served workflow. Do not treat an existing PostgreSQL/SQLite fall-through
as either served or recovery authorization.

Source evidence is the checked-in guidance named in the first column, the
Sprintctl served route table at
`/projects/dev/sprintctl/sprintctl/served_routes.py`, and the recorded deployed
assessment at
[`../../.agents/sessions/2026-07-26-vuoro-blind-agent-parity-next-devbox.md`](../../.agents/sessions/2026-07-26-vuoro-blind-agent-parity-next-devbox.md).
The latter records the production image verdict, rather than extrapolating
from a newer local checkout. `sprintctl` commit references below identify
implementation that has landed on its `main` branch; they are not acceptance
evidence for an untested future deployment. “Source-ready (deployment
pending)” means the command has a catalog route and direct source tests, but
the deployed adapter does not yet contain it. “Deployed failure” preserves the
observed production verdict rather than reclassifying it from local source.

**Source hardening update.** Sprintctl `bdabf23` classifies all 78 registered
CLI leaf paths as catalog, explicitly local/recovery-only, or unavailable in
served mode. Its callback guard runs before store construction and its
inventory assertion fails if a new command is added without a classification.
This prevents source-level accidental SQLite/PostgreSQL fall-through; it does
not establish that the currently deployed adapter contains the guard.

## Orientation and selection

| Guidance source | Prescribed command or operation | Status | Evidence and required disposition |
| --- | --- | --- | --- |
| workspace `AGENTS.md` / devbox start | `sprintctl doctor --json` | served | Recorded as a successful served read in the handoff; catalog probing is part of `doctor`. |
| `task-pickup` step 1 | `sprintctl sprint list --active --json` | served | `sprint.list` routes to `work.read.sprints`; its served implementation forwards `active_only` (`cli.py:sprint_list`). |
| `task-pickup` step 1 | `sprintctl sprint list --include-backlog --json` | served | Same `work.read.sprints` route; the served implementation forwards `include_backlog`. Project-wide `--project` has a separate, deployment-pending aggregate route. |
| unattended-dispatch binding prerequisite | `sprintctl sprint create --name ... --status active --json` | source-ready (deployment pending) | `work.sprint.create` landed in Sprintctl `1aa8cc3`. It is repository-scoped and requires the distinct `work:sprint` authority, so a release/deployment must explicitly grant it to an authorized operator; it does not widen normal claim/lifecycle permissions. |
| `task-pickup` step 3; `sprint-resume` step 3 | `sprintctl claim list-sprint --sprint-id <sprint-id> --json` | source-ready (P0; deployment pending) | `work.read.claims` route landed in Sprintctl `934ceb6`/`c199961`; production still has the handoff’s direct PostgreSQL fall-through and misleading `psycopg` advice. |
| `task-pickup` step 4 | `sprintctl next-work --sprint-id <sprint-id> --json --explain` | source-ready (P1; deployment pending) | Atomic `work.read.next-work-explain` landed in `8b585a6`; it is not yet available from the deployed adapter. |
| `task-pickup` step 6; `sprint-resume` step 3 | `sprintctl item show --id <item-id> --json` | served | `item.show` routes to `work.read.item`; served output includes events, active claims, refs, and dependency fields (`cli.py:item_show`). |
| `task-pickup` step 6 | `sprintctl item ref list --id <item-id> --json` | source-ready (P0; deployment pending) | `work.read.item` item-scoped reference view landed in `934ceb6`; deployed behavior remains the observed direct-store fall-through. |
| `task-pickup` step 6 | `sprintctl item dep list --id <item-id> --json` | source-ready (P0; deployment pending) | `work.read.item` item-scoped dependency view landed in `934ceb6`; deployed behavior remains unavailable. |
| `task-pickup` step 7; `sprint-resume` step 4 | `sprintctl claim start --item-id <item-id> ... --json` | deployed served | `claim.start` routes to `work.claim.start`; the deployed verdict includes claim start. |
| shared/project orientation | `sprintctl usage --context --sprint-id <id> --json` | source-ready (P0; deployment pending) | Atomic `work.read.context` landed in `3ac6cac`, with snapshot-isolation regression evidence in `fa1ccc7`; deployed behavior remains the handoff’s direct PostgreSQL fall-through and integer-only scope. |
| shared/project orientation | `sprintctl usage --context --project --json` | source-ready (P1; deployment pending) | `work.project.context` landed in `43cab10`. The served CLI treats the client path as presence-only and never reads `project.toml`; the owner requires a canonical server binding and authorization for every member before member reads. |
| project orientation | `sprintctl sprint list --project ... --json` | source-ready (P1; deployment pending) | `work.project.sprints` landed in `43cab10`, preserving the existing bare JSON array of origin-tagged sprints. It fails closed without the canonical server binding and all-member authorization. |
| project orientation | `sprintctl sprint show --detail --json` | source-ready (P1; deployment pending) | Server-side `work.read.sprint-detail` landed in `4cc02c0`; it does not make project-wide orientation available and is not in the deployed adapter. |

## Inspect, claim, resume, and iterate

| Guidance source | Prescribed command or operation | Status | Evidence and required disposition |
| --- | --- | --- | --- |
| `sprint-resume` step 3 | `sprintctl sprint show --json` | served | `sprint.show` routes to `work.read.sprint`; basic show is in the deployed happy path. Use `--id repo#id` when a scoped identifier is needed. |
| `sprint-resume` step 3 | `sprintctl item list --sprint-id <id> --json` | source-ready (P0; deployment pending) | Repository-scoped `work.read.items` landed in `934ceb6`; the deployed command remains the observed direct PostgreSQL fall-through. |
| `sprint-resume` step 3 | `sprintctl claim list --item-id <item-id> --json` | source-ready (P0; deployment pending) | Non-secret `work.read.claims` inspection landed in `934ceb6`/`c199961`; deployed behavior remains unavailable. |
| `sprint-resume` step 3 | `sprintctl claim resume --instance-id <id>` / `--runtime-session-id <id>` | source-ready (P0; deployment pending) | Safe served resume/read behavior landed in `934ceb6`/`c199961`; it does not expose bearer proof. Production has no established served equivalent. |
| `sprint-resume` step 4 | `sprintctl claim heartbeat --claim-id ... --claim-token ...` | served | `claim.heartbeat` routes to `work.claim.arbitrate`; deployed happy-path evidence includes heartbeat. |
| `sprint-resume` step 5 | `sprintctl agent-protocol --json` | served (static) | Local command-shape help only; it neither opens a store nor establishes server state. Keep its examples aligned with served command contracts. |
| `sprint-resume` step 7; `item-done` step 2 | `sprintctl event add --sprint-id <id> --item-id <item-id> ...` | served | `event.add` routes to `work.event.add`; the deployed verdict includes event creation. |
| blind-agent shaping requirement | `sprintctl item ref add` / `item ref remove` | source-ready (P0; deployment pending) | Repository-scoped `work.item.ref.*` writes landed in `934ceb6`; deployed agents cannot yet shape refs through the adapter. |
| blind-agent shaping requirement | `sprintctl item dep add` / `item dep remove` | source-ready (P0; deployment pending) | Repository-scoped `work.item.dep.*` writes landed in `934ceb6`; deployed agents cannot yet shape dependencies through the adapter. |
| `sprint-resume` step 8 | `sprintctl claim handoff --claim-id ... --claim-token ...` | served | `claim.handoff` routes to `work.claim.arbitrate`; deployed happy-path evidence includes handoff. |
| `sprint-resume` step 8; workspace switching guidance | `sprintctl handoff --sprint-id <id> --output <path>` | source-ready (P0; deployment pending) | Tracker snapshot plus authenticated record operations landed in `89b22b8` and machine-safe/unconfirmed-record handling in `0fe7e72`; deployed behavior remains unavailable. |
| `sprint-resume` step 9; `item-done` step 4 | `sprintctl item done-from-claim --id <id> --claim-id ... --claim-token ...` | source-ready (P0; deployment pending) | Durable atomic authority operation landed in `791786b` and was made replay-safe in `c9cdc07`, `067186b`, and `7b9da6a`; deployed behavior has no served route. |
| close/release part of the loop | `sprintctl claim release --claim-id ... --claim-token ...` | served | `claim.release` routes to `work.claim.arbitrate`; deployed happy-path evidence includes release. |
| `sprint-resume` steps 4 and 9 | `.sprintctl/claims/claim-<item-id>.token` | recovery-only | Local proof persistence is a crash-recovery aid. It must never be inferred as server truth and must not be passed to agents. |
| `sprint-resume` step 10 / `item-done` step 5 | `sprint-snapshot` | recovery-only | Repository-generated projection/snapshot workflow, not a Vuoro served authority operation. It cannot substitute for tracker reads or handoff. |

## Knowledge handoff and preflight

| Guidance source | Prescribed command or operation | Status | Evidence and required disposition |
| --- | --- | --- | --- |
| `kctl-extract` step 2 | `kctl preflight --sprint-id <id>` | source-ready (P1; deployment pending) | Sprintctl `071f747` adds the owning `work.maintain.check` read and Kctl `9954f2b` consumes it directly. The currently deployed adapter does not contain either artifact, so its failure remains deployed evidence until release acceptance. |
| `kctl-extract` step 2 | `sprintctl maintain check --sprint-id <id>` | recovery-only | Direct-store diagnostic with no served equivalent; retain only for separately authorized recovery, not normal blind-agent execution. |
| `kctl-extract` steps 4–9 | `kctl extract --sprint-id <id> --basis-git-revision <full-commit>`, `kctl review list/show/approve/reject`, `kctl status` | source-ready (deployment pending) | Kctl `b3b6dac` serves extraction, UUID-based list/show/approve/reject/status without opening SQLite. Extraction requires an explicit full immutable Git commit, derives/digests candidates deterministically, and invokes `knowledge.candidate.intake`; it does not infer `HEAD` or write a local candidate/watermark store. |
| `kctl-extract` step 10 | `kctl publish`, `kctl render` | unsupported | Publication/render remain kctl-owned persistence/output operations in the checked-in CLI. No served blind-agent acceptance evidence exists; keep them outside the normal loop pending an explicit domain decision. |

The existing Kctl adapter catalog is not a CLI composition: `kctl extract`
still writes a local SQLite candidate/watermark store after its served event
read, and review/status commands open that same store. Completing this domain
requires (1) Kctl served facades for candidate intake/list/show/review and
publication-reference reads, and (2) the decided evidence-bearing
event-to-candidate composition below.
Kctl source `c21dffe` now makes repository-bearing knowledge operations
envelope-scoped and verifies their record arguments before application calls;
it is deployment-pending and does not itself make the local CLI served.
Publication, render, and export remain Git-owned projections unless a
separate ownership decision changes that boundary.

### Served Kctl extraction evidence decision

The authority choice for served extraction is an **explicit immutable CLI
input**. `kctl extract` must require `--basis-git-revision <full-commit>` in
served mode. The value must be a complete 40- or 64-hex Git object ID supplied
by the invoking dispatch composition; Kctl must validate it and must never
derive it from a mutable checkout, branch, or abbreviated revision.

Kctl owns the deterministic event-to-candidate transformation. For each
selected Sprintctl event it must canonicalize the candidate, compute
`content_digest` from `summary` and `detail`, and invoke
`knowledge.candidate.intake` with:

- the explicit commit in `candidate.basis_git_revision` and the invocation
  basis revision;
- the computed candidate content digest; and
- an idempotency key derived from repository identity, source event identity,
  Git basis, and content digest.

The central Kctl application remains responsible for recomputing the digest,
rejecting content/evidence mismatches, and rejecting a changed replay. Served
mode must not create or advance local SQLite candidates or extraction
watermarks. Its durable progress is the central candidate identity and
idempotent intake result; rereading the append-only Sprintctl event stream is
safe.

Sprintctl event metadata is not the Git authority. Its event payload may carry
incidental `git_sha` data, but `work.read.events` does not guarantee immutable
Git provenance for every knowledge-bearing event. A new catalog aggregate is
also out of scope: Vuoro composes the existing Sprintctl read and Kctl intake
without becoming a third knowledge or Git authority.

## Implementation and release queue implied by this inventory

Sprintctl source-ready work awaiting release is: `usage --context`; `item
list`; ref/dependency list and mutations; claim list/list-sprint/show/resume;
tracker `handoff`; `item done-from-claim`; `next-work --explain`; sprint
detail; authorized `sprint create`; and the exhaustive served command guard.
The adapter release must include at least `7b9da6a`, `4cc02c0`, `1aa8cc3`, and
`bdabf23`, then Vuoro must pin that immutable artifact and an operator must
deploy it. The deployed composition must grant `work:sprint` only to the
intended operator identity. Only post-deploy black-box calls may replace the
deployed-failure wording above.

The project-orientation source contracts now exist, but a released Vuoro
composition must construct the guarded aggregate from an immutable canonical
binding before either command is callable in a served profile. Remaining
source decisions are knowledge CLI composition. `kctl preflight` must fail
visibly when an older deployed profile lacks `work.maintain.check`; it must
not recommend PostgreSQL support or a direct fallback. The matrix intentionally
does not turn any of these into direct-mode instructions.
