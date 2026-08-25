# `mechanical_bulk` is a route and an action class — decision document

**Status: analysis and recommendation. NOT a ruling.** The manifest sets
`acceptance_authority: human`, and items (1)–(5) in §6 are owner calls. Nothing here has been
applied to any file.

Blocks `agentops#2100`. Prepared 2026-08-25. Claims below were independently re-verified against
the code before this document was committed; where the check disagreed with the analysis it is
marked.

## 1. The collision, precisely

**As a route** — *who executes, on what model, under what budget.*
`templates/dispatch/hybrid/hybrid-dispatch.v1.json:72` binds `harness_model`
`opencode-go/deepseek-v4-flash`, agent `ao-mechanical-bulk`, `max_attempts: 3`.
`route` is a **closed enum** (`task-packet.schema.json:74-80`): `mechanical_bulk |
bindery_external_runtime_w0`.

**As an action class** — *whether a green gate may mint a `candidate` with no human review record.*
`agentops.dispatch.json:32-38` carries `self_candidate: true` with an L-3/D-8 owner ruling.

**They are the same string in one dict lookup, with no indirection.**
`hybrid_dispatch.py:self_candidate_class()` is literally `classes.get(packet["route"])`, returning
`packet["route"]`. *Verified.*

And the collision is **enforced**, not incidental. `validate_hybrid_dispatch.py:182`:

```
if name not in worker_routes:
    raise ValueError(f"{path}: action class {name} is self_candidate but is not a hybrid worker route")
```

*Verified verbatim.* So **renaming the action class alone is impossible** — the validator refuses it.
That closes the most obvious repair before it starts.

The asymmetry that makes this a collision rather than a deliberate unification: the other action
classes (`plan`, `build`, `review`, `verify`, `reconcile`) are coordinator-side, carry
`model_alias`, are never routes, and are never looked up by a packet. `mechanical_bulk` is the only
key living in both namespaces.

## 2. Blast radius (measured)

- **34 frozen packets, 100% `route: mechanical_bulk`.** No packet uses
  `bindery_external_runtime_w0`. There is no route diversity to preserve. *(Analysis said 33; it is
  34 as of `V6-H`, which landed during the analysis. Direction unchanged.)*
- **19 receipts** embed `"route": "mechanical_bulk"`. These are audit records: re-interpretable,
  not rewritable.
- **Seven repos** opt into the route name (`actionq`, `hostproto`, `outctl`, `sprintctl`, `vuoro`,
  `vuoro-bounded-output-starter`, `agentops`). **Only `agentops` has `mechanical_bulk` in
  `action_classes`.** *Verified.* So in the other six `self_candidate_class()` returns `None` and
  every packet still needs a review record — the authority grant is agentops-only, but it is
  granted by a *coincidence of key naming* rather than by an explicit statement.
- Every file where the name is load-bearing is a **protected path**. No dispatched worker can make
  any version of this change; it is a coordinator hand-pass regardless of which option is chosen.

## 3. A finding that changes the question

**`#2100`'s stated premise is stale.** It asks to split the route because `mechanical_bulk`
"structurally supports only adding coverage to already-working behavior" and "CANNOT support new
behavior whose acceptance test must fail before implementation", wanting an explicit
expected-failure receipt.

`oracle.starts_red` already *is* that receipt, and postdates the item (`#2100` is dated
2026-08-03). Named commands must be red at `starting_commit`; a declared-red command that is
already green is a fault; every unrelated command must still be green; exit 127 is rejected so a
packet cannot dispatch against an oracle its workspace never contained. Reinforced since by
`reference_patch` (must turn the oracle green) and `defect_seeds` (must turn it red).

**All 34 frozen packets carry a non-empty `starts_red`.** *Verified.* The "cold-green-only" route
does not exist in practice: every packet ever run was a build-against-a-red-oracle packet.

So the residual content of `#2100` is **not an execution split**. `mechanical_patch` and
`build_from_spec` would share harness, model, agent and attempt budget. They differ only in
precondition shape and in *what authority a green gate carries* — an action-class distinction
wearing a route's clothes. The collision is precisely why `#2100` was written as a route split.

## 4. Options

**A — rename the action class only. Blocked** by `validate_hybrid_dispatch.py:182`. Recorded so it
is not re-proposed.

**B — rename the route (and class in lockstep).** Touches both schema enums, the policy, the agent
name, 34 packets, 7 manifests, 15 test files. Breaks every external repo simultaneously (the enum
is closed). Editing `route` in a frozen packet moves `packet_hash`, so every receipt's
`execution_id` de-links from its packet and replay/audit breaks. **Pays no debt** — the welding
survives the rename. Strictly worse than doing nothing.

**C — decouple with an explicit `action_class` on the packet.** Optional `action_class` in the
packet schema; `self_candidate_class` becomes
`classes.get(packet.get("action_class") or packet["route"])`; the validator's route-membership test
becomes "permitted for an enabled worker route". **The fallback is what makes this free for
history**: no packet is edited, no `packet_hash` moves, no receipt de-links, and the six external
repos are bit-identical because they have no such action class. One agentops-only hand-pass.

**D — keep the collision, document it, close `#2100` as substantially delivered.** Zero migration.
Cost: the next route added silently acquires whatever `action_classes[<that name>]` says — nothing
(fail-safe) or a copy-pasted `self_candidate: true` (not).

## 5. Recommendation

**Option C**, on three grounds:

1. The two concepts differ and are about to fork. `#2100` wants two preconditions on **one**
   execution binding, which is inexpressible today at any price.
2. The failure mode is **authority escalation, one copy-paste away**. Under D, adding
   `build_from_spec` as a route tempts adding `action_classes.build_from_spec`, and the nearest
   template block carries `self_candidate: true`. `build_from_spec` — new behaviour, red oracle, no
   baseline — is the single case where minting a candidate without human review is least
   defensible. Under C the grant requires writing a fresh `self_candidate_ruling`: an act, not an
   inheritance.
3. It is the only option preserving the frozen corpus exactly, and it respects the protected-path
   boundary at minimum cost.

**Falsifiers.** The recommendation rests on route and class diverging. It is wrong if:

- the owner rules that route and authority are one axis by design — then **D is correct**;
- a `build_from_spec` design needs a different model, agent or attempt budget — then they are
  genuinely two routes and the split proceeds route-side;
- six months on, every packet's `action_class` still equals its `route` — the decoupling bought
  nothing and should be collapsed.

**Cheapest thing that settles the second today:** draft one `build_from_spec` packet against
`hybrid-dispatch.v1.json:72` and see whether any field other than the precondition shape changes.
Given all 34 packets already use `starts_red`, the prediction is none does — testable before any
file is touched.

## 6. Owner calls (not to be dispatched)

1. **Are route and authority one axis or two?** C vs D turns on this and on nothing technical.
2. **Does any future class inherit `self_candidate`?** Recommended: never implicitly.
3. **Does the existing L-3 ruling transfer to a renamed class?** It was written about this class on
   this evidence. Owner's to re-affirm.
4. **Is `#2100` rescoped or closed?** Its premise is contradicted by `starts_red`; rescoping a p2
   item is a scope change.
5. **Alias lifetime** for `mechanical_bulk` as an action-class key.

Unsettled from the repo alone: whether `bindery_external_runtime_w0` is ever intended to be
`self_candidate` (zero packets, no evidence either way).
