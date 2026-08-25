# v5.9 — the refactor pass, built from the accumulated `debt:` lines (C-3)

Pathway: vuoro `docs/plans/2026-08-23-requirements-pathway-v5-v7.md` §4 — "**v5.9 refactor/
architecture pass (C-3, from the accumulated `debt:` lines)**". Implementation plan
`docs/plans/2026-08-23-v5-implementation-plan.md` §"Phase D": "Every packet above carries a
`debt:` line when it defers a refactor. Under C-3 that is the whole mechanism — the last phase
gets a list, not a guess."

Sprint item `agentops#2254`. Route `mechanical_bulk` (`self_candidate: true` since L-3; D-8 now
stands at 11 consecutive first-attempt greens). Coordinator workspace `/tmp/v5-coordinator` on
`devbox-agent`. Freeze shape, oracle discipline and the L-2a/L-2b validation are unchanged from
the v5 metanarrative brief, §§2–4; read that first if resuming cold.

## 1. The list, re-derived rather than inherited

The point of C-3 is that the last phase gets a list. A list is only worth having if it is true,
so every carried line was re-checked against the code on 2026-08-25 before this brief was
written. **Four of the nine were already closed and still recorded as open.**

| Carried line | Source | State on 2026-08-25 |
|---|---|---|
| The PR body must be bounded; "the receipt is the body" cannot hold against 65536 chars | M-series | **Already closed.** `build_pr_body` (`dispatch_release.py:243`) renders a fixed set of fields and carries no transcript |
| The driver must commit the worker's changes before pushing | M-series | **Already closed** in M-9: `_commit_worktree` (`dispatch_release.py:471`) |
| `dispatch_release._path_allowed` is weaker than `hybrid_dispatch._matches_any` | M-series | **Already closed** in M-11: the two are now the same function, with an agreement oracle in `test_dispatch_release_pathmatch.py` |
| `AUDITCTL_ARTIFACTS_ROOT` defaulted in two places | P-series | **Already closed** 2026-08-23 (`71ed5b7`): stated once in `templates/dispatch/artifacts-root.default` |
| **The manifest schema is not machine-enforced; `validate_hybrid_dispatch` holds the invariants by hand** | M-series | **Open — and it has drifted.** §2 |
| **`worker_totals` does not `list()` its argument, so `attempts` raises on a generator** | T-series | **Open.** §2 |
| `mechanical_bulk` is both a hybrid route and an action class | L-3 | **Open, owner's call.** §4 — not dispatched |
| devbox's `/projects/dev/agentops` is 159 commits behind main with local modifications | T-series | **Open, hand step.** §4 — not a packet |
| Identity registry startup-only; profile `required_authorities` lists dead `work:claim`; sprintctl behind main; `next-work` adapter | P-series | **Not agentops.** Other repos and the operator; carried forward unchanged |

Marking four lines closed is not bookkeeping. A debt list that names already-fixed things is one
a reader stops trusting, which is the same failure as a CI gate red on every legitimate PR (§3f
of the v5 brief) and a detector that fires on good news (§3i). The list is the mechanism; if it
rots, C-3 has nothing to run on.

## 2. What is actually open, and what was found while checking

### The manifest schema drifted, and its checker is weaker than it claims

`templates/dispatch/manifest.schema.json` (326 lines) is read by nothing that runs. Checked by
hand against every manifest in the repo on 2026-08-25:

- **`agentops.dispatch.json` — the repo's own manifest, read by every dispatch — violates it**,
  twice. `skills.selected` carries `dispatch-wave` and `session-handover`; the schema's enum
  admits neither.
- `templates/dispatch/repository-baseline/example.dispatch.json` violates it once, the same way.
- The enum is missing three skills that exist on disk: `dispatch-wave`, `friction` and
  `session-handover`. `friction` is the skill T-5 shipped.

This is #97 again, one file over: an unchecked document drifting from the thing it documents.

**And the checker that found it is weaker than the schema it checks.** #97 wrote a hand-rolled
JSON Schema subset checker inside `templates/dispatch/tests/test_task_packet_schema.py`. Its
docstring says it covers "only the constructs this schema actually uses" and that "anything else
in the schema is ignored rather than silently passed off as checked". Enumerating the keywords
the two schemas actually use:

```
manifest.schema.json:  $ref allOf if/then oneOf not propertyNames minItems minProperties
                       maximum format  — plus the eleven the checker implements
task-packet.schema.json: $ref allOf if/then minItems maximum — plus the same eleven
```

Every keyword on those first lines is silently ignored today. The packet schema **already** used
five of them when #97 shipped, so the sentence in that docstring was true about intent and false
about outcome from the day it was written. A constraint the checker ignores is a constraint that
does not exist, and nothing says so at runtime.

That is this tract's §3h instance: correct code that reads as stronger than it is. The fix is
not "implement more keywords" — it is **make an unimplemented keyword an error**, so the checker
can never again be quietly weaker than its schema.

### `worker_totals` raises on a generator

`release_scorecard.py`'s `worker_totals` never calls `list()` on its argument, so
`attempts = len(receipts)` raises `TypeError` on any iterable that is not a sequence. The spec
says "a list", so it is latent rather than broken — but every other function in that module
accepts what it is given.

## 3. Rows to freeze and run, in order

Rows 1 and 2 split `schema_check.py` on a seam its oracle already has, following the T-6 and
M-10 precedent: the second row cannot start until the first has merged, because they write the
same file.

| # | Row | Writable | What the oracle must assert |
|---|---|---|---|
| **V59-1** | `templates/dispatch/scripts/schema_check.py`: the subset checker, extracted from #97's test into a module a script can import. Same eleven keywords, same violation strings, same bool-is-not-an-integer rule — **plus** an unimplemented keyword in the schema is a raised error, not silence | `templates/dispatch/scripts/schema_check.py` | the eleven keywords each accept and each reject; a schema carrying a keyword the checker does not implement raises rather than passing; the checker discriminates (a permissive checker fails the suite) |
| **V59-2** | The composition keywords `schema_check` must implement for the two real schemas to be checkable at all: `$ref` (internal `#/...` only), `allOf`, `if`/`then`, `oneOf`, `not`, `propertyNames`, `minItems`, `minProperties`, `maximum`. `format` is annotation-only and is declared as accepted-and-not-checked, by name, not by silence | same | each new keyword accepts and rejects; `$ref` resolves internally and refuses an external one; both real schema files are now checkable end-to-end with no unimplemented-keyword error |
| **V59-3** | `templates/dispatch/scripts/validate_dispatch_manifest.py`: validate one or more `*.dispatch.json` against `manifest.schema.json` using `schema_check`, **and** cross-check `skills.selected` against the skills that exist under `skills.template_root` — the directory is the source of truth, the enum is a copy | `templates/dispatch/scripts/validate_dispatch_manifest.py` | a valid manifest passes; each drift in §2 is reported with its path; a selected skill absent from the directory is reported; exit codes distinguish clean from violations |
| **V59-4** | `worker_totals` accepts any iterable of receipts | `templates/dispatch/scripts/release_scorecard.py` | a generator of receipts totals identically to the same receipts as a list; the empty generator answers as the empty list does, `cost_reported` included |

Coordinator hand-passes, after the rows land (protected paths, declared under rule 14):

- `manifest.schema.json`: add the three real skills to the enum, restoring its truth.
- `test_task_packet_schema.py`: import the shared checker instead of carrying its own copy, so
  there is one implementation and #97's discrimination tests keep guarding it.
- Register the new command ids in `agentops.dispatch.json`.
- Reconcile the stale debt lists in the M-series scorecard and the Track L rows in
  `docs/plans/agentops/2026-08-23-handoff-loop-and-telemetry.md`, which still show L-1, L-2 and
  L-4 open although the M-series closed all three.

## 4. Not dispatched, and why

- **`mechanical_bulk` is both a hybrid route and an action class.** Renaming either touches
  `agentops.dispatch.json` and `manifest.schema.json` and changes what every existing packet's
  `route` field means. That is a boundary decision, not a refactor; §7 of the v5 brief says stop
  and report. Recorded here, left for the owner.
- **The stale devbox checkout.** A hand step on another machine, not a packet: nothing in a
  worktree can fix it. The dispatch path does not read it — the coordinator runs from
  `/tmp/v5-coordinator` — but the hook symlinks point into it, so it is worth doing by hand.
- **The four non-agentops lines** (identity registry restart lever, `work:claim` in
  `required_authorities`, sprintctl behind main, `next-work` through the served adapter). They
  belong to vuoro-cloud, sprintctl and the operator. Carried, not adopted.

## 5. Outcome

**Three rows dispatched, three worker greens on the first attempt, $0.066 billed.** Main went
870 → 1039 tests. Merged: #100, #101, #102, plus this closing hand-pass.

| Row | PR | Billed | Tokens | Oracle |
|---|---|---|---|---|
| V59-4 `worker_totals` accepts any iterable | #100 | $0.006692 | 122,868 | 13 tests |
| V59-1 `schema_check.py`, extracted and made honest | #101 | $0.020443 | 282,378 | 63 tests |
| V59-2 composition keywords; both schemas checkable | #102 | $0.038918 | 460,899 | 92 tests |

`docs/evidence/scorecards/v5-9-refactor.generated.json` was produced by `release_scorecard.py`
over this window. **Read its frontier block as "not measured", not as zero.** The Stop hook writes
a cost row per turn, and this tract ran inside a single very long coordinator turn, so at the time
the scorecard was generated the sink held no row for the session that was generating it. The
worker side is real metered spend and is complete. That gap is a seventh instance of the §3h
pattern, this time in the measuring instrument: `sessions: 0, turns: 0, usage_equivalent_usd: 0.0`
is arithmetically correct and reads to any human as "the coordinator cost nothing". The scorecard
has `cost_reported` and `total_reliable` for the worker side and nothing equivalent for the
frontier side. That is a `debt:` line, recorded in the M-series scorecard.

### The debt line is closed, and the fourth row was not built

`manifest.schema.json` is now enforced by code that runs: `schema_check.validate` reaches it end
to end, and the oracle suite checks every manifest in the repo against it on every run. **The
drift was real and it was in the file every dispatch reads** -- `agentops.dispatch.json` selected
`dispatch-wave` and `session-handover`, and the schema's enum admitted neither, because that enum
duplicates a directory listing and had fallen three skills behind. `friction`, the skill T-5
shipped, was one of them. The enum now agrees with the directory and a test holds them together,
so the next person who adds a skill and forgets the schema is told immediately.

The planned fourth row was a `validate_dispatch_manifest.py` CLI. **It is not built, and that is
a decision rather than an omission.** The debt line said the manifest schema was not
machine-enforced. It now is. A CLI would have been built because the plan named it, not because
anything needed it -- and this project's standing rule puts the burden of proof on the addition.

What a CLI *would* buy, stated so the next session can weigh it honestly: the eleven
`*.dispatch.json` manifests in **other** repos (actionq, appservice, auditctl, kctl, sprintctl and
the rest) are not checked by anything, because the agentops suite cannot see them. That is a real
gap and a genuine new capability. It is not this debt line, and it should be argued for on its
own evidence.

### What re-deriving the list was worth

Four of nine carried lines were already closed. Two more of the remaining five were resolved by
rows 1, 2 and 4. **One was not a code defect at all**: `mechanical_bulk` as both route and action
class is a boundary decision, and it is still the owner's (§4). Five new lines were found *while
doing the work*, four of them by oracle authors rather than by anything that runs -- they are in
the M-series scorecard's `debt_for_v5_9`.

### The pattern held, again

The v5 brief's §3h recorded three defects that were arithmetically correct and said the wrong
thing, and §3i added a fourth. This tract found the fifth and sixth, and neither was findable by
a gate:

- **The checker's docstring overstated it.** `test_task_packet_schema.py`'s checker said
  unimplemented keywords were "ignored rather than silently passed off as checked". It ignored
  them *silently*, and the packet schema already used five such keywords the day that sentence was
  written. Every constraint it could not read was reported as satisfied.
- **Auditing keyword names was not enough.** The first fix raised on unknown keyword *names*.
  `manifest.schema.json` uses `additionalProperties` in its subschema form -- a recognised name in
  an unenforceable form -- which passed the name audit and was then ignored: the same silence, one
  level down, in three separate nodes, one only reachable through a `oneOf`. An oracle author
  found it while writing tests, before the row was frozen.

Both are the same shape as the earlier four. A gate asks whether the code does what the packet
said. Neither of these was a question about the code; they were questions about whether the
packet was asking for the right thing, and the answer came from a person reading, every time.

### Coordinator errors this tract, recorded

- **I scoped row 2 wrongly.** "The composition keywords" would have left the manifest still
  raising on three nodes, so the manifest validator that followed could never have run. I would
  have shipped a row whose stated payoff was half false and found out one row later. Folded the
  subschema form in before freezing; the oracle author judged the folded row the more coherent one.
- **That flip broke seven tests in the previous row's oracle**, three deliberately unconditional.
  Nothing was deleted to make a packet pass: a probe now asks the module which world it is in, both
  answers stay pinned, and a new test fails on the one answer that is never acceptable -- silence.
  Declared in the freeze commit.
- **I lost three packets.** Commit 2 of a freeze carries the packet and its reference patch, and
  the worker's PR is cut from commit 1, so deleting the freeze branch after merging drops them.
  T-11, V59-1 and V59-4 went that way and were recovered from unreferenced objects and restored
  here. The process needs to pick one of the two fixes deliberately; it is a `debt:` line now.
- **One undeclared read, caught by L-2b before any spend.** Row 2's oracle validates every
  committed packet and reads `agentops.dispatch.json`; neither was in `readable_context_paths`, and
  `validate` returned `unfit` twice until both were declared. That is the read-trace doing exactly
  what it was built for.

## 6. Correction, 2026-08-25: why the probe was green here

Recorded because the correction matters more than the finding it corrects.

Bringing devbox's checkout current ran this suite there for the first time, and two tests in
`RetryWorkspaceReuseTests` failed on devbox while passing on the workstation. The fixture defect
was real -- a `TemporaryDirectory` is 0700, the worker user cannot traverse it, and the real
worktree root `/tmp/agentops-hybrid` is 0755 -- and the one-line fix (#104) stands.

**The explanation attached to it did not.** I wrote that the probe is skipped on hosts without an
`agentworker` user, "which includes the workstation". I had not checked, and both halves were
false: `agentworker` exists here too, uid 1101, in `agentdispatch`, and `sudo --non-interactive
--user agentworker` works. The owner asked whether they had not specifically created that user.
They had.

The real cause is one line: `--worker-user` defaults to `os.environ.get("AGENTOPS_WORKER_USER")`.
Devbox's agent login shell exports it; the workstation does not set it. With no worker user,
`worker_can_write` returns `True` immediately -- *"no worker user: writes happen as the
coordinator"* -- and never reaches the group check or the sudo probe.

So **whether the loop's containment check runs is decided by an environment variable in whatever
shell invoked the suite.** That is a worse property than the one I claimed. "This host lacks the
user" is at least discoverable from the host. An unexported variable is invisible in the repo,
invisible in the test output, and differs between two machines that both have the user and both
have the sudo rights.

It is also, once more, the §3h shape -- and this time I produced it rather than found it. A
skipped check and a passed check reported the same thing, I read the green and inferred a cause
that fit, and the inference went into a commit message, a debt line and a report to the owner
before anyone tested it. The loop's own answer to this class of problem already exists: L-2b's
read-trace reports `"skipped:untraced"` and never `true`, precisely so that "did not look" cannot
be read as "looked and was fine". This probe has no such marker. That is the debt line now.
