# Model Routing

## Native foreground worker wrapper

Use `agentops dispatch run` when a coordinator needs a bounded worker to run
without interactive prompts and to wake the coordinator on completion. Start the
command as a foreground harness background task; the wrapper does not daemonize
or create a second task system. The task's completion is the wakeup signal, and
`--status-file` is the coordinator-readable result path.

Example (Codex):

```sh
agentops dispatch run --worker codex --model gpt-6-luna \
  --timeout 1800 \
  --worktree /path/to/worktree --status-file /path/to/run-status.json \
  'Implement the bounded outcome; run the named checks. If blocked by an escalation condition, stop and print DISPATCH_OUTCOME: ESCALATED and ESCALATION_REASON: <reason>.'
```

OpenCode Go uses an explicit provider model and requires the caller's boundary
attestation:

```sh
agentops dispatch run --worker opencode --model opencode-go/deepseek-v4.1-flash \
  --data-boundary-attested --worktree /path/to/worktree \
  --status-file /path/to/run-status.json 'Public-repository bounded outcome…'
```

Before setting `--data-boundary-attested`, check the rules below and confirm the
prompt and worktree content are cleared for that external provider. Do not send
queue/work contracts, authority or effect designs, protected/private repository
content, served records, handoffs, telemetry or customer data.

The wrapper validates the selected CLI's help output before starting work.
Codex is invoked with `codex exec -s workspace-write --model MODEL`; it does not
use the rejected `--full-auto` flag. OpenCode uses `opencode run --model MODEL`.
Missing CLIs or unsupported required flags fail before the worker starts, with
a diagnostic. `--timeout` defaults to 3600 seconds; expiration sends SIGTERM to
the worker process group, waits up to `--kill-grace`, then sends SIGKILL to any
remainder. It records `failed` with exit code 124 and appends
`DISPATCH_TIMEOUT` to the stdout transcript. `--kill-grace` defaults to 5
seconds (0 disables the grace period; values above 300 seconds are rejected).
A `running` record
is written before launch and replaced with a terminal record on completion or
SIGTERM (failed, exit code 143; SIGINT and SIGHUP use 130 and 129). On a signal,
the wrapper terminates the worker's isolated process group with SIGTERM, waits
up to `--kill-grace` for the entire process group to exit, then sends SIGKILL
to any remainder and reaps the worker. On the signal path, a second signal
skips the remaining grace; timeout handling always uses the configured grace.
A signal received
while the terminal record is being atomically committed does not change the
committed outcome or process exit code. Worker exit zero writes `done`, nonzero writes
`failed`, and the explicit `DISPATCH_OUTCOME: ESCALATED` marker in the worker's
final message writes `escalated` even if the worker exits nonzero. Include
`ESCALATION_REASON: …` for a concise reason.

The wrapper exits 0 for `done` or `escalated`, preserves a failed worker's exit
code (signal exits map to 128 plus the signal number), and exits 2 for launch
validation errors. `--model` is passed through as supplied; the caller is
responsible for resolving it against aliases in `model-routing.json`.

The atomic JSON status record (`agentops-dispatch-run/v1`) contains outcome,
exit code, branch, head SHA, dirty flag, a bounded/redacted final-message tail
(Codex's final-message file, or OpenCode's stdout text events; it does not copy
the stdout transcript or timeout marker into this field),
escalation reason, UTC start/end timestamps, model and worker. Put it outside
the worktree if the record should not make that worktree dirty. The wrapper
does not pass extra network/effect grants or credentials, and stores no
environment dump or secret values. The worker retains only its native sandbox
and the caller-selected worktree.

If writing the terminal status file fails, the wrapper attempts to write the
terminal result to `<status-file>.fallback.json`. This is a recovery artifact for
the coordinator; it does not make the primary write successful, so the wrapper
exits nonzero if the worker succeeded (exit code 1); otherwise it preserves the
worker's terminal exit code.

After a failed terminal write, the primary status file stays `running`; the
fallback file carries the terminal result. If writing the final transcript to a
closed stdout pipe fails after status commit, the wrapper preserves the
committed worker exit code and status record.

Optional follow-up: a separate watcher may register Vuoro run records and
report outcomes via `register_run` / `report_outcome`; this wrapper intentionally
does not integrate with Vuoro.

`model-routing.json` is the machine-readable source of truth for dispatch model aliases. Repositories may use provider-qualified model strings in runtime configuration, but those values must resolve to an alias in this policy.

## Alias Policy

| Alias | Anthropic model | Codex model | Fallback / status |
|---|---|---|---|
| `clerical` | `claude-haiku-4-5-20251001` | `gpt-5.6-luna` | Read-only triage, polling, formatting, and deterministic closeout; not the default implementation tier. |
| `frontier-default` | `claude-fable-5` | `gpt-5.6-sol` | Claude falls back to `claude-opus-5-5` when Fable is unavailable. |
| `frontier-plan` | `claude-opus-5-5` | `gpt-5.6-sol` | Verified: GPT-5.6 GA 2026-07-09; ID confirmed via OpenAI docs. |
| `frontier-review` | `claude-opus-5-5` | `gpt-5.6-sol` | Explicit high-consequence semantic validation; not the default review tier. |
| `review-synthesis` | `claude-sonnet-5-5` | `gpt-5.6-terra` | Verified: GPT-5.6 GA 2026-07-09; ID confirmed via OpenAI docs. |
| `release-ops` | `claude-sonnet-5-5` | `gpt-5.6-terra` | Strong general model within the calling provider family. |
| `fast-build` | `claude-sonnet-5-5` | `gpt-6-luna` | Operator-selected implementation model; native route verified 2026-10-24. Long-running programmes carry explicit planning and realignment instructions. |
| `standard-build` | `claude-sonnet-5-5` | `gpt-5.6-terra` | Implementation requiring repository discovery, contract inference, or interpretation of non-obvious failures. |
| `hard-build` | `claude-sonnet-5-5` (fallback `claude-opus-5-5`) | `gpt-5.6-terra` | Semantically hard implementation after decisions are settled; unresolved architecture routes to `frontier-plan`. |

The `verified` field belongs to the concrete provider ID, not the alias. The gpt-5.6 tier IDs (`-sol`/`-terra`/`-luna`) were confirmed against OpenAI's GA announcement and Codex model docs on 2026-07-18; recent Codex CLI releases ship them in the built-in catalog, but tier access depends on the authenticated plan (free/Go accounts get Terra only) and older CLI builds (e.g. 0.144.x) may predate the catalog entries. An unverified ID must not become a required default until its provider CLI or official documentation confirms availability.

On 2026-10-24 the operator selected GPT-6 Luna for `fast-build`, superseding
the October 20 GPT-5.6 Luna baseline. A native Codex no-tools request explicitly
using `gpt-6-luna` returned the requested marker. This establishes native route
availability; Cloud model selection, environment access and continuation must
be verified separately. It does not establish comparative outcome quality or
retire other models. Build prompts must name required verification commands.

On 2026-11-03, a devbox running Codex CLI 0.166.0 reported ChatGPT
authentication and completed an explicit `gpt-6-luna` request. Initial model
catalogue requests returned `401 token_expired` warnings without preventing
that execution. In the same persistent session, a plain resume selected the
configured `gpt-5.6-sol` default, warned of the model change, and preserved
conversation context. Resuming with an explicit `--model gpt-6-luna` selected
Luna and warned about the preceding Sol model. Session continuity therefore
does not establish model continuity. When a programme requires a fixed model,
select it explicitly on resume and record the model reported by the runtime;
apply the programme's attempt-boundary rules if the model changes. This is an
observation of that host and CLI version, not proof of billing, quality, or
behavior in other runtimes.

The model alias selects a model, not the worker's authority or stopping rule.
An explicitly approved long-running programme can give Luna responsibility for
discovery, planning, defining missing tests and interfaces, and realigning the
chosen backlog within existing product boundaries. Use the
[long-running worker contract](long-running-worker.md) for that instruction
set. Do not give such a session a bounded-worker instruction that requires it
to stop after its first candidate or seek coordinator approval for ordinary
engineering decisions. Production authority and acceptance remain separate.

`caller_harness_providers` maps a trusted calling harness to the provider
branch used for alias resolution. Claude maps to `anthropic`, Codex maps to
`codex`, and `kimi` is reserved as an extensible family. No Kimi alias branch
is executable until concrete model IDs and a harness adapter are verified.
Multi-provider harnesses need an explicit runtime provider mapping; a
dispatcher must not guess from the harness name.

## Worker Routes (retired)

`model-routing.json` carried a `worker_routes` table (OpenCode-backed workers,
including a `local_workstation` route onto `local3090`) for supervised hybrid
dispatch mode. Hybrid dispatch retired with S2 item 6 (2026-09-17); see
`docs/runbooks/hybrid-dispatch.md` for the historical record of its policy
and driver. Per `docs/plans/2026-09-17-target-state.md` TS-2, model choice
stays harness-native (Claude Code, Codex) and agentops keeps no OpenCode
provider, worker route, or worker qualification data. `model-routing.json`
no longer declares `worker_harness_providers` or `worker_routes`.

## Resolution

Dispatch routing resolves harness, model, and optional reasoning in this order:

1. Explicit action payload values.
2. Concrete action-class overrides.
3. Concrete project defaults.
4. Trusted caller inheritance when the selected default is `caller`.
5. A single configured harness fallback.

After resolving the harness, map it to a provider family and select that
branch of the logical model alias. Same-provider fallback is allowed when
recorded in the branch. Crossing to another provider consumes a different
subscription and requires an explicit action or runtime policy; usage
exhaustion alone is not permission to switch providers.

`frontier-default` is deliberately not a blanket hard-coded value: each
calling provider resolves its own branch and transport-specific availability
before selecting a fallback.

## Work Routing

### Active dogfood practice (2026-11-04)

Status: operator-directed working practice, effective immediately. Take it into
use on real work, assess functionality, and fix or retire it as evidence warrants.
This records the instruction; a policy PR, detailed coordinator plan or separate
qualification project is not a prerequisite to using the practice. Comparative
model quality and automatic routing remain observations to establish.

The unit of ownership is a useful outcome with acceptance criteria. Select Luna
or Terra by semantic complexity and uncertainty, not file count, diff size or
task granularity. Luna can own discovery and planning within a clear outcome;
Terra suits difficult semantic, concurrency, authority or architectural problems.
An obvious minor task can be cheaper for the coordinator to complete directly.

Give the owner the outcome, acceptance criteria, constraints, ownership boundaries
and escalation conditions. Reuse existing requirements and checks. Do not build
a detailed implementation plan merely to make work delegable to Luna. The owner
plans, decomposes, implements, verifies and repairs within the authorized scope,
including native delegation of granular work to cheaper sessions. Ordinary
engineering decisions do not require repeated coordinator approval.

Consider authorized OpenCode Go routes for suitable complete outcomes and for
worker-owned implementation subtasks. Keep runtime model selection explicit and
observe the actual binding; one model's successful result does not qualify another.
Preserve existing data, effect, review and integration boundaries, with one
declared integration owner for overlapping files and target-branch writes.

**External-provider data boundary (OpenCode Go and any non-first-party route).**
An OpenCode Go request leaves the estate for an external model provider. Send
only material that is already public or that the operator explicitly cleared
for that provider: public-repository source and docs, synthetic fixtures, and
self-contained implementation subtasks derived from them. Do not send queue or
work contracts, authority, credential or effect designs, protected-horizon or
private-repository content (appservice, cred-broker, vuoro-cloud operations,
private sprintctl state), served tracker records, handoffs, telemetry, customer
or tenant data, or anything under a data restriction. When an outcome needs
restricted context, route it to a first-party harness instead; do not redact
restricted material into an external prompt. This is why the automatic approval
review rejected sending a detailed queue contract to OpenCode Go on 2026-11-06:
the boundary held, and that request is not to be rerouted.

**Operator amendment (2026-11-08): public lane designs are cleared.** Work-queue,
contract, gate, admission and authority/effect *designs and code that live in
public repositories* (lanectl, agentops, vuoro, sprintctl) are cleared for
OpenCode Go, so DeepSeek lanes can build the lane system itself; keeping them
first-party only pushed that work onto Opus quota. Still excluded: credentials
and secret values, private repositories (appservice, cred-broker, vuoro-cloud
operations), private sprintctl state, served tracker records, handoffs,
telemetry, and customer or tenant data. This supersedes the 2026-11-06 rejection
for public-repository designs only.

Autonomous implementation lanes (2026-11-08): `lanectl` (`/projects/dev/lanectl`,
ADR 0001) runs planner-written WorkReleases through `agentops dispatch run` with
OpenCode Go `deepseek-v4.1-flash` (alias `fast-build`, provider `opencode-go`) in
isolated worktrees, gates them deterministically and lands candidate trains
interactively. Its Definition of Ready refuses `data_class = "restricted"`
releases for external models, enforcing the boundary above.

Use a lightweight deterministic complexity decision when useful; consult an
advisory classifier such as Jev only for ambiguous cases, with abstention and
escalation available. Classify the outcome, not every microtask, and reconsider
when new evidence changes its complexity. This instruction does not qualify the
historical Jev classifier or authorize an autonomous router or effect decision.

Assess through ordinary outcome closeouts: acceptance, coordinator preparation
and intervention effort, review findings, repairs, elapsed time and observed
route. Record them as one
[`outcome-closeout-record/v1`](closeouts/README.md) per outcome (copy
`closeouts/TEMPLATE.json`), with each measurement's basis `measured`,
`estimate` or `unknown`. Record available measurements and label estimates or unknowns. Avoid
duplicate bookkeeping and utilization targets that manufacture work. Adjust the
practice as results arrive; retain useful patterns in guidance and mark failed
ones retired with their evidence. Do not revive the retired hybrid driver.

### Decision feedback planning amendment (2026-11-09)

Status: accepted operator planning direction; implementation interfaces are
proposed. Extend native `agentops dispatch run` status and existing
[`outcome-closeout-record/v1`](closeouts/README.md) evidence with stable links to
[lanectl decision records and capacity feedback](https://github.com/bayleafwalker/lanectl/blob/main/docs/plans/2026-11-09-decision-records-and-capacity-feedback.md),
following the [portable direction](https://github.com/bayleafwalker/vuoro/blob/main/docs/plans/2026-11-09-decision-records-and-lane-feedback.md).
The supplied model is a request; record the runtime-reported model/provider,
runtime version and observation basis separately, including unknown bindings.
Join attempt and accepted-outcome records without duplicating closeout entry or
reviving the legacy route emitter. Existing manual closeouts do not establish
automatic capture.

Lanectl owns allocation/admission; native runtimes retain execution and effective
model binding. Cheap agents and Jev may consume compact, permitted projections;
Jev remains advisory for ambiguous semantic choices. Deterministic gates and
existing acceptance/effect authority remain decisive. Record alternatives,
policy revision, validity, expiry, actual selection probabilities and later
dispositions; confidence scores are not selection probabilities. Scale record
depth with effect class and observe the proposed overhead budget in the lanectl
plan. No new benchmark gate precedes ordinary dogfooding; this instruction does
not promote the historical Jev classifier or change its qualification status.

### Alias guidance

Route implementation by boundedness and uncertainty rather than by diff size:

- `fast-build`: scope and acceptance criteria are concrete, the pattern is known, and deterministic checks can reject a bad result. Local feature work, test additions, contained bug fixes, adapters, and repetitive cross-cutting edits can all qualify.
- `standard-build`: locating the change is part of the problem, a behavioral contract must be inferred, multiple implementations are plausible, or test failures require interpretation.
- `hard-build`: state-machine, authority, parity, migration, or similarly subtle implementation whose architecture is already decided. This is still build work, not permission for the worker to redesign the tract.
- `frontier-plan`: unresolved architecture, ownership, cross-repository sequencing, compatibility boundaries, or backlog realignment. Sol and Opus are decision tiers, not bulk implementation defaults.
- `frontier-review`: selected final validation where a subtle semantic miss has unusually high consequence. Ordinary independent validation remains `review-synthesis`.

Provider ladders are intentionally asymmetric. Luna is the observed bounded
Codex implementation baseline; Haiku remains a clerical/read-only worker.
Anthropic therefore uses Sonnet at different effort levels for code-bearing
build tiers rather than pretending its tiers are equivalent to Codex tiers.

Validation does not have to use a more expensive model to be independent. Fresh context, direct diff inspection, cold checks, and authority to reject are the minimum contract. Use `review-synthesis` for ordinary independent verification and reserve `frontier-review` for high-consequence semantic risk, not every patch.

## Historical local route-decision records

The `dispatch.route.decision` emitter is historical local-dispatch instrumentation, not an active
native-session route recorder. Its producer is the saved `vuoro-dispatch-build` workflow
(`agentops/.claude/workflows/vuoro-dispatch-build.js`, repo-relative) and
`scripts/jev_shadow.py record`; `/projects/dev/AGENTS.md` marks the saved workflow as legacy and
prohibits using it for new work until it is migrated. Do not revive that workflow to create
telemetry. The last workstation snapshot found 80 host-local events from September 28–30, 2026,
none since October 1, and no run reference on those historical events; see
[`docs/evidence/2026-11-03-routing-estate.md`](../evidence/2026-11-03-routing-estate.md) for the
dated query and limits. The implementation can attach a local RunManifest reference, but that
capability is not evidence of current emission or an active producer.

When present, these records describe dispatch-workflow decisions and outcomes. The fields include:

- **Route:** the lane (`build`, `oracle` or `refine`), the tier, and the source (`explicit`,
  `haiku-route`, `explicit+haiku-route` or `route-missing`).
- **Refinement:** the outcome (`refined`, `retired` or `deferred`).
- **Oracle:** its kind (`tests`, `checklist` or `none`).
- **Verification:** the number of repair rounds, the per-item verify verdicts and the
  check-outcome counts.
- **Outcome:** the unit's final state (`confirmed`, `parked`, `unverified`, `retired`,
  `deferred`, `not_built` or `halted`), plus the tier it finally built at.
- **Run:** `{run_id, manifest_digest, status}`, the RunManifest the run emitted at start
  (`docs/contracts/local-run-manifest.md`). `status` is `resolved`, or says why the record is
  unbound (`absent`, `invalid`, `unresolved`, `manifest-invalid`, `digest-mismatch`). Closeout
  results carry `run_citation` (`cited`, `not-cited`, `unbound`). This is a non-fatal check that
  the closeout note carried the `Run-Manifest` line.

Every field is an identifier, an enum or a count. The recorder relays no prose, makes no network
call, and always exits 0. Pass `record_decisions: false` to skip it. Such records measure the
historical workflow's lane/tier choices and outcomes. They do not establish the model or provider
actually selected by a native harness, token usage, subscription allocation, quota, or cost. The
current session-binding observation does not fill this gap: it records session and declared
settings context, not the selected model/provider or an attempt link. Native route telemetry under
the target-state emit-only policy is not established by these historical records.

**Offline Jev scoring.** `jev_shadow.py score` reads recorded decisions back from the
audit shards and rebuilds each unit's item text from sprintctl. It then asks TypeSafe
Jev the pinned `jev/bundles/route-v1.json` questions. `jev_shadow_report.py` measures
agreement with the recorded decision.

- **What is sent:** item title and description, and the manifest's risk-surface ids and paths. `route_state` is the only code that builds it.
- **Key:** the operator's 0600 file named by `TYPESAFE_API_KEY_FILE`. Without it, scoring runs in `fake` mode.
- **Before any decisions exist:** `corpus` and `replay` build and score an item corpus.

Jev is not in the dispatch path. The latest independent evaluation is the
[2026-10-20 W41-R1 comparison](../../jev/eval/agentops-2026-10-20/README.md), which says to keep
production routing unchanged. On 33 held-out attempts from 16 work groups, native Haiku had 60.6%
non-abstaining coverage versus the preregistered 90% minimum, 15.2% joint lane/tier agreement versus
18.2% for the deterministic comparator, and 20.8% group-weighted agreement versus 27.1%. These
historical choices are imitation labels, not independent safety labels; neither arm was qualified
as a safe router, and the comparator was not proposed as a production replacement. False-escalation
and under-escalation counts are disagreement proxies, not measured unsafe outcomes. Actual billed
cost and operator correction time were unavailable, and the Decisions API arm was unmeasured.

The preregistered adoption rule requires every bound to be measured and met: zero independently
labeled unsafe under-escalations, false-escalation rate at most 10%, at least 90% coverage, at least
10% held-out macro-agreement gain, at least 30% measured operator-correction-time savings, and an
actual billed-charge observation. The current evaluation does not satisfy those evidence
requirements. Do not tune on its held-out cases or infer adoption, safety, billing, or provider
entitlement from this comparison. Any future routing change should be supported by a new
independently qualified evaluation, with its disposition recorded consistently with the current
target state; Jev remains advisory and outside dispatch.

Moving any router judgment into dispatch is an operator decision. It needs measured
agreement against recorded decisions and hindsight labels, using a pinned bundle and
model. Never use Jev for credential or effect authorization, for judging an
irreversible operation safe, for arithmetic or date logic, or for any decision whose
facts are not in the state it is sent.

## Reasoning Controls

Reasoning controls are selected by the outcome owner within the authorized
runtime and model scope, using the native runtime's verified interface. Do not
require a frontier coordinator to tune every worker step. Treat unsupported or
unverified controls as absent and record the observed model/binding assurance in evidence. The
retired `actionq-dispatcher` supplies no routing or reasoning behavior.

## Refresh Procedure

1. Update `model-routing.json` only after verifying concrete IDs through a provider CLI or official provider documentation.
2. Inventory live configuration, examples, deployment manifests, and guidance with `rg`.
3. Update each live value to the matching alias policy and retain an explicit fallback where provider access differs.
4. Re-scan for retired IDs. Historical training or archival records may remain only when their historical status is clear.

The shared `model-routing-optimizer` skill carries the repeatable audit workflow.

`scripts/audit_model_routing.py` checks aliases against observed native
catalogues without selecting models, dispatching work or changing runtime
configuration. Pass `--catalogue codex=<models_cache.json>` and
`--catalogue anthropic=<native-probe-results.json>`. A supported fallback does
not hide an unobserved primary, a model in another provider's catalogue cannot
qualify a fallback, and malformed input means **could not check**. The report
records policy/catalogue digests and observed model IDs; it grants no authority.

## Historical Exceptions

- 2026-09-28 move to Sonnet 5.5 / Opus 5.5: the older IDs `claude-sonnet-5` and `claude-opus-4-8` remain only in historical material:
  - dated history notes in `model-routing.json`;
  - lane-loop assessments and plans;
  - harness-evidence and maintenance-lane test fixtures, which record the models that actually ran;
  - `scripts/maintenance_lane_report.py` `MODEL_ALIASES`, which buckets past session tags written as `sonnet`;
  - `session-mechanization/session-capsule.example.json`.

  None of these is live routing.

The dated appservice training records
`docs/training/health-checks/cluster-health-check-2026-03-29.md` and
`docs/training/health-checks/cluster-health-remediation-2026-03-29.md` retain
their original `claude-sonnet-4-6` attribution. They are historical evidence,
not live routing configuration.
