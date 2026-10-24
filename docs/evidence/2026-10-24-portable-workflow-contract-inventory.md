# Portable agent workflow contract inventory

Snapshot: 2026-10-24. Scope: AgentOps PW-01 and the Vuoro VU-PW1 inventory
queue. This is a source inventory of local candidate branches, not an accepted
wire contract, release receipt, deployment observation, or runtime
qualification.

## Source pins

| Owner | Candidate source | Relevant existing records |
| --- | --- | --- |
| AgentOps | `cloud/20261024/programme-08-integration-agentops-exact` at `0e5c9a1f234f7f986443a82c6c69618c564ec22c` (code head `af5b58643ce486a17069eee84effa6edad299bba`) | `schemas/session-binding.schema.json` (`session-binding/v0`, file-backed); `schemas/handoff.schema.json` (`handoff/v1`, local successor handoff); `schemas/project-release/project-evidence-package.v1.schema.json` (`project-evidence-package/v1`, repository bundles and digests). |
| Vuoro | `cloud/20261024/programme-08-integration-vuoro-exact` at `e849c4e7a231585330980bf4bd5aeb00ebfa6150` | `packages/vuoro-mcp-edge/src/vuoro_mcp_edge/{runs,record_tools,claim_tools}.py` define caller-bound run registration/continuation, owner evidence forwarding, and Sprintctl lease tools. `vuoro-worker` documents a host-local Managed Agents poller. `vuoro-workspace` stores repository-document citations as repository/commit/path references. `packages/vuoro-demo/pyproject.toml` pins `vuoro-client==0.1.2`, `vuoro-service==0.1.97`, `sprintctl==0.22.0`, and `sovite-platform==0.1.16`; these are source dependency pins, not proof of published or deployed artifacts. |
| Sprintctl | `cloud/20261024/programme-08-integration-sprintctl` at `e80df31ad6424f1c757ebbab68dfe0042fb4d571` | `docs/reference/vuoro-work-adapter.md` catalogs the protocol-v1 owner operations, their authority, idempotency, and schema evolution. `docs/reference/operator-request-lifecycle.md` describes the schema 28 request candidate and `work.request.*` operations. `docs/reference/context-and-handoff.md` documents served-only `run brief`, backed by `work.run.continuation-delta-v1`. The pinned Vuoro demo uses Sprintctl `0.22.0`. |
| Sovite | `cloud/20261024/programme-08-integration-sovite-exact` at `46c2670d6a047367617b58af7e5cf62a43f4ccae` | `docs/plans/2026-10-23-execution-lease-owner.md` describes internal reserve/start behavior. `docs/contracts/worker-execution-v1-candidate.md` is a proposal; `pyproject.toml` says `0.1.17`, while the Vuoro demo dependency pin remains `0.1.16`. |
| Vuoro Cloud | `cloud/20261024/programme-08-integration-vuoro-cloud-exact` at `95b6af72f2addec4fcfaf1461ea873d5a61d6816` | `src/vuoro_cloud/oauth_scopes.py`, `security.py`, and `config/schemas/` describe caller grants, connector/invocation records, and evidence shapes. No portable-workflow owner plan or supported new-Cloud task-launch API is present in this candidate. |
| Appservice | `cloud/20261024/programme-08-integration-appservice-exact` at `5b552c37e8de8fb2a13806da4c88bd09db973b14` | `docs/plans/2026-10-24-portable-agent-workflows.md` assigns onboarding, worker-host commissioning, landing prerequisites, observability, and source/artifact reachability. It is explicitly documentation-only; its surveyed source pin is `5ab5e11771a07585457759c0344908d6d0011286`. |

The `gitops-nixos`, `cred-broker`, and `mars-founder` source trees are not present
in this workspace. The survey pins in the AgentOps plan (`b554d5e0`,
`c0bee20e`, and `134396d9`) were not refreshed here. No host enrollment,
broker registration, or Mars Founder runtime claim is made.

The Vuoro owner plan `docs/plans/2026-10-24-portable-agent-workflows.md` was
read through the GitHub connector from `main` (blob SHA
`00616d1355e1b67631507134222faf248fee62ca`); it surveys Vuoro source at
`61df7c27217b1e2818737b19481ebe07e4c9f6bd`. That plan defines VU-PW1 as a
published-operation/version inventory and VU-PW2 as scoped portable context
against PW-01 fixtures. The plan file is not present in the pinned local Vuoro
candidate tree; its contents are cited as plan context, not candidate code.

## Capability map

| Capability | Existing owner source | Current limit |
| --- | --- | --- |
| Repository identity and artifact refs | AgentOps `handoff/v1` records local repo paths, heads, branches, and diff digests. `project-evidence-package/v1` records repo IDs, commits, bundle names, and file digests. Sprintctl runs bind to the authenticated owner identity and repository. | These records have different owners and purposes. They do not form one portable, owner-authorized binding of canonical locator, immutable base, target branch, permitted change surfaces, and input access classes. A path or bundle ref does not grant access. |
| Work and readiness | Sprintctl `work.read.context`, `work.read.context-candidates`, and `work.read.next-work`; the context read is an owner-side aggregate. | `context-candidates` is a bounded dispatch projection; invoking it does not reserve or start work. Reservations remain advisory. |
| Predecessor context | Sprintctl `work.run.register-v1` accepts optional `predecessor_run_id`; `work.run.predecessor-context-v1` returns a bounded page of predecessor notes and evidence (schema 20). | The link transfers readable context under current grants. It does not transfer authority, cancel a live predecessor, or resume a native process. |
| Vuoro caller binding and owner forwarding | `packages/vuoro-mcp-edge/src/vuoro_mcp_edge/runs.py` binds run handles to principal, workspace, repository, and asserted OAuth client/grant; predecessor registration requires the same workspace and repository. `record_tools.py` forwards run, evidence, and note operations to Sprintctl through the runtime shell. `claim_tools.py` forwards acquire, heartbeat, and report-outcome to Sprintctl; its source names Sprintctl 0.10.0 as the minimum lease-owner version. | These are narrow owner adapters, not environment capability discovery or a provider execution state machine. A successor run resolves only under its own caller binding. The lease owner evaluates and settles work; Vuoro does not keep lease state. |
| Fresh-reader work comparison | Sprintctl's served-only `run brief` calls `work.run.continuation-delta-v1` for an explicitly named item and currently owned successor run. JSON preserves the owner response, checkpoint and cursors; text marks changed, unchanged, and unknown owner records. | It is a useful one-owner continuation surface, not a whole-programme packet: reference records do not fetch or verify source bytes, it does not publish host/harness capability or startup state, and it does not establish a candidate-to-landing chain. A fresh-host end-to-end continuation has not been demonstrated by this inventory. |
| Repository source references | Vuoro `packages/vuoro-workspace/src/vuoro_workspace/vuoro_adapter.py` accepts `repository_document` citation refs containing repository, commit, and path. | A citation is an owner record. It does not retrieve bytes or grant source/artifact access. The inspected execution-facing contracts do not bind transferred bytes to a successor attempt. |
| Checkpoints and evidence | Sprintctl run registration/resolution, `work.session-note.write-v1`, `work.evidence.append-v1`, `work.evidence.tail-v1`, and exact evidence lookup. Work leases expose acquire, heartbeat, report-outcome, and read operations. | These are owner records with separate authority and schema histories. They do not establish one cross-owner attempt lifecycle or prove useful progress from a heartbeat. |
| Operator requests | Sprintctl schema 28 candidate operations: `work.request.publish-v1`, `work.request.get-v1`, `work.request.list-v1`, `work.request.events-v1`, `work.request.revise-v1`, `work.request.dependent-add-v1`, `work.request.dependent-withdraw-v1`, `work.request.progress-v1`, `work.request.report-performed-v1`, `work.request.attest-v1`, `work.request.decline-v1`, and `work.request.supersede-v1`. | The candidate provides revisioned owner history and human attestation. It has no live session-liveness observation, native wake/resume, or per-dependant continuation acknowledgement. |
| Grants and execution authority | Sprintctl run records bind principal, workspace, repository, and asserted client/grant. Work operations require owner scopes such as `work:read` and `work:evidence`. Vuoro Cloud OAuth scopes describe the caller's grant. | A caller grant, advisory reservation, run link, or published environment is not an enrolled worker identity or execution lease. |
| External execution references | Sovite's internal lease owner has reserve/start behavior. The `worker-execution-v1-candidate.md` explicitly does not admit an external route. | Renew, status, handback, complete, and lookup wire operations remain unfrozen. No external worker enrollment or remote repository-editing path is qualified. The inference connector is not a worker-control channel. |
| Existing Vuoro consumer | `packages/vuoro-worker/README.md` describes a Managed Agents poller with a host-local MCP server; its tests use `FakeQueueClient`. The private-workflow demo is labeled local C0 fixture execution and records that it has no hosted or production qualification. | The Managed Agents vendor client is explicitly not exercised in repository tests. Neither this poller nor the synthetic demo establishes Cloud launch support, general repository editing, or a clean-host portable successor. |
| Progress through landing | Sprintctl records work, run/evidence, lease, decision, and effect-intent facts under their respective owners. AgentOps has local continuation and release projections. | No shared record carries submitted, acknowledged, started, progress, candidate, verified, accepted, landed, and deployed as distinct owner-backed observations. AgentOps continuation-ready is read-only and does not wake a runtime. |

The Sprintctl adapter reference identifies run/evidence/note operations as
package `0.8.0`, remote schema 17; leases as package `0.9.0`, schema 18;
effect intents as package `0.11.0`, schema 19; predecessor context as package
`0.11.0`, schema 20; run resolution v2 as schema 26; and run-scoped delegation
as schema 27. Those are operation-owner revisions, not a portable workflow
packet version. Vuoro's claim adapter names Sprintctl `0.10.0` as its minimum
lease-owner version; its record adapter describes predecessor context at
Sprintctl `0.11.0`/schema 20; the Vuoro demo source pins Sprintctl `0.22.0`.
These are a consumer minimum, an operation's owner release, and a demo source
pin respectively. None establishes what is currently deployed.

## Existing owner-level test coverage

These are source references found in the pinned candidate branches. A passing
owner test covers that owner behavior; it does not prove the full portable
workflow across repositories or hosts. This inventory pass did not rerun these
tests.

| History | Existing source coverage | Remaining integration gap |
| --- | --- | --- |
| Wrong repository/workspace | Sprintctl `tests/pg/test_agent_inbox.py::test_run_lookups_are_scoped_to_the_callers_workspace`; Vuoro `packages/vuoro-workspace/tests/test_workspace_hardening.py::test_cross_workspace_references_are_refused` and `packages/vuoro-mcp-edge/tests/test_run_continuation.py::test_a_successor_outside_the_predecessors_workspace_or_repository_is_refused`; AgentOps `scripts/tests/test_execution_authority.py::test_repository_not_in_scope_refuses`. | No end-to-end dispatched worker proves tenant and repository bindings persist through launch and artifact access. |
| Stale source or governing revision | Sprintctl `tests/test_handoff_checkpoint.py::test_a_recorded_checkpoint_is_served_to_the_next_process`, `::test_a_position_without_a_revision_is_not_a_checkpoint`, and `tests/test_result_packet.py::test_expected_hash_grammar_is_not_silently_ignored`; Vuoro `packages/vuoro-workspace/tests/test_vuoro_adapter_served.py::test_stale_base_is_refused_with_the_current_revision`; Sovite `tests/test_workflow_admission.py::test_worker_rechecks_revoked_source_before_attempting_public_job`. | No clean-host attempt binds every governing document and delivered input digest to its execution. |
| Revoked grant or enrollment | Vuoro `packages/vuoro-mcp-edge/tests/test_claim_tools.py::test_a_run_of_another_grant_is_refused_before_the_lease_owner`; Sovite `tests/test_execution_lease_regressions.py`, `tests/test_execution_leases.py`, and `tests/test_result_access.py`; Vuoro Cloud `tests/test_scope_matrix.py` and `tests/test_oauth_integration.py`. | Caller-scope refusal tests do not establish worker enrollment or remote execution revocation. |
| Lost response, uncertain startup, and takeover | Vuoro `packages/vuoro-mcp-edge/tests/test_claim_tools.py::test_takeover_supersedes_and_the_former_holder_gets_claim_superseded`; Sovite `tests/test_execution_leases.py`, `tests/test_backend.py::test_o2_same_worker_old_task_cannot_borrow_replacement_fence`, and `tests/test_model_authority.py::test_LEASE_FENCED_hand_back_reclaim_while_streaming_cancels_old_fence`; AgentOps `scripts/tests/test_host_adapter.py::test_ambiguous_abandon_resumes_frozen_intent_after_lost_result_response`. | Owner-specific retry/fencing is covered; the worker-origin startup receipt and submitted/acknowledged/started distinction are unqualified. Remote renew/status/handback/complete/lookup remain unspecified. |
| Candidate head and review | AgentOps `scripts/tests/test_execution_authority.py::test_publication_requires_redeemed_unreported_attempt_for_the_same_commit`, `scripts/tests/test_commit_audit_shards.py::test_protected_github_merges_with_match_head_commit`, and `apps/operator-projection/tests/test_bundle.py::test_stale_release_and_decision_substitution_never_imply_current_acceptance`; Sprintctl `tests/pg/test_protected_artifact_acceptance.py::test_release_named_check_revision_is_required_on_actual_acceptance` and `::test_release_revision_moves_after_receipt_refuses_and_cannot_downgrade_frozen_requirement`. | Individual exact-commit gates exist; stale independent review and exact-head CI/review receipt binding are unqualified end to end. |
| Missing usage coverage | AgentOps `hooks/tests/test-cost-hook-publish-failure.sh`, `hooks/tests/test-cost-hook-fields.sh`, and `scripts/tests/test_profile_comparison.py::test_missing_ledger_fails_instead_of_reporting_zero_history`; Vuoro Cloud `tests/test_tenant_coverage.py`. | Missing provider usage has not been shown as unknown spend for one correlated worker attempt. |
| Clean host without predecessor archive | Sprintctl `tests/test_run_brief.py` covers the served CLI's bounded owner response; `tests/pg/test_run_continuation.py` covers owner continuation behavior. Vuoro `packages/vuoro-mcp-edge/tests/test_run_continuation.py::test_a_different_identity_successor_reads_the_predecessors_notes_and_evidence` exercises a different bound caller; AgentOps `apps/operator-projection/tests/test_portable_acceptance.py` covers a local portable-acceptance view. | No fresh-host history registers and authenticates a successor, reconstructs a multi-owner programme from owner reads, resolves transferred source inputs, and reaches a candidate without the first host's private archive. The existing tests do not qualify that end-to-end path. |
| Managed Agents consumer | Vuoro `packages/vuoro-worker/tests/test_poller.py::test_run_once_is_idempotent_for_a_repeated_task_id` covers fake-queue replay, and `::test_run_once_skips_dispatch_when_tools_are_unavailable` covers unavailable local tools. | The repository README states the vendor queue client is not exercised in tests; process restart, host replacement, and the external session/startup receipt are not qualified by these fake-client cases. |

## PW-01 result and next work

Existing contracts cover useful pieces of repository binding, owner work
readiness, predecessor context, evidence, grants, and execution leases.
Sprintctl's `run brief` already gives an authorized successor a bounded,
owner-backed comparison for one item; it avoids depending on the prior host's
private archive for those facts. The contracts remain separate owner records.
The cross-owner programme packet, caller-visible capability negotiation, and
evidence-backed startup/landing chain are not implemented as a shared contract,
and this inventory does not demonstrate a fresh-host end-to-end continuation.

The next PW-01 design should start by composing the existing Sprintctl `run
brief`, AgentOps handoff, and owner-scoped source/evidence references; it must
not assume a new shared record is needed. Any extension must preserve the
TypeSpec ownership and release path, leave execution authority with Sovite,
keep work state with Sprintctl, and keep provider session state with the native
harness. A packet can describe requests and observations; it cannot grant
itself access, start work, accept a candidate, or authorize landing.

Before a new shared schema is admitted, review the unresolved EC-00 acceptance
conditions and pin the generation/validator toolchain. Follow-on threat
fixtures should exercise wrong repository/workspace, stale source and governing
refs, revoked grants, missing transfer permission, response loss, uncertain
startup, stale attempt/candidate, and unknown usage coverage. Existing fake
poller coverage is not clean-host or provider qualification.
