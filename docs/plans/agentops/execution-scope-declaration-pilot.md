---
doc_id: execution-scope-declaration-pilot
status: draft (advisory pilot — no gate authority granted)
supersedes: planner-focus-manifest-pilot
---

# Execution scope declaration pilot (`execution-scope/v0`)

Two bounded experiments over declared and reconstructed scope. Neither claims
access to model internal state; both are measured against work the system can
verify independently.

Everything here is advisory. Nothing in this plan may fail a dispatch, block a
packet, or contribute to acceptance. Each track carries an explicit
keep-or-delete decision.

> Renamed from `planner-focus-manifest-pilot`. "Focus manifest" implied a window
> into what the model was attending to. The evidence below does not support that
> reading, and the name invited exactly the interpretation the design must
> refuse.

## Why this is not introspection

Two results constrain the design, and both come from introspection experiments
run separately from this plan's own items (#2053–#2056 remain pending and have
produced no data).

### The independent-branch limitation

A self-report completion and a behavior completion do not share a stochastic
trajectory. The model that writes "I am treating retries as at-least-once" is
sampled independently from the model that writes the retry code. No methodology
can correlate one branch's declaration with another branch's private choice on
an individual-run basis. Under genuine ambiguity the report therefore cannot
reveal which interpretation actually drove the action.

This is decisive against reading any declaration as evidence about a specific
run. It is *not* an argument against the artifacts in this plan, because none of
them make that claim — see "What survives" below.

### The confabulation result

A reporting prompt does not merely surface concepts; it pressures the model to
manufacture a coherent semantic account. Free-text "list the concepts affecting
your reasoning" formats reliably produce fluent, plausible, unfaithful output.
Unconstrained free text is therefore unsuitable as audit evidence anywhere in
this plan.

### The reconstruction control

Nearly all information recoverable from a self-report was equally recoverable by
an *external* model reading the same artifacts. This is the most design-relevant
finding: if an independent reader gets the same signal, prefer the independent
reader, because it has no incentive alignment with the work being judged.

## What survives

Three roles, none of which require privileged access.

| Role | Claim | Track |
|---|---|---|
| Planner gap detection | The planner wrote a concern down and then did not formalize it | A (#2053–#2056) |
| Independent reconstruction | An external reader infers apparent scope from artifacts alone | B (new) |
| Prospective intervention | Requiring a scope declaration *before* acting changes what gets built | C (new) |

Track A is untouched by the introspection results. It never claimed the manifest
revealed hidden state; it compares two coordinator artifacts — what the planner
recorded against what the frozen packet contains. The independent-branch
objection does not apply to a comparison between two written documents.

One introspection result *does* bite Track A: a confabulated
`design_concerns_not_yet_requirements` entry produces a `PLANNER_GAP` finding
about a concern the planner never actually held. That is noise, and #2056's
measurement must be able to tell it apart from signal.

## Naming and field discipline

The artifact is an `execution-scope/v0` **declaration** — what an agent commits
to considering and proving — not a report of what was internally active. Storage
type is `planner.scope_declaration` / `executor.scope_declaration`; the word
"focus" is retired.

All fields are constrained and tied to the work contract:

- requirement ids
- accepted exclusions
- unresolved ambiguities
- assumptions
- expected files or evidence
- likely failure modes
- dependencies

Free text may appear only inside a bounded field (the `reason` on an at-risk
requirement, for example) and may never independently trigger a finding. A
declaration field whose whole content is free-form prose is a design error.

### Preflight shape

```yaml
execution_scope_declaration:
  version: execution-scope/v0
  phase: preflight
  requirements_selected: [REQ-004, REQ-007, REQ-009]
  requirements_at_risk:
    - id: REQ-009
      reason: expected cancellation behavior is ambiguous
  assumptions:
    - database migration is permitted
  explicit_exclusions:
    - dashboard changes
  expected_evidence:
    REQ-004: [atomicity tests]
    REQ-007: [retry idempotency tests]
```

### Submission shape

```yaml
execution_scope_declaration:
  version: execution-scope/v0
  phase: submission
  requirements_claimed_complete: [REQ-004, REQ-007]
  requirements_incomplete:
    - id: REQ-009
      reason: unresolved specification ambiguity
  evidence:
    REQ-004: [tests/test_atomic_publish.py]
    REQ-007: [tests/test_retry_idempotency.py]
  residual_risks:
    - process termination during publication untested
```

## Blocking precondition: stable requirement IDs

Unchanged and still first. In `templates/dispatch/hybrid/task-packet.schema.json`
`acceptance_properties[].requirement`, `required_outcomes`, and `non_goals` are
all free-text strings, so every comparison in this plan would otherwise reduce to
fuzzy-matching coordinator prose. Adding a packet-unique `id` to
`acceptance_properties` items is the load-bearing first step (#2053).

`hybrid_dispatch.py::_receipt` folds `acceptance_properties` into
`inputs.gate_set_hash`, so the change breaks hash comparability across the
boundary; record the schema version where it breaks for the #2017 corpus.

## Track A — planner gap detection (#2053–#2056)

Unchanged in substance; the artifact is renamed to `planner.scope_declaration`
and its fields are brought under the constraint discipline above. At freeze the
packet fixes `required_outcomes`, `acceptance_properties`, `non_goals`, and
`oracle`; nothing records what the planner considered and dropped. The finding:

```text
PLANNER_GAP: cancellation recovery appeared in planner analysis, but was absent
from the frozen requirements, exclusions, and acceptance criteria.
```

#2056 decides keep-or-delete on one question: did any `PLANNER_GAP` finding name
a concern that later cost real work? It must now also report how many findings
rested on concerns the planner plausibly never held.

## Track B — independent scope reconstruction (new)

The reconstruction control is the strongest result to act on. Rather than asking
the implementer what it considered, have a cheap independent model read the
packet, diff, and test artifacts and reconstruct:

- apparent implemented scope
- omitted requirements
- inferred assumptions
- likely failure modes

This has no incentive alignment with the work under review and no dependence on
self-report faithfulness. Findings it can support:

```text
FAIL: 11 mandatory requirements were present in the packet. The implementer
selected 5, and no evidence exists for 4 of the omitted 6.

WARN: the implementation assumes retries are at-least-once. The execution packet
does not define retry delivery semantics.
```

The second is valuable in a direction the rest of this plan does not reach: it
finds gaps in the *packet*, not in the agent.

Storage and comparison land in auditctl; kctl stores nothing here. The comparison
surface is:

```text
frozen requirements
  vs implementer declaration
  vs observed actions
  vs submitted evidence
  vs independent reconstruction
```

## Track C — scope declaration as prospective intervention (new)

This is the reframing that un-parks the executor-side declaration. The earlier
revision parked it as untrustworthy *observation*, and that judgment stands. But
as an **intervention** it needs no trustworthiness at all:

> Does requiring a structured scope declaration before tool use reduce missed
> requirements and scope drift?

The declaration's causal effect on the work is measurable regardless of whether
it faithfully describes anything. This is cognitive scaffolding, not telemetry.

A second, weaker use survives alongside it: comparing a declaration against
subsequent artifacts yields contradiction findings whose value comes from the
contradiction, never from assuming the declaration was true.

```text
WARN: REQ-007 was declared complete, but no corresponding implementation or
verification evidence was identified.

INFO: preflight declaration reproduced all requirement IDs but identified no
risks, assumptions, exclusions, or differentiated implementation concerns.
```

The `INFO` case is a plausible weak-model signal: a declaration that mechanically
copies the packet is technically complete and demonstrates no task decomposition.

### Experiment design

Randomize comparable packets across three arms:

1. **Control** — normal implementation packet.
2. **Preflight declaration** — executor must emit the structured declaration
   before tool use.
3. **External preflight review** — a cheap independent model reviews the packet
   and hands the executor likely omissions and ambiguities.

Measure: mandatory requirements missed; exclusions violated; unsupported
completion claims; acceptance-test failure rate; rework required; token and
latency overhead. Stratify by model strength and packet size — the effect is
expected to be strongest for weaker models on moderately sized packets and
absent for scopes that are simply too large.

Arm 3 is included because if an external reviewer beats self-declaration on
underdefined packets, Track B is the better investment and Track C's arm 2 can be
dropped.

## Parked

- **Any claim that a declaration reveals internal state**, and any feature named
  or documented as introspection. Closed by the independent-branch limitation,
  not merely deprioritized.
- **Free-form concept reporting** ("list the concepts affecting your
  reasoning"). Closed by the confabulation result.
- **Gate authority for an executor-side declaration**, at any maturity. A
  declaration authored inside the session being judged must never be able to pass
  its own work. Track A's planner-side comparison may become blocking later
  because it compares two coordinator artifacts.
- **kctl as a storage home.** kctl is a knowledge-lifecycle tool and must stay
  read-only from sprintctl. auditctl stores declarations and reconstructions.
- **A fourth `session-note/v1` `note_kind`.** The schema defers process-
  observation kinds pending a demonstrated consumer; a keep ruling in #2056 or
  the Track C trial is how that bar clears.
- **Runner-published model-internal-state capture.** Parked on capability,
  privacy, and interpretation-stability grounds rather than on the epistemic
  grounds that closed self-report. No schema accommodation is in scope; see
  "Ingestion-path notes" above.

## Ingestion-path notes (not owned by this plan)

Assessing whether a hypothetical richer telemetry source — runner-published
model-internal-state capture — would fit the existing audit ingestion path
surfaced two defects that are live today and have nothing to do with this
pilot. They are filed independently as #2063 and #2064 and must not be
scheduled or descoped as part of it.

Recorded here only because this plan is where they were found, and because they
establish the shape any bulky payload would have to take: a digest and an
`immutableRef {kind: "artifact"}` in the event, with the bulk in
`_artifacts/<repo_id>/` and never in the ledger line. `allow_nan=False` in
`canonical_payload_json` is deliberately retained as the mechanical enforcement
of that boundary.

The internal-state capability itself remains parked — see below. It would
dissolve the independent-branch limitation, since capture would come from the
same forward pass as the action, which is exactly what makes it tempting. It is
still not worth designing for: no runner in use exposes it, activations are
plausibly prompt-invertible and so exceed the privacy line `session-capsule`
already drew by storing prompt digests and never content, and a vector is
meaningless without extractor identity that churns far faster than an
append-only ledger's permanence contract. Forward compatibility here is free
precisely because the comparison surface takes it as one more column.

## Acceptance

1. `acceptance_properties` items carry unique validated ids; the `gate_set_hash`
   break is documented with its schema version. (#2053)
2. Freezing a packet emits exactly one `planner.scope_declaration` bound to the
   packet and work item, using only constrained fields; re-freezing does not
   duplicate it. (#2054)
3. The `PLANNER_GAP` pass is read-only and cannot change a dispatch outcome,
   proven by a test where maximal findings still dispatch unchanged. (#2055)
4. #2056 reports predictive value *and* an estimate of findings resting on
   concerns the planner plausibly never held.
5. Track B reconstruction runs from artifacts alone, with no access to any
   declaration, and its findings are recorded separately so its independent
   contribution is measurable.
6. Track C reports per-arm outcomes stratified by model strength and packet size,
   including the null result if arms do not separate.

## References

- `templates/dispatch/hybrid/task-packet.schema.json`
- `templates/dispatch/scripts/hybrid_dispatch.py` — `validate_packet`, `_receipt`
- `templates/dispatch/session-mechanization/session-note.schema.json`
- `auditctl/auditctl/validation.py` — event type freedom, `VALID_REF_PREFIXES`
- AgentOps #2036 — execution-envelope compilation (freeze boundary)
- AgentOps #2046 — hybrid packet gate hardening (adjacent)
- AgentOps #2017 — frozen assessment corpus (consumes the `gate_set_hash` note)
