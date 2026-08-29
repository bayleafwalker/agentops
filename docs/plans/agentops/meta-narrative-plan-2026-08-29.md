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
`browser-workbench`, `outctl`.

Two corrections rev. 4 owes:

- **hostproto and scribectl are constituent, and the evidence is code, not
  documents.** `vuoro-evidence` registers exactly two ingress edges: HostProto,
  and outctl-under-auditctl. Vuoro's planning documents name `hostproto`,
  `scribectl` and `browser-workbench` zero times. Both readings were of real
  evidence. They do not contradict each other: the coupling is in code the
  planning documents do not know exists — in a package that was untracked and
  whose sources had been deleted until yesterday. That is one measurement of the
  drift between written intent and built system, and it is the reason this plan
  exists.
- **outctl's three recorded statuses cannot all hold.** Retired from the Vuoro
  binding (08-20, `[reconciled]`); an owned architectural area (control-plane
  plan, 08-15); a live ingress lane in `vuoro-evidence/ingress/command_capture.py`,
  built 08-28. The code is the most recent and the least ambiguous. Treat outctl
  as a live evidence-acquisition lane and amend the direction document, or delete
  the lane. Not both.

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
- **`agentops.io` occurs zero times across the workspace.** If it is intended as
  a called-for provider, that intent exists only in conversation. Name the
  capability it would own, in the plane table, or drop it. Note the collision:
  the local `agentops` repo is unrelated.

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

## 9. First moves

1. Serve `session resume` (§5.1) — the intent's own first word.
2. Wake acceptance-lab and encode the five surviving invariants (§2).
3. Fix the cost over-count and publish the historical conversion (§7).
4. Reconcile outctl to one status (§3).
5. Ask `bindery-core` what made its dispatch cycle work (§3).

Each is small, each is traceable to the sentence in §1, and none needs a gate to
justify it.

---

## 10. What is not established

- **Beads / Gas Town**: the comparison lane is unrun. Carried as an open prior.
- **Restate pilot**: placement decided, nothing built.
- **`agentops.io`**: no written intent anywhere.
- **The orchestration loop's own design**: the agent tasked with it did not
  finish. §8 states the mode and its constraints; the loop mechanics are not
  designed.
- **`vuoro-evidence` carrier-agnosticism**: asserted by design, unproven by test
  since the recorded traffic was lost. The `record-session.mts` scripts survive
  in four adapter repos, so it is re-recordable — an environment task, not a
  research one.
- **Devbox-agent and cluster reality** beyond the vuoro-shared deployment: still
  unverified, as rev. 4 §10 said.
