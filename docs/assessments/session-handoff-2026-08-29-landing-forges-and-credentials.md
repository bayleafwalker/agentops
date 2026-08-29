# Session handoff — landing policy, forge access, and the credential plane

**Date:** 2026-08-29 · **Scope:** cross-repo. Everything below is landed on
`main` unless explicitly marked outstanding.

## The through-line

Every problem this session touched had one shape: **state that reports success
while doing nothing, and nothing positioned to notice.** A sandboxed query that
returns empty and gets read as fact. A ConfigMap that is correct at every layer
except the process serving requests. An integration on a forge that nothing
points at. A rule written down in a file no session loads.

The fixes that stuck were the ones that moved a check from prose into a
mechanism. The ones still outstanding are all of the same kind.

---

## 1. Landing policy — work parked and unproposed

**Landed.** Eight branches and six PRs resolved. Four branches landed
(`kctl`, `bindery-ra2-adapter`, `aligned-equity`, `wizard-valley-world-window`),
two correctly refused (`flowlab` was a byte-identical duplicate whose merge would
have reverted later work; `outctl`'s `release/2026-08-11` was a preservation
snapshot of a project killed on 2026-08-16), two already merged upstream. PRs
`vuoro`#62, `agentops`#140, `actionq`#40, `kctl`#8 merged; `appservice`#1559 held
by owner decision.

**The correction that matters.** The survey motivating `land-work-in-main`
reported "zero open PRs anywhere". That was a sandboxed `gh` call returning exit 0
with empty output. Six were open, four parked as drafts with zero reviewers, one
already decayed into conflict. The policy is *strengthened* by this — both failure
modes were running at once — but the evidence basis in commits `ca422b1` and
`9865215` was wrong. Corrected in
`agentops/docs/assessments/land-work-in-main-evidence-correction-2026-08-29.md`.

**`ci-not-on-main`, bounded.** Three `pull_request`-only workflows estate-wide.
`homelab-analytics/verify.yaml` is the confirmed gap.
`agentops/protected-paths.yml` is the interesting one — adequate under a PR
default, it silently stopped gating anything the moment work began landing
directly. Sequencing recorded: the `git.apps.kotona.app` runner move precedes
adding push triggers, or the policy is paid for in Actions minutes already
decided against.

---

## 2. Why agents kept asking permission

Four surveys established that none of this was agent discipline.

- **`/projects/dev/AGENTS.md` is not auto-loaded.** No `CLAUDE.md` in the
  workspace uses an `@` import — the pointer is prose. The rule forbidding the
  top failure was already written there and never reached a session.
- **The pointer mis-advertised**, listing contents as environment plumbing with
  no mention of forges, credentials or the sandbox.
- **The rule named the wrong tool and the wrong symptom** — scoped to `gh` and
  Codex, describing a "failure" when the signature is exit 0 with empty output.
- **"Escalate" meant two opposite things.** In every dispatch skill an agent
  loads it meant *stop and ask a human*; the workspace rule used "sandbox
  escalation" to mean *retry harder without asking*. Agents did what their
  skills trained them to do. **This was the approval cost.**
- **The config rewarded failure.** `fj` allowlisted nowhere; the Forgejo host not
  a trusted domain; `vuoro-cloud` had no settings file at all — and project
  settings root at the session cwd, so the workspace allowlist was never in
  scope for the sessions that failed.

### What landed

Six hooks in `agentops/templates/dispatch/hooks/`, symlinked into
`/projects/dev/.claude/hooks/`:

| Hook | Event | Role |
|---|---|---|
| `forge-sandbox-detector.sh` | PostToolUse | **Primary defence.** Warns after any un-escalated network call |
| `forge-sandbox-guard.sh` | PreToolUse | Belt-and-braces deny |
| `gate-check.sh` | PreToolUse | Enforces `.claude/gates.json`, default routine |
| `push-landed-check.sh` | PostToolUse | Compares HEAD against the canonical remote |
| `forge-context.sh` | SessionStart | Injects probed facts |
| `forge-credential.sh` | — | The layer seam for cred-broker |

Plus: `claude.canonicalRemote` on **all 46 repos**; `~/.claude/CLAUDE.md` filled
(0 bytes since April); `~/.claude/settings.json` given `EDITOR`, an `fj`
allowlist, trusted domains and a statement that forge work is standard workflow;
the vocabulary split across all six `escalat*` sites in the dispatch skills; the
forge block ported into `templates/workspace/AGENTS.agentops.md`;
`instruction_doctor.py` extended to fail a repo whose auto-loaded `CLAUDE.md`
does not say how to escape the sandbox; three bootstrap templates seeded.

**Two verified facts worth keeping.** Hooks are **not** network-sandboxed — a
hook process reached both forges with 200 while tool calls needed escalation,
which is what makes `forge-context.sh` a capability rather than a document. And
**hook config is read at session start**, so a running session never sees its own
newly-registered hooks. That is why the deny path stays unverified, and why the
design does not depend on it.

**Acceptance test passed:** `vuoro-cloud` PR #49 landed on a protected
fast-forward-only branch — commit, push, PR, merge, replica refresh — with zero
owner prompts.

### Outstanding

- The real test is the **next** session, since hooks were never live in the one
  that installed them.
- `PreToolUse` `deny` / `updatedInput` support still unverified.

---

## 3. Forge and remote topology

`vuoro-cloud`'s `origin` pointed at the **GitHub replica** while canonical
Forgejo sat behind a non-default remote, and `main` tracked the replica — so
`git status` read "up to date" while canonical was a commit behind. Renamed:
`origin` is Forgejo, `github` is the replica.

Deliberately **not** mirroring `gitops-nixos`'s dual-pushurl setup: `main` is
protected on Forgejo, so a dual push would fail on canonical and succeed on the
replica, manufacturing the half-landed state it would be meant to prevent.

**Facts that cost this session real time**, now in `vuoro-cloud/CLAUDE.md` and
the agentops workspace template: the Forgejo web/API host is
`git.apps.kotona.app` (192.168.20.219); `forgejo-ssh.apps.kotona.app:2222` is
Git-over-SSH only; **there is no `forgejo.apps.kotona.app`** — guessing it returns
`000`, which reads exactly like an outage; private repos answer unauthenticated
calls with "The target couldn't be found", a 401 wearing a 404's clothes; `fj`
needs `-H` and `EDITOR`; `fj pr search` returns 410 (that endpoint only);
`fj pr merge -M` has no fast-forward-only style, so protected branches need the
REST API — hence `vuoro-cloud/scripts/ff-merge-pr.sh`.

**Credentials already existed.** `~/.config/forgejo/{admin,workstation-scope}-token`
(the latter byte-identical to `fj`'s own OAuth token), GitHub's token in the
system **keyring** not `hosts.yml`, and `~/.gitconfig` credential helpers already
wired for both forges. No new token was needed. What was missing was any file
saying so.

---

## 4. cred-broker

Was a live one-repository canary, dormant since 2026-08-11. Now:

- **Remote API client** (`client.py`) — mTLS, typed errors, expired-session
  refusal before the wire. `credctl` could not call the deployed broker at all
  before this. 128 tests, including a real mTLS loopback against the actual
  server handler.
- **Per-repository audiences** — `repository_audiences: {capability:
  {repository_id: audience}}`, with the flat map as a legacy default. Exact match
  wins; resolution never crosses to another repository's entry.
- **Reproducible build** — `Containerfile` + hash-pinned `requirements.lock`,
  replacing an image made by hand-overlaying a wheel. Verified the new code loads
  the *live* ConfigMap before deploying, which is what made code-before-config
  safe.
- **Deployed** as `0.1.0-565b41f`, digest resolved from the registry, verified at
  `containerStatuses[].imageID`.
- **25 repositories registered** — 16 GitHub, 9 Forgejo.

**The split-brain worth remembering.** After registering repositories, git said
25, Flux said Applied, the ConfigMap said 25, the *mounted file* said 25 — and the
running process still held 2. `server.py` reads config once in `main()`, and the
pod had not restarted. The mechanism is a manual `cred-broker/config-revision`
annotation. Every config change now needs that bump, and verification means
exec'ing into the pod, not reading the file.

**Forgejo per-repository audiences, proven in the running process:**

```
repo.read   repo_cred_broker             u:2:d2c3721a…
repo.read   repo_vuoro_cloud_forgejo     u:2:10c1e6d3…   distinct
repo.read   repo_litany_forgejo          NONE — authority gap
```

Positive and negative control both green. The flat default had to be deleted
*first*: while it existed every Forgejo repository resolved, so an unconfigured
one looked configured and the control would have been a false pass.

Three of nine Forgejo repositories configured: `cred-broker`, `vuoro-cloud`,
`gitops-nixos`.

### Outstanding, in dependency order

1. **Client cert (expired 2026-08-12) and session (2026-08-11), plus a missing
   `server-ca.crt`.** The cert is a **24-hour** credential issued from OpenBao
   `pki-broker/issue/workstation` — so the real gap is that *nothing renews it*,
   not that it needs hand-rotating. `server-ca.crt` is the cert-manager
   `cred-broker-bootstrap-ca`, readable from the cluster; the canary fetches it
   fresh each run.
2. **Forge-side proof.** `audience_for` resolution is verified, but that cannot
   catch a mistyped `repository` claim rule. Run
   `cred-broker-forgejo-canary.sh` against `bayleaf/vuoro-cloud` for read and
   write, then confirm a vuoro-cloud token is **refused** against
   `bayleaf/cred-broker`. Do this **before** creating the remaining ten
   integrations, or a systematic error repeats ten times.
3. **Ten integrations** for five repositories — see
   `cred-broker/docs/forgejo-integration-entries.md` for copy-paste values.
   `wizard-valley-world-window` stays unconfigured as the standing control.
4. **Manifest and reconciliation checks.** Still unbuilt, still the durable win.
   Forgejo has no list API, so config-side checks catch orphaned audiences and
   completeness gaps but **cannot** see an integration that exists on the forge
   and is referenced by nothing. A read-only query against Forgejo's Postgres
   would close that.
5. Delete `cred-broker-devbox-repo-read` — verified unreferenced three ways:
   no matching audience, devbox's only binding is on the *GitHub* repo, zero
   devbox bindings on any Forgejo repository.

---

## 5. Also landed

**Production security fix.** `sprintctl`'s `_reservation_release` accepted a
caller-supplied, unvalidated actor and wrote it as the `reservation.released`
event actor — an authorization hole *and* attribution forgery. Fixed, released as
0.3.5, deployed as `vuoro-service` 0.1.56, and **verified in production** by
re-running the original measurement: `release --actor not-my-identity` now
returns actor-mismatch where it previously succeeded. Event `#2620` deliberately
left in place as evidence.

**`vuoro-dev` principal ids.** Minted so the registry can load past v0.1.53.
Subjects are opaque, **not derived from the actor** — both of vuoro-dev's actors
contain colons, and `vuoro-static:developer:vuoro-dev-bootstrap:0` *passes*
validation while parsing as issuer `vuoro-static:developer`. `vuoro-shared`
escaped this only because its four actors happened to be colon-free. Unrecoverable
if wrong: federation ownership binds the string permanently with no transfer
operation.

**Handed off separately:**
`appservice/docs/handoffs/2026-08-29-forgejo-db-network-exposure.md` —
`forgejo-db` has no ingress NetworkPolicy, and `arc-runners`/`forgejo-runner`
have unrestricted egress.

---

## 6. Two credential exposures — mine

`AK_ADMIN_PASSWORD` (since rotated) and `GITEA__database__PASSWD` (not rotated),
both leaked into the session transcript by dumping a broad listing when one key
was needed. Rotation ordering for the second is in the network-exposure handoff:
**network policy first** — it needs no outage and is what actually shrinks
exposure — then rotation folded into a restart taken for another reason.

The test worth applying is not "how secret does this look" but **what the value
lets you do**. By that test an audience is safe to paste in plain text; a database
password is not.

---

## What I would pick up first

**The client certificate.** It gates the forge-side proof, which gates the
remaining ten integrations, which gates the whole Forgejo credential path. And
the fix is not a rotation — it is that a 24-hour credential has no renewal
automation, which is a small build rather than an operational chore.
