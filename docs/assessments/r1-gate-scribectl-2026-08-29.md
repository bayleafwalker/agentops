# R1 gate — scribectl vertical slice, 2026-08-29

**Gate:** cross-repo dogfood plan §5 R1 — *D1, D2, D3, D6(interrupt) hold for scribectl.*

Three of the four hold, one holds with a stated qualification, and two of R1's six
bullets are handed to another session rather than done here.

## Bullets

| # | Bullet | State |
|---|---|---|
| 1 | Fix the `adapter-result-invalid` P0 on served `next-work` | **Done before R1** — sprintctl 0.3.3, verified in all six scopes 2026-08-28, vuoro #2313 closed |
| 2 | Make shards authoritative in fact | **Done, and the bullet's premise was wrong** — see below |
| 3 | Audit principal binding per served operation (`#1245`) | **Done, and it found a live defect** — sprintctl `48deaee` |
| 4 | Pin the same service digest across all three deployments | **Handed off** — vuoro deployment-verification session; still three digests |
| 5 | Run `next-work`, interrupt it, resume from a fresh shell | **Done** — scribectl #2328, reservation #49 |
| 6 | Publish one repo-local receipt; rebuild the index from shards | **Done** — `ad:01M16RA47B8T8RPTAEYVECMVA3`, rebuild clean |

## D1 — resume from a fresh process

Item #2328, reservation #49, session `r1-d1-probe`. `next-work` returned the item,
it was reserved and activated, then the process was lost. A new process started with
`SPRINTCTL_BACKEND`, `SPRINTCTL_VUORO_PROFILE`, `AUDITCTL_ARTIFACTS_ROOT` and
`AUDITCTL_DB` all unset.

The resumer recovered, from the repository's own declared environment plus the served
backend and nothing else:

- `active_reservations` → `(49, 2328, 'r1-d1-probe')`
- `next_action` → `inspect-active-reservation` for item #2328
- `last_checkpoint` → sha `4a64fc8`, branch `main`, worktree path

It then transitioned the item to `done` and released the reservation. **Zero operator
actions after interruption**, consistent with the NARROW baseline
(`docs/assessments/narrow-baseline-2026-08-29.md`).

`next-work` after resume correctly reported nothing ready — the item was `active` and
reserved by then, which is the right answer, not an empty one.

**Method note.** A first pass read `active reservations: []` and looked like a defect.
It was a measurement error: the bundle key is `active_reservations` and the probe
asked for `reservations`. Checked before reporting, which is the only reason it is
not recorded here as a substrate bug. Same shape as the other "empty is not absent"
cases this session.

## D6 — interrupt fault case

The interruption above was a real process loss, not a simulated one. What survived
was what the repository declares (`.envrc`, now tracked) and what the principal holds
(the credential at its declared per-host path). Nothing session-local was carried.

**Stated limitation, unchanged from the baseline:** this interrupted a *process*, not
a *host*. Cross-host recovery is a separate case and must not be inferred from it.

## D3 — rebuild

Index 53, committed shards 53, `rebuild --from-ndjson` validates 6 shards / 53 events
against `_artifacts/scribectl/audit/`.

A clean pass proves nothing on its own, so the discriminating control is agentops,
where the identical command **refuses**: 36 index-only events, naming count, sources
and dates. The mechanism works and is not a no-op.

**But D3 is only enforced by unreleased code.** The guard lives in auditctl `main`
(`d88a34c`); the installed 0.1.2 reports `Validated 5 shard(s): 51 event(s)` for an
index holding 52 — success, while silently dropping the event. The gate should be
claimed as *"the rebuild mechanism is correct"*, not *"the deployed tool enforces
it"*. auditctl 0.1.3 is no longer blocked on the central verification
(`auditctl docs/operations/running-the-central-verification.md`).

## D2 — receipt, and the qualification

`ad:01M16RA47B8T8RPTAEYVECMVA3` is written and committed under
`scribectl/_artifacts/scribectl/audit/`. That is a real repo-local receipt.

The qualification is what bullet 2 was actually about. Before today, every receipt
lived under `/projects/dev/_artifacts/`, which is in **no git repository** while
`AGENTS.md` simultaneously classified auditctl "Durable, authoritative | Served". The
two halves of the bullet it names — publisher-appends-before-index, and `rebuild`
refusing index-only events — were both already done. What was not done, and not
named, was that **nothing auditctl wrote was durable anywhere**. That is fixed for
`agentops`, `vuoro` and `scribectl` by rooting evidence at each repository; it is not
fixed for the other twelve scopes.

Cross-host *availability* remains unmet by design: the served audit substrate is
deployed and migrated but holds zero rows, because no client writes to it. Deferred
to a consumer rather than a date.

## The finding worth carrying out of R1

Bullet 3's audit was supposed to be routine — `#1245` had already been narrowed from
a gate to an audit by the 2026-08-28 sample session. It found that of 43 served work
operations, `work.reservation.release` was the only one that accepted a
caller-supplied actor without binding it to the authenticated identity, and that
`release_reservation` writes that actor as the `reservation.released` **event
actor**. So it was not merely an authorization gap: any principal authorized for the
repository could attribute a release to an arbitrary string in the durable record.

Verified in production before fixing, with a control:

```
reserve  --actor not-my-identity  ->  rejected, actor-mismatch
release  --actor not-my-identity  ->  SUCCEEDED
```

and scribectl item #2326 permanently reads
`#2620 [reservation.released] not-my-identity`. That event is deliberately not
retrofitted; it is the evidence.

**The fix is unreleased.** sprintctl `48deaee` is on `main`; the running
`vuoro-shared` still has the vulnerable behaviour until a sprintctl release and a
`vuoro-service` redeploy, filed as sprintctl item **#2327** and handed to the
deployment-verification session with bullet 4.

## Gate disposition

**D1, D6 hold. D3 holds as a mechanism, not as a deployed enforcement. D2 holds for
the three rooted repositories.** R2 may proceed — its question is whether the seam
generalizes with no repo-specific branch in Vuoro, sprintctl or auditctl core, and
nothing here required one: the scribectl enablement was an `authority_repo_uuid` and
an `.envrc` line, both repo-owned config.
