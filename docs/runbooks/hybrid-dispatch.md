# Supervised hybrid dispatch

Status: operational as a workflow. The sole qualification is the
[`vuoro` `mechanical_bulk` named pilot](../dispatch/hybrid-vuoro-bulk-pilot-2026-07-28.md)
on devbox with `opencode-go/deepseek-v4-flash`. Every other worker
model/task-class/repository pairing is experimental, benchmark-only,
available-unqualified, or coordinator-only. Availability is not qualification,
and a passing smoke run promotes nothing.

The OpenCode profile `opencode-nixpkgs-devbox-1.18.4` is currently
`preflight_observed`, not qualified. Its lifecycle contract is deliberately
narrow: JSON stdout event envelopes carry a `type` and
top-level `sessionID`; finalization continues that same session with
`--continue --session <sessionID>` and the exact `ao-finalizer` agent; and the
finalizer has no tools. The fake and contained probes are not qualification
evidence. Contained identity and provider qualification remain explicit
blockers. The controller owns the work/finalization budgets, terminal result,
settlement, and any publication. A worker transcript or finalizer response is
evidence for the controller, never settlement by itself.

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
  "worker_routes": ["mechanical_bulk"],
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

# 4. One bounded worker loop, as the contained identity.
python "$AO" --packet packets/EX-1.json --worker-user agentworker run

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
criteria, a missing or worker-authored oracle, tests/parity fixtures/adversarial
verification as the primary deliverable, cross-layer behavioural proof,
security/credential/authority/release/compatibility/migration/recovery
semantics, changes smaller than the packet overhead, and any rejected worker
attempt without a materially revised coordinator packet.

## Routes

| Task class | Production owner/model | State |
|---|---|---|
| `mechanical_implementation`, low risk, external oracle | `opencode-go/deepseek-v4-flash` | named pilot, one attempt |
| `bounded_semantic_implementation` | coordinator; paired K2.7 assessment only | unqualified |
| `adversarial_verification` | coordinator | coordinator-only |
| `architecture_authority` | coordinator | coordinator-only |
| worker failure | coordinator triage | GLM has no assigned escalation role |
| experimental benchmark | none | K3 benchmark-only |

Route by failure mode and oracle ownership, not diff size. A large repetitive
migration with generated falsifying checks can be mechanical; a tiny fixture
whose author must infer behavioural parity is not. A worker that cannot execute
its registered focused gate returns `blocked`, not `complete`. Packet
contradiction or a missing oracle is `task_defect`, never a model escalation.

Every mechanical packet declares coordinator-owned acceptance properties. Each
property binds one requirement to a registered command and describes the
incorrect behaviour that makes that command fail. A passing test is not
discriminating evidence when the worker invented or was allowed to modify the
test oracle.

## Host containment (devbox)

The worker runs as `agentworker`, a separate uid, because nothing in the
OpenCode overlay stopped a worker writing into the coordinator's checkout.
Pass `--worker-user agentworker`; the driver refuses to dispatch unless that
identity genuinely cannot write the checkout, asked of the kernel rather than
inferred from modes.

The workspace is shared through the `agentdispatch` group, which holds both
identities and grants `/var/lib/agentops/hybrid-dispatch` and nothing else.
Ownership alone cannot span the split: whichever identity creates a file, the
other is "other". setgid carries group ownership but not the group write bit,
so both halves are explicit — the driver opens its own clone at the end of
`prepare`, and `Defaults>agentworker umask = 0002, umask_override` keeps the
worker's output group-writable for the cold gates.

Verify after any rebuild, on the host:

```bash
sudo ./scripts/check-worker-containment.sh \
  agentworker /var/lib/agentops/hybrid-dispatch/worktrees /projects/dev
```

It must pass before any run counts. It asserts the group set is exactly
`{agentworker, agentdispatch}`, that `agentdispatch` owns nothing under the
coordinator paths, that the workspace round-trips in both directions, and —
adversarially — that the worker cannot create a sentinel under `/projects/dev`.

**Reads are not contained.** `/projects/dev` is world-readable, so a worker can
read every repository on the host. The uid boundary stops writes only; the
mount namespace is still outstanding.

**Provider access follows the identity.** `agentworker` has its own OpenCode
auth store — deliberately, so a compromised worker cannot spend the
coordinator's budget — and until it is credentialed the paid routes are not
reachable as the worker. `--worker-model` runs the loop on a model the worker
can reach, for diagnostics about the harness rather than the model. It marks
the receipt `qualification_eligible: false`, because a route assessed on a
model it does not name measured nothing about that route.

### Credentialing the worker

The key is delivered as a sops secret decrypted straight to the worker's uid,
never through the coordinator. `auth.json` is just
`{"opencode-go":{"type":"api","key":"…"}}`, so the whole mechanism is a file
drop at `/var/lib/agentworker/.local/share/opencode/auth.json`.

1. Create a **new** key in the OpenCode provider console — on its own capped
   plan if one exists. Do not reuse the coordinator's key; that removes the
   separation the worker uid exists to create. This step cannot be automated.
2. Encrypt it, from the gitops-nixos checkout:

   ```bash
   ./scripts/rotate-agentworker-opencode-key.sh --no-deploy
   git commit -m 'chore(secrets): rotate agentworker opencode key' -- secrets/common.yaml
   ```

   The script prompts with echo off and passes the key to sops through the
   environment — never argv, never a plaintext file.
3. Set `profiles.hybridDispatch.workerAuthSecret = "opencode/agentworker/auth"`
   in `hosts/devbox/default.nix`. **After** step 2: sops-nix validates that the
   secrets file is in the store, not that the key exists, so naming a missing
   key builds cleanly and then fails during activation.
4. Deploy and verify:

   ```bash
   ./scripts/rotate-agentworker-opencode-key.sh --verify-only
   ```

   It asserts the worker can list `opencode-go` models *and* that the
   coordinator cannot read the worker's credential. Then revoke the previous
   key in the console — nothing local can do that, and until it is done the old
   key still spends.

Rotation afterwards is the same script with no flags: encrypt, deploy, verify.

**The separate key does not isolate spend.** As deployed 2026-07-28 both keys
sit on the same usage plan, because no separate budget exists to put the worker
on. The split still buys independent revocation, separate provider-side
attribution, and a worker compromise that does not yield the coordinator's
credential — but a runaway worker can still exhaust the shared plan and degrade
the coordinator. Until a capped plan exists, `limits.max_cost_usd` is the only
spend control: the driver totals OpenCode's own per-step cost reporting into
the run receipt and fails the packet as `budget_exceeded` (exit 4) when the cap
is passed. That is necessarily post hoc — one packet can still overspend once —
so its job is stopping a wave from repeating the overspend, not preventing it.

Token ceilings are process-health controls rather than price controls. Small
mechanical packets start with a 500,000-token soft ceiling and a 1,000,000-token
hard ceiling. Crossing the soft ceiling is retained for coordinator review;
crossing the hard ceiling fails the run receipt and stops the packet. Cheap
multi-million-token loops are operational failures even when provider cost is
microscopic.

The optimization target is total operational cost:

```text
coordinator preparation + worker latency + review effort
+ correction effort + verification latency + model cost
```

Run the fastest falsifying command per candidate, focused owner tests after the
candidate is captured, and the full suite only after independent approval.
Retain the packet, candidate bundle, run receipt, logs, gate results, and review
outcome under one durable execution identity.

## Validation

```bash
python templates/dispatch/scripts/validate_hybrid_dispatch.py \
  --agentops-root . --manifest agentops.dispatch.json
python -m unittest discover -s templates/dispatch/tests
```

Before a profile or host change is considered, run the offline contract probe:

```bash
python templates/dispatch/scripts/probe_opencode_profile.py --mode fake
```

On the intended devbox, the contained host probe additionally checks the real
1.18.4 executable as `agentworker` and checks coordinator-root writability. It
then invokes the configured model to exercise the real JSON lifecycle. It
returns non-zero when provider, identity, CLI-shape, or filesystem-boundary
evidence cannot be proven:

```bash
python templates/dispatch/scripts/probe_opencode_profile.py \
  --mode contained --worker-user agentworker --coordinator-root "$PWD"
```

`--mode all` is an explicit convenience for both checks. Fake evidence is
never qualification evidence; contained evidence is still harness/host and
single-invocation evidence, not provider qualification, model-quality, route,
settlement, or deployment authorization.

Add `--live` after an OpenCode upgrade, credential change, or model-catalog
refresh to confirm the concrete model ids are still listed. The OpenCode
permission-overlay shape was verified against **OpenCode 1.18.4**; re-verify the
overlay and the `--file` argument ordering on upgrade.

## Lifecycle and finalization boundary

The work loop and finalizer are separate controller phases. The controller
captures the session identity from JSON events, verifies that every observed
event in the work phase carries the same top-level `sessionID`, rejects
malformed and error events, and invokes the
no-tools finalizer on that identity. The finalizer may synthesize the bounded
terminal handoff from the same observed session; it may not investigate,
edit, run commands, fetch, spawn agents, settle an ActionQ action, or change
Sprintctl state. A missing, malformed, or identity-changing event fails
closed. A process exit, a natural-language claim of completion, or a
finalizer response without a valid immutable result can never settle success.

Continuation here means same-process-session protocol continuation, not a
restart/recovery policy and not the ActionQ `session.resumed` re-dispatch
event. Recovery, retry, settlement, and publication remain owning-controller
contracts and are outside this AgentOps qualification item.

## Contract files

- `templates/dispatch/hybrid/hybrid-dispatch.v1.json` — modes, routes, gates, authority split
- `templates/dispatch/hybrid/task-packet.schema.json` — v1 legacy packets and the current `agentops-task/v2` packet. New v2 packets give every acceptance property a packet-unique stable id. Their receipt records both `packet_schema_version` and `gate_set_hash_schema_version`; never compare a v1 and v2 `gate_set_hash` as though they used the same input contract.
- `templates/dispatch/hybrid/opencode.hybrid.json` — checked-in worker agents
- `templates/dispatch/scripts/hybrid_dispatch.py` — coordinator driver
- `templates/dispatch/scripts/validate_hybrid_dispatch.py` — deterministic policy gate
- gitops-nixos `modules/system/hybrid-dispatch.nix` — pinned host deployment

## Measured OpenCode 1.18.x worker behaviour

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

### Open: the worker escapes to the coordinator checkout

**A worker writes to the coordinator's main checkout instead of its disposable
workspace.** It globs correctly relative to its own tree, then issues `write`
against the coordinator's absolute path. `external_directory: deny` does not
stop it. It reproduced on every attempt.

Three fixes were tried and **all failed**, in this order:

1. Rewriting the absolute coordinator path out of the workspace's auto-loaded
   `AGENTS.md`. No effect — on a linked worktree OpenCode resolves the project
   root to the main checkout and loads *that* copy.
2. Replacing the linked worktree with a standalone clone (no `origin`, own
   object store). A bare probe in such a clone wrote only inside the clone, but
   the same clone driven through the full packet path still escaped on its
   first tool call.
3. Clone plus reroot together, with the rewrite verified to have applied. Still
   escaped.

So the channel is **neither git topology nor the auto-loaded context file**, and
further textual mitigation is not worth chasing. The boundary has to be one the
worker cannot address at all — an identity without write access to the
coordinator checkout, or a mount namespace where that path is absent.

Two controls hold in the meantime, both enforced by the driver rather than by
operator discipline:

- `run` **refuses to dispatch** when the coordinator checkout is writable by the
  worker's identity, which is exactly the condition under which the escape
  succeeds. `--allow-writable-coordinator` overrides it for a supervised run on
  a disposable host. This is why workers belong on devbox, where the agent
  identity has no write access, and not on the workstation.
- `run` snapshots the coordinator's porcelain status around the worker loop and
  fails the packet as `containment_breach` (exit 3), naming the escaped paths
  and the commands that undo them. Note the post-gates alone would **not** catch
  this: they only ever observe an empty workspace diff.

`prepare` also pins `safety/pre-dispatch-<task_id>` and reports the reset
command, plus any uncommitted coordinator paths that ref cannot protect.

### Qualification is void until this closes

Route assessments recorded before 2026-07-27 measured the overlay, not the
models, and must be rerun against the fixed driver. Runs from that period are
additionally contaminated: an empty worker diff did **not** mean no edit
occurred.
