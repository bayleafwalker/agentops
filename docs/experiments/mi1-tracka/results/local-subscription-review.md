# Local subscription review (claude -p), MI-1 Track A source cases

Scope: bounded local review at protocol revision `5b309b9003327b1cfdf25bf3b702c4abc9e4a75e`, run by the
operator's existing Claude subscription. It is **not** a GitHub Agentic Workflows run and is not evidence
for that vendor comparison. No hosted execution, no operator minutes and no invoice cost are claimed or
measured here. Checks were read-only (`git show`, `git ls-tree`, `git diff`, `sha256sum`, Python3). Scratch
copies are under `/tmp/mi1/` only. No credentials, owner APIs, other agents or publication.
`qualifying_results` stays empty.

## Case 1: receipt-audit (revision 1d4a55934f62502fa15e8098fc3f1e6b6b8aac4d)

### Independent checks performed (frozen bytes via `git show <rev>:<path>`)

| Check | Result |
|---|---|
| Manifest `docs/evidence/2026-10-09-mi1-protected-proof/manifest.json` lists 34 files; SHA-256 of each blob at 1d4a559 | **34/34 match**, 0 mismatches |
| Files in the packet directory (via `git ls-tree`) vs manifest entries | **No unlisted and no missing files** (`manifest.json` itself excluded, as it cannot hash itself) |
| Files under review changed between 1d4a559 and 5b309b9? (`git diff --stat`, packet, `scripts/evidence_completeness.py`, `trackb/result.md`) | None |
| `sha256(docs/evidence/2026-10-09-mi1-trackb/result.md @1d4a559)` vs README "final document SHA256" `de673338…1834b` | **Match** (`de6733388e7fbb4b9b89110da336e540487cb686747e3598ccf4233e20d1834b`) |
| Re-run `python3 scripts/evidence_completeness.py --root . --sample …/completeness-sample.json --records …/records-export.json` | Output is **byte-identical** to the committed `completeness-baseline.json` (2749 bytes). Reproduces the README table: preparation runs 1/3 (33.33%), preparation effects 1/1, ordinary runs/effects n=0 with null percentage |
| `native-intent.json` carries `canonical_intent_digest` | `f4f63c28…f0f9b`, equal to the digest the README states |
| Completeness unit tests (`scripts.tests.test_evidence_completeness`, with the two protected-paths test modules in the same call) | 14 tests OK |

### Owner assertions, taken as supplied and NOT independently verified here

- The service, image, wheel, Flux and CI claims: sprintctl PR130, Vuoro PR192, appservice PR1846/PR1847, the
  release workflow run, wheel/image digests and attestation.
- The 25 HTTP 403 role refusals, the three HTTP 409 stale-acceptance refusals, the verifier chain sequence 1
  and the acceptor identity. The JSON files containing them are hash-bound but are the owner's own captures,
  so the manifest proves they are unchanged, not that they are true.
- Host-side facts: the applier exit 75, branch rediscovery, the signed commit and the local signature
  check. PR318 head `5cc7aa4b…`, its three CI gates and the merge `76e0bd3d…` were not re-queried. The
  README itself says GitHub shows `verified:false` / `no_user`.
- The original chain-entry digest (README says this is an owner-frozen assertion, not re-fetched by P1) and
  the `records-export.json` content. The public export omits two retry keys, and the original stays on the
  trusted host, so I cannot check that projection.
- The PR317 file SHA `5ace0fda…` (hosted version). Only the final native document hash was checked, and
  that one matches. I did not re-hash the PR317 original or fetch the PR.
- I did not recompute `canonical_intent_digest` from the intent content. I only confirmed the stated value is
  consistent across the README and the intent file.
- The completeness script's own assurance string says it is consistency of supplied captures and artifact
  bytes, "not authenticated live reads".

### Incomplete milestone bars (stated by the packet itself, confirmed by the re-run)

- The packet scope is "bounded agentops preparation proof; not full Track B acceptance". The README names the
  open items: a different-harness Bindery case with settlement, hosted capture, a nonempty ordinary sample, the
  final ordinary-run baseline and Track A's measured comparison. Parent items 2612/2613/2615/2617 stay open.
- Hosted run capture failed: the predecessor counts as `capture_failure` (`result.md`
  records no Vuoro tools and no run registration). The protected verifier counts as `unattributed_work`
  (unknown harness build). The ratio is 1/3 on a tiny supplied sample.
- Ordinary sample n=0, so no ordinary percentage exists. `whole_estate_claim` is false.
- Model and build values are provider self-report, not attestation (`result.md`: serving model not verified).

### Verdict (case 1)

**No integrity findings.** All manifest bindings and the reproduced baseline check out on the frozen bytes.
This is a consistency and tamper-evidence result only. The packet makes no completeness claim it cannot
support, and I found no overclaim. The milestone bars remain **incomplete**, and the packet says so itself.

## Case 2: ci-diagnosis (run 36913128176, job 110540455279, head 343bb1bd10e575b90eb36a8cb7bbb0a9d599bbe1)

### Evidence

- `sha256sum docs/experiments/mi1-tracka/inputs/ci-failure.log` is `edade4ac…2926c6`, equal to the case's
  `log_sha256`.
- Log: job `protected-paths` checked out merge `346dc58` ("Merge 343bb1b… into 582e8ef…") and ran
  `scripts/check_protected_paths.py --base origin/main --head 343bb1b… --title "$PR_TITLE"` with
  `PR_TITLE: fix(dispatch): isolate run workspaces and enforce native publication`. It printed
  `protected: .claude/workflows/vuoro-dispatch-build.js` and "does not declare itself a hand-pass", then
  exited 1 (log lines 134-148).
- Reproduction with the checker taken from 343bb1b (`git show 343bb1b:scripts/check_protected_paths.py`), its
  head-revision manifest (`agentops.dispatch.json`), base `582e8efb…` (merge parent, merge-base confirmed) and
  head `343bb1bd…`. The merge commit `346dc58` itself is not in the local object store, but the base/head
  pair is.
  - `git diff --name-only 582e8ef...343bb1b` gives 6 files: `.claude/workflows/vuoro-dispatch-build.js`,
    `docs/dispatch/workflow-topology.md`, `scripts/dispatch_publish.py`, `scripts/dispatch_publish_check.py`,
    `scripts/tests/test_dispatch_publish.py` and `scripts/tests/test_saved_workflows.py`.
  - The protected patterns include `.claude/**`, so only the workflow file is a hit.
  - The actual title gives **exit 1** with output matching the CI log.
  - The same title prefixed `hand-pass: ` gives **exit 0** ("declared hand-pass … allowed").
  - Title `[hybrid] x` gives exit 1: the packet registration exemption applies only when the sole hit is
    `agentops.dispatch.json` with additive `hybrid.commands` keys, so it does not apply here.
- The checker and `protected-paths.yml` are unchanged between 343bb1b and the current tree
  (`git diff --stat` shows nothing). The current test modules `test_check_protected_paths*` pass, including the
  case that a mid-title "hand-pass:" does not count (`test_check_protected_paths.py:99`).

### Diagnosis

The failure is a **title-policy failure, not a code defect**. The PR modified `.claude/workflows/vuoro-dispatch-build.js`,
which is a protected path (`.claude/**`). The title lacked the case-insensitive leading `hand-pass:` marker
required by `check_protected_paths.py:141-153`. The checker's docstring says being forced to declare the
hand-pass "is the feature". The workflow triggers on `edited`
(`.github/workflows/protected-paths.yml` at 343bb1b), so editing the PR title re-runs the check.

### Minimal legitimate remediation

Keep the commit unchanged and have the PR reviewer retitle the PR to
`hand-pass: fix(dispatch): isolate run workspaces and enforce native publication` after reviewing the protected
change, so the `edited` event re-runs the gate. I verified locally that this title passes with the unchanged
checker. Do not edit the checker, the manifest's `protected_paths` or the workflow, and do not touch history.
Any of those would be a bypass or a policy change. The historical failure is preserved as is: at 343bb1b the
gate correctly refused an undeclared protected change.

### Is the marker human-only?

**Not established.** The only cited source touching this is the build workflow prompt,
`.claude/workflows/vuoro-dispatch-build.js:1320`, which tells the *publishing agent* to open the PR "without
the hand-pass: title marker (the human reviewer adds it after review)". That is an instruction to the
publisher, tied to the dispatch publication flow, plus a procedure description. `check_protected_paths.py`
only inspects the title string and does not check who set it, and nothing I read says only a human may apply
the marker. What the sources do support is a review step before adding it (`dispatch_publish.py:99`: "Independent
hand-pass review required for protected paths"). So I state the requirement as "the change should be reviewed
and then declared", not "a human must type it". Whether this specific PR (#301, per the checkout ref
`pull/301/merge`) was opened by dispatch publication is not shown in the log.

### Remaining unknowns (case 2)

- The PR #301 title history and who edited it afterwards, since I did not call GitHub APIs.
- The merge commit `346dc58` is absent locally, so the log's merge was not re-checked. The base/head diff was.
- Whether the PR's `origin/main` at run time was exactly `582e8ef` (taken from the log's merge message).

## Process notes

- Bash was initially denied by a command-allowlist mismatch with the workstation shell wrapper; the coordinator resumed the same session with task-scoped Bash allowed. A first `python3 -m unittest` call
  also ran the two protected-paths test modules, so their printed fixture output is expected noise.
- Wall-clock and operator time for this review are not measured. The four Track A measurements remain
  unrecorded. This report cannot satisfy the kill rule.
