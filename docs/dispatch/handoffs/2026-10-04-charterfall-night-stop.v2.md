# Handoff 2026-10-04-charterfall-night-stop.v2

<!-- Rendered from the canonical JSON beside this file. Do not hand-edit:
     `agentops handoff validate` and `ack` read the JSON, never this. -->

**Objective.** After the operator resumes, implement full three-faction sets and stronger battlefield mechanics in Charterfall.

**Next action.** Wait for operator resume, then cd /projects/dev/charterfall, git fetch origin, read docs/plans/IMPLEMENTATION.md and refresh the served Vuoro reservation before choosing the next audited gap.

## Predecessor

- harness: codex
- session: 6b4585a0-a7ca-4b26-a7dd-77e947240aea
- model: GPT-6
- context used: unknown%
- transcript: unknown
- origin: `workstation:/projects/dev/agentops/docs/dispatch/handoffs/2026-10-04-charterfall-night-stop.v2.json` (authoritative copy; an ack from another host goes through it)

Read-only after transfer: once a successor acks, the predecessor makes no
edits and takes no external actions. It stays consultable.

## Constraints

- Operator explicitly stopped for tonight; do not resume development until requested.
- Three playable factions, two doctrines each; five-unit neutral Custodian Array. No playable Cold Mandate expansion now.
- Canonical repository is bayleaf/charterfall on git.apps.kotona.app; land ordinary work on main with exact-SHA CI.
- Use served Vuoro through project direnv; never use local database or SPRINTCTL_URL.
- Run Node, Chromium and network commands with sandbox escalation when required. Credential probes precede credential reasoning.
- Static catalog is first presentation increment; do not claim final production art or full product acceptance.

## Decisions

- **Original SVG masters and paired albedo/ownership-mask atlases supply the complete static roster first.** — Provides inspectable original provenance and deterministic byte-identical builds while leaving pinned Blender animations for later.
- **Normal CI validates assets with Node only.** — The Node slim CI container does not require Python or Chromium; authoring tools are needed only for rebuilding.
- **Ruleset 17 preserves purchased presentation IDs.** — Existing units and queued purchases retain their appearance when a doctrine changes.

## Rejected

- **Binding controls only after initial atlas load.** — An early replay upload was ignored; handlers now bind before awaiting initial preparation, and browser replay coverage passes.
- **Broker repo.write credential for this repository.** — Earlier measured repository-unregistered denial; use existing configured Git SSH, never widen credentials.
- **Treating generated static silhouettes as production art acceptance.** — Six HQ module files still reuse two underlying shapes; facings, animation, human recognition and performance acceptance remain open.
- **Broad build/ ignore rule for generated simulation output.** — It also omitted two assets/source/command/build masters; canonical CI caught this. Root-only /build/ now preserves the original command masters.

## Repo state

Digest definition: v5 (see the handoffs README).

| path | branch | head | dirty | unpushed | diff_sha256 |
|---|---|---|---|---|---|
| `/projects/dev/charterfall` | main | `f746d9e53448` | no | 0 | `e3b0c44298fc1c14…` |

## Unresolved

- Refine six doctrine module silhouettes by faction and audit tactical recognition.
- Full faction role/doctrine matchup acceptance remains unfinished.
- Array controller extraction and concurrent-sector incidents remain open.
- Authored terrain/LOS, physical production structures, formation traffic, scale/performance and multiplayer authority remain open.
- Richer program hardware, camera/minimap and Phaser presentation remain open.
- Pinned Blender facings/animation, original map kits, effects and audio remain open.
- Earlier 600-unit benchmark around 49.37 ms/tick exceeds the 10 ms target; not resolved by this asset increment.

## Evidence

- artifact: `/projects/dev/charterfall/docs/plans/IMPLEMENTATION.md`
- artifact: `/projects/dev/charterfall/tools/assets/README.md`
- artifact: `/tmp/charterfall-assets-browser-final.log`
- artifact: `/tmp/charterfall-assets-all-tests.log`
- sprintctl: `served item 2610, sprint 561, reservation 180, session charterfall-factions`
- sprintctl: `served item 2610 note 4498: exact SHA f746d9e534487fd182648ae019378969dcf43751 CI run 25 succeeded`

## sprintctl bundle

- `/projects/dev/agentops/docs/dispatch/handoffs/2026-10-04-charterfall-night-stop.v2.sprintctl-bundle.json` (sha256 `c18a9f0edf63ace4…`)

## Successor

- session: (unacknowledged)
- acknowledged: —
