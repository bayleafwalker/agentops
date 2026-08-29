# Dev Environment — Agent Reference

This file applies to all projects under `/projects/dev/`. Read it at the start of any session before touching project files, sprint state, or cluster resources.

---

## Shared workspace

All projects live at `/projects/dev/`. The path is canonical in every environment, but **it no longer resolves to the same underlying storage everywhere** (agent hardening migration, 2026-07-17 — see `gitops-nixos/docs/runbooks/devbox-vm-zvol-migration.md`):

| Environment | How `/projects/dev/` is provided | Same files as workstation? |
|-------------|----------------------------------|---------------------------|
| Workstation | **local Btrfs** under `/projects` | yes (the canonical workstation copy) |
| devbox-vm (`agent@devbox`, 192.168.20.108) | **local zvol clones** on `agentpool/projects` | **no — independent clones** |
| Legacy devbox (vscode-shell pod, pending decommission) | TrueNAS PVC at `/workspace`, subPath `dev` | **no — separate legacy NFS copy** |

The workstation must not use TrueNAS NFS as a writable Git workspace. NFS is
only the migration source and emergency recovery location; the workstation's
local Btrfs snapshots (7 daily, 4 weekly) are the initial recovery policy.

Consequence: pulling a repo or reinstalling a tool on the workstation (or pod) does **nothing** for devbox-vm. Its clones and `uv tool` installs must be updated separately (`ssh devbox-agent`, then pull + reinstall from `/projects/dev/<repo>` there). Untracked files (`.claude/settings.local.json`, `.envrc` state, gitignored configs) do not propagate to devbox-vm at all. Workstation, legacy-pod, and devbox-vm trees are independent unless a deliberate migration or Git operation synchronizes them.

---

## Detecting the active environment

| Signal | devbox-vm | Legacy devbox (pod) | Workstation |
|--------|-----------|---------------------|-------------|
| `$USER` | `agent` | `dev` | other |
| `$HOME` | `/home/agent` | `/home/dev` | `/home/<user>` |
| `$WORKSPACE_ROOT` | unset | `/workspace/dev` | unset |
| `hostname` | `devbox` | pod name (`vscode-shell-...`) | machine hostname |

Check with: `[[ "$USER" == "agent" ]]` (devbox-vm), `[[ -n "$WORKSPACE_ROOT" ]]` or `[[ "$USER" == "dev" ]]` (legacy pod).

devbox-vm is a hardened agent host: no sudo, no Talos/TrueNAS reach, egress allowlisted at the host (nftables `agent-egress`) and perimeter (OPNsense). Queue access is via LoadBalancer IPs (`actionq-pg` 192.168.20.216, `sprintctl-pg` 192.168.20.220); DB URIs live in `~/.config/actionq-env`. Expect network denials for anything off-allowlist — that is policy, not an outage.

---

## Tool install rules — devbox-vm

devbox-vm is a plain NixOS VM: everything under `/home/agent` and `/projects/dev` persists across reboots (ZFS `agentpool`). Install Python tools with `uv tool install 'name[extras] @ /projects/dev/<repo>/'` as the `agent` user — installs land in `~/.local/bin`, which is in PATH. System packages come from the NixOS config in `gitops-nixos/hosts/devbox/` (no sudo on the host; config changes deploy via the infra path).

sprintctl needs the `remote` extra there (`sprintctl[remote]`) — without psycopg it cannot reach the Postgres backend and fails with "psycopg is not installed".

## Tool install rules — legacy devbox pod

The devbox container image is fixed. Only paths on the PVC survive a pod restart. `/home/dev` is mounted from the PVC so home-directory paths persist; system paths do not.

| Method | Destination | Survives restart |
|--------|-------------|-----------------|
| `sudo apt-get install` | container layer | **No** |
| `sudo npm install -g` | `/usr/lib/node_modules` | **No** |
| `uv tool install` | `~/.local/` | **Yes** — on PVC |
| `pip install -e .` into venv in `/projects/dev/` | PVC | **Yes** |
| Binary placed in `~/.local/bin` or `/projects/dev/` | PVC | **Yes** |

**Rule**: prefer `uv tool install <pkg>` or user-local paths for anything that needs to outlast the current pod. If you apt-install something for a task, note it will be gone after a restart and it may need to be added to the Dockerfile for permanence.

Tools pre-installed in the devbox image (always available regardless of PVC state): `kubectl`, `talosctl`, `flux`, `helm`, `sops`, `gh`, `age`, `node`, `npm`, `uv`, `python3`, `jq`, `fzf`, `ripgrep`, `tmux`, `vim`, `direnv`, `git`, `claude` (Claude Code), `codex`, `opencode`.

---

## PATH in legacy devbox pod

`/home/dev/.local/bin` is in PATH in all sessions (set as a deployment env var). Tools installed with `uv tool install` are available immediately without sourcing anything.

When invoking commands through `kubectl exec`, remember that the pod may default
to `root` even though the interactive devbox user is `dev`. If switching users,
preserve the deployment-provided model-provider environment instead of rebuilding
a small environment by hand. An `Invalid API key` result from
Claude/Codex/OpenCode after switching users usually means those injected variables
were dropped, not that `vscode-shell` itself is misconfigured.

---

## direnv

`.envrc` files at project roots load automatically on `cd` when direnv is active. The first time entering a project, run `direnv allow` — this state persists on the PVC.

Always load `.envrc` before running `sprintctl`, `kctl`, `kubectl`, or `flux`. In non-interactive shells use `direnv exec /projects/dev/<project> <command>`.

Key vars set per project:

| Project | Vars |
|---------|------|
| `appservice/` | `KUBECONFIG`, `TALOSCONFIG`, `CLUSTER_NAME` |
| `homelab-analytics/` | `SPRINTCTL_DB`, `KCTL_DB` |
| `sprintctl/` | `SPRINTCTL_DB` |
| `kctl/` | `KCTL_DB` |

---

## Forge access, the sandbox, and credentials

**Every network call made through an agent tool is sandboxed unless escalated.**
This applies to `gh`, `fj`, `curl`, `wget`, `hcloud`, `kubectl` and
`git push/fetch/pull/clone/ls-remote`, under any harness — not only `gh`, and not
only Codex. The failure signature is the thing to internalise: such calls do
**not** error. They return **exit 0 with empty output**, so an unreachable call
and a genuinely empty result are indistinguishable from the output alone.

Escalate the sandbox on every such call (in Claude Code, the Bash parameter
`dangerouslyDisableSandbox: true`). **Never conclude absence from a sandboxed
result.** If a probe could not run, the finding is *could not check*, which is a
different fact from *none found* and is usually a blocker rather than a result.

Enforcement does not rely on anyone remembering this: `forge-sandbox-detector.sh`
(PostToolUse) fires after any un-escalated network command, and
`forge-sandbox-guard.sh` (PreToolUse) refuses it where the harness supports a
deny. Both live in `templates/dispatch/hooks/`.

### Three words, three meanings

| Term | Meaning | Who acts | Prompts the owner? |
|---|---|---|---|
| **sandbox escalation** | Re-run outside the sandbox context | Agent, autonomously | **Never** |
| **operator handoff** | Stop; a person takes over | Human | Yes — that is the point |
| **gated operation** | A project explicitly declared this needs approval | Per-repo declaration | Only that operation |

Never write "escalate" unqualified. It has meant both "retry harder without
asking" and "ask a human", and agents trained on the second reading interrupt the
owner when they hit an apparent network wall. That ambiguity is a defect, not a
wording preference.

**Standard workflow does not need permission.** Advancing `main` — commit, push,
PR create, PR merge, release cut, deploy — is routine, as are minting and
reviewing. A repo declares exceptions in `.claude/gates.json` with tiers
`operator-approved` (owner approves, agent then performs) and `operator-actioned`
(a human performs it; approval alone is insufficient — reserved for destructive
mutation of live shared infrastructure). **Absence of a declaration means
routine**, never the reverse. One repo gating its promotions does not make deploys
gated anywhere else.

### Forges

Forgejo web and API: `https://git.apps.kotona.app` (192.168.20.219, Forgejo
16.0.3) — reachable from the workstation outside the sandbox.
`forgejo-ssh.apps.kotona.app:2222` (192.168.20.218) is Git-over-SSH **only** — its
HTTP ports do not answer. There is **no** `forgejo.apps.kotona.app`; that name does
not resolve, and guessing it returns `000`, which reads exactly like an outage.
Private repos answer unauthenticated API calls with "The target couldn't be found"
— that is a 401 wearing a 404's clothes.

`fj` holds its own OAuth login (`fj auth list` → `git.apps.kotona.app`; check with
`fj -H git.apps.kotona.app whoami`). It needs `-H git.apps.kotona.app` and an
`EDITOR` set for any command that opens one. `fj pr search` returns `410 Gone` on
this instance — that endpoint only, not the CLI. `fj pr merge -M` has no
fast-forward-only style, so a protected fast-forward-only branch needs the REST
API with `{"Do":"fast-forward-only"}`.

`origin` is **not** reliably canonical — the convention differs per repo. Each
repo records the truth in `git config claude.canonicalRemote`, and
`push-landed-check.sh` verifies against it. A push that succeeded to a replica is
not landed work.

Always `git fetch origin` before trusting local repo state. Local `main` silently
falls behind origin between sessions and environments; a commit hash, plan doc, or
item named in a handover can look "not found" purely because it has not been
fetched. Fetch first, then fast-forward or rebase local `main` onto the fetched
remote before starting new work. Note the compounding failure: a stale local
`main` plus a `[gone]` tracking ref reads exactly like "this branch was never
pushed" — that misreading sent a session chasing branches that had been merged
nine days earlier. If a rebase or merge produces conflicts, resolve them directly
(read both sides, merge the actual intent) rather than aborting or force-picking
one side; only stop and flag it if a conflict cannot be resolved confidently.

### Credentials already exist — check before asking for more

- **GitHub**: `gh`. The token is in the **system keyring**, *not* in
  `~/.config/gh/hosts.yml`. Finding no token in that file is not evidence of
  being unauthenticated.
- **Forgejo**: `fj` holds its own OAuth (`fj auth list`); also
  `~/.config/forgejo/workstation-scope-token` (routine) and `admin-token`
  (break-glass).
- **`git push` needs no token handling** — `~/.gitconfig` already wires credential
  helpers for both forges.
- **Check a credential's audience before using it.**
  `~/.config/vuoro/credentials/vuoro-cloud.token` is a vuoro-cloud *application*
  operator token (`vuo_operator_`); Forgejo rejects it as malformed. Do not reach
  for it against Forgejo.
- Encrypted repo secrets: `~/.config/sops/age/keys.txt`. Clusters:
  `/projects/dev/appservice/clusters/.kube/config` — a bare `kubectl` hits a local
  kind cluster.

## Agentops repository contracts

`/projects/dev/agentops` is the canonical source for shared dispatch skills,
manifest schemas, state-protocol context/result schemas, and the dependency-free
repository gate.

Use the narrowest reusable command prefix appropriate to the requested operation.

- Repositories opt in with one root `*.dispatch.json` and repository-specific overlays under `.agents/overlays/`.
- Reusable verification intent belongs in data-only `verification/contexts/*.json`; executable tests and production logic remain in the owning repository.
- Inspect declared `risk_surfaces` before changing queue, claim, lease, retry, recovery, projection, publication, reconciliation, or backend-parity paths.
- Run `python /projects/dev/agentops/templates/dispatch/scripts/validate_verification_artifacts.py --root .` from an opted-in repository.
- `full` is a sequence, not blanket repair authority. Repair and production mutation remain separately authorized.

## ActionQ retirement boundary

ActionQ 0.1.26 removed `actionq-daemon`, its harness/worktree/session execution
plane, and the standalone `actionq-server` source. `actionq-dispatcher` 0.2.0 is
an inactive, fail-closed tombstone: do not install, invoke, or schedule it for
new work. An existing host may upgrade to the tombstone once so a stale
`dispatcher-once` shim fails clearly, then remove it after operator-owned
callers and services are retired.

Repository retirement and running-system retirement are different facts. Do
not claim the appservice server or devbox unit is gone without operator rollout
evidence. The gated order remains appservice phase 1 and health proof, then
phase 2 and health proof, then interactive disablement of the devbox unit and
the separately reviewed NixOS retirement. Do not revive the removed daemon by
bumping its pinned revision.

## Vuoro served-work cutover

Normal shared Sprintctl work is moving to the durable `vuoro-shared` served API.
`vuoro-dev` is ephemeral and is reserved for development-build tests and UX
validation; never select it as a repository's normal Sprintctl authority. Do not
obtain, export, or reuse `SPRINTCTL_URL` / a PostgreSQL URI for workstation or
devbox-vm normal operation. The only approved client selection is a validated
non-secret Vuoro profile plus its local credential-file reference; direct
database commands remain deployment or explicitly marked recovery work.

Before changing a repository profile, follow
`/projects/dev/agentops/docs/runbooks/vuoro-workstation-cutover.md`. Workstation
and devbox-vm have independent checkouts, profile state, credential files, and
tool installations, so a cutover must pass separately on each host. The final
eight-repository scanner and the profile validator in that runbook are required
before database bootstrap access can be revoked.

---

## Cluster access (kubectl, flux, talosctl)

Credentials are not baked into the devbox image. The appservice kubeconfig is at:

```
/projects/dev/appservice/clusters/.kube/config   (gitignored — must exist on PVC)
```

If this file is missing from the PVC, kubectl and flux will fail silently or target the wrong cluster. Copy it to the PVC once from your workstation if it is not already there.

Load cluster context before any kubectl/flux operation:
```bash
cd /projects/dev/appservice && direnv allow
# or in non-interactive context:
direnv exec /projects/dev/appservice kubectl get nodes
```

From the devbox, `https://192.168.87.20:6443` (the appservice API server) is reachable over the cluster network — the pod runs inside the same cluster.

**Do not run kubectl against any cluster without first confirming `$KUBECONFIG` points to the intended config.** The default `~/.kube/config` may be absent or stale in the devbox.

### Vuoro Cloud PoC (a different cluster, different path)

The Hetzner PoC node is **not** reachable with the appservice kubeconfig and is
not on the cluster network. It needs the operator WireGuard tunnel, which on
this workstation is a NetworkManager profile rather than
`/etc/wireguard/wg0.conf` — `wg-quick up wg0` fails and `sudo` is not required:

```sh
nmcli connection up vuoro-cloud-operator      # tunnel; expect 10.44.0.2/24
export KUBECONFIG=/home/bayleaf/.config/vuoro/kube/poc.yaml
kubectl get node vuoro-cloud-poc
nmcli connection down vuoro-cloud-operator    # tear down afterwards
```

Full contract in `vuoro-cloud/docs/runbooks/operator-access.md`; agent-facing
summary in `vuoro-cloud/CLAUDE.md`.

---

## OpenCode config

The global OpenCode config is mounted into the devbox as a read-only ConfigMap at `~/.config/opencode/opencode.json`. To change it, edit `clusters/main/kubernetes/apps/vscode-shell/app/opencode-config.yaml` in the appservice repo and reconcile.

Project-level `opencode.json` at any repo root overrides the global model selection for sessions in that repo. `homelab-analytics` defaults to Haiku for its well-scoped Python sprint work. All other projects default to Sonnet.

**Model ID format**: verify with `/model` inside OpenCode on first launch — the provider prefix format (`anthropic/model-id`) may differ between OpenCode versions. opencode-ai 1.x was a major version bump from 0.x; the config schema URL (`https://opencode.ai/config.json`) is authoritative.

## Session workflow telemetry

`Stop` and `PostToolUse` hooks record every session's cost **and** its workflow shape. The Stop
hook appends one record per session to:

```
/projects/dev/.claude/session-costs.jsonl
```

Each record carries the original cost fields (`model`, `in`, `cache_write`, `cache_read`, `out`,
`cost_usd`) plus `turns`, `assistant_msgs`, `tool_calls` and `duration_s`, all derived from the
transcript. The same session is published to auditctl as a `workflow.session` event with its
gate outcomes and `rework_rounds`, which is what the release scorecard reads (T-6).

**Rows supersede; they do not accumulate.** `Stop` fires once per assistant turn, not once per
session, and every record is a cumulative snapshot of the session so far. Any consumer must
reduce to the newest row per `session` before aggregating — summing every row over-counts
roughly quadratically (measured 2026-08-23: $56,485 summed against $3,825 actual across 97
sessions; `cost-summary.sh` was reporting the former until it was fixed). The same rule applies
to `workflow.session` events: newest per `metadata.session` wins.

The `PostToolUse` hook (`gate-log.sh`) logs one row per gate command — pytest,
`run_round_checks`, `hybrid_dispatch … gate`, `cargo test`, `unittest discover` — to a
per-session file the Stop hook drains and deletes. The Bash tool result carries no exit code,
so each row records which signal decided its verdict (`signal`: `exit_code`, `is_error`,
`interrupted` or `heuristic`); a consumer that needs certainty reads `signal`, not just `ok`.

Both hooks are wired per-repo in `.claude/settings.local.json` (untracked) and are registered
(2026-08-23) in `/projects/dev` itself, `actionq`, `agentops`, `appservice`,
`homelab-analytics`, `kctl` and `sprintctl`. The hook scripts are **versioned in
`agentops/templates/dispatch/hooks/`** and symlinked into `/projects/dev/.claude/hooks/`;
edit them there, not through the symlink. `/friction` records a workflow friction note into the
same auditctl sink.

The workstation writes to its local Btrfs copy. **devbox-vm** and the legacy pod
write to independent copies; entries are not merged unless synced manually.

To view a summary:
```bash
/projects/dev/.claude/hooks/cost-summary.sh
/projects/dev/.claude/hooks/cost-summary.sh homelab   # filter by project name
```

---

## Devbox asset sync

Use the workstation-only sync script to propagate shared agent assets to the
isolated devbox-vm clone:

```bash
/projects/dev/.claude/scripts/sync-devbox.sh --dry-run
/projects/dev/.claude/scripts/sync-devbox.sh --apply
```

It copies the root guidance, shared Claude hooks/scripts, and canonical
agentops template trees. It merges only the recognized shared hook
registrations in local settings, imports only deduplicated cost records with
stable session IDs, creates remote backups, and refuses to overwrite a
divergent dirty canonical template tree.

It does not sync Git state, repository source, `.envrc` state, ignored
configuration or secrets, worktrees, or tool installations; it never deletes
remote files. Run the dry run first and use `--apply` only after reviewing its
plan.

---

## Evidence, scratch, and durability

Durability and cross-host availability are separate properties. The shared
`/projects/dev/...` path convention gives sessions a common *view*, not a
common *filesystem* — workstation, devbox-vm, and the legacy pod are
independent trees (see Shared workspace above). A path is not a distributed
system merely because it starts with `/projects`.

| Storage/channel | Purpose | Durability | Cross-host expectation |
|---|---|---:|---:|
| Git | maintained source, specs, runbooks, project guidance | Durable | Replicated through Git |
| kctl | curated knowledge, decisions, reusable findings | Durable **only where rendered and committed** | **Not served** — local sqlite per repo |
| auditctl | immutable operational observations, receipts, evidence events | Durable **where the artifacts root is a repository**, otherwise host-persistent | **Not served today** — schemas deployed, no client writes to them |
| sprintctl | work state, dependencies, claims, refs to evidence | Durable workflow state | Served |
| `<repo>/_artifacts/` (rooted at a repository) | audit shards, metanarrative model records | Durable, replicated by Git | Replicated through Git |
| `/projects/dev/_artifacts/` (workspace root) | evidence bundles, exports, receipts, handoff transport | Semi-ephemeral | Host-local unless explicitly copied |
| `/tmp`, worktrees, scratchpads | active session scratch | Ephemeral | Never assumed available elsewhere |

**Two of these rows were false until 2026-08-29 and are corrected above; the
correction is the useful part, so it is recorded rather than quietly edited.**

- **kctl is not served.** Its own README says so — *"Local-first: SQLite on disk,
  convergence through committed markdown"*, *"Not a hosted service or remote
  knowledge store"*. Measured: five per-repo `.kctl/kctl.db` files, nothing served.
  Its real durability path is `kctl render` into a committed
  `docs/knowledge/knowledge-base.md`, which two repos already do.
- **auditctl was not durable anywhere.** Every `add` wrote a host-local sqlite index
  plus an NDJSON shard under `/projects/dev/_artifacts/`, which is in no git
  repository — so the "Durable, authoritative" row and the "Semi-ephemeral,
  host-local" row described *the same bytes*, and the second was the true one. The
  served substrate **is** deployed and migrated (`audit` schema on the vuoro
  database, principals provisioned, daily off-site backup, restore drill rehearsed)
  but holds zero rows, because no client writes to it: auditctl's CLI is
  `add/list/rebuild/render` with no submit path. The gap is a client, not a
  deployment.

A repository fixes its own row by rooting evidence at itself —
`export AUDITCTL_ARTIFACTS_ROOT="$PWD"` in a **tracked** `.envrc` — after which its
shards are replicated by the same push that carries the code. `agentops` and `vuoro`
did this on 2026-08-29. Committing shards trades immutability for durability, so
`agentops templates/dispatch/scripts/check_append_only_shards.py` refuses any commit
that rewrites, truncates or deletes an existing shard line.

Rationale and the options not taken:
`agentops/docs/plans/agentops/operative-position-durability-2026-08-29.md`.

`_artifacts/` content can be copied to every host without becoming
authoritative; a kctl or auditctl record is durable even when no exported
file has been copied anywhere. Use this vocabulary explicitly in session and
dispatch output — never describe `_artifacts/` content as "durable" or
generically "host-shared":

```
session-local | host-persistent | cross-host-replicated | durable-authoritative
```

Prefer, in dispatch/session-closure output:

```
Semi-ephemeral evidence retained on host devbox-agent:
  /projects/dev/_artifacts/...

Durable references:
  sprintctl: ...
  auditctl: ...
  kctl: pending / ...
```

over the vaguer (and misleading) `Durable evidence written to _artifacts/...`.

**Handoff contract.** A handoff package is a transport/inspection aid, not
the source of truth. Any handoff where continuation might happen on another
host must record: `source_host`, absolute `source_path`, `classification`
(per the vocabulary above), `created_at`, basis (sprint item + sprintctl
event IDs + repo commits), `durable_refs` (kctl/auditctl IDs), a file
inventory with SHA-256 hashes, known `replicas` (host + path + verified
bool), and a retention rule. A handoff is cross-host-ready only when either
(1) everything needed to continue is reachable through served durable
systems, or (2) the package has been explicitly copied to the destination
host with hashes verified. `rsync` success is evidence of transfer, not
evidence of identity.

**Session closure.** At closure: push raw findings to auditctl; publish
reusable conclusions to kctl when authorized; update sprintctl work-state and
durable refs; leave large receipts under host-local `_artifacts/`; record
host+path for anything retained locally; replicate only when a known
subsequent session needs file-level access elsewhere. A local README or
handoff bundle existing is not itself durable closure.

**Missing authority stays visible.** When kctl publish isn't reachable this
session, record the raw finding and the authority rejection via auditctl, add
a sprintctl ref marking publication pending, and keep the extraction input as
a hashed host-local package — never claim the kctl pipeline completed, and
never grant yourself broader authority just to finish conveniently. Audit
capture can complete independently of kctl publication, which stays a
separate pending action for an authorized actor.

---

## Workflow — workstation

- Full IDE integration (VS Code, JetBrains)
- kubectl over LAN to `192.168.87.20:6443`
- All native tools available
- Claude Code subscription auth via `claude auth login`
- Codex via `codex login`

## Workflow — devbox-vm

- SSH access: `ssh devbox-agent` (agent user) or `ssh devbox-vm` (dev user) from the workstation — use `tmux` for persistence
- Own local repo clones (see Shared workspace above) — pull/install per-host
- Claude auth via `CLAUDE_CODE_OAUTH_TOKEN` in `~/.config/claude-token.env`; codex via ChatGPT OAuth
- No cluster tools, no Talos/TrueNAS reach — queue and sprint DBs only, via the LB IPs

## Workflow — legacy devbox pod (pending decommission)

- SSH access: `ssh dev@<shell-ip>` — use `tmux` for persistence across disconnects
- All cluster tools in-pod: kubectl/flux operations are lower-latency than over LAN
- Claude Code, Codex, OpenCode all available in the terminal session
- No GUI — terminal-only
- API keys injected as env vars from the `vscode-shell-llm-api-keys` secret (Anthropic, Mistral, OpenAI)

## Switching environments mid-work

Sessions are not automatically transferred between workstation and devbox. Before switching:

1. Use `sprintctl handoff` to produce a handoff document
2. Commit or stash in-progress changes
3. Resume in the new environment with `sprint-resume`

Sprint state and cost logs are not automatically shared across environments;
handoff and deliberate synchronization are required.

---

## Fresh legacy-pod bootstrap (new PVC or first login)

Run once after a new PVC is provisioned or if the home directory is reset:

```bash
# 1. Allow direnv for each project you'll use
for proj in appservice homelab-analytics sprintctl kctl; do
  direnv allow /projects/dev/$proj
done

# 2. Copy cluster credentials to the PVC (from workstation or secrets store)
cp ~/.kube/appservice-config /projects/dev/appservice/clusters/.kube/config
cp ~/.talos/appservice-config /projects/dev/appservice/clusters/.talos/config

# 3. Install Claude Code natively (PVC-persistent, auto-updates without sudo)
# claude is pre-installed in the image via npm — run this to install the self-updating native binary to ~/.local/bin
claude install

# 4. Install project-scoped Python tools (installed from local source, not PyPI)
uv tool install /projects/dev/sprintctl/ --python python3
uv tool install /projects/dev/kctl/ --python python3

# 5. Bootstrap Python venvs for projects that need them
bootstrap-python-envs /projects/dev

# 6. Verify sprint tooling
SPRINTCTL_DB=/projects/dev/homelab-analytics/.sprintctl/sprintctl.db sprintctl sprint list

# 7. Verify cluster access
direnv exec /projects/dev/appservice kubectl get nodes
```

After step 4, all uv-installed tools are at `~/.local/bin` which is in PATH. The claude native install (step 3) also lands there and auto-updates without sudo.

## Common paths

| Path | Contents |
|------|---------|
| `/projects/dev/` | All project repositories |
| `/projects/dev/_artifacts/` | Semi-ephemeral, host-local evidence/scratch cache — see Evidence, scratch, and durability above |
| `/projects/dev/.claude/hooks/` | Shared Claude Code hooks |
| `/projects/dev/.claude/session-costs.jsonl` | Unified session cost log (all envs) |
| `/projects/dev/appservice/clusters/.kube/config` | Appservice kubeconfig (gitignored) |
| `/projects/dev/appservice/clusters/.talos/config` | Talos config (gitignored) |
