# The dispatch cycle: what the substrate owns, and what bindery-core owns

2026-08-29. Answers plan §10.5, which asks for the consumer proof and is explicit that
the way to get it is *not* to ask bindery-core what worked. So this reads what the
substrate durably recorded — `_artifacts/<repo>/audit/` and the receipts the accepted
attempts cite — and separates the half that is a mechanism from the half that is not.

Scenario: `templates/dispatch/acceptance/dispatch-cycle.scenario.json`
Probe: `templates/dispatch/scripts/dispatch_cycle_probe.py`

## The cycle, at its smallest

`ERM-005-redaction-idempotency` is the smallest complete cycle on record: three events,
two attempts, six minutes.

| | Event | What it establishes |
|---|---|---|
| 14:02:47 | `dispatch.packet.rejected` (r2) | The contained attempt was refused **before mutation**: `no_mutation: true`, `retry_required: true`. A refusal that costs nothing is the only kind that scales. |
| 14:06:59 | `dispatch.packet.reviewed` (r3) | The revised candidate matched the coordinator's reference patch exactly, and cites the receipt that says so. |
| 14:08:29 | `dispatch.packet.accepted` (r3) | Merged as `39cf292`, sprint item `bindery-core#2284` closed, reservation 9 released. |

`ERM-WIDE-fixture-wave` is the same shape with the refusal one stage earlier — refused
at preflight, before any worker started, because `go vet` was red on the coordinator
tree.

## What the substrate owns

These are mechanisms. They exist as code and schemas, they run the same way in any
repository, and nothing about them is bindery-specific.

| Owned by | What |
|---|---|
| `hybrid_dispatch.py` | `agentops-hybrid-receipt/v1` — packet hash, exact starting commit, per-file candidate digests, touched paths, worker identity, worker exit code |
| `task-packet.schema.json` | `agentops-task/v2` — the frozen packet a worker is given |
| `hybrid_dispatch.py` | `agentops-hybrid-gate-set/v2` — the gate-set hash that makes two runs' gates comparable |
| sprintctl | the reservation lifecycle (open, refresh, release) and the work item whose status closes |
| auditctl | the append-only, hash-chained stream the whole cycle is recovered from |
| the dispatch harness | containment: a separate `agentworker` identity, a disposable worktree, protected paths, diff scope |

## What bindery-core owns

These are bindery's, and correctly so. The scenario never reads them; the probe carries
them as data under `metadata.consumer_specific`, which is what lets the same scenario
score a consumer written in another language against another toolchain.

- the gates themselves: `bindery.unit.race`, `bindery.unit.vet`, `bindery.redaction`,
  `bindery.verification.artifacts`
- the redaction oracle, and the public `relay_endpoint` placement exception whose
  contradiction refused a packet on 2026-08-24
- the reference-patch convention: a coordinator writes the expected diff first, and the
  worker's candidate is accepted only on an exact or semantic match
- Go, the module layout, and what any of the work means

## What neither owns, which is the finding

**The cycle's own vocabulary is not a mechanism. It is prose.**

`dispatch.packet.rejected`, `dispatch.packet.reviewed`, `dispatch.packet.accepted`,
`dispatch.preflight_rejected` appear nowhere in auditctl as a validated type, and
nothing in `templates/dispatch/` emits them. Every one of the 23 such events was written
by hand by a single actor — `luna-coordinator` — in one repository, over one day.

The measurement, from the probe run unchanged across every repository that has an audit
stream:

| Repository | Cycles | Complete |
|---|---|---|
| `bindery-core` | 18 | **2** |
| `agentops` | 6 | 0 |
| `p3-driver` | 1 | 0 |
| 12 others | 0 | 0 |

agentops' own dispatched work records `workflow.escalation` and nothing else — not the
arms under a different spelling, but no arms at all. `homelab-analytics`, which §10.5
names as the non-agent-infrastructure consumer to follow with, has **no dispatch cycles
of any kind**. That follow-on cannot be extracted from the record, because there is
nothing in the record to extract; it has to be run first.

So the answer to "whatever made that cycle work is the most valuable undocumented thing
here" is: **a coordinator's discipline, not a mechanism.** Sixteen of bindery's own
eighteen cycles are incomplete for the same reason every other repository's are — the
arms were emitted when someone remembered to emit them.

That is exactly the class of thing that dies with the session that held it, which is why
extracting it was worth doing before asking anyone to reproduce it.

## Scored

`dispatch-cycle@1.1.0`, both complete cycles:

| Run | Cycle | Status | Score |
|---|---|---|---|
| `10a5bf6a` | `ERM-005-redaction-idempotency` | CONDITIONAL | 0.889 |
| `aad7ff07` | `ERM-WIDE-fixture-wave` | **PASS** | 1.000 |

Both clear all eight hard gates. ERM-005 fails only the soft economics gate, and for a
real reason: its receipt carries `reported_cost_usd: 0.0` but no `cost_reported` flag —
that flag was added later. A zero without an assertion that anything was reported is
ambiguous between "it cost nothing" and "nothing was reported and the field defaulted",
and the probe refuses to resolve that ambiguity in its own favour. The wide cycle's
receipt does assert it, and passes.

Two runs at `1.0.0` are kept rather than rescored. `31e100ee` failed
`cycle-runs-in-order` there because that cycle's refusal was spelled
`dispatch.preflight_rejected` while the check enumerated `dispatch.packet.rejected` —
the same arm under a second name. The fix was to name the three arms rather than the
event types, which is also what makes the scenario portable to a substrate that spells
its events differently.

## The smallest thing that would change the measurement

Give the arms a producer. The receipt already knows its own disposition — it carries
`disposition: candidate` and a `review.decision` — so the accepted arm could be emitted
by `hybrid_dispatch.py` at the moment it writes the receipt, with no new judgement
required. The refused arm is the one that matters more and is equally available: the
driver already knows it stopped at preflight, and already knows whether a worker was
started.

Until then, `dispatch-cycle` measures how reliably a coordinator remembered to write
prose, and reports it as a property of the consumer. That is a fair reading of the
current record and a poor one of the substrate.
