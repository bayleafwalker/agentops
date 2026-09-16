# Dev Environment — Agent Reference

Applies to every project under `/projects/dev/`. Short on purpose: only facts a
session needs. Enforcement lives in hooks (`agentops/hooks/`) and CI, per-host
setup in `agentops/docs/runbooks/dev-environments.md`, component status in
`agentops/docs/ecosystem.md`. History belongs in git and sprintctl, not here.

## Hosts and workspace

`/projects/dev/` is the same path on every host but **not the same files**:

| Host | Detect | Tree |
|---|---|---|
| Workstation | default | local Btrfs, the canonical copy |
| devbox-vm | `$USER == agent` | independent clones; pull and install there separately; no sudo, egress allowlisted (denials are policy, not outages) |

Nothing propagates between hosts except Git (and `/projects/dev/.claude/scripts/sync-devbox.sh`
for shared agent assets). The TrueNAS NFS copy of `/projects/dev` is tombstoned: never
work there.

## Tools

- **direnv**: load the project's `.envrc` before `sprintctl`, `kctl`, `kubectl` or `flux`;
  non-interactively `direnv exec /projects/dev/<repo> <cmd>`.
- **snip** filters Bash output on the workstation. Need raw output? `snip proxy -- <cmd>`.
- **Cluster**: the appservice kubeconfig is `/projects/dev/appservice/clusters/.kube/config`
  (loaded by the appservice `.envrc`); a bare `kubectl` hits a local kind cluster. The Vuoro
  Cloud PoC is a different cluster: see `vuoro-cloud/CLAUDE.md`.

## Forge access, the sandbox, and credentials

- Network calls through agent tools (`gh`, `fj`, `curl`, `kubectl`, `git push/fetch/ls-remote`;
  not only `gh`, and not only Codex) are sandboxed and return **exit 0 with empty output**.
  Pass `dangerouslyDisableSandbox: true`. That sandbox escalation is autonomous and routine,
  never an operator handoff. A probe that could not run is
  *could not check*, not *none found*. (`forge-sandbox-guard.sh`, `forge-sandbox-detector.sh`.)
- **Standard workflow needs no permission**: commit, push, PR, merge, release, deploy. Land
  reviewed work directly on `main`, gated on CI; where a host requires a PR, open and merge it
  yourself. Exceptions exist only where a repo declares them in `.claude/gates.json`; absence
  means routine. Do not propose approval, signed-release or step-up gates as a safety control
  (operator decision, agentops#2413, 2026-09-16); vuoro-cloud alone may keep release gates.
- Forgejo is `https://git.apps.kotona.app` (web and API). `forgejo-ssh.apps.kotona.app:2222`
  is Git-over-SSH only. `forgejo.apps.kotona.app` does not exist. An unauthenticated private
  repo answers "The target couldn't be found": that is a 401. `fj` needs
  `-H git.apps.kotona.app` and `EDITOR`; `fj pr search` returns 410 Gone here; a fast-forward-only
  merge needs the REST API with `{"Do":"fast-forward-only"}`.
- `origin` is not reliably canonical; `git config claude.canonicalRemote` records it. A push
  to a replica is not landed work.
- `git fetch` before trusting local state: a stale `main` plus a `[gone]` ref looks like
  "never pushed". Resolve rebase conflicts by merging intent, not by picking a side.
- Credentials already exist; check before asking. `gh` keeps its token in the system keyring;
  `fj` has its own OAuth login; `git push` credential helpers are wired. The FORGE CONTEXT
  session-start block reports status. Check a token's audience before use: a `vuo_operator_` token is
  vuoro-cloud's, not Forgejo's.

## Working with the operator

- A plan or memo the operator submits is a directive: execute it and report. Do not ask for
  acceptance or signatures; ask only when options are genuinely open.
- Decide, don't queue: nothing waits on the operator unless the blocker is verified (you ran
  the check and it failed). Report the exact denied command; never improvise with personal or
  admin tokens.
- Homelab standing decisions (ephemeral pools, media backup policy) arrive in the session-start
  HOMELAB STANDING FACTS block. They are decisions, not findings.
- When an action needs the operator, give a runnable block: directory, exact command, the
  verified precondition, expected result, and what to send back.

## Durability

| Store | Durability |
|---|---|
| Git | durable, replicated |
| sprintctl (served) | durable work state |
| kctl | served for candidate intake/review; publication is Git-owned |
| auditctl | durable only where `AUDITCTL_ARTIFACTS_ROOT` is a repo (tracked `.envrc`); otherwise host-local |
| `/projects/dev/_artifacts/` | semi-ephemeral, host-local |
| `/tmp`, worktrees, scratchpads | ephemeral |

Say which: `session-local | host-persistent | cross-host-replicated | durable-authoritative`.
Never call `_artifacts/` content durable. Handoffs use the `/handoff` skill; continuation on
another host needs served state or a hash-verified copy. When authority to publish is missing,
record the finding and the rejection; never widen your own authority to finish.

## Retired and moving

- ActionQ's daemon is removed; `actionq-dispatcher` 0.2.0 is a fail-closed tombstone. Do not
  install, invoke or schedule it, and do not claim running systems are retired without rollout
  evidence.
- Normal sprintctl work uses the served `vuoro-shared` API through a validated Vuoro profile.
  Never export `SPRINTCTL_URL` or a PostgreSQL URI for normal work; `vuoro-dev` is for
  development-build tests only. Profile changes follow
  `agentops/docs/runbooks/vuoro-workstation-cutover.md`.
- Dispatch contracts (skills, schemas, `*.dispatch.json`, verification contexts): see
  `agentops/AGENTS.md`.
