# Meta-narrative plan — 2026-08-29 (rev. 2, alignment-amended)

**Supersedes** `cross-repo-dogfood-plan-2026-08-28.md` (rev. 4). That plan's
findings survive; its shape does not.

Scope: everything under `/projects/dev` — about fifty repositories — classified
by the value it provides, not by whether a gate has been written for it.

---

## 0. Why rev. 4 is superseded

Three defects, each verifiable:

1. **It governed ten repositories out of fifty, and misjudged which ten.** It
   listed `hostproto` as one dormant repo blocked on a P0. `hostproto` is a
   seven-repo constellation — `hostproto`, `-semantics`, `-dap-core`,
   `-dap-debugpy`, `-dap-delve`, `-mcp-playwright`, `-a2a-worker` — every one of
   which was committed to on 2026-08-28. `vuoro-cloud` (79 commits in eight
   weeks, committed today) does not appear in the plan at all, and it is the
   repository that states Vuoro's product sentence. `browser-workbench` is alive.
   `bindery-core` (99 commits) holds the only complete accept/reject/merge
   dispatch cycle on record and is mentioned nowhere.

2. **It hand-wrote its gates while the workspace already contained two machines
   for deriving gates from intent.** Vuoro's own direction document §7.1
   classifies every candidate check into five kinds and admits only two as
   permanent. `acceptance-lab` turns requirements into executable acceptance
   records over mechanism, quality, authority and economics. Neither was used.
   D1–D8 were written by hand and then treated as settled.

3. **The `dispatchable` promotion gate measured a label, not value.** An
   adoption level promoted "from receipts on record" is a receipt that a receipt
   exists. Deleted below, with reasons that generalise.

The correction is not a longer plan. It is a plan that derives its checks from
what the projects are *for*, and that treats a check nobody can trace to an
intent as a defect in the check.

---

## 1. The intent, stated once

Vuoro's own sentence, from `vuoro-cloud/README.md`:

> **Keep long-running agent work resumable — and know which result actually counts.**

Two halves. *Resumable* is recovery. *Which result counts* is settlement. Every
project below earns its place by serving one of them, by consuming something
that does, or by being honestly adjacent.

Three actors read this system, and a thing that only one of them can read is not
yet finished:

- the **operator**, deciding what to do next;
- the **agent**, resuming work it did not start;
- the **future reader**, reconstructing why a result was accepted.

### The state of the intent, measured today

`sprintctl next-work` works in every repo scope — the served result-schema P0 is
fixed, released and deployed.

**Correction, rev. 2.** Rev. 1 led with `sprintctl session resume` returning
`served-operation-unavailable` and called it "the gap between intent and system,
in one line". That was **label treated as proof**, which is the exact error this
plan diagnoses in others. Two independent reviews caught it, and reading the
implementation settles it:

```python
@session.command("resume")
def session_resume_cmd(...):
    """Show a combined resume surface (context, next-work explain, and git context)."""
```

`resume` is a **convenience aggregate**, and all three of its components are
served today, as are `handoff`, `context-candidates` and `reservation list`. Its
absence costs six commands, not a capability. An operation named `resume` is not
evidence that resumption works, and its absence is not evidence that resumption
is broken.

**So the honest statement of the primary product question is:**

> Resumability is **unproven**, not simply broken. Nobody has run the outcome.

The outcome that would settle it: from a **fresh process with no local cache,
after interruption, through the served backend**, recover session identity, work
authority, checkpoint, and exact revision. That is a black-box scenario, and it
is the first move in §10 — write it so it fails, then make it pass. Whether the
fix is the missing aggregate, a compatibility rollout across mixed service
versions, or something not yet visible is a question the scenario answers and
speculation does not.

## 2. What replaces D1–D8

Vuoro §7.1 already specifies the classification. Applied to rev. 4's gates:

| Gate | Kind | Disposition |
|---|---|---|
| D1 served sprint + resume from a fresh shell | essential workflow outcome | **Keep.** Currently unmet by the substrate — `session resume` is unserved. This is a defect to fix, not a bar consumers must clear. |
| D2 exact-revision receipt from gating runs | essential workflow outcome | **Keep.** This *is* "know which result counts". |
| D3 rebuild gate | essential safety/recovery invariant | **Keep.** Implemented and released. |
| D4 agent writes through `credctl exec` | essential safety invariant | **Keep, scoped.** It binds when an unattended agent first writes, and not before. Today's agents are supervised; enforcing it now protects nothing. |
| D5 independent exact-head evaluation | essential safety invariant | **Keep.** The strongest single expression of the second half of the intent. |
| D6 interrupt/resume and revocation fault cases | essential safety/recovery invariant | **Keep.** |
| D7 human review policy | not a gate | **Move.** It is standing policy (rev. 4 §4, unchanged), not an admission criterion. |
| D8 NARROW scorecard per packet | not a gate | **Move to telemetry** (§7). A measurement that never blocks anything is an instrument, not a bar. |
| `dispatchable` promotion | incumbent convenience | **Delete.** |

**The arithmetic, stated explicitly.** Six rows are kept (D1–D6). They become
**five scenario families** only because D2 and D5 combine into one path — receipt
plus independent evaluation is a single journey, not two bars. Rev. 1 said "five
permanent invariants" over a six-row table without saying why.

**Every scenario needs an admission subject.** A gate with no subject is a gate
that applies to everyone, which is how D1 became something consumers were
expected to clear rather than something the platform owes them:

| Scenario family | Subject |
|---|---|
| D1 resumability | platform deployment |
| D2+D5 receipt → evaluation → settlement | individual workflow result |
| D3 rebuild | provider release |
| D4 guarded write | unattended-write mode, once enabled |
| D6 fault cases | platform deployment |

Consumer integration is a subject too, and no surviving scenario carries it —
which is a finding, not an omission to paper over: the seam-generalisation
question needs its own scenario written.

**`CONDITIONAL` must not become D8 wearing a better hat.** A conditional verdict
carries machine-readable conditions, a named owner, and a re-evaluation trigger
or expiry, or it is not a verdict. **Applicability is separate from verdict**:
"not enabled" (D4 today) is not "conditionally accepted".

**The engine.** `acceptance-lab` is the workspace's evaluation organ and it is
idle — four commits in eight weeks. Its architecture is already the one this
workspace has converged on independently: an append-only hash-chained event log
that is authoritative, disposable rebuildable projections, deterministic scorers,
CI exit codes, zero runtime dependencies. It emits `PASS` / `CONDITIONAL` /
`FAIL` over mechanism, quality, authority and economics. Twenty-two of its tests
pass today; only its jsonschema-dependent schema validation fails, on a missing
dev dependency.

The five scenario families become acceptance-lab scenarios.

**Evaluation is subordinate to settlement.** Rev. 1 said "the score is the
disposition". That gives acceptance-lab authority it must not have: if a score is
the decision, changing a scorer silently changes history and the test runner
becomes king. The durable path is:

```
gating run → exact-revision receipt → version-pinned EvaluationRecord
           → authorized SettlementRecord → auditctl
```

An evaluation **pins scenario and scorer revisions**. A score is *evidence used
by* settlement, never the authority decision. **Vuoro owns which result counts;
acceptance-lab is a replaceable evaluator** — and by the build-versus-buy test
below, that is precisely the split: the evaluator may be replaced, the settlement
record must survive its replacement.

Correction: acceptance-lab runs **15 passed, 7 skipped** — the jsonschema tests
skip, they do not fail. Waking it is an install, not a repair.

**The build-versus-buy test**, applied verbatim, and it is the owner's own:

> If replacing the provider makes this feature irrelevant, buy or adapt it. If
> the information must survive provider replacement to preserve intent,
> authority, evidence, recovery, or learning, Vuoro owns the contract.

---

## 3. The workspace by role

Roles are claims about value, and each is falsifiable.

**Coverage.** This classifies **37 repository slots**, counting the hostproto
constellation as seven. Rev. 1's "about fifty repositories" counted directories,
not classified slots. Twelve git repositories remain unclassified —
`bindery-ra2-adapter`, `china_traveling_2025`, `cred-broker-public`,
`datacluster-template`, `fsharp-the-world`, `ha-elisa-kotiakku`,
`homelab-gitops-template`, `kotona-notes-private`, `outctl`, `reverse-collapse`,
`sprintctl-bootstrap-template`, `vuoro-bounded-output-starter` — and naming them
is better than a round number that covers the gap.

**Constituent — inside the intent.** These implement resumability or settlement.
`vuoro`, `vuoro-cloud`, `sprintctl`, `auditctl`, `actionq`.

**The hostproto constellation, enumerated and classified separately.** Rev. 1
promoted all seven to constituent on the strength of recent activity plus one
ingress edge. Activity is not ratification, and code coupling proves drift and
integration, not leverage:

| Repo | Role | Basis |
|---|---|---|
| `hostproto-semantics` | constituent | owns the ingress semantics `vuoro-evidence` decodes |
| `hostproto` | constituent | the conformance study and spec lineage |
| `hostproto-dap-core` | provisional | adapter; producer-side generality shown |
| `hostproto-dap-debugpy` | provisional | adapter |
| `hostproto-dap-delve` | provisional | adapter |
| `hostproto-mcp-playwright` | provisional | adapter |
| `hostproto-a2a-worker` | provisional | adapter |
| `browser-workbench` | provisional | the intended consumer, unproven as one |

**Provisional** means: producer-side generality is demonstrated, consumer-side
leverage is not. It resolves when one measured generic consumer runs — which is
the consumer-integration scenario §2 says is missing.

Two corrections rev. 4 owes:

- **hostproto's coupling to Vuoro is real and lives in code, not documents.**
  `vuoro-evidence`'s one live ingress edge is HostProto. Vuoro's planning documents name `hostproto`,
  `scribectl` and `browser-workbench` zero times. Both readings were of real
  evidence. They do not contradict each other: the coupling is in code the
  planning documents do not know exists — in a package that was untracked and
  whose sources had been deleted until yesterday. That is one measurement of the
  drift between written intent and built system, and it is the reason this plan
  exists. **Correction:** rev. 1 extended this to `scribectl` and so listed it as
  both consumer and constituent. It is a **consumer**, and that is the point of
  it — its independent worth is what makes it a real test of the seams, not a
  demotion.
- **outctl is retired, and the contradiction was mine.** I read an 08-28 commit
  date on `vuoro-evidence/ingress/command_capture.py` as evidence of current work.
  It is old retired work that was published on that date. *Owner ruling
  2026-08-29: outctl is retired and killed fully, unless new evidence suggests a
  better niche or product direction.* The command-capture ingress lane is
  therefore historical, and `vuoro-evidence` has one live ingress edge, not two.

  Worth keeping as a method note, because this plan is about exactly this: a
  commit date is not evidence of intent. I inferred a status from repository
  metadata and stated it as a finding. The classification in §2 exists to stop
  that, and it did not, because I applied it to the gates and not to myself.

  A narrow-retention option was proposed in review — outctl surviving as a
  replaceable command-evidence ingress adapter owning capture, redaction and
  local spool. The owner ruling supersedes it: retired and killed fully, unless
  new evidence suggests a better niche or product direction. The option is
  recorded here so the next investigator sees it was considered and declined,
  not overlooked.

  **Open decision:** `vuoro-evidence/ingress/command_capture.py` and its
  registration are live code for a retired lane. Leaving them invites exactly the
  inference I made. Deleting them, with git history retaining the work, is the
  reviewer's recommendation and mine — noting the consequence that the recovered
  `test_ingress.py` covers that lane and would shrink with it. Owner call.

**Consumer — proves the substrate by using it.** `scribectl`, `bindery-core`,
`homelab-analytics`, `frontier-weave`, `kotona.app`.

`homelab-analytics` earns particular weight precisely because it is *not* agent
infrastructure. It is the household domain, publicly published with CI, with
bronze/silver/gold boundaries and explicit lineage. A substrate that serves only
its own tooling has proved nothing.

`bindery-core` is the anomaly worth acting on: 17% of all measured spend, the
only complete accept/reject/merge dispatch cycle on record, and absent from every
plan. Whatever made that cycle work is the most valuable undocumented thing here.

**Provider — capability the intent depends on but does not own.**
`cred-broker` (authority), `local-inference` (execution; Vuoro's plane table
already names it `local3090`), `gitops-nixos` and `appservice` (deployment),
`kctl` (projection).

**Adjacent — real work, correctly outside.** `cv-studio`, `render-fabric`,
`wizard-valley-world-window`, `worldwindow-kernel`, `aligned-equity`, `litany`,
`box`, `knowledge-base`, `datacluster`, and the rest. Adjacency is a decision,
not neglect. They may consume the substrate; they owe it nothing.

**Dormant by choice, with the condition written down.** `actionq-dispatcher`
(tombstoned), `cluster-alignment-mvp`, `flowlab`, `sprintctl-orchestrator`,
`acceptance-lab` — the last of which §2 wakes.

---

## 4. External providers — where they are actually called for

Vuoro's plane table (`docs/plans/2026-08-22-long-term-direction.md` §6) is the
authoritative list, and it already answers this. Planes are an operator taxonomy,
not six services to stand up.

| Plane | Named providers | Status here |
|---|---|---|
| Work and tracking | Sprintctl, GitHub, Jira, **Beads**-class | Sprintctl incumbent. Beads is an open prior. |
| Coordination | ActionQ; **Restate, Hatchet, DBOS, Temporal**-class | ActionQ incumbent until a challenger qualifies. A Restate pilot is decided-but-unbuilt. |
| Execution | Codex, Claude Code, OpenCode, **`local3090`**, CI, Kubernetes | `local-inference` is `local3090`. It is running and unwired. |
| Authority and policy | OIDC, **OPA, OpenBao** | cred-broker holds this seam. |
| Evidence and provenance | Git, object storage, Auditctl | Held. |
| Observability and analytics | **OpenTelemetry, Prometheus**, evaluation products | The largest genuine gap (§7). |

Three specific answers:

- **Beads and Gas Town** are "useful challengers and sources of design evidence,
  not proven replacements", and the five-lane comparison is *written and never
  run*. So the honest status is not "time-box or delete" — it is that an
  unresolved assumption is being carried as though it were a result. Run Lane 1,
  or record that the prior is being carried deliberately.
- **Temporal-class durable workflow** is called for by the plane table as a
  challenger to ActionQ, under §7.2's controls, and by nothing else. It is not
  called for by the dogfood loop.
- **`AgentOps.io (external market sample)`** — carry it in the challenger
  landscape under exactly that label, distinct from the local `agentops`
  repository and from any chosen Vuoro surface. The capability it would own —
  cross-run observability, cost attribution, evaluation — is already present in
  the plane table, so the named product is not introduced until requirements show
  that buying or adapting it beats the existing components. *Owner clarification
  2026-08-29.* It is a comparator in the observability-and-analytics
  plane — evidence about what that market provides — and it stays a comparator
  unless something material changes in acceptance-lab's evaluation surface. It is
  not a called-for provider and needs no plane-table entry. I had conflated it
  with the local `agentops` repository, which is unrelated to it.

---

## 5. Making the environment usable

The rollout is small, because most of it already exists and is merely unwired.

1. **Serve `session resume`.** The named product capability, unavailable on the
   only supported backend. Everything else here is smaller than this.
2. **Environment parity on devbox-agent.** `.envrc` and served markers for
   hostproto, cred-broker, auditctl, kctl; sprintctl 0.3.3. `.envrc` is
   gitignored, so the workstation fix did not propagate — the parity itself is
   the defect, not the missing files.
3. **Wake acceptance-lab**: add the `jsonschema` dev dependency so `make
   validate` passes end to end, then encode the five invariants as scenarios.
4. **Qualify `local3090`** — smaller than rev. 1's "wire it up". A harness
   profile already exists at `qualification.state: preflight_observed`, blocked
   on exactly two named probes: `contained-identity` (satisfiable today — the
   `agentworker` identity exists) and `provider-qualification`, plus a version
   repin from 1.18.21 to the installed 1.18.23. Its measured envelope is
   context-disciplined bulk work: no session limit and no per-token cost, but one
   model in 24 GB with an asymmetric ~100s swap cost, so excursions must be
   batched, and TTFT degrades 0.74s at 2K to 24.8s at 64K — a large window is not
   permission to use it.
5. **Converge the remaining `vuoro-service` digests** (`vuoro-dev`,
   `agent-cockpit`), which now also requires migrating their identity registries
   to `principal_id`.
6. ~~**Give `hostproto` a git remote.**~~ **Withdrawn — the claim was false.**
   Verified 2026-08-29: all seven hostproto repositories and `browser-workbench`
   have reachable remotes and **zero unpushed commits**. Rev. 1 inherited "no git
   remote" from rev. 4 and did not check it. That is the third inherited claim
   this plan has had to retract, which is itself the argument for §8's rule.

   The real prerequisite in its place: **inventory the served deployment
   topology** — deployments, image digests, served catalogs and `principal_id`
   migration state — *before* touching resumability. With mixed service versions
   in play, serving a contract is a compatibility rollout, not an endpoint
   addition, and it should be additive so it can be disabled without disturbing
   `next-work`.

---

## 6. Workflows that actually use the projects

A workflow counts only if removing the project breaks it.

- **Work intake** — served sprintctl is the authority; `next-work` works; resume
  does not yet. One workflow, one authority.
- **Verification → settlement** — a gating run emits an exact-revision receipt to
  auditctl; acceptance-lab scores it; the score, not the writer's own claim, is
  the disposition. This is D2 and D5 as one path instead of two gates.
- **Agent write** — `credctl exec` when unattended writes begin (D4).
- **Evidence ingress** — HostProto and command-capture into `vuoro-evidence`,
  reduced by one host-agnostic reducer. Live in code today.
- **Session record** — §7.

---

## 7. Telemetry, session notes, qualitative assessment

This is the weakest organ and the one the meta-narrative mode depends on most.

**Read these as the loop working, not as an indictment.** *Owner position
2026-08-29:* finding defects like these is the entire reason for dogfooding.
These are pre-alpha tools being used for real work; the applications are stronger
because the defects surfaced against real sessions rather than against fixtures.
The items below are therefore a work list, not a verdict on the substrate.

Measured state:

- **Session cost: the over-count is real (reproduced at 5.93×) but it is a
  *consumer* bug, and it is recomputable.** Rev. 1 said the error was inherited
  by the immutable store and could only be handled by forward correction plus a
  published conversion. That is wrong. `log-session-cost.sh` emits one cumulative
  snapshot per assistant turn *by design*, and `cost-summary.sh` already reduces
  `group_by(.session) | last` before aggregating. The 5.93× appears only when
  rows are naively summed. `metadata.session` survives in both the NDJSON shards
  and `auditctl.db`, so a corrected figure is a `GROUP BY session, MAX(cost_usd)`
  away.

  This is the store's own architecture working exactly as designed — append-only
  authoritative log, disposable rebuildable projections — and `auditctl rebuild`
  already exists. **Rebuild the projection; do not publish a conversion factor
  for a number that can simply be recomputed.**
- **69% of `workflow.session` events are test fixtures**, one named
  `sess-poison`. 318 of 473 rows in `_artifacts/agentops/audit/` are fixtures.
  The 2026-08-26 ruling retired the derived index only; the authoritative shards
  still carry them.
- **All spend percentages are withdrawn as evidence.** Rev. 1 argued from "31%
  to agentops" and "17% to bindery-core". Since the error varies by session and
  row count, those figures are **not decision-grade** and must not vote on
  priorities. They are struck until recomputed. `bindery-core` still deserves
  attention — but because it holds the only complete accept/reject/merge cycle on
  record, which is a fact about what happened, not a number.

Three fixes, in order:

1. **A published conversion is insufficient for a variable error.** Instead: a
   versioned `cost_v2` computation; exact per-session replay wherever raw
   provider usage survives; append-only correction and supersession records where
   it does not; rebuilt projections defaulting to corrected values; and explicit
   uncertainty where exact recovery is impossible. Capture whatever raw provider
   usage signal makes replay possible going forward, so this cannot recur.
2. **Partition fixtures semantically, not physically.** Stream, namespace and
   provenance, with enforcement at ingestion. Physical shard separation is one
   implementation choice and not the requirement. Preserve the historical fixture
   records and **append** their corrected classification — an append-only store
   is not repaired by deletion.
3. Add the qualitative half. Cost and counts cannot answer "was this worth
   doing". Session notes carrying the operator's own assessment are the only
   instrument for that, and D8's scorecard — operator actions after
   interruption, glue lines, state locations — belongs here as an instrument.

### 7a. Dispatched work dies invisibly, and the contract for it already exists

The failure that prompted this: three dispatched sessions died on a provider
usage limit and the loss was noticed by accident. The mechanical root cause is
exact — **no `SubagentStop` hook is registered anywhere.** Only `Stop`,
`PostToolUse` and `SessionStart` exist. Nothing in the harness observes a
dispatched unit ending.

And the contract for recording it is already built and validated:
`auditctl/validation.py` defines `ACTIONQ_TERMINAL_REASON_CODES = {completed,
process-exit, start-failed, cancelled, timeout, usage-limit, crash-inferred}`.
The validator is live. **It has no producer** — its intended writer was the
actionq daemon, retired 2026-08-22, and the contract outlived its only writer.

With a `session.start` / `session.exit` pair carrying `terminal_reason`, the loss
predicate is a **join, not a heuristic**: a start event appearing in no exit
event's refs. No daemon, one subprocess per event.

*Not* reservations, as first proposed: `sprintctl/reservation.py` opens with "A
reservation is a detector, not a lease" — no TTL, no heartbeat, nothing reaps
them (there is a live 59-hour leak on item 2254 now), and `maintain check` /
`sweep` are unavailable in served mode, which is the mode agentops runs in. A
unit that dies in three minutes is invisible to a four-hour detector the backend
cannot run. Reservations remain the right *second* signal for abandoned
long-horizon work.

**Headroom is worse than missing — it is confidently stale.**
`.claude-headroom.json` and `.codex-headroom.json` were last written 2026-05-14,
107 days ago; the poller described in a code comment was never committed. Both
files self-report `"available": true` with **no timestamp field**, so the cockpit
renders May's figures as current, and its Refresh button writes a trigger nothing
reads. The fix is not to revive the scraper: Claude Code's own statusline input
already carries live `rate_limits.*.used_percentage`, so a hook can write the
file with a `refreshed_at` field and the cockpit consumes it unchanged.

**Sessions do not fit the reset window.** Measured: median 0.40h, **p90 7.35h**,
max 71.3h, 40 of 261 sessions over 4h — against a 5-hour reset. The p90 session
structurally cannot complete inside one window. This is the strongest evidence
for resumability being the primary product question, and it is an outcome
measurement rather than an argument from an operation's name.

Telemetry that only measures the substrate's own activity will keep confirming
the substrate's importance. The signals that matter are consumer-side: dispatch
survival rate, headroom at dispatch and at death, the re-dispatch multiplier
(already in the harness-profile `receipt_fields`, needing only a producer), and
**sessions per accepted result** rather than dollars per session.

---

## 8. The meta-narrative mode

Vuoro already specifies this layer, and calls it missing:

> `AgentProfileRevision` — **the missing meta-layer above native harnesses.** It
> defines a logical agent role independently of whichever runtime currently
> executes it.

The mode, concretely: the operator works with one session that holds current and
intended state; that session dispatches explorers, planners and orchestrators and
reconciles what they return; the operator's attention goes to judgment, not to
driving an orchestrator.

Two properties, both from Vuoro's own text and both non-negotiable:

- **The logical agent identifier is not an authorization principal.** Each
  runtime actor gets its own identity binding and `EffectGrant`. A meta session
  coordinating others must not become a way to launder authority.
- **Subagent findings are claims, not conclusions.** Every layer of the last
  fortnight's investigation found the previous layer's claim wrong. The habit
  that caught each one was re-measuring before writing. That habit is the
  method, and it is why §1 states measured facts rather than inherited ones.

Human judgment stays where rev. 4 §4 put it: architecture and spec freeze,
public release, canon ratification, trust-root and credential-scope changes,
authority-boundary changes, destructive migrations. Per-packet sign-off remains
theatre.

---

## 9. Projectized repositories, hand-offs and onboarding

The plan so far says what is true and what must hold. This section is what a
repository actually *does* to participate — the part that has been improvised per
repo and is the largest remaining source of friction.

### 9.1 A project is a repository plus a declared participation

"Projectized" means the participation is declared in the repository, versioned
with it, and readable by a fresh session with no operator present. Today it is
none of those things. The evidence is the cred-broker incident: no
`.sprintctl/backend.json`, so sprintctl resolved `backend=local` from the working
directory and wrote a sprint and four items to a local database **while appearing
to succeed**. A repository left the shared authority silently, and nothing
noticed.

The participation set is larger than sprintctl, and should be one declaration:

| Facet | Today | Should be |
|---|---|---|
| Work authority | `.sprintctl/backend.json` marker + `SPRINTCTL_VUORO_PROFILE` env var | one declaration |
| Evidence | `AUDITCTL_ARTIFACTS_ROOT` env var; unset means writes fail | declared, defaulted |
| Knowledge events | ad hoc | declared |
| Acceptance | nothing; acceptance-lab is unwired | declared scenario set |
| Telemetry | session hooks, repo-agnostic | declared, with the repo as a dimension |
| Workflow mode | implicit in the operator's head | declared |
| Agent instructions | `AGENTS.md` / `CLAUDE.md`, hand-written per repo | minimal, generated from the above |

### 9.2 The onboarding tool already exists and is disconnected

`vuoro bootstrap <endpoint> --repo-id <id>` writes exactly the three files whose
absence caused the cred-broker incident: `.vuoro/project.json`,
`.sprintctl/backend.json`, `.vuoro/profile.json`. The onboarding failure that
generated a plan finding was a case of not using a tool that exists.

**But it cannot work as-is, and this is verified, not inferred:** `sprintctl`
resolves its profile from the `SPRINTCTL_VUORO_PROFILE` environment variable and
never looks for `.vuoro/profile.json`. The bootstrap writes a profile sprintctl
cannot find. Meanwhile every workstation repo uses a gitignored `.envrc` pointing
at a shared profile under `agentops/templates/`, which is why the workstation fix
did not propagate to devbox-agent.

Two onboarding paths exist, neither complete, and they do not meet. The work is
to make them one:

1. Teach sprintctl to discover `.vuoro/profile.json` from the repository root,
   with the environment variable as an override rather than the only mechanism.
   This alone removes `.envrc` from the critical path and makes onboarding
   propagate with the repository, as it should have from the start.
2. Widen the bootstrap's scope from work-authority-only to the §9.1
   participation set.
3. Then, and only then, is "onboard a repository" one command.

### 9.2a Bootstrap is a reconciliation, not an event

*Owner amendment 2026-08-29.* Onboarding modelled as a one-time act is why
participation drifts: it is performed once, by hand, and never checked again. The
same command must serve **initiation, routine realignment, and migration to newer
schemas and tooling** — cheap enough to run often, ideally on a schedule or in
CI.

The shape is convergence to a declared desired state:

- The project manifest declares intended participation (§9.1); the command
  computes the difference against actual and applies it.
- **Idempotent and safe to rerun.** Converged is a no-op.
- **Dry-run and diff first**, always available and always cheap.
- **Versioned schemas, with migrations.** A repository pinned to an older
  participation schema is realigned by rerunning, not by hand-editing.
- **Selective**: install only the integrations the manifest selects; reference
  credentials rather than copying them; be straightforward to remove.
- **Exit code signals drift**, so an unconverged repository is a detectable
  condition rather than a surprise.

That last property is the one that pays for the rest. The cred-broker incident —
a repository silently resolving to a local backend and writing work nobody could
see — becomes **drift the next alignment run reports**, instead of an incident
discovered by accident weeks later. Realignment is also the natural carrier for
rollouts: when a schema or tool version is released, repositories converge to it
on their next run rather than through a coordinated flag day.

A project may span repositories while repository identity stays explicit. Making
alignment routine is what finally separates *project*, *workspace* and
*repository*, which this workspace has treated as interchangeable nouns.

**This is itself a candidate acceptance scenario:** align a drifted repository,
assert it converges; run again, assert it is a no-op.

`vuoro-bootstrap` is currently release-gated as a Vuoro Cloud external-onboarding
contract candidate. Internal projectization is a second consumer of the same
mechanism; if that conflicts with its release gating, the gating is what should
give, and the constraint should be recorded.

### 9.3 Hand-offs and work pick-up

Two shapes, both currently manual:

- **Ad-hoc** — an operator or a session hands work to another session mid-flight.
- **Triggered** — work becomes available and is picked up without anyone watching.

Both need one thing the substrate does not have: a resumable session record. This
is the same `session resume` gap as §1, seen from the workflow side rather than
the API side, and it is the reason that item is first in §5. Until it is served,
every hand-off is the operator carrying context in their head or in a paste.

Work pick-up should follow from what already exists — `next-work` for readiness,
reservations for claim (they already bind the actor to the authenticated
identity), receipts for what happened — and should not acquire a new mechanism.

### 9.4 Role definitions and workflow modes

The operator called for meta-narrative role definitions and workflow modes.
Vuoro's `AgentProfileRevision` (§8) already specifies the schema for exactly
this — purpose, task classes, inherited skills, hook bindings, required tools,
effect ceiling, evidence obligations, interaction mode, escalation contract. The
roles should be instances of it, not a parallel invention.

The interaction-mode axis it names — **unattended / episodically supervised /
interactive** — is the workflow-mode axis, already written down. A repository's
declared mode (§9.1) selects which roles may operate in it.

**Delivered 2026-08-29.** Seven roles as `AgentProfileRevision` instances —
coordinator, explorer, planner, executor, verifier, settlement/reconciliation,
operator — each with objective, inputs, outputs, authority, completion condition
and hand-off trigger. Two properties are load-bearing:

- **The coordinator holds no write authority at all.** Everything it would write,
  a settlement role writes as a proposal. Served sprintctl ignores `--actor` in
  favour of the authenticated server actor, so a served coordinator *physically
  cannot* write as a subagent — the anti-laundering property is enforced by the
  substrate, not by discipline.
- **The verifier is deterministic, not a model.** An LLM verifier produces another
  claim wearing a verdict's clothes, which is the laundering this mode exists to
  prevent. Verifier and settlement are separate roles precisely because
  acceptance-lab is a replaceable evaluator and Vuoro owns which result counts.

**The coordinator is not a state.** Every unit of work lives as an envelope in a
durable store, in a named state, with its own resume plan. Kill the coordinator
mid-journey and nothing is lost. That is the replaceability test, passed by
construction.

### 9.6 The work envelope

One new schema, `work-envelope/v1`, and the case for it being new is specific:
`session-capsule/v1`, `session-note/v1` and `reconciliation-proposal/v1` exist and
work, but all three are *retrospective*. None carries grants, provider history,
wait eligibility or a required acceptance outcome, and none is forward-looking.
The envelope **embeds them by reference** rather than restating them.

It carries: project and repository identities; work authority with observed and
current revisions; a checkpoint (`git-commit+evidence`, per Vuoro's rule against
wrapping Git to manufacture another noun); claims with evidence class, locator
and rerun command; unfinished actions; provider history; principal and grant
references with grant state; retry/wait eligibility and portability class;
required acceptance outcome; and a **resume plan**.

One envelope serves all five hand-off triggers — human reassignment, rate-limit
recovery, scheduled pickup, process loss, cross-provider continuation. Only the
trigger and the provider history differ.

**The resume plan is how the compatibility rollout avoids a flag day.**
`sprintctl session resume` sits first in the plan and is marked *not required*.
A resumer runs the plan top-down and skips what is unavailable: one call where
the aggregate is served, five where it is not — verified working today. Mixed
service versions and catalogs need no feature flag and no version negotiation,
because unavailability is just a skip. The envelope must never become unreadable
without `resume`, or the rollout becomes the flag day it was meant to avoid.

### 9.5 Agent instructions, minimally

Per-repo `AGENTS.md` and `CLAUDE.md` are hand-written and drift. Once §9.1 is a
declaration, most of their content is derivable: which authority, where evidence
goes, which acceptance scenarios apply, which mode is in force. What should stay
hand-written is what is genuinely repo-specific — domain knowledge, local
conventions, hazards. Generate the mechanical half; keep the judgment half short.
The test is that instructions describing available functionality should not be
maintained by hand in fifty places.

## 10. First moves

Reordered, rev. 2. Rev. 1 led with `session resume`; two reviews and a
verification pass agree that over-ranks a convenience aggregate.

1. **Make dispatched death observable.** Register a `SubagentStop` hook and emit
   `session.exit` carrying `terminal_reason`. The vocabulary, the validator and
   the storage already exist — `ACTIONQ_TERMINAL_REASON_CODES` includes
   `usage-limit` — and the contract has had **no producer** since its intended
   writer was retired on 2026-08-22. The loss predicate becomes a join over
   start/exit events, not a heuristic. This is a hook file and a settings block,
   and it converts the failure that commissioned this design from invisible to a
   one-line query.

2. **Fix telemetry capture, then recompute rather than convert.** Export
   `AUDITCTL_ARTIFACTS_ROOT` so the `Stop` hook's publish stops failing silently
   at a 36% capture rate; rebuild the cost projection with
   `GROUP BY session, MAX(cost_usd)`; give the headroom file a `refreshed_at`
   field fed from Claude Code's own statusline input, so a 107-day-stale file
   cannot report itself as available. Recompute the workspace distribution before
   any further allocation claim.

3. **Prove recovery as an outcome.** Encode a failing black-box scenario — fresh
   process, no local cache, after interruption, through the served backend,
   recovering session identity, work authority, checkpoint and exact revision —
   then implement until it passes. Additive rollout, so it can be disabled
   without disturbing `next-work`. The walking-skeleton scenario
   (`resume-and-settle`) is drafted with eight hard gates and one soft gate.

4. **Pin scorer revisions in acceptance-lab.** A **present, verified defect**:
   `EvaluationResult` pins `scenario_version` but `SCORERS` is a bare unversioned
   dict of thirteen callables. Changing one silently rewrites the meaning of
   every historical `PASS`. Until fixed, no evaluation record is comparable across
   time and any settlement citing one cites a moving target. Then join D2+D5 into
   the receipt → evaluation → settlement path.

5. **Extract the consumer proof.** Not "ask bindery-core what worked": encode the
   smallest complete accept/reject/merge cycle as a reusable scenario and
   identify what belongs to the substrate versus to bindery itself. Follow with
   one non-agent-infrastructure consumer, `homelab-analytics`.

6. **Then run the loop once, manually.** Distinct principals and grants, durable
   external state, independently checkable claims, interruption and resume, and
   settlement. Let its measured operator interventions and failure modes generate
   the mechanics — rather than designing more of them first.

Bootstrap realignment (§9.2a) and telemetry repair (2) can proceed concurrently;
neither waits on the orchestration design.

## 11. What is not established

- **Beads / Gas Town**: the comparison lane is unrun. Carried as an open prior.
- **Restate pilot**: placement decided, nothing built.
- **`credctl` is not installed on this host.** The unattended executor lane is
  designed but not deployable. Supervised execution is unaffected, and D4 binds
  only when unattended writes begin — which they cannot yet.
- **Reservations are not leases.** The CLI help says so outright: "a reservation
  is a coordination signal, not a lease". Duplicate-execution safety rests on the
  envelope `dedup_key`, CAS on item status, and exact-revision receipts. Any
  future step that leans on a reservation for exclusivity is a defect, and this
  is the most likely place the design gets broken later.
- **`work-envelope/v1` is designed, not built.**
- **Half of §11's rev. 1 entry was false.**
  `agentops/templates/dispatch/session-mechanization/` — four schemas, three
  scripts, three skills, **24 passing tests** — already implements the
  park → resume → retain arc, including a shared cursor that makes double
  processing impossible by construction. It should be embedded, not rebuilt.
- **Devbox-agent and cluster reality** beyond the vuoro-shared deployment: still
  unverified, and now a stated prerequisite (§5).

### Retractions, rev. 2

Four claims this plan asserted and has had to withdraw, kept visible because the
pattern is the finding:

| Claim | Reality |
|---|---|
| "hostproto has no git remote" | All seven repos plus `browser-workbench` have reachable remotes and zero unpushed commits. Inherited from rev. 4, unverified. |
| "`session resume` unserved = resumability broken" | It is a convenience aggregate over three served surfaces. Label treated as proof. |
| "the cost error is inherited by the immutable store and cannot be corrected in place" | It is a consumer-side summing bug; `metadata.session` survives and the figure is recomputable. |
| "the orchestration loop is not designed" | Half of it is built and tested in `session-mechanization/`. |

Every one was an inherited or inferred claim stated without measurement — which
is exactly what §8's rule exists to prevent, and it caught none of them until a
reviewer or a subagent re-measured. The rule is right; applying it to my own
assertions rather than only to the plan's gates is the correction.
