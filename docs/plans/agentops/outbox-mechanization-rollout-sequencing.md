---
doc_id: outbox-mechanization-rollout-sequencing
status: reviewed
last_verified: 2026-07-21
supersedes: null
---

# Outbox / session-mechanization rollout — cross-repo execution sequencing

Sequencing owner: **agentops** (sprint item #1110). Per
`sprintctl/docs/ops-upgrade-plan.md` ("Keep cross-repo sequencing in agentops
rather than hiding all work in one meta-repository") this document is the
single place where the rollout order, gates, and per-repo ownership of the
outbox/mechanization work are decided. Protocol semantics stay in
`sprintctl/docs/plans/adr-outbox-sync-model.md`; mechanism design stays in
[`session-mechanization-plan.md`](session-mechanization-plan.md); per-event
ownership stays in
[`state-event-command-matrix.md`](state-event-command-matrix.md). This doc
sequences; it does not re-specify.

## Shipped baseline (verified 2026-07-14)

| Repo | Shipped | Evidence |
|---|---|---|
| sprintctl | outbox schema + record envelope/class contracts + shadow projection pilot (phases 26–28); `sprintctl_sprint_activate()` SQL handler (applied to live `sprintctl-cnpg-main` DB); capability receipts | `outbox.py`, `contracts.py`, `bf919e83`; ADR `adr-outbox-sync-model` |
| agentops | session-capsule/v1 + reconciliation-proposal/v1 contracts (#1106); periodic scribe (#1107); fresh post-session reconciler (#1108); cockpit reconciliation surfaces (#1109); cockpit sprint-activation via domain-owned handler (#1105) | `f530a00`, `94b362b`, `af34b96`, `f2f138d`, `044bfaf` |
| appservice | agent-cockpit deployment (image `0.1.13`, predates #1105/#1109 code); `agent-cockpit-write` secret exists; CNPG clusters + backup/restore-drill CronJobs | `clusters/main/kubernetes/apps/agent-cockpit/app/` |

Known caveat: sprintctl `main` carries unpushed commits (including the
sprint-activate handler); the live DB already has the function applied.

Operator attestation, 2026-07-18: agent-cockpit is deployed. This workstation
does not have firewall permission to reach the runtime, so the exact image
tag, environment values, and smoke results were not independently verified.

## Sequenced tranches

Each tranche is independently valuable and reversible (ops-upgrade-plan
requirement 7). A tranche's **gate** must hold before starting it; nothing
inside a tranche depends on a later tranche.

### Tranche A — deployed; operational evidence capture remains

The operator reports the cockpit deployed. The original rollout procedure is
retained below as the provenance and rollback checklist; it is not an open
application deployment blocker.

1. Rebuild `agent-cockpit` image from agentops `main`
   (`apps/web/Dockerfile`), push to the cluster registry, bump the tag in
   `appservice/.../agent-cockpit/app/deployment.yaml`. Owner: operator
   (workstation build) + appservice.
2. Post-rebuild follow-ups, same change window:
   - revert `COCKPIT_ARTIFACTS_ROOT` from `/projects/dev` back to
     `/projects/dev/_artifacts` (the audit.js double-path workaround is fixed
     in source);
   - set the browser `localStorage["cockpit_write_token"]` (write routes
     start enforcing auth once the env var is live);
   - smoke: sprint activation via cockpit exercises
     `sprintctl_sprint_activate()` (expect SP404/SP409 semantics), and
     `GET /cockpit/api/reconciliation` returns an empty-but-healthy queue.
3. Push sprintctl `main` to origin so the deployed handler's source of truth
   is not workstation-only.

Gate: satisfied by operator deployment attestation. Runtime smoke evidence is
still pending firewall-permitted access. Rollback: pin the previous image tag.
Detailed runbook: [`agent-cockpit-deployment-handoff.md`](agent-cockpit-deployment-handoff.md) (#951).

### Tranche B — Tier-0 capsule producer (actionq)

The scribe (#1107), reconciler (#1108), and cockpit surfaces (#1109) all read
`session-capsule/v1` artifacts that nothing produces yet — they have been
validated against synthetic capsules only. The harness-neutral session
wrapper is the missing producer.

- Owner: **actionq** owns the wrapper mechanism; **agentops** owns the
  capsule contract. This assignment is ratified by the matrix and actionq
  decision #968. Implementation is tracked by actionq #969/#971/#1114/#1115.
- Scope: wrapper emits `session.started` / `session.ended` /
  `session.end-inferred` plus capsule fields per the contract; fails open
  for manual work; crash recovery for unclosed sessions.

Gate: satisfied 2026-07-21. `actionq-session-wrap` (actionq #1114/#1115,
already merged) was reinstalled and exercised for real on devbox-vm, producing
two genuine `session-capsule/v1` artifacts under
`_artifacts/agentops/session-capsules/` — real git evidence (base/head commit,
diff stat, touched paths, dirty state), not fixtures. See Tranche C below for
what consumed them. Rollback: wrapper is additive exhaust; disable it and the
ecosystem returns to today's behaviour.

### Tranche C — trigger wiring (agentops)

Deliberately excluded from #1107/#1108: scheduling the scribe (cron/dispatch)
and firing the reconciler at session end. Wire both only after Tranche B
produces real capsules — wiring triggers against synthetic exhaust proves
nothing and risks cargo-cult cron jobs.

- #1172 owns the immediate-reconciler and periodic-scribe trigger wiring.
- #1173 owns idempotent execution of accepted proposals through normal
  sprintctl authority commands; acceptance itself never implies success.

Agentops source status: #1173 now has the bounded, feature-flagged executor,
durable execution sidecars, stable retry identities, operator read surface,
and accepted/rejected/stale/duplicate/partial/unavailable test histories.
`#1173`'s runtime enablement stays gated: the cockpit pod's read-only
workspace and lack of a writable sprintctl command-outbox path is a separate,
still-open decision from #1172's trigger wiring below.

**#1172 — closed 2026-07-21.** Runtime path selected: devbox-vm via
`systemd --user` timers, not a new in-cluster runner. Devbox-vm already has
git-write access, `ACTIONQ_URL`/`SPRINTCTL_URL`, and is the existing agent
dispatch host — no new appservice secrets, PVC, or workload identity needed.
`templates/dispatch/scripts/session_mechanization_trigger.py` provides
`reconcile-tick` (dispatches one fresh, non-interactive `claude -p` session
per unconsumed capsule, following `skills/session-reconciler/SKILL.md`) and
`scribe-tick` (one fresh session per artifact root on a schedule, following
`skills/session-scribe/SKILL.md`); `ops/systemd/session-mechanization-{reconcile,scribe}.{service,timer}`
schedule them (5 min / 30 min). A per-project-root flock keyed the same for
both tick types makes them single-consumer even if they race; the shared
`session_scribe.py` cursor makes a capsule immune to double-processing even
across separate invocations. Neither skill executes a sprintctl authority
command — both only ever write a `reconciliation-proposal/v1` or a no-change
record, so a bad tick produces at most a bad proposal for a human to reject.

Real end-to-end evidence (devbox-vm, 2026-07-21): two capsules produced via
`actionq-session-wrap`. `reconcile-tick` discovered the first, dispatched a
real Claude session, which read the actual sprintctl item #1172 (including
its own open blocker event #1249), classified it `mark-item-advanced` at
medium confidence, and wrote a valid proposal
(`a26b9407-e54b-469d-91e3-a4dd06ec42eb`) — cursor advanced, no sprintctl
authority command ran. A second `reconcile-tick` against the same (now empty)
backlog correctly no-op'd (duplicate-trigger case). `scribe-tick` against the
second capsule dispatched a real session that wrote a second proposal
(`1879f07b-5e5c-4ae3-8b17-a5a26def1006`) and advanced the cursor the same way.
`session_mechanization_trigger.py status` correctly reports backlog age
(`unreconciled_count: 0` after both ticks) and the trigger attempt history
(`dispatched-ok` / `no-op` outcomes), covering the item's "expose trigger
failures and backlog age" scope. The `.service`/`.timer` units are installed
on devbox-vm (`systemctl --user daemon-reload`) but deliberately left
`disabled` — proven correct once, not left running unattended pending an
explicit decision to enable recurring autonomous dispatch.

Gate: live capsules exist (Tranche B) and #1172's trigger wiring is proven
end-to-end. Rollback: `systemctl --user disable` the timers (a no-op today
since they were never enabled) or remove the unit files; capsules accumulate
safely for a manually-invoked scribe pass to drain later — the designed
degradation mode (bounded, visible lag).

### Tranche D — config/secret hardening (source scope complete; runtime evidence pending)

- Agentops #947 and #948 are complete through normal claim/evidence history.
- Appservice #977 retains the cluster-owned rotation and consumer-reload
  procedure; #979/#982 retain authorized runtime config and network evidence.

Gate: satisfied by the 2026-07-18 deployment attestation. Rollback: env-var
level, per change.

### Tranche E — migration and removal (sprintctl-owned, P3)

Shadow-projection parity checks, sprintctl dogfooding pilot, per-repo
feature-flagged cutover to the outbox path, direct-SQL write removal
(cockpit side already done in #1105), backend-mode code removal **only after
evidence**. Sequencing within this tranche belongs to sprintctl's own plan
(`adr-outbox-sync-model` migration section); this doc only pins the gate.

Gate: Tranches A–C live and the dogfooding metrics
(session-mechanization-plan §Dogfooding) show real data, not synthetic.
Agentops #1174 owns the cross-repo gate record consumed by sprintctl #1163.

### Housekeeping (any time)

- #1111 is complete as a backlog record. The remote GitHub archive state was
  not independently re-verified from this workspace.

## Dependency summary

```
A (deploy shipped)  ──► D (hardening)
B (capsule producer) ──► C (triggers + proposal execution) ──► E (dogfood/cutover)
A ────────────────────────────────────────────► E
```

## Standing rules

- New cross-repo work discovered during the rollout is sequenced here first,
  then placed in the owning repo's backlog scope (never accumulated in a
  meta-repo).
- A tranche that stalls must leave a visible queue (artifacts, blocked items
  with events), never silent divergence — the same failure posture the
  mechanization itself targets.

## Related documents

- `sprintctl/docs/ops-upgrade-plan.md` — ratified product direction (priority
  structure P0–P3 this sequencing refines).
- `sprintctl/docs/plans/adr-outbox-sync-model.md` — protocol + migration
  semantics.
- [`session-mechanization-plan.md`](session-mechanization-plan.md),
  [`state-event-command-matrix.md`](state-event-command-matrix.md),
  [`write-surface-policy.md`](write-surface-policy.md).
- [`agent-cockpit-deployment-handoff.md`](agent-cockpit-deployment-handoff.md)
  — Tranche A runbook (#951).
