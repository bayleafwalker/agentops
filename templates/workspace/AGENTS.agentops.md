## Agentops repository contracts

## Workstation workspace storage

On the workstation, `/projects/dev` is local Btrfs storage. TrueNAS NFS is
only a migration and emergency-recovery source, never a writable live Git
workspace. The initial local recovery policy retains seven daily and four
weekly read-only Btrfs snapshots. devbox-vm has an independent workspace tree;
do not assume ignored state, tool installations, cost logs, or Git worktrees
propagate between environments.

`/projects/dev/agentops` is the canonical source for shared dispatch skills,
manifest schemas, state-protocol context/result schemas, and the dependency-free
repository gate.

Always `git fetch origin` before trusting local repo state. Local `main` silently
falls behind origin between sessions/environments; a commit hash, plan doc, or
item referenced by a handover can look "not found" purely because it hasn't been
fetched yet. Fetch first, then fast-forward or rebase local `main` onto the
fetched remote before starting new work. If a rebase or merge produces conflicts,
resolve them directly (read both sides, merge the actual intent) rather than
aborting or force-picking one side; only stop and flag it to the user if a
conflict can't be resolved confidently.

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

Forgejo web and API: `https://git.apps.kotona.app` (192.168.20.219).
`forgejo-ssh.apps.kotona.app:2222` (192.168.20.218) is Git-over-SSH **only** — its
HTTP ports do not answer. There is **no** `forgejo.apps.kotona.app`; guessing it
returns `000`, which reads exactly like an outage. Private repos answer
unauthenticated API calls with "The target couldn't be found" — that is a 401
wearing a 404's clothes.

`fj` needs `-H git.apps.kotona.app` and an `EDITOR` set. `fj pr search` returns
`410 Gone` on this instance — that endpoint only, not the CLI. `fj pr merge -M`
has no fast-forward-only style, so a protected fast-forward-only branch needs the
REST API with `{"Do":"fast-forward-only"}`.

`origin` is **not** reliably canonical — the convention differs per repo. Each
repo records the truth in `git config claude.canonicalRemote`, and
`push-landed-check.sh` verifies against it. A push that succeeded to a replica is
not landed work.

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
  operator token (`vuo_operator_`); Forgejo rejects it as malformed.
- Encrypted repo secrets: `~/.config/sops/age/keys.txt`. Clusters:
  `/projects/dev/appservice/clusters/.kube/config` — a bare `kubectl` hits a local
  kind cluster.

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
validation; never select it as a repository's normal Sprintctl authority. Do not obtain,
export, or reuse `SPRINTCTL_URL` / a PostgreSQL URI for workstation or
devbox-vm normal operation. The only approved client selection is a validated
non-secret Vuoro profile plus its local credential-file reference; direct
database commands remain deployment or explicitly marked recovery work.

Before changing a repository profile, follow
`/projects/dev/agentops/docs/runbooks/vuoro-workstation-cutover.md`. Workstation
and devbox-vm have independent checkouts, profile state, credential files, and
tool installations, so a cutover must pass separately on each host. The final
eight-repository scanner and the profile validator in that runbook are required
before database bootstrap access can be revoked.
