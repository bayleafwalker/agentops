---
name: realign
description: Check work against current tenets and directions, record observations, and open or resolve a realignment session. Use when work may diverge from a stated position, when a claim looks contradicted by what the repository actually does, or when starting a session and wanting to know what is operative.
---

# Realign

The metanarrative model in `templates/dispatch/model/README.md` is authoritative.
Read it if anything below is ambiguous.

## Start here, always

```bash
templates/dispatch/scripts/metanarrative.py --scope <repo> status
```

Cheap, safe when no records exist, and it answers three questions at once: what is
current, what is contradicted, and what sessions are open.

## The rules that matter when applying this

- **`current` means operative, not approved.** Never wait for a human to make a
  claim current, and never add an approval step to any flow here.
- **`actor_type` is provenance.** Record `agent` when an agent established
  something. It carries no less weight than `human`.
- **A contradicted claim does not change state.** `current` + `contradicted` is a
  legitimate, useful position: it names reconciliation work. Do not "fix" it by
  editing the claim or suppressing the observation.
- **Only `divergent` opens a session.** `tension` is recorded and watched.
- **Escalation closes nothing.** `--attention` leaves the session open.

## Classifying work

| Class | Meaning |
|---|---|
| `aligned` | consistent with the tenet |
| `extension` | goes beyond it without contradicting it |
| `tension` | pulls against it; recorded, watched, no session |
| `divergent` | incompatible with it; opens a session |

```bash
metanarrative.py align wi:2311 --tenet sprintctl-lifecycle --alignment extension
metanarrative.py align wi:2400 --tenet sprintctl-lifecycle --alignment divergent
```

A divergence prints the tenet's `basis_for` — the blast radius of superseding it.
Read that before choosing a resolution.

## Resolving

Two substantive resolutions, and they are genuinely different decisions:

```bash
metanarrative.py resolve <session> --resolution realign-work      # the work changes
metanarrative.py resolve <session> --resolution supersede-tenet   # the position changes
```

If neither is available within delegated authority, request attention on one of
four grounds and **leave it open**:

```bash
metanarrative.py resolve <session> --attention unresolved-value-choice \
  --detail "the tenet and the work encode different product positions"
```

`missing-delegated-authority` · `unresolved-value-choice` · `owner-reserved-change`
· `conflict-without-precedence`. If your reason is "a person should decide", it is
not one of these — find which of the four actually applies, or resolve it.

## Recording an observation

When the repository contradicts a stated practice, say so. This is the mechanism
that keeps declared position and reality from drifting apart silently.

```bash
metanarrative.py observe obs-forgejo-remotes --subject hosting-github \
  --stance contradicts --evidence-ref sha:<commit>
```

## Invariants

A claim with `enforcement_mode: block` is an invariant. Divergence from it is not
a session — it stops the work. Encode invariants as acceptance-lab scenario
checks; tenets are not scenario checks, by construction.
