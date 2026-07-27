# Handover — hybrid worker routes, 2026-07-27

Session outcome in one line: the "cheap worker routes cannot produce a patch"
result was **two driver defects**, both fixed; the routes are still not usable
unattended because a **worker escapes its workspace and writes to the
coordinator's checkout**, and that is detected but not prevented.

Full evidence: agentops#2017 event #2121. Measured against
`opencode-go/deepseek-v4-flash`, OpenCode 1.18.5.

## Resolved

**Worker toolset restored** (`8084176`). OpenCode 1.18.5 treats a
`"*": "deny"` permission as *withholding* tools rather than gating them, so the
deny-by-default overlay handed the worker no toolset and it emitted pseudo tool
calls as prose. The same holds inside a per-tool map: an `edit` map whose `"*"`
is `deny` withholds the edit tool even with per-path allows, so scoping `edit`
to `writable_patch_paths` silently guaranteed an empty diff. Tools are now
enumerated explicitly and `edit` is granted whole; writable scope is enforced by
the `diff-scope-respected` post-gate, always its real adjudicator. `bash` does
not share the behaviour and keeps its registered-command map.

**Worker stdin hang closed** (`8084176`). `opencode run` blocks in `init` when
stdin is inherited, burning the packet's whole timeout without reaching
inference — indistinguishable from a slow model, and the likely cause of the
glm-5.2 ten-minute overrun. Worker and gate subprocesses now run with stdin
closed.

**Workspace isolation** (`756c768`). Disposable standalone clone instead of a
linked worktree: `origin` removed, `--no-hardlinks`, so a worker shares neither
push topology nor object store with the coordinator. Needed **no**
`agentops-task` schema bump — `worktree.{root,branch,cleanup}` are
mechanism-agnostic.

**Recoverability made structural** (`756c768`). `prepare` pins
`safety/pre-dispatch-<task_id>`, emits the exact reset command, and lists
uncommitted coordinator paths that ref *cannot* protect. Breach receipts carry
their own cleanup commands. No operator has to remember to checkpoint.

**Dispatch refuses where the escape works** (`d0ee0de`). `run` refuses when the
coordinator checkout is writable by the worker's identity — exactly the
condition under which the escape succeeds. `--allow-writable-coordinator`
overrides for a supervised run on a disposable host. This makes "workers on
devbox, not the workstation" a property of the CLI rather than a convention.

**Branch backlog cleared for decision.** All seven stale branches across
agentops/vuoro/gitops-nixos are deletable; `sprintctl-1245-adapter-pin` must
*not* be merged (it would roll the composition back to actionq schema v1). The
only content not otherwise on main is `hyprlock.nix`/`hypridle.nix` in
gitops-nixos, worth redoing fresh rather than merging a February snapshot.
Deletions are **not** yet executed.

## Still needs resolution

**The containment escape (blocking unattended use).** A worker writes to the
coordinator's main checkout instead of its workspace. `external_directory:
deny` does not stop it. Reproduced on every attempt.

Three fixes were tried and **all failed — do not retry them**:

1. Rewriting the absolute coordinator path out of the workspace's auto-loaded
   `AGENTS.md`. No effect: on a linked worktree OpenCode resolves the project
   root to the main checkout and loads *that* copy.
2. Standalone clone alone. A bare probe in such a clone stayed inside it, but
   the same clone driven through the full packet path escaped on its first tool
   call.
3. Clone plus reroot together, with the rewrite verified to have applied.

The channel is therefore **neither git topology nor the auto-loaded context
file**. Further textual mitigation is the wrong move. The boundary must be one
the worker cannot address at all: an identity without write access to the
coordinator checkout, or a mount namespace where that path is absent. **The
devbox uid/permission change requires sudo and was not performed.**

Interim controls, both driver-enforced: the refusal gate above, and a porcelain
snapshot around the worker loop that fails the packet as `containment_breach`
(exit 3). The post-gates alone would *not* catch this — they observe only an
empty workspace diff.

**Route qualification is void.** Every assessment predating 2026-07-27 measured
the overlay, not the models, and must be rerun against the fixed driver. Those
runs are additionally contaminated: an empty worker diff did **not** mean no
edit occurred. Every route remains `available_unqualified`, `qualification:
none`. The one honest new data point is the opposite of the original — given
actual tools, the bulk route completed a trivial task correctly on first
attempt, repeatedly.

**Item descriptions are immutable in served mode.** `sprintctl item edit` fails
with `served-operation-unavailable`, so vuoro#2019's stale acceptance criterion
survives in its stored description; the correction lives only in events
#2123/#2124. Filed as **sprintctl#2021**. This affects any item fleet-wide
whose description asserts a stale conclusion.

## Deferred

Deferred deliberately, in the revised plan order:

- **Atomic worker-commit contract** — pointless until workers land patches.
- **Integration-wave branches / cherry-pick queue** — main stays the integration
  branch, per the single-maintainer posture. Revisit only if a wave needs easy
  abandonment.
- **Write-claim scheduling and exclusive-path leases** — speculative. Zero
  qualified routes and no measured contention; build after evidence, not before.
- **Conflict-resolution task type** — same reason.
- **Mount namespaces** — only if workstation workers are wanted. uid separation
  on devbox is the cheaper control and should be tried first.
- **Frontier subagent isolation** — explicitly *not* pursued. Frontier subagents
  sharing the coordinator tree is the daily workflow and works; isolation is a
  cheap-worker control, not a general one.
- **Branch deletions** — decided but awaiting the operator.

## Next actions, in order

1. Devbox uid separation so the agent identity cannot write coordinator
   checkouts (**needs sudo — operator**).
2. Re-verify the escape under that boundary; the refusal gate should then pass
   on devbox and continue refusing on the workstation.
3. Rerun the #2017 qualification corpus against the fixed driver — the first
   real measurement of these routes.
4. Confirm no deployment path follows `main` HEAD (gitops-nixos
   `deploy-host.sh`, appservice GitOps revisions) before relying on "main may
   break". **Unverified.**
5. Execute the branch deletions.
