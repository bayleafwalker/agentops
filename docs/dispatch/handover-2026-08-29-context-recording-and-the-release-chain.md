# Handover — the release chain twice over, and context that records itself

**Date:** 2026-08-29 · **Continues:** `handover-2026-08-29-audit-resolution-and-context-contract.md`,
whose "Next steps, in order" items 2, 3 and 4 are done and whose item 1 is half done.

## Landing status

| Repo | HEAD | State |
|---|---|---|
| auditctl | `5f45f12` | clean, pushed |
| agentops | `a342850` | clean, pushed |
| vuoro | `5e51ce9` | clean, pushed |
| appservice | `93fe0bb1` | clean, pushed |
| gitops-nixos | `f7405e1` | untouched — but see *Open items 8* |
| sprintctl / homelab-analytics / scribectl | `95e18f5` / `eb56331` / `07ae91b` | clean, untouched |

Nothing is parked in a PR. The `agentops devbox/worktree-snapshot-2026-07-21` branch from the
previous handover is still unread and still needs a reader.

## Releases

| Artifact | Version | State |
|---|---|---|
| auditctl | 0.1.5 | released, wheel `313c73a9…` — superseded the same day |
| auditctl | **0.1.6** | released, wheel `285c59be…`, **installed on workstation and devbox** |
| vuoro-service | 0.1.58 | released, image `sha256:6823c5dd…` — superseded the same day |
| vuoro-service | **0.1.59** | released, image `sha256:9d3f1797…`, **live on vuoro-shared** |

Production ran auditctl **0.1.3** at the start of this session and runs **0.1.6** now.
Verified at the artifact each time, not at the report: the running pod's `imageID`, a live
handshake reporting `service_version 0.1.59`, and a real event in the live agentops store
carrying its own resolved context.

## What got done

**The release chain, twice.** 0.1.5 carried the `--allow-index-only` continuity fix and
0.1.4's resolved audit context, which had been released but never repinned — so the first
repin advanced production two versions. 0.1.6 carried `resolved_context` (below). Both went
release → composition repin → vuoro-service → cluster roll → live handshake. The catalog
revision does not move in either, which is what confirms the change is adapter-internal.

**The bash resolver is retired** (item 3). `auditctl_export_root` is gone, along with the
root-setting in `dispatch_release.py`, `hybrid_dispatch.py` and `metanarrative.py`. No
caller decides the artifacts root any more; the publisher does.

The precondition for this was "0.1.4 deployed everywhere", which the contract stated and
nobody had checked. **devbox was still on auditctl 0.1.2.** Retiring the export first would
have silently stopped publishing there. Upgraded, then retired.

Guards are rewritten against the class rather than deleted: **REQ-025** (no hook or driver
assigns `AUDITCTL_ARTIFACTS_ROOT`, whatever value it derived) and **REQ-026** (publish from
two repositories with nothing set; each event must land under its own). REQ-026 is what
catches a host downgraded below 0.1.4 instead of letting it misroute a day of shards. The
superseded M-6a REQ-006..009 and the M-6b oracle each say in place where the property went.

`artifacts-root.default` survives, narrowed to `metanarrative.py`'s *model record* store —
a workspace-scoped artifact with no repository of its own. That was never auditctl's
question, and one file answering both is how they were conflated.

**Two fixture bugs, both hiding the guards on the host that needed them.** The resolver
oracle assumed `/bin/true` and `PATH=/usr/bin:/bin`. On NixOS neither holds, so on devbox it
aborted before a single assertion. The PATH repair that looks obvious — drop directories
holding an `auditctl` — is wrong here: on this workstation the *kernel* audit tool is
`/usr/bin/auditctl`, so that filter removes jq and coreutils and REQ-023 passes because the
hook cannot run at all. It shadows the PATH instead: symlinks to every reachable executable,
minus that one name.

**devbox has working agreements** (item 4). It had none for the `agent` identity. Not a
copy — the workstation's credentials section names `~/.config/forgejo/`, a sops age key and
the appservice kubeconfig, **none of which exist there**, and GitHub authenticates through
`GITHUB_TOKEN` rather than a keyring. Every claim probed on devbox; absences stated as
absences. Tracked at `templates/workspace/CLAUDE.devbox.md`. Also recorded: devbox's
`git user.email` is `test@test.com`, so a commit without a per-repo identity is misattributed.

**Item 1, measured then half built.**

Two measurements, both in `docs/evidence/measurements/`:

- *The coherent redirect.* The contract asserted that `AUDITCTL_DB` alone routes both halves
  consistently. Measured across six writes varying only the environment, it does — and the
  boundary is sharper than the finding said. 0.1.4 took the power to redirect away from
  `AUDITCTL_ARTIFACTS_ROOT` (a contradicting root is now refused, with a good message);
  `AUDITCTL_DB` keeps it in full, because four fields derive from that one input. Both stores
  validate clean afterwards, because both are.

  **What the finding did not have:** a coherent redirect is worse than an undetected one.
  August's misrouting was repairable *because* it was incoherent — the mismatch was itself
  the evidence of where each event belonged. A coherent one leaves nothing: across 1593
  events in 11 stores, no record carried a working directory, a repository, or a host. A
  receipt written afterwards cannot reconstruct what the write never recorded. That is an
  ordering constraint on the applier, not a nice-to-have.

- *Session is produced 354 times and had nowhere typed to go.* `runtime_session_id` was
  populated **zero** times; `metadata.session` was populated 1258 times one line away, in a
  dict that validates nothing. 1258 is the wrong number: 904 are the `sess-a`/`sess-poison`
  fixture family, 898 of them in the two agentops stores, consistent with the suites writing
  into the live index until `b55df7e`. The honest figure is 354. That same untyped key holds
  two different identifier shapes, because nothing can refuse either.

Built on top:

- **auditctl 0.1.6 attaches `resolved_context`** to every event — `repo_id`, `repo_root`,
  `artifacts_root`, `published_from`, `resolution_source`. A redirected write now says so in
  its own record. Three deliberate constraints: it is a **record, not a check** (writing into
  another store on purpose is legitimate; auditctl records conformance, it does not state
  desired state); it is the **resolver's, not the publisher's** (no flag sets it, unknown
  keys are refused); and it is **not an envelope field**, because `ENVELOPE_FIELDS` is
  validated all-or-nothing and adding to it would invalidate every event ever written.
- **The session identity reaches its field.** The Stop hook falls back to the harness session
  id — the same equality actionq's contract asserts when it requires `session_id` and
  `runtime_session_id` to match. `unknown` is excluded: a placeholder in a typed field is the
  untyped field's disease. REQ-012 guards all three directions.
- **The SessionStart hook emits parseable JSON.** See *the part worth reading first*.

## Open items

1. **Item 1's open half — the channel.** The record answers *where a write came from*. It
   does not answer *who set the context and what entitled them to*, which is the question the
   applier needs: not "do these values agree" — the accepted rows already agree — but who is
   entitled to assert. Everything else here is downstream of that.
2. **`SPRINTCTL_DB` is sprintctl's `AUDITCTL_DB`.** `backend.py:332-348` genuinely
   cross-checks repo identity against the committed marker; `db.py:316-319` reads the store
   path from the environment with no cross-check at either call site.
3. **The binary half of "where am I" is open.** Four resolvers, three policies:
   `auditctl-resolve.sh` and `hybrid_dispatch.py` carry the ELF guard and honour
   `AUDITCTL_BIN`; `metanarrative.py:84` has neither; `dispatch_release.py:1071` accepts a
   bare name on `shutil.which()` alone. Both of the latter swallow failure, so a shared-scope
   `AUDITCTL_BIN=/bin/true` silences telemetry without a trace. The shape to copy is
   `AGENTOPS_ROOT`: script-relative default, passed explicitly to children, and `env.pop`'d
   before spawning a worker so it cannot inherit the coordinator's checkout.
4. **`.auditctl-id` has zero instances.** The mechanism that would stop identity being a
   directory basename is implemented and used nowhere; every `repo_id` in the fleet is a
   basename.
5. **Duplicate model-record trees, owner decision.** Eight files with the same names under
   both `/projects/dev/_artifacts/agentops/model` and `agentops/_artifacts/agentops/model`
   (and two more for `vuoro`). Reads no longer create directories and the scope now matches
   the root, so this is residue, not an active leak — but which root model records belong
   under is a decision, not a cleanup.
6. **The metanarrative status is gated behind an unrelated condition.** It is emitted only
   when the sprint summary is non-empty, because `[[ -n "$summary" ]] || exit 0` precedes it.
   The comment says the model "is only worth having if it shows up in ordinary work", which
   argues the gating is accidental — but the oracle requires a healthy sprint to produce no
   output at all, so widening when this hook speaks is a call about session context.
7. **`vuoro-client` fails 2 tests on unmodified HEAD.** `test_resource_transport.py` reads
   owner-supplied golden captures under `packages/vuoro-client/verification/` which are not in
   the repository and do not exist on this workstation. The 0.1.57 repin commit claims
   "vuoro-client → 38 passed", so they existed somewhere then; that claim is not reproducible
   here.
8. **`gitops-nixos` has an untracked `.auditctl/`.** Every sibling repo gitignores it; that
   one does not, so its local index reads as a dirty tree forever. One line, not taken here
   because it was outside what was asked.
9. **`vuoro-dev` is stalled in flux**, at an older revision with
   `Deployment/vuoro-dev/vuoro-dev status: 'Failed'`. Pre-existing, unrelated to these rolls,
   not investigated.
10. **nix-daemon recovered on its own** during the session and `nix shell` works again. But
    the store was garbage-collected mid-session: the realized postgresql path this repo's
    runbook recommended as the daemon-down fallback **vanished between two runs an hour
    apart**. The runbook's claim that a realized path "stays usable once used" is falsified
    and now corrected in place, with the instruction to check the skip count either way — a
    vanished fallback and a working one print the same green summary.
11. **The devbox working agreements are a second document sharing a body with the
    workstation's, and will drift.** One body plus a per-host credentials fragment is the fix.

## Next steps, in order

1. **Answer the entitlement question** (open item 1). Everything in items 2–4 is the same
   defect wearing different variable names, and each one fixed individually will be
   rediscovered as a class later.
2. **Close the binary half** (item 3) — it is bounded, it has a worked example to copy in
   `AGENTOPS_ROOT`, and unlike the others it fails *silently*, which is the worst property in
   this stack.
3. **Write `.auditctl-id` files** (item 4), or delete the mechanism. A built-and-unused
   identity path is a claim in the code that the fleet contradicts.
4. **Decide the model-record root** (item 5), then clean the duplicate trees.

## The part worth reading first

`test-sprintctl-maintain-check.sh` failed at the start of this session, and I wrote it off as
"pre-existing, unrelated" **twice** before reading its output. It was reporting a live defect
the whole time: the metanarrative block printed its status lines *after* the
`hookSpecificOutput` object, and a SessionStart hook's stdout is read as JSON — so appending
prose did not add a note beside the sprint context, it discarded the context along with the
note. The error said `jq: parse error ... line 2, column 7`, which is precisely what that
means. The same eight lines also paired a scope from `basename "$PWD"` with a root from a
data file, and `mkdir`'d on reads so that asking about a scope created it. The empty
`agentops/_artifacts/vuoro/model` directory was the fingerprint, sitting there since 15:25.

**A failing test dismissed as pre-existing is an unread finding.** "Pre-existing" describes
when it started, not whether it matters, and the two get conflated because the first is cheap
to establish and the second is not. Both times I confirmed it failed identically on unmodified
HEAD — a correct measurement, of the wrong question.

Two smaller ones from the same session, in the same family:

- The session-identity count was first reported as **1258**. Correct, and useless: it answers
  "how often is the key present" when the question was "how often is a session recorded". The
  fixtures were separated only because this stack has already paid for not separating them —
  and they were the *same fixture family* two earlier passes misread as production residue.
- I "fixed" a `[[ … ]] && …` as a `set -e` hazard, then checked and found the hook runs under
  `set -u` alone. Kept the clearer form; corrected the claim rather than the code.

The rule the previous handover wrote — *pair evidence with its own scope before believing it*
— held up. What this session adds is that a **dismissal** needs the same treatment as a
finding. "Pre-existing", "unrelated", "fixture problem" are all conclusions, and each one was
reached here without opening the thing it described.
