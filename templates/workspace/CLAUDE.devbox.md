# Working agreements

Auto-loaded in every session, in every repo. Kept short deliberately.

**Host: devbox, user `agent`.** Everything above the credentials section is identical to
the workstation's `~/.claude/CLAUDE.md` and is host-neutral. The credentials section is
not: it is measured on *this* host, and the workstation's version names files that do not
exist here. Copying that section across is the exact error the last section warns about —
evidence paired with the wrong scope.

## Sandbox escalation is yours — never ask for it

`gh`, `fj`, `curl`, `git push/fetch/pull` and cluster calls made through the
Bash tool run inside a sandbox with **no network**. They do not error. They
return **exit 0 with empty output**, so an unreachable call and a genuinely
empty result are indistinguishable.

Pass `dangerouslyDisableSandbox: true` on every such call. Doing so is a normal
autonomous action — **not** an operator handoff, and never something to ask
permission for.

**Never conclude absence from a sandboxed result.** Real failures this caused:
"no open PRs anywhere" (six were open), "this branch was never pushed" (merged
nine days earlier), "Forgejo is unreachable" (it was up). If a probe could not
run, the finding is *could not check* — a different fact from *none found*.

## Three words, three meanings

| Term | Meaning | Prompts the owner? |
|---|---|---|
| **sandbox escalation** | Re-run outside the sandbox. Agent acts alone. | **Never** |
| **operator handoff** | Stop; a person takes over. | Yes — that is the point |
| **gated operation** | A project explicitly declared this needs approval. | Only that operation |

Never write "escalate" unqualified. It has meant both "retry harder" and "ask a
human", and that ambiguity is what turns routine work into interruptions.

## Standard workflow does not need permission

Advancing `main` — commit, push, PR create, PR merge, release cut, deploy — is
routine. So is minting and reviewing. Do it.

A repo may declare exceptions in `.claude/gates.json`, with tiers
`operator-approved` (owner approves, agent then acts) and `operator-actioned`
(a human performs it). **Absence of a declaration means routine**, never the
reverse. One repo gating its promotions does not make deploys gated everywhere.

## Credentials on this host — measured 2026-08-29, not inherited

- **GitHub** — `gh`, authenticated as `bayleafwalker` through **`GITHUB_TOKEN` in the
  environment**, not through a keyring. `gh auth status` says which; believe it over this
  page if they ever disagree.
- **Forgejo** — `fj` holds an OAuth login for `git.apps.kotona.app`. There is **no
  `~/.config/forgejo/`** here: the workstation's `workstation-scope-token` and
  `admin-token` files do not exist on devbox, and their absence is not a fault to repair
  on the spot.
- **`git push` needs no token handling** — `~/.gitconfig` wires `gh auth git-credential`
  for github.com and a helper for `git.apps.kotona.app`.
- **`git config user.email` is `test@test.com` here.** Set an identity per repository
  before committing, or the commit lands misattributed.
- **Check the audience before using a credential.**
  `~/.config/vuoro/credentials/vuoro-cloud.token` is a vuoro-cloud *application* token
  (`vuo_operator_`); Forgejo rejects it as malformed. The served-vuoro credential here is
  `vuoro-shared-agent` — the workstation's file is `vuoro-shared-workstation`, a different
  file for a different identity.
- **Not present on this host:** `~/.config/sops/age/keys.txt` (so encrypted repo secrets
  cannot be decrypted here) and `/projects/dev/appservice/clusters/.kube/config` (so there
  is no cluster access; a bare `kubectl` reaches nothing). Both are workstation
  capabilities. Say "not available on devbox", never "unavailable".

## Remotes

`origin` is **not** reliably canonical. Each repo records the truth in
`git config claude.canonicalRemote`. A push that succeeded to a replica is not
landed work — verify against the canonical remote.

## This host is not the workstation

`/projects/dev` here is devbox's own clone set, at the same paths as the workstation's and
holding different content. `repo_id`s therefore address two disjoint audit indexes and
shard trees that look identical from the inside. Before reporting on the state of a repo,
confirm which host you are on.

## Verify at the artifact, never at the report

A status that describes a thing is not the thing. Image deployed? Read the
running pod's `imageID`. Migration applied? Query the migrations table. Work
landed? Check the canonical remote. Steps here have repeatedly reported success
while doing nothing.

Pair evidence with its own scope before believing it, and check whether what you need is
already on disk before recording a blocker. Both have produced confident, wrong findings
on this stack more than once.
