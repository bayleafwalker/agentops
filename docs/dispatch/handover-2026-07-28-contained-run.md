# The first contained worker run — 2026-07-28

Supersedes the open questions in
[`handover-2026-07-27-worker-routes.md`](handover-2026-07-27-worker-routes.md)
about whether the uid boundary holds in practice. It does, and the
end-to-end contained run now passes its gates. Route qualification is still
blocked, for a reason nobody had written down.

## What now works

`agentops` `8611fe5` + gitops-nixos `c0d25f2`, deployed to devbox.

A packet prepared by the coordinator, dispatched to `agentworker`, and gated
cold: **`disposition: candidate`, all five post-gates green**, one touched
path, nothing out of scope, nothing protected, registered commands exit 0.
The worker's file landed in its clone as `agentworker:agentdispatch 0664`,
and the coordinator's checkout was untouched across the loop.

The `--worker-model` caveat below means this measures the *harness*, not the
`bulk` route. Its receipt says so: `qualification_eligible: false`.

## The workspace was not writable by the worker either

The 2026-07-27 deployment established the boundary and stopped there. What
it actually produced was a worker that could write **nothing at all** —
including the disposable clone it is dispatched into. `prepare` clones as
the coordinator, so every file landed `agent:agent 0644` inside an
`agentworker`-owned root, and the worker, being neither that user nor in its
group, fell through to "other". Confirmed by asking the kernel, not by
reading modes.

This is worth more than a missing `chmod`. The failure is **shaped exactly
like success**: the worker's first edit fails `EACCES`, the driver's
pre-dispatch probe reports `contained` (it is), and the packet ends with an
empty diff. Every signal available at the time says "containment working".
The smoke run would have passed for the wrong reason and the route would
have been recorded as weak.

Ownership cannot span the split in either direction — whichever identity
creates a file, the other is "other" — so the grant is a group,
`agentdispatch`, holding both and scoped to `stateRoot` alone. Two halves:

- setgid carries group *ownership* but not the group *write bit*. The
  coordinator's clone is opened by the driver (`share_workspace_with_group`,
  end of `prepare`); the worker's output by
  `Defaults>agentworker umask = 0002, umask_override`, since sudo otherwise
  takes the union of the caller's umask and the sudoers default and discards
  anything set before exec.
- `check-worker-containment.sh` round-trips the workspace in **both**
  directions, each identity writing a file the other created. The previous
  one-directional check passed in precisely the broken state. It also now
  asserts what makes the group relaxation safe: the worker's group set is
  exactly `{agentworker, agentdispatch}`, and `agentdispatch` owns nothing
  under any coordinator path.

## Provider access follows the identity — this blocks #2017

The first contained run reached inference and stopped at:

```
Model not found: opencode-go/deepseek-v4-flash. Did you mean: deepseek-v4-flash?
```

`opencode models` as `agent` lists the whole `opencode-go` provider plus
`github-copilot`. As `agentworker` it lists seven free `opencode/…` models
and nothing else. The auth store is per-identity, which is *correct* — it is
what stops a compromised worker spending the coordinator's budget, and
2026-07-27 called for exactly that — but it means **no paid route is
reachable as the worker until `agentworker` is credentialed**, and that is
an interactive login the coordinator cannot perform.

Until then `--worker-model` runs the loop on a model the worker can reach.
It is disqualifying on the same footing as `--allow-writable-coordinator`:
a route assessed on a model it does not name measured nothing about that
route. The receipt carries `worker_model`, `route_model`, `model_override`,
and a false `qualification_eligible`, and the override moves the overlay
hash.

## A gate command must not need a project environment

`agentops.dispatch.tests` runs on whatever host a worker is dispatched to,
in a cold clone, with no project environment. One module in that directory
imported `pytest`, which devbox's python does not have, so the first real
contained `prepare` went red and correctly refused the packet.

That module was also pytest-style bare functions, so `unittest discover`
never collected it: on the workstation it contributed **no tests at all**,
and on devbox a single import error. Converting it to stdlib `unittest`
took the suite from 130 to 137 — the extra seven had not been running
anywhere.

## Reads are still not contained

Unchanged from 2026-07-27 and still the bubblewrap justification.
`/projects/dev` is `drwxr-xr-x agent:agent`, so `agentworker` can read every
repository on the host. The uid boundary stops writes and nothing else.
Tightening `/projects/dev` to `0750 agent:agent` is a cheap partial
mitigation ahead of namespaces, at the cost of anything that reads those
paths as another user.

## Next actions, in order

1. **Credential `agentworker` for `opencode-go`** (operator; interactive).
   Separate and spend-capped, per 2026-07-27. Nothing about route
   qualification can start before this.
2. Re-run the smoke packet **without** `--worker-model` and confirm a
   `candidate` on the route's own model. That is the first receipt with
   `qualification_eligible: true`.
3. Re-confirm the two OpenCode overlay findings on **1.18.4** — they were
   measured on 1.18.5 and devbox has not moved. Record the build in any
   corpus.
4. Add the mount namespace (bubblewrap) as the second boundary. Check
   `security.unprivilegedUsernsClone` on devbox first. Network cannot simply
   be unshared while OpenCode needs provider access.
5. Rerun the #2017 qualification corpus from zero.
