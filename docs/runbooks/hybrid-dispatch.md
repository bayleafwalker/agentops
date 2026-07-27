# Supervised hybrid dispatch

Status: operational as a workflow; every worker model/task-class pair is
**available but unqualified**. Availability is not qualification, and a passing
smoke run promotes nothing.

## What it is

A frontier **coordinator** (a Claude or Codex harness session) resolves
architecture, freezes a bounded task packet, and reviews the result. A cheap
**OpenCode Go worker** implements only inside that frozen solution space in a
disposable worktree. Deterministic gates reject bad candidates before review; a
human accepts and merges.

```text
coordinator (claude-code | codex-cli)
  → sprintctl item + claim
  → frozen agentops-task/v1 packet at an exact commit
  → disposable worktree, cold registered-command run
  → one bounded worker loop (opencode-go, session permission overlay)
  → cold deterministic gates over the captured diff
  → independent coordinator review
  → human disposition, merge, and sprint state change
```

The design generalizes Frontier Weave's `frontier-routing/v1` supervised harness
hybrid. Frontier Weave's mediated-local vLLM route is deliberately **not** part
of this contract: it is that repository's backup/secure pathway and depends on
its own orchestrator.

## Authority split

| | Coordinator | Worker |
|---|---|---|
| Architecture, ambiguity, scope | yes | no |
| Edit files | yes | only inside `writable_patch_paths` |
| Run commands | yes | only registered `allowed_command_ids` |
| Git | yes | denied |
| sprintctl / kctl / actionq | yes | denied |
| Network fetch/search, sub-agents | n/a | denied |
| Deployment or cluster mutation | no (human) | denied |
| Acceptance and merge | no (human) | denied |

`sprintctl_authority: coordinator_only` is a hard contract line. A worker never
claims, advances, or closes an item, and the packet records which coordinator
actor holds the claim.

## Repository eligibility

A repository is hybrid-eligible only when its `*.dispatch.json` manifest has a
`hybrid` block:

```json
"hybrid": {
  "enabled": true,
  "worker_routes": ["bulk"],
  "commands": { "repo.unit.tests": "uv run pytest -q tests/unit" },
  "protected_paths": ["deploy/**", "*.dispatch.json"],
  "max_timeout_seconds": 1800
}
```

`commands` is the whole command vocabulary a packet may grant — free-form shell
is never handed to a worker. `protected_paths` must be non-empty: without it,
any in-scope path would be writable. Writable packet paths must additionally sit
inside `scope.allowed_path_roots`.

## Operator sequence

Run these from the repository root as the coordinator.

```bash
AO=/projects/dev/agentops/templates/dispatch/scripts/hybrid_dispatch.py

# 1. Freeze the packet, then prove it is fit. A contradictory packet stops here
#    as a task defect; it is never softened into a retry.
python "$AO" --packet packets/EX-1.json validate

# 2. Inspect the exact session permission overlay the worker will receive.
python "$AO" --packet packets/EX-1.json overlay

# 3. Disposable exact-commit worktree + cold gate run. A non-green cold run
#    means the packet is not eligible: developer-tree build products are not
#    evidence that a clean worktree passes.
python "$AO" --packet packets/EX-1.json prepare

# 4. One bounded worker loop.
python "$AO" --packet packets/EX-1.json run

# 5. Cold post-gates over the captured diff. Worker claims are not evidence.
python "$AO" --packet packets/EX-1.json gate
```

Then review the diff in a fresh coordinator context and classify the result as
`candidate`, `retry_same_route`, `reroute`, `task_defect`, or `human_decision`.
Only a human accepts, merges, and moves the sprintctl item.

## Dispatching from the operator via sprintctl

sprintctl is the work-state authority; the packet only references it.

1. `sprintctl next-work` — pick a ready item whose architecture is already settled.
2. `sprintctl claim acquire` — the **coordinator** takes the claim and records
   its actor in `sprint_item.claim_actor`.
3. Freeze the packet at `git rev-parse HEAD` and dispatch as above.
4. On a candidate: the coordinator commits on the packet branch, the human
   reviews and merges, then the item advances (`item-done` skill).
5. On any other disposition: release or hold the claim explicitly and record a
   sprintctl event. Never leave a claim held by a finished worker loop — the
   worker never held it in the first place.

Routes that must go back to the coordinator instead of a worker: unresolved
architecture or ownership, cross-repository sequencing, contradictory acceptance
criteria, security/credential/authority/migration semantics, changes smaller
than the packet overhead, and anything that already failed its escalation
attempt.

## Routes

| Route | Model | Attempts | Use |
|---|---|---|---|
| `bulk` | `opencode-go/deepseek-v4-flash` | 2 | Routine bounded work, fixtures, schemas, mechanical migrations, test-driven repair |
| `substantial` | `opencode-go/kimi-k2.7-code` | 1 | Multi-file work with contracts already decided |
| `escalation` | `opencode-go/glm-5.2` | 1 | One corrected retry after coordinator triage |
| `worker_review_challenger` | `opencode-go/kimi-k3` | 1 | Read-only cheap challenger; never replaces coordinator review |

Do not keep a premium model inside a worker retry loop. A worker gets a fixed
attempt allowance and returns a candidate or a structured blocker; failures are
triaged as a wave, then reissued as corrected packets or rerouted explicitly.

## Validation

```bash
python templates/dispatch/scripts/validate_hybrid_dispatch.py \
  --agentops-root . --manifest agentops.dispatch.json
python -m unittest discover -s templates/dispatch/tests
```

Add `--live` after an OpenCode upgrade, credential change, or model-catalog
refresh to confirm the concrete model ids are still listed. The OpenCode
permission-overlay shape was verified against **OpenCode 1.18.5**; re-verify the
overlay and the `--file` argument ordering on upgrade.

## Contract files

- `templates/dispatch/hybrid/hybrid-dispatch.v1.json` — modes, routes, gates, authority split
- `templates/dispatch/hybrid/task-packet.schema.json` — the `agentops-task/v1` packet
- `templates/dispatch/hybrid/opencode.hybrid.json` — checked-in worker agents
- `templates/dispatch/scripts/hybrid_dispatch.py` — coordinator driver
- `templates/dispatch/scripts/validate_hybrid_dispatch.py` — deterministic policy gate
- gitops-nixos `modules/system/hybrid-dispatch.nix` — pinned host deployment

## Measured OpenCode 1.18.5 worker behaviour

Established 2026-07-27 against `opencode-go/deepseek-v4-flash` on a trivial
single-file task, by comparing a permissive control run with the packet
overlay. Each item cost a real dispatch to find; none is inferable from the
OpenCode config schema.

**A `"*": "deny"` withholds tools, it does not gate them.** The overlay's
blanket top-level deny left the worker with no toolset at all. The model then
emitted a pseudo tool call as prose — `<read_file src="…"/>` — and stopped with
an empty diff after ~15s and exit 0. This reads exactly like a weak model and is
not: the same model with tools enumerated completes the task in two calls. The
overlay therefore enumerates every tool explicitly.

**The same applies inside a per-tool map.** An `edit` map whose `"*"` is `deny`
withholds the edit tool even when specific paths are allowed, so per-path
scoping of `edit` silently guarantees an empty diff. `bash` does not share this
behaviour and keeps its registered-command map. `edit` is consequently granted
whole, and `writable_patch_paths` is enforced where it was always adjudicated:
the cold `diff-scope-respected` post-gate.

**A worker loop must have stdin closed.** With the coordinator's stdin
inherited, `opencode run` blocks in `init` and burns the packet's entire timeout
without ever reaching inference — indistinguishable from a slow model, and the
likely explanation for any route that "ran past its timeout". The driver passes
`stdin=subprocess.DEVNULL`.

### Open: the worktree is not a containment boundary

**A worker in a linked git worktree writes to the main checkout.** The model
globs correctly relative to its worktree, then issues `write` against the
*coordinator's* absolute path — OpenCode resolves a linked worktree's project
root to the main checkout. `external_directory: deny` does not stop this. It
reproduced on every attempt.

Scrubbing the absolute root from the worktree's `AGENTS.md` does **not** fix it
(the path also appears across `docs/**`, and the root is resolved by OpenCode
rather than read from context), so that mitigation was tried and removed rather
than left in place looking protective.

Until this closes, containment rests on one thing: `run` snapshots the
coordinator's `git status --porcelain` around the worker loop and any new entry
fails the packet as `containment_breach` (exit 3), naming the escaped paths. A
breach is never a retryable quality result — it stops for human triage. Note the
post-gates alone would *not* have caught this: they only ever saw an empty
worktree diff.

The candidate fix is to stop using linked worktrees for dispatch and give the
worker a standalone local clone, so no coordinator path exists to resolve to.
That is unimplemented and unverified.
