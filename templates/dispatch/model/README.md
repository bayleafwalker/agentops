# The metanarrative model

Authoritative. Supersedes the document lifecycle in
`../capability-receipt/README.md` and every workflow that had a ratification step.

> **Governing rule.** Current claims describe the operative position; observations
> test them; dependencies determine change consequence; delegated authority
> determines who or what may resolve divergence. **No workflow contains a
> human-approval stage merely because a human exists.**

## Four axes, kept orthogonal

Most of the confusion this model replaces came from collapsing these onto one
another — `ratified` was a lifecycle state, an authority claim, and a human
workflow stage at the same time.

| Axis | Field | Values |
|---|---|---|
| **kind** | `kind` | `tenet`, `direction`, `practice`, `decision` |
| **state** | `state` | `draft`, `current`, `superseded` |
| **provenance / authority** | `established_by` | `actor`, `actor_type`, `authority_basis` |
| **validity** | `validity` | `effective_from`, `effective_to` |

`state: current` means operative, not approved. `actor_type: human` means a person
did it, not that a person signed it off. An agent-established claim is exactly as
current as a human-established one.

## There is no Practice object

Practices, directions and tenets are all **claims**. Observations corroborate or
contradict them. What is operative now is a **projection** over establishing and
superseding events — `current_claims()` in `../scripts/validate_model_records.py`
— not a separate mutable record somebody has to remember to update.

This admits the state that matters:

```text
claim lifecycle:      current
observational status: contradicted
```

"We host on GitHub" can remain the declared practice while repository
observations show a Forgejo migration has already begun. That discrepancy is
**reconciliation work**. Neither the history nor the policy is silently rewritten
to make the contradiction disappear.

## Commitment is a relation

`committed: true` hides exactly the part that gives commitment meaning: who
depends on which revision, and under what terms.

```yaml
provider: session-note/v1
consumer: doc-refs
effective_from: 2026-08-29
compatibility: backward-compatible
supersedes: null
```

An artifact-level "committed" may exist as a **projection** — *has active consumer
commitments* — but never as the source record.

## Canonicality is a basis relation

```yaml
kind: tenet
scope: sprintctl
statement: sprint lifecycle aligns with market operators and intended user workflows
state: current
basis_for: [sprintctl-design, composition-v4]
enforcement_mode: review
review_trigger: divergence-finding
```

`basis_for` is what makes a claim canonical, and its dependents are the
realignment blast radius. Canonicality is **not** inferred from a dependent
count: a widely used utility may have many dependents without defining product
identity, and a newly established tenet may be canonical before anything is built
on it. It expresses product dependency and change consequence — never approval,
maturity or permanence.

## Tenets and invariants differ in one field

- `enforcement_mode: review` — a **tenet**. Divergence opens a realignment session.
- `enforcement_mode: block` — an **invariant**. Violation stops the work.

A tenet must declare its mode, because a tenet that does not is indistinguishable
from an invariant.

## Alignment and realignment

Work is `aligned`, an `extension`, in `tension`, or `divergent`. Only
**divergent** opens a session; tension is recorded and watched, because treating
every difference of emphasis as a process event is how process becomes noise.

A realignment session is **agent-run** and has exactly two substantive
resolutions:

```yaml
resolution_options: [realign-work, supersede-tenet]
on_unresolved:
  state: open
  emit: attention-request
```

**Escalation is routing, not a resolution.** If neither resolution is available
within delegated authority, the session stays *open* and emits an attention
request. Asking closes nothing. Divergent work may remain an experiment or a
branch, but it cannot silently become aligned current work.

Attention has exactly four grounds. "A human should look at this" is not one:

- `missing-delegated-authority`
- `unresolved-value-choice`
- `owner-reserved-change`
- `conflict-without-precedence`

## Using it

The model is only worth having if writing to it is cheap, so there is one command:

```bash
metanarrative.py status                      # what is current, contradicted, open
metanarrative.py claim <id> --kind tenet --statement "..." --basis-for a b
metanarrative.py observe <id> --subject <claim> --stance contradicts --evidence-ref sha:...
metanarrative.py align <work-ref> --tenet <id> --alignment divergent
metanarrative.py resolve <session> --resolution realign-work
metanarrative.py resolve <session> --attention unresolved-value-choice
metanarrative.py publish <claim>             # hand it to kctl
```

Every mutation emits an auditctl event, `publish` writes the claim to kctl, and
`status` is what a `SessionStart` hook reports so the model shows up in ordinary
work rather than in a separate ritual. Records live under
`<artifacts-root>/<scope>/model/`.

## Stores, not new stores

- **kctl** is the claims store. These schemas are the *shape*; `publish` hands a
  claim over as a knowledge entry. No parallel knowledge store is introduced.
- **auditctl** is the evidence spine. Every model mutation is an event there.
- **acceptance-lab** is the evaluator. An invariant (`block`) is the natural
  scenario check; a tenet is not, by construction.

## Migration

`capability-receipt/v1` files still validate — they are migrated in memory, with
`ratified` mapping to `current` and the `ratification` block to `established_by`
with `authority_basis: owner-reserved`, which is what the literal
`authority: human` assertion was being used to mean. New receipts must be v2.

**One deferred migration, and it is deliberate.** kctl's knowledge category check
constraint (`decision | pattern | lesson | risk | reference`) lives in the
Postgres central schema, on a federation database that is not initialised
cluster-wide. Adding `tenet` and `direction` as first-class categories therefore
needs a live DB migration that cannot be run today. Until then `publish` maps
every claim to the existing `decision` category and carries `kind` in the body.
This is a fidelity loss in kctl, not in the record: the JSON keeps the true kind.
