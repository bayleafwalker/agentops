# NARROW baseline — native scribectl path, 2026-08-29

**Item:** agentops #2310 (sprint #551, cross-repo-dogfood-r0)
**Rubric:** operator actions after interruption · glue lines added · state locations touched
**Vehicle:** scribectl #2325, sprint #439, reservation #46. Carries no scribectl product change.

This is the regression baseline every later packet is measured against (D8).

## Scope correction, and why

The item names two paths: scribectl and hostproto. **Only scribectl was run, and the
hostproto half is retired rather than deferred.**

`hostproto` was archived read-only on GitHub on 2026-08-28 and its work split into six
successors, none of which carries a dispatch manifest, a skills directory or a
work-authority marker. Running "the current native hostproto path" is impossible because
that path was retired the day before the item was written. Onboarding a successor to
create one is forbidden by the operative non-goals — *no pre-emptive enablement of
repositories without a consumer* — since no successor has a consumer.

Minting scribectl's authority UUID, by contrast, **is** authorized by the same non-goal:
the dogfood plan §5 names scribectl as R1's first consumer, so its enablement is
consumer-driven, which is the case the non-goal exists to permit rather than forbid.

## The run

Pre-interruption: reserve (#46, session `narrow-baseline`), transition `pending → active`,
record a note carrying git context, produce a handoff bundle.

Interruption: process loss. A new process was started carrying **nothing** — no exported
`SPRINTCTL_BACKEND`, no `SPRINTCTL_VUORO_PROFILE`, no `SPRINTCTL_DB`, no shell state.

Post-interruption: recover position, close the item, release the reservation.

## Result

| Metric | Count |
|---|---|
| **Operator actions after interruption** | **0** |
| **Glue lines added** | **1** |
| **State locations touched** | **6** |

### Operator actions after interruption: 0

The resumer needed nothing from a person. `.envrc` — the repository's own declared
environment — supplied backend, profile and evidence root; the credential was already at
its declared per-host location; the handoff bundle carried `git_context` (branch, sha,
worktree, dirty files) and the active reservation, so position was read rather than
reconstructed. `item status --status done` and `reservation release` both succeeded from
the cold process.

**The one-time enablement cost is separate and must not be folded in: 1 operator action,
before the cycle could run at all.** Without an `authority_repo_uuid`, every authority
command was refused client-side. That is an onboarding cost, not a recovery cost, and a
second interruption on the same repository would cost 0 again.

**A cold process with no declared environment fails correctly**, and this is worth
recording as a pass rather than a defect: `SPRINTCTL_BACKEND=local cannot be used in repo
'scribectl'; repo marker requires served`. The local default is *refused* rather than
silently used — the cred-broker failure mode, guarded.

### Glue lines added: 1

One line: `"authority_repo_uuid": "cc38d8fe-…"` in `scribectl.dispatch.json`
(`4a64fc8`). **Zero glue in the work path itself** — no wrapper scripts, no shims, no
per-repo adapters. The native path is the product's own commands.

### State locations touched: 6

| # | Location | Access | Notes |
|---|---|---|---|
| 1 | Served work authority (`vuoro-shared` → Postgres) | read/write | item, reservation, note, two transitions |
| 2 | `.sprintctl/backend.json` | read | repo marker; the thing that refuses `local` |
| 3 | `scribectl.dispatch.json` | write (once) | the authority UUID |
| 4 | `.envrc` | read | declared environment; what makes recovery cost 0 |
| 5 | `~/.config/vuoro/credentials/vuoro-shared-workstation` | read | **outside the repository**, per-host, carried by no checkout |
| 6 | git worktree | write | commit `4a64fc8` |

Location 5 is the one that matters for later comparison: it is per-host state no
repository can carry, the same class as the Playwright browser cache found during the §10
item 6 loop run. A packet that reduces the other five to zero still cannot reduce this one
below one without changing where credentials live.

## What this baseline means for D8

**0 operator actions after interruption is the number to beat, and it cannot be beaten —
only matched or regressed.** Any later packet that reports a non-zero count on a
repository already carrying an authority UUID is a regression, and the cause will be
either a state location that stopped being declared or a credential that stopped being
where the profile says it is.

The honest limitation: this run interrupted a *process*, not a *host*. Recovery consumed
`.envrc` and a credential file that both survived because the filesystem did. A host-loss
or cross-host interruption would touch location 5 in a way this baseline does not measure,
and devbox-agent is known to diverge — it runs sprintctl 0.3.2 against the deployed 0.3.4
(`docs/assessments/devbox-and-cluster-reality-2026-08-29.md`). Measuring that is a
separate baseline and should not be inferred from this one.
