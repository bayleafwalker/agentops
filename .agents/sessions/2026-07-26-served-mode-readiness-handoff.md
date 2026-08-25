# Handover: served-mode readiness and UX robustness

- Cut: `2026-07-26T09:10:00+03:00`
- Objective: complete `served-mode-gaps` and `vuoro-ux-robustness-plan` so
  served mode is safe for ordinary agent use with minimal operator handholding.
- No deployment, Flux, Kubernetes, live backlog, claim, or outbox recovery was
  performed in this session segment.

## Published baseline before this cut

- `sprintctl/main`: `b7c1301` (previous source work already published):
  - `eadc53a`: `work.read.events` catalog operation.
  - `d8bd7fa`: served `event list` CLI path.
  - `c2c28cf`: claim UUID fallback and conservative item-status outbox retry
    guard.
- `kctl/main`: `2187c5c`: direct `vuoro-client` served source; durable event
  ID watermarking; preflight refuses to claim clean without a
  `maintain.check`-equivalent operation.

## Frozen source work requiring review

### Sprintctl #1984 remaining command surfaces

`/projects/dev/sprintctl` is **ahead of origin by one commit**:

```text
c607b48 feat(served): route remaining command gaps
```

It adds the planned source-level operations and CLI paths:

- `work.event.add` / served `event add`, with server-authenticated actor;
- `work.item.create` / served `item add`, with server-side track resolution;
- `work.read.sprint` / basic served `sprint show`; `--watch` polls it
  client-side; `--detail` fails explicitly because its aggregation has no
  catalog operation;
- catalog routes and doctor probe entries for all three operations;
- tests and plan-status updates in the commit.

Do **not** push it without an independent review. Run its focused tests and
inspect authority choices, response-shape parity, `--watch`, and doctor probe
coverage. The builder was interrupted after committing, so no builder test
report was captured in the orchestrator transcript.

Its worktree also has an **unstaged** `.envrc` simplification from the separate
cutover unit; it is not part of `c607b48` and must be handled as configuration
work below.

### Workstation cutover configuration (uncommitted, cross-repo)

The cutover unit was deliberately interrupted before testing/committing. It
left these unstaged changes:

| Repo | Files |
| --- | --- |
| `agentops` | `templates/dispatch/scripts/validate_vuoro_workstation_cutover.py`, its tests, `.envrc.example`, one validation-command correction in `docs/assessments/vuoro-architecture-implementation-plan-2026-07-25.md` |
| `sprintctl` | `.envrc` |
| `box` | `.envrc` |
| `homelab-analytics` | `.envrc`, `.envrc.example`, `AGENTS.md`, `tools/project-env.sh` |
| `scribectl` | `.envrc`, `AGENTS.md` |

The validator changes are intended to fix two confirmed false positives:

1. It previously expected a bare profile name even though sprintctl requires a
   profile **file path**.
2. It scanned commented rollback text as executable direct-backend wiring.

The consumer edits remove shared direct-remote rollback sourcing and require
the served profile in executable config. Review carefully before commit:

- `actionq` has not yet been edited.
- `aligned-equity` is on user branch
  `codex/adopt-working-process-dispatch`; leave it untouched unless explicitly
  coordinated.
- expected `_orchestration` is absent from `/projects/dev`; validator should
  support a deliberate selected-repository subset, but do not redefine the
  full workspace gate as clean.
- Run the validator only after checking all affected env files and commit each
  repository separately. Do not delete pre-existing untracked `.envrc.local`,
  `.claude`, `.agents`, or audit files.

Initial authoritative gate result was a failure from:

```bash
python /projects/dev/agentops/templates/dispatch/scripts/validate_vuoro_workstation_cutover.py \
  --root /projects/dev \
  --profile workstation-vuoro-shared
```

The historical ledger's runtime cutover claim should not be contradicted by
that result: it revealed validator/configuration-policy disagreement and
committed rollback residue. Separate **runtime cutover**, **configuration
conformance**, and **deployment verification** in all follow-up reporting.

## UX robustness audit (no edits)

`docs/plans/vuoro-ux-robustness-plan.md` remains materially unimplemented:

- D2–D8 and D-new-1 lack `repo#id` parsing, repo precedence,
  resolved-context output, universal preflight, marker-less non-local guard,
  taxonomy, and tombstone detection.
- Current `backend.py` still derives repo identity from cwd/path; all relevant
  IDs are Click `int`s; doctor has only generic backend diagnostics.
- Safe pre-policy work: D2/D3 parsing and precedence scaffolding, D4/D6
  context model/rendering, most D5, D8 taxonomy scaffolding, D-new-1 with
  disposable fixtures, docs.

The user supplied the policy direction that resolves UX-plan O1/O6:

- fail closed by default for marker-less `remote` or `served` execution;
- accept explicit `--repo-id` plus an invocation-scoped opt-in flag as
  corroboration;
- do not use a persistent global allowlist bypass;
- daemon/service environments must explicitly identify the repo or use a
  marker; reconcile their environment split separately before daemon D7
  rollout.

The user also supplied required architecture-plan amendments. In
`agentops/docs/assessments/vuoro-architecture-implementation-plan-2026-07-25.md`:

- rename its existing Vuoro CLI `O1`/`O2` to `V0`/`V1` to avoid collision with
  UX-plan labels;
- add Track G (served command completeness, G0–G5), Track I (identity and
  references, I0–I3), and Track U (UX fail-closed robustness, U0–U5);
- make G1–G4 + U1–U3 dependencies explicit;
- rename P2 to configuration conformance and make P1 reconcile the static
  checker with historical runtime cutover evidence;
- add an independent secondary-review checklist covering malformed/mismatched
  refs, precedence, context redaction, markerless behavior, disposable
  tombstone tests, unchanged local behavior, no global daemon bypass, and
  only commands whose G/#1984 paths have landed.

The plan document currently has only an incidental one-line validation command
edit from the interrupted cutover unit. Apply the full user-requested
amendment after resolving or committing that partial agentops work.

## Deployment/release boundary

The current Vuoro work adapter pin is still old (`f750d63` in the local Vuoro
checkout) and cannot expose `eadc53a`, `d8bd7fa`, or `c607b48` operations.
The required wheel release, Vuoro pin bump/tag, and appservice deployment/
Flux reconciliation are **separately authorized appservice/vuoro work**. Do
not perform them from agentops or sprintctl without that authorization. After
an authorized release, verify doctor/catalog and real served calls from both
workstation and devbox-agent.

## Required next sequence

1. Independently review/test `sprintctl` `c607b48`; fix if needed, then push.
2. Review, finish, and separately commit the frozen workstation cutover
   configuration changes; re-run its static gate and clearly report excluded
   `aligned-equity`/missing `_orchestration` status.
3. Amend the agentops architecture implementation plan with the user-provided
   G/I/U tracks and policy/dependency language.
4. Build UX work in bounded units using the recorded O1/O6 direction; use only
   disposable fixtures for remote/tombstone verification.
5. Obtain separate release/deployment authority for Vuoro/appservice, then
   perform live verification.
6. Completion audit must distinguish source, config, released-adapter, and
   deployed-runtime evidence. The persistent goal is not complete.

## Worktree hygiene at cut

Tracked changes are intentionally preserved as listed above. Pre-existing
untracked files remain untouched, including sprintctl/homelab local settings,
actionq/kctl local agent/audit material, and the older agentops handover. No
agents remain running; both build agents were interrupted at this cut.
