# The `build_from_spec` probe — does a second route need to exist?

**Status: measurement, for an owner ruling. Nothing has been applied.**

Prepared 2026-08-26 as Row 0 of the resumption plan, to settle owner call 1 of
`agentops#2100` — *are route and authority one axis or two?* — before any file is touched.

The boundary decision document
(`docs/plans/agentops/2026-08-25-mechanical-bulk-boundary-decision.md`) recommends **Option C**
(decouple with an explicit `action_class` on the packet) and names its own falsifier:

> a `build_from_spec` design needs a different model, agent or attempt budget — then they are
> genuinely two routes and the split proceeds route-side

and prescribes the cheap test:

> draft one `build_from_spec` packet against `hybrid-dispatch.v1.json:72` and see whether any field
> other than the precondition shape changes. Given all 34 packets already use `starts_red`, the
> prediction is none does — testable before any file is touched.

**The prediction holds, and the result is stronger than predicted.** Not only does no field change —
the route has already run four `build_from_spec` tasks, successfully, without anyone noticing.

## 1. Every field a `build_from_spec` packet would set

Measured across all **38** committed packets (35 at the time of the decision document, plus the
three recovered on 2026-08-26).

| Field | Value across 38 packets | Would `build_from_spec` differ? |
|---|---|---|
| `route` | `mechanical_bulk`, 38/38 | this is the question |
| `task_class` | `mechanical_implementation`, 38/38 | **no** — and nothing reads it |
| `risk` | `low`, 38/38 | **no** — and nothing reads it |
| `oracle.ownership` | `externally_defined` | no |
| `oracle.worker_may_modify` | `false` | no |
| `oracle.starts_red` | present and non-empty, **38/38** | **no — see §2** |
| `limits`, `context_churn`, `network_policy`, `worktree`, `review` | task-shaped, not route-shaped | no |

`risk` and `task_class` appear in **no** code path — `grep` finds no read of either in
`templates/dispatch/scripts/*.py`. They are descriptive.

**`route` is read in exactly four places**, and this is the whole of what the route decides:

- `hybrid_dispatch.py:1985`, `:2184`, `:2397` — `policy["routes"][route]["harness_model"]`
- `hybrid_dispatch.py:1903` — `policy["routes"][route]["agent"]`
- `hybrid_dispatch.py:2119` — `classes.get(packet["route"])`, the authority lookup, **the collision**
- `hybrid_dispatch.py:389-390` — the qualification pair `(route, harness_model)`

So a route means: **which model, which agent** — plus, by the collision, **whether a green gate may
mint a candidate without a human review record.**

## 2. The precondition shape does not change either — it is already enforced

`#2100`'s premise is that `mechanical_bulk` "CANNOT support new behavior whose acceptance test must
fail before implementation", and asks for an explicit expected-failure receipt.

`oracle.starts_red` **is not a boolean flag**. It is a list of registered command ids, and
`check_oracle_attainable` (`hybrid_dispatch.py:1165`) *executes every one of them* at
`starting_commit` in a throwaway clone and requires each to be **red for a reason other than
absence** — exit 127 is a fault, because "the oracle does not exist in the workspace the worker will
be given" is a missing test, not a failing one.

That is not a declaration of an expected failure. It is an **executed proof**, taken before the
worker is dispatched, and it is strictly stronger than what `#2100` asks for. All 38 packets pass it.

## 3. The empirical result: the route has already done it, four times

If `build_from_spec` means *the acceptance test fails before implementation because the thing does
not exist yet*, then four of the last five rows were `build_from_spec` tasks dispatched on
`mechanical_bulk`:

| Row | Sole writable path | At its `starting_commit` |
|---|---|---|
| V6-E | `templates/dispatch/scripts/churn_metrics.py` | **did not exist** |
| V6-F | `templates/dispatch/scripts/gate_tiers.py` | **did not exist** |
| V6-G | `templates/dispatch/scripts/defect_seeds.py` | **did not exist** |
| V6-H | `templates/dispatch/scripts/command_evidence.py` | **did not exist** |

Each was given a red oracle testing a module with no baseline whatsoever, and each produced it. This
is not an edge case the route tolerates — it is the **established shape** for anything touching
protected code: the worker writes a new pure-logic module, the coordinator hand-passes the wiring.

The route did not merely support building from spec. For the whole V6 tract, that is the only thing
it did.

## 4. What this settles, and what it does not

**Settled — falsifier 2 of the decision document is answered: NO.** A `build_from_spec` task needs no
different model, no different agent and no different attempt budget, because four have already run
on the existing binding. The split does not proceed route-side. There is no second route coming.

**Consequence for `#2100` (owner call 4).** Its stated premise is not merely stale, it is
contradicted by four dispatched rows. The item asks for a capability the route demonstrably has.

**Consequence for calls 1–3 and 5 — and this is the part that needs your ruling.** Option C's case
rested on route and class being *about to fork*, with the specific danger being that adding
`build_from_spec` as a route would tempt copy-pasting an `action_classes` block carrying
`self_candidate: true`. **If no second route is coming, that danger does not arise**, and Option C's
own third falsifier applies immediately rather than in six months:

> six months on, every packet's `action_class` still equals its `route` — the decoupling bought
> nothing and should be collapsed.

On this measurement it would equal it on day one, for all 38 packets, with no second route in
prospect. That points at **Option D** — keep the collision, document it, close `#2100` as
substantially delivered — where the decision document pointed at C.

**This is a ruling, not a calculation, and it is yours.** The measurement changes what the options
cost; it does not decide whether route and authority *ought* to be one axis. Specifically:

1. If you hold that they are one axis by design, **D** follows and this document is the evidence.
2. If you hold that they are two axes on principle — that authority to skip human review should
   never be inherited from an execution binding, whether or not a second route is coming — then
   **C** still follows, and it is cheap (one agentops-only hand-pass, no packet edited, no
   `packet_hash` moved, no receipt de-linked).

What the measurement *does* remove is the urgency argument. Neither option is now racing a
forthcoming route.

## 5. Cost of this probe

One frontier reading pass. No packet drafted, no file changed, no dispatch. The decision document
predicted this test would be cheap; it was.
