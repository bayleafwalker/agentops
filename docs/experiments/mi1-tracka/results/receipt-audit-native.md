# MI-1 Track A `receipt-audit`: native agent proposal

Agent proposal only; a separate reviewer applies the rubric. No acceptance, cost, usage or operator time is claimed (all unknown here).

## Scope and frozen inputs

- Ledger: `docs/experiments/mi1-tracka/cases.json`, `input_revision` `1d4a55934f62502fa15e8098fc3f1e6b6b8aac4d`. Worktree HEAD was `5b309b9` (later).
- Read via `git show 1d4a559:<path>`: `result.md`, `manifest.json`, `evidence_completeness.py` and the test file. The frozen bytes for these four files equal the worktree bytes. Every manifest-listed packet file was also compared against the frozen revision in the manifest check below.
- Not independently re-derived: the other packet files beyond digest and the checks below. I did not read most of the JSON receipts' contents, and I did not read the README of the experiment's `inputs/`.
- Constraints: the shell was limited to `git show`, `git status` and `python3`. Output of one `python3 -B` script is cited below. The script ran `git show` through subprocess, so a worktree-based run was not compared against `git` for the query output itself.

## Checks actually run

1. **Manifest binding.** `manifest.json` (SHA256 `a627897b…4a3c`, schema `mi1-receipt-set/v1`) lists 34 files. For every entry, SHA256 of the frozen-revision bytes and of the worktree bytes both equal the manifest digest: 0 mismatches. The directory holds no unlisted file other than `manifest.json` itself, and no listed file is missing. Caveat: the manifest cannot bind itself, and it is self-attesting, not an independent authority.
2. **Cross-reference of documented digest.** `result.md` frozen SHA256 is `de6733388e7fbb4b9b89110da336e540487cb686747e3598ccf4233e20d1834b`, which equals the "final document SHA256" in the packet `README.md` (lines 51-52). The predecessor digest `5ace0fda…` is a historical value inside `result.md` and the README, which I did not check against PR317.
3. **Completeness query.** I ran the README's command (`scripts/evidence_completeness.py --root . --sample …completeness-sample.json --records …records-export.json`): exit 0, and stdout is byte-identical to `completeness-baseline.json`. Groups: `run:preparation` 3 entries / 1 reconstructible; `effect:preparation` 1/1; `run:ordinary` and `effect:ordinary` 0/0. Entry failures: hosted session `session_01R4…` → `capture_failure`; `protected-verifier` → `unattributed_work`; native session and `intent_83661…` → none. This matches the README table (1/3, 1/1, n=0).
4. **Tests.** `python3 -B -m pytest -p no:cacheprovider -q scripts/tests/test_evidence_completeness.py`: 9 passed. This matches the README's "nine focused failure cases". A first attempt with `python3 -m unittest` ran 0 tests (exit 5) because the file is pytest-style, so that attempt carries no evidence. I did not run the broader suite (1254 tests) the README cites.
5. **Live reconstruction label.** `live-owner-reconstruction.json` has status `complete`, empty `missing` and `conflicts`, and `authorizes_effects: false`. This is a supplied capture; I did not re-run P1 against a live owner.

## Findings

No factual defect found in the checked claims. The following are verified-in-bounds versus asserted:

- **Independently checked (here):** manifest digests; document digest consistency between `result.md` and the README; reproducibility of the completeness baseline from supplied bytes; the 1/3 and 1/1 ratios; the 9 focused tests.
- **Owner or third-party assertions, not checked:** Sprintctl/Vuoro/appservice PR numbers, merge SHAs, wheel and image digests, CI results, attestations, the HTTP 403/409 refusals, SSH fingerprint, signature verification, PR318 `verified:false`, session IDs, the 155-passed result and the 1254-test suite. These are recorded in the packet, not confirmed against GitHub or the owner by me.
- **Scope honesty:** the packet states it is not full MI-1/Track B acceptance; Track A, hosted capture, a different-harness Bindery case, and a nonempty ordinary sample remain open. The completeness query itself says it measures consistency of supplied records, not authenticity (`evidence_completeness.py` docstring and `assurance` field). The 3-entry sample is explicit, not an estate rate. I see no overclaim in the README on these points.
- **Observation (not a defect):** the `records-export.json` is a public projection that omits two owner retry keys (README lines 137-140), so it cannot equal the trusted host's original; the query's equality to the baseline holds only for the public bytes.
- **Observation:** `result.md` records the successor's own session telemetry (build 2.1.289, unverifiable model); the README carries the same limitation.

## Remaining unknowns

- Whether the packet files other than those listed match the external sources they describe (PRs, runs, owner state).
- Whether `result.md` content matches PR317's published file (not fetched).
- Full-suite results and the CI-equivalent run.
- Operator time, agent wall time, usage and cost for this attempt: not measured.
