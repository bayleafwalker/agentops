# Resolution pathway: silent sandbox failures, credential discovery, approval friction

**Date:** 2026-08-29 · **Status:** drafted, awaiting owner ratification of Wave 1

## The problem

Agent sessions fail to use `gh`/`fj` outside the tool sandbox, fail to find
credentials that are already minted, and lose track of git remotes. The owner
must therefore approve routine operations — "every single damn time I just want
main advanced." `cred-broker` was built to end this and has not.

The acceptance corpus is 15 failures observed in a single session on 2026-08-29,
in four classes: **A** silent sandbox failures read as facts, **B** credential
and host discovery, **C** remotes and landing, **D** approval friction.

## Why the existing rule failed

A rule forbidding the top failure was **already written** in
`/projects/dev/AGENTS.md` and was violated anyway. That single fact disqualifies
documentation as the primary mechanism. The causes, in order of weight:

1. **`/projects/dev/AGENTS.md` is not auto-loaded.** The only auto-loaded file
   there is a 3-line `CLAUDE.md` referencing it in prose, not as `@AGENTS.md`.
   There is not one `@` import in any CLAUDE.md in the workspace.
2. **The pointer mis-advertises.** It lists the file's contents as environment
   plumbing — no mention of GitHub, Forgejo, `gh`, `fj`, credentials or the
   sandbox — so agents doing forge work correctly conclude it is irrelevant.
3. **The rule names the wrong tool**: it is scoped to `gh` and the *Codex*
   sandbox; the failures are `fj`/`curl` under the *Claude Code* sandbox.
4. **It describes the wrong symptom**: it says the call "fails", but the real
   signature is **exit 0, empty output, no error**. An agent checks for an error,
   finds none, and the rule never fires.
5. **Vocabulary collision**: in every dispatch skill agents load, "escalate"
   means *stop and ask a human*; the rule uses "sandbox escalation" to mean
   *retry harder without asking*. Agents do what their loaded skills trained
   them to do — they ask the owner. **This is the approval cost.**
6. **The config rewards failure.** `fj` is allowlisted nowhere; the Forgejo host
   is not a trusted internal domain; `vuoro-cloud` had no settings file at all.
   Correct behaviour produces a prompt, incorrect behaviour produces none.
7. **No enforcement surface.** No hook inspects `gh`/`fj`/`curl` or their output.

Additionally: the workspace allowlist in `/projects/dev/.claude/settings.local.json`
**was never in scope** for the failing sessions, because project settings root at
the session cwd and the session ran in `vuoro-cloud`. Per-repo allowlisting is
therefore the wrong layer; it must land at user level.

## Vocabulary — three terms, used verbatim

| Term | Meaning | Who acts | Prompts owner? |
|---|---|---|---|
| **sandbox escalation** | Re-run outside the tool sandbox (`dangerouslyDisableSandbox: true`) | Agent, autonomously | **Never** |
| **operator handoff** | Stop; hand the work to a person | Human | Yes — that is the point |
| **gated operation** | An operation a *project* explicitly declares needs operator handoff | Declared per-repo | Yes, for that op only |

**The default is ungated.** Absence of a declaration means routine. Minting,
reviewing and deploying releases are standard workflow and must not prompt.
Advancing `main` is the paradigm routine case. A repo declares exceptions in
`.claude/gates.json`; the template ships with `"gated": []`. vuoro-cloud's five
owner-authorized actions are an opt-in exception that **must not generalise**.

## Layer 1 — relief today

- **`forge-sandbox-guard.sh`** (`PreToolUse`/Bash) — the keystone. Denies
  network-reaching forge commands about to run *inside* the sandbox, with a
  refusal message that names sandbox escalation and explicitly disclaims
  operator handoff. Converts the rule from something an agent may skip into a
  path that does not exist. Local git (status/log/diff/commit) untouched.
- **`gate-check.sh`** (`PreToolUse`/Bash) — reads `.claude/gates.json`; match →
  `ask` with the project's reason; no match → `allow`, suppressing the
  classifier prompts. Default allow, never ask.
- **`push-landed-check.sh`** (`PostToolUse`/Bash) — after any push, compares
  HEAD against the **canonical** remote and warns loudly on divergence. This is
  the check that would have caught the half-landed commit.
- **`forge-context.sh`** (`SessionStart`) — injects *probed* facts that cannot
  go stale: `fj auth list`, an audience-labelled credential inventory,
  `git remote -v` with canonical marked, the resolved Forgejo host plus
  liveness. Must print `PROBE FAILED` rather than omitting a line.
- **`~/.claude/settings.json`** — `env.EDITOR`; allowlist `Bash(fj:*)`,
  `Bash(gh:*)`, `Bash(git push:*)`, `Bash(git fetch:*)`; populate trusted
  internal domains; state in `autoMode.environment` that forge work is standard
  workflow. **User level, because the per-repo layer is what created the gap.**
- **`~/.claude/CLAUDE.md`** — currently **0 bytes**, auto-loaded in every
  session in every repo. Fill it. Highest-leverage documentation surface.
- **`git config claude.canonicalRemote`** per repo — turns ADR-003 from a
  document into machine-readable state. Discriminator: `.forgejo/workflows/`
  present ⇒ Forgejo canonical.
- **`scripts/ff-merge-pr.sh`** — REST `{"Do":"fast-forward-only"}`, routing
  around the `fj pr merge` gap rather than documenting it.

**Wave 1 exit criterion:** advance `main` in vuoro-cloud end-to-end — commit,
push canonical, PR, fast-forward merge, replica refresh — with **zero owner
prompts**. That is the owner's stated goal and the acceptance test.

## Layer 2 — cred-broker completion (the durable fix)

Not a bypass. Missing functionality indicates work to dispatch. The keystone is
confirmed at the source: `cli.py:21` has `--test-context` with `required=True`
and `cli.py:73-74` raises without it, and `git_helper.serve_get()` takes an
**in-process** broker object — so `credctl` structurally cannot call the
deployed broker at `192.168.20.223:8443`.

Build: `client.py` (remote mTLS client), drop `required=True` and add
`credctl get` / `git-credential`, rewire `git_helper.py`, client config,
install on PATH via gitops-nixos.

Commission (owner-authorized): reissue the workstation cert (expired 2026-08-12)
and session (expired 2026-08-11); enrol devbox; register repositories (only
`cred-broker` itself is registered today); GitHub App installations; per-repo
Forgejo integrations.

Unlocks: the git credential helper becomes broker-backed, so `git push` needs no
token file and no prompt; no long-lived tokens at rest; receipts give an
auditable evidence trail.

**Seam:** Layer 1's hooks, gates, vocabulary and allowlists are broker-agnostic.
The only coupling is credential lookup, isolated behind one indirection script
`forge-credential.sh` whose body swaps from reading `~/.config/forgejo/*` to
calling `credctl get`. Swapping layers is a one-file change.

## Proof table — mechanism class per failure

| # | Failure | Mechanism | Class |
|---|---|---|---|
| A1 | Sandboxed `gh` empty → "no open PRs" | guard denies the sandboxed call; empty result never produced | CAPABILITY |
| A2 | `[gone]` + stale main → "never pushed" | guard forces escalated fetch; push-landed check | CHECK |
| A3 | **The rule existed and was violated** | enforcement moves from prose to a deny the agent cannot skip; rule text delivered at the moment of violation | CAPABILITY |
| B1 | Guessed hostname → "unreachable" | SessionStart injects probed host + liveness; no guessing step remains | CAPABILITY |
| B2 | App token used as Forgejo credential | audience-labelled inventory (L1); token files retired (L2) | CHECK → CAPABILITY |
| B3 | Didn't know `fj` had OAuth | SessionStart runs `fj auth list` before the agent can fail to ask | CAPABILITY |
| B4 | `fj` "unable to locate editor" | `env.EDITOR`; failure cannot occur | CAPABILITY |
| B5 | 410 over-generalised to "CLI broken" | scoped fact in guard text + CLAUDE.md — **partial, honestly weakest** | DOCUMENTATION |
| B6 | Private-repo 404 reads as missing | injected fact + removal of the sandbox confound | DOCUMENTATION + CHECK |
| C1 | Push landed on replica, not canonical | `push-landed-check.sh` + `claude.canonicalRemote` | CHECK |
| C2 | No fast-forward-only in `fj` | `ff-merge-pr.sh` wrapper | CAPABILITY |
| D1 | Agent dispatch denied ×2 | autoMode declares forge work standard; gate-check allows | CAPABILITY |
| D2 | `git push` denied then permitted | user-level allowlist (root cause: repo had no settings file) | CAPABILITY |
| D3 | `fj pr merge` denied | `Bash(fj:*)` allowlisted + declared routine | CAPABILITY |
| D4 | Reading `fj` credential store denied — correctly | denial unchanged; obviated by injecting auth *status*, never secrets | CAPABILITY |

**11 CAPABILITY · 2 CHECK · 2 DOCUMENTATION-led.** Both documentation answers
are stated as such rather than dressed up, and both sit behind a capability that
removes the confound making them expensive.

## Falsifiers

- **Guard:** any transcript with a `gh`/`fj`/`curl`/`git push` call lacking
  `dangerouslyDisableSandbox` that was *not* denied. Expected count: zero.
- **Guard's wording:** a denial followed by an owner turn with no intervening
  escalated retry — means the refusal is still read as operator handoff.
- **Routine path:** any owner prompt for `git push`, `fj pr create/merge`, or a
  release deploy in a repo with no matching gate. Target: zero.
- **Gated path:** `terraform apply` or `promote-release.sh` in vuoro-cloud
  running *without* a prompt. Under-gating fails as hard as over-gating.
- **SessionStart injection:** any session issuing `fj auth list` or host
  discovery in its first 10 turns; any `PROBE FAILED` line.
- **Vocabulary:** `escalat` still appearing in any SKILL.md meaning "ask a human".
- **Whole plan:** the owner is interrupted for routine "advance main" even once
  after Wave 1 lands.

## Propagation

Unversioned guidance cannot propagate, so two structural defects come first.

1. **The false versioned source.** `/projects/dev/AGENTS.md:127` claims its
   source is `templates/workspace/AGENTS.agentops.md`. That template lacks every
   Forgejo/`fj`/credential fact and holds a `git fetch origin` rule the live file
   lost. No renderer exists. Make the claim true: port the content, add the forge
   block, add a render step.
2. **`/projects/dev` is not a git repo** — verified: `.git` contains only an
   empty `info/`. Stop treating its `AGENTS.md` as a source of truth; it becomes
   a rendered artifact of agentops, and durable content lives in
   `~/.claude/CLAUDE.md`, versioned via `gitops-nixos/modules/users`.

Targets: `~/.claude/settings.json` and `~/.claude/CLAUDE.md` (version both in
gitops-nixos — currently unmanaged home state); `AGENTS.agentops.md`; the six
`escalat*` sites in dispatch skills; `templates/dispatch/hooks/` (the existing
`/projects/dev/.claude/hooks/` is already a symlink farm into it, so propagation
is a symlink); `instruction_doctor.py` and `validate_project_workspace.py` gain
checks that keep propagation honest; the three bootstrap templates
(`sprintctl-bootstrap-template` has no `CLAUDE.md` or `.claude/` at all;
`datacluster-template` has neither `CLAUDE.md` nor `AGENTS.md`).

Per-repo `.claude/settings.json` exists in only 2 of ~60 repos. **Do not fix
per-repo** — that is what created the gap. Fix at user level; per-repo files
carry only `gates.json` deviations.

## On `@` imports

**Recommended against as a blanket change.** An `@` import is DOCUMENTATION: it
makes a rule present, not followed — and A3 is exactly the case where a present
rule was violated. Importing a rule that names the wrong CLI, the wrong sandbox
and the wrong symptom just costs tokens. `/projects/dev/AGENTS.md` is ~6k tokens
and there are 38 `AGENTS.md` files; workspace-level import taxes every session in
~60 repos to serve the minority doing forge work. Imports also recurse up to 5
levels with non-obvious precedence.

Instead: fill the 0-byte `~/.claude/CLAUDE.md` (same universal reach, no import
machinery); inline ~40 essential lines into each forge-touching repo's
`CLAUDE.md`, as vuoro-cloud already proves works; reserve `@` for one narrow
`FORGE-CONTRACT.md` where verbatim consistency matters. And fix the
mis-advertisement in `/projects/dev/CLAUDE.md` regardless — it is cheap and
removes a rational reason to skip the file.

## The admin token

**Do not mint a new one.** Two already exist at `0600`:
`~/.config/forgejo/admin-token` and `~/.config/forgejo/workstation-scope-token`.
Both authenticate as `bayleaf`, `is_admin=true`; the second is **byte-identical
to the token `fj` already uses**, so despite its name it is not a narrower
credential. A third would add a third undocumented secret to a set whose
defining problem is that it appears in no file anywhere.

Instead: document both today with explicit **audience** labels; adopt an
audience-labelling convention for every credential file so
`vuoro-cloud.token` is visibly marked *not a Forgejo credential* (that label
alone retires B2); establish actual scope by probing; prefer the
workstation-scope token for routine work and treat admin as break-glass; rotate
admin if it proves broader than needed; register both as cred-broker migration
targets so Layer 2 replaces them with short-lived scoped issuance. If a new
token is genuinely needed, mint it **through the broker**, not by hand into a
fourth unlabelled file.

## Assumptions requiring verification before building

1. **`PreToolUse` deny semantics.** `dangerouslyDisableSandbox` is confirmed
   present in Bash `tool_input`, so the hook can see the condition. Not
   confirmed: that this harness honours `permissionDecision: "deny"` on
   `PreToolUse` for Bash, nor whether `updatedInput` is supported. If
   `updatedInput` works, prefer it — the guard becomes silent and frictionless
   rather than a deny-retry loop.
2. **SessionStart hooks are unsandboxed.** The entire capability claim for
   `forge-context.sh` (B1, B3) rests on this. Strongly implied but not
   empirically confirmed. **Verify first** — if false, B1/B3 drop to
   DOCUMENTATION and the plan weakens at exactly the point it claims strength.
3. Token scopes for the two existing Forgejo tokens are unknown; establishing
   them is a planned step, not an assumption to carry.
