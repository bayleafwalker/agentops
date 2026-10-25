# Candidate branch disposition, 2026-10-25

This record preserves the useful findings from the 2026-10-24 programme branch
audit before stale refs are retired. A branch head is evidence of source state,
not current owner policy or release qualification.

## Source disposition

| Source | What it contains | Disposition |
|---|---|---|
| Vuoro `cloud/20261024/programme-08-integration-vuoro-exact`, [`9d7003ee2b693c91695f124bc16dc30639bd74ca`](https://github.com/bayleafwalker/vuoro/commit/9d7003ee2b693c91695f124bc16dc30639bd74ca) | Candidate MCP metadata projection, provisional Sovite demo client, and changes to contract CI. | Do not merge the branch wholesale. The current authored operator-requests contract contains models but no HTTP routes; the production contract test source remains the probe fixture. The proposed catalog must stay definition-only and empty for current production operations until owners add an explicit operation roster and mapping. The branch also removes the pinned Ubuntu runner, exact offline wheel install, and separate wire/wheel qualification gate; those weakened checks are not accepted. The demo client has no route/shape/ambiguous-outcome test against the current published Sovite release. |
| AgentOps `cloud/20261024/programme-08-integration-agentops-exact`, [`195465f2167876b2b779fedb5adb91345e390e80`](https://github.com/bayleafwalker/agentops/commit/195465f2167876b2b779fedb5adb91345e390e80) | Local-only portable batch preparer, exact-candidate reviewer, and source-pin verifier; also candidate workflow/document/evidence deletions. | The three local tools are retained as candidate-only source and qualified by `scripts/tests/test_portable_batch_tools.py`. They perform local inspection and format bounded packets; they authenticate no issuer, contact no owner, dispatch no work, change no grants, and do not land or deploy. The candidate parser changes to `scripts/operator_requests.py` are excluded because they regress the bounded strict JSON and valid-packet protections in PR416. |
| Vuoro `claude/ecstatic-albattani-ahk3vi7fa56fd23f24`, [`7fa56fd23f2410642c7bed12df635c2dde3048c0`](https://github.com/bayleafwalker/vuoro/commit/7fa56fd23f2410642c7bed12df635c2dde3048c0) | Revised versioning-backend assessment only. | Historical proposal, not current policy. It recommends a common revision reference, workspace publications/selections, and a Git source-resolution kit while rejecting a Vuoro-owned Git object store or fork. Its metadata remains `purpose: proposal`, `lifecycle: draft`, and it grants no migration authority. |
| Vuoro `claude/pensive-cray-bszpta41e927b2a833`, [`41e927b2a8337a470e6859599742245fa819de6f`](https://github.com/bayleafwalker/vuoro/commit/41e927b2a8337a470e6859599742245fa819de6f) | Revised agent discovery/reachability assessment only. | Historical proposal, not current policy. It rejects a coordinator service, distinguishes discovery/notification from scheduling/dispatch, and leaves outbound reachability unverified for several harnesses. It authorizes no build, deployment, register change, repin, or publication. |

## Preserved evidence and retirement boundary

The AgentOps P08 candidate deletes the approved-experiment plan
`docs/plans/agentops/2026-10-25-subscription-cross-harness-pilot.md` and the
autonomous-investigation evidence/source set. The pilot plan is marked
`approved-experiment-plan` with approval date 2026-10-25. The investigation
implementation is explicitly candidate source built without its named roadmap
attachment. Its demo is a synthetic configuration case with no historical
incident data and no deployed-system claim; its history replay is a
retrospective, unblinded smoke qualification over sanitized training summaries.
These are distinct records and none is an ActionQ worker or daemon. Their
deletion in P08 is not a supersession decision; the current Git history keeps
the source and artifacts available for review.

The ActionQ execution daemon is retired and `actionq-dispatcher` is a
fail-closed tombstone. Old schemas, fixtures, handoff examples, or source-pin
rows that name ActionQ are historical inputs only. They do not restore an
ActionQ runtime. Do not delete a fixture or mark it superseded without the
owning disposition record; do not treat an old ActionQ receipt as evidence of
current startup, authority, or service state.

## Qualification receipt for the portable helpers

The local test gate is:

```text
pytest -q scripts/tests/test_schema_check.py scripts/tests/test_schema_check_audit.py \
  scripts/tests/test_schema_check_composition.py scripts/tests/test_portable_batch_tools.py \
  scripts/tests/test_operator_requests.py
```

Result on the exact candidate worktree: 213 passed, 19 skipped by the existing
schema-check test suite, 871 subtests passed. `python -m json.tool` accepted the
portable request and review-request schema documents; `compileall` accepted the
three tool modules. Synthetic tests cover strict bounded JSON (byte/depth/
duplicate/non-finite refusal), scope/path rejection, secret-shaped prompt
refusal, schema/runtime alignment, local snapshot mutation, origin mismatch,
immutable commit/blob pin checks, stale branch heads, duplicate/stale/mismatched
review receipts, and explicit non-authority output. `operator_requests.py` was
not changed; its existing valid-request and parser-refusal tests passed in the
same run.

This is local source qualification only. Source pins in the candidate manifest
remain a snapshot and must be rechecked against current owners before use. The
report does not certify provider capability, receipt authenticity, owner
readiness, a public MCP roster, a service, a release, or a deployment.

## P08 Sovite client disposition update — 2026-10-25

The earlier P08 assessment above predates the current published Sovite owner
source. Sovite v0.1.21 is released from public source commit
[`f76ff8cad5e5733721d5ba37dcf13444f732bd3a`](https://github.com/bayleafwalker/sovite/commit/f76ff8cad5e5733721d5ba37dcf13444f732bd3a).
Its published wheel is
[`sovite_platform-0.1.21-py3-none-any.whl`](https://github.com/bayleafwalker/sovite/releases/download/v0.1.21/sovite_platform-0.1.21-py3-none-any.whl),
SHA-256 `ec0790a6d09f914661f6cd5fc24f4390516acb44f3749b8af6af0ea2bc59f017`.
The generated F2 execution contract and strict owner client are in that source
under `contracts/execution-v1/`,
`sovite/execution_contract/vuoro_contract_c3c73ae52d117dd8407c15d4b4b549461e753e30de4783134a2cad02f5dd1ab4_client/`,
and `sovite/execution_client.py`; tests exercise the generated client through
the owner API. Current canonical Sovite main also contains PR #17 at
[`1939baadc80dc1dd51cea9ad9f47e63eb817e412`](https://github.com/bayleafwalker/sovite/commit/1939baadc80dc1dd51cea9ad9f47e63eb817e412).

Disposition update: Vuoro P08's handwritten provisional Sovite adapter in
`packages/vuoro-demo/src/vuoro_demo/sovite_execution.py` and its earlier
`vuoro-client` prototype are superseded by the generated owner contract/client
and bounded strict client in the released Sovite source. The old prototype
remains historical evidence only; the P08 branch may retire after its other
source items are reconciled. This source disposition does not make a new claim
about rollout or owner acceptance.
