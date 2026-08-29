# Meta-narrative plan — 2026-08-29

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

`sprintctl session resume` returns:

```
served-operation-unavailable: 'session resume' is not available through the
Vuoro served catalog yet. The combined session-resume contract is not yet served.
```

The product sentence begins with *resumable*. The one operation named `resume`
is not served on the backend every repository is now required to use. That is
the gap between intent and system, in one line, and it needs no gate to justify
fixing.

---

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

Five permanent invariants, two relocations, one deletion. Nothing new invented.

**The engine.** `acceptance-lab` is the workspace's evaluation organ and it is
idle — four commits in eight weeks. Its architecture is already the one this
workspace has converged on independently: an append-only hash-chained event log
that is authoritative, disposable rebuildable projections, deterministic scorers,
CI exit codes, zero runtime dependencies. It emits `PASS` / `CONDITIONAL` /
`FAIL` over mechanism, quality, authority and economics. Twenty-two of its tests
pass today; only its jsonschema-dependent schema validation fails, on a missing
dev dependency.

The five surviving invariants become acceptance-lab scenarios. `CONDITIONAL` is
the outcome hand-written gates could never express, and it is the outcome most
of this work actually deserves.

**The build-versus-buy test**, applied verbatim, and it is the owner's own:

> If replacing the provider makes this feature irrelevant, buy or adapt it. If
> the information must survive provider replacement to preserve intent,
> authority, evidence, recovery, or learning, Vuoro owns the contract.

---

## 3. The workspace by role

Roles are claims about value, and each is falsifiable.

**Constituent — inside the intent.** These implement resumability or settlement.
`vuoro`, `vuoro-cloud`, `sprintctl`, `auditctl`, `actionq`, `hostproto` +6,
`browser-workbench`.

Two corrections rev. 4 owes:

- **hostproto and scribectl are constituent, and the evidence is code, not
  documents.** `vuoro-evidence`'s one live ingress edge is HostProto. Vuoro's planning documents name `hostproto`,
  `scribectl` and `browser-workbench` zero times. Both readings were of real
  evidence. They do not contradict each other: the coupling is in code the
  planning documents do not know exists — in a package that was untracked and
  whose sources had been deleted until yesterday. That is one measurement of the
  drift between written intent and built system, and it is the reason this plan
  exists.
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
- **`agentops.io` is a market sample, not a chosen Vuoro surface.** *Owner
  clarification 2026-08-29.* It is a comparator in the observability-and-analytics
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
4. **Wire `local-inference` as a named execution provider** rather than a
   workstation convenience.
5. **Converge the remaining `vuoro-service` digests** (`vuoro-dev`,
   `agent-cockpit`), which now also requires migrating their identity registries
   to `principal_id`.
6. **Give `hostproto` a git remote.** The most active constellation in the
   workspace, and its trunk has none.

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

- **Session cost is over-counted 5.4–5.9×**, unbounded, scaling with rows per
  session — and the error is **inherited by the immutable auditctl store**, so
  every historical figure is wrong by a varying factor and cannot be corrected
  in place. Only forward correction plus a documented conversion is available.
- **69% of `workflow.session` events are test fixtures**, one named
  `sess-poison`. 318 of 473 rows in `_artifacts/agentops/audit/` are fixtures.
  The 2026-08-26 ruling retired the derived index only; the authoritative shards
  still carry them.
- **Spend does not match plans.** 31% went to `agentops` — the substrate this
  plan calls over-designed. `scribectl` and `cred-broker`, rev. 4's two named
  consumer packets, drew 0%. `bindery-core` drew 17% and appears in no plan.

Three fixes, in order:

1. Fix the cost computation; publish the conversion for historical figures.
2. Partition fixtures from real observations at the shard level. A store whose
   integrity guarantee is meaningful must not silently mix them.
3. Add the qualitative half. Cost and counts cannot answer "was this worth
   doing". Session notes carrying the operator's own assessment are the only
   instrument for that, and D8's scorecard — operator actions after
   interruption, glue lines, state locations — belongs here as an instrument.

Telemetry that only measures the substrate's own activity will keep confirming
the substrate's importance. The signals that matter are consumer-side.

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

*The concrete role set and the loop mechanics are being designed in a dispatched
session; §10 records that as open rather than guessing here.*

### 9.5 Agent instructions, minimally

Per-repo `AGENTS.md` and `CLAUDE.md` are hand-written and drift. Once §9.1 is a
declaration, most of their content is derivable: which authority, where evidence
goes, which acceptance scenarios apply, which mode is in force. What should stay
hand-written is what is genuinely repo-specific — domain knowledge, local
conventions, hazards. Generate the mechanical half; keep the judgment half short.
The test is that instructions describing available functionality should not be
maintained by hand in fifty places.

## 10. First moves

1. Serve `session resume` (§5.1) — the intent's own first word.
2. Wake acceptance-lab and encode the five surviving invariants (§2).
3. Fix the cost over-count and publish the historical conversion (§7).
4. Reconcile outctl to one status (§3).
5. Ask `bindery-core` what made its dispatch cycle work (§3).

Each is small, each is traceable to the sentence in §1, and none needs a gate to
justify it.

---

## 11. What is not established

- **Beads / Gas Town**: the comparison lane is unrun. Carried as an open prior.
- **Restate pilot**: placement decided, nothing built.
- **`agentops.io`**: no written intent anywhere.
- **The orchestration loop's own design**, including the §9.4 role set:
  re-dispatched 2026-08-29 after the first attempt died on a provider limit. §8
  states the mode and its constraints; the mechanics are in flight.
- **Provider usage rates and their workflow consequences**: dispatched
  2026-08-29. The prompting failure is concrete — three subagents died on an HTTP
  429 session limit and the loss was silent. The question asked is broader than
  retry policy: if provider limits are a normal condition rather than an
  exception, what does the workflow have to look like.
- **`vuoro-evidence` carrier-agnosticism**: asserted by design, unproven by test
  since the recorded traffic was lost. The `record-session.mts` scripts survive
  in four adapter repos, so it is re-recordable — an environment task, not a
  research one.
- **Devbox-agent and cluster reality** beyond the vuoro-shared deployment: still
  unverified, as rev. 4 §10 said.
