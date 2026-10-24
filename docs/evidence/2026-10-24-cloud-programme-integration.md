# Cloud programme candidate handback

Snapshot: 2026-10-24. This records local source candidates and focused disposable checks for the eight programmes in `docs/dispatch/programmes/2026-10-24/`. It is not a deployment, production, retained-state, or owner-acceptance receipt.

## Dispatch and continuation

The Codex Cloud submission failed before task creation because this environment could not reach `chatgpt.com/backend-api/wham/environments`; its enforced restricted network policy excludes that host. No Cloud task ID was returned. The available controls expose neither a working Cloud submission path nor a persistent native Goal create/read/update path. The 30-hour prompt therefore does not establish automatic continuation, remote task identity, selected remote model, or a started implementation session. Source work proceeded in local isolated Git worktrees with GPT-6 Luna subagents where useful.

The programme specifications and long-running worker contract were read from AgentOps source commit `b760494dea018794231e197e71927b12e14efa53`. The initial source seeds were verified as Vuoro Cloud `a237bbdade2528c6769af666bc84c25e3caa1ca3`, Vuoro contracts `ff5b468a4c977dc098aa1395bbe70f283fdae2c3`, and Appservice native309 `04119cd0c5edfd92eeb839ce78d43dc313bb3a0d`.

## Exact integration candidates

The hashes below identify the integrated code trees before this evidence-only update. All branches are local and clean.

| Repository | Local branch | Code commit | Code tree |
| --- | --- | --- | --- |
| Vuoro | `cloud/20261024/programme-08-integration-vuoro-exact` | `b961d2a4c68ae30d6dd126cb2e065a6dafd3678b` | `26a1037b9c5226a20f967c6323da7239eb7d4d9e` |
| Vuoro Cloud | `cloud/20261024/programme-08-integration-vuoro-cloud-exact` | `d2bd1ca899a29bb5df98de9b7bc2bd0c26975494` | `613dd1e3963b8a26a38a82a2561faa29688c6306` |
| Sprintctl | `cloud/20261024/programme-08-integration-sprintctl` | `86a6131e4e7b8cd03d0fa7e8897bf59dab1ccd77` | `cb25e4d7e159e9c35b14285db3ec9ef80865e6ec` |
| AgentOps | `cloud/20261024/programme-08-integration-agentops-exact` | `25aa124badfd610f23775538c79220f60160d0db` | `9331503cd351fb462f17f51f1372b4f550f4f391` |
| Appservice | `cloud/20261024/programme-08-integration-appservice-exact` | `67caf54ef5eacbe63401e4cc8ccbd9396e238e73` | `a2aad0282db338b0393c399b240fbea75446f2b5` |
| Sovite | `cloud/20261024/programme-08-integration-sovite-exact` | `eea0ec1c0d50cf76022df42537029201cafd91fe` | `f78db04806dee6f48a93a0d1bce91f4b1b5a21b4` |

## Implemented increments

- **01 Contract foundation:** retained deterministic namespaces and the separate 26-case portability gate. Added an offline installed-wheel test for two generated SDK packages with normal bytecode enabled, resource integrity checks, and tamper rejection. The test exposed a malformed distribution filename for hashed SDK package names; the builder now preserves underscores so pip parses one distribution field. Candidate commit: `60442af910eba5e23e1927cf0fc1b42f34a402ca`, integrated as `b961d2a`.
- **02 Cloud recovery:** selected backup validation requires same-timeline evidence and LSN ordering, while documenting that this does not prove ancestry or WAL continuity. The named backup evidence reader now rejects duplicate JSON keys and non-standard constants before owner/network or security-key activity. Candidate commit: `ce2c82bc96c4d30d982aae671a6ef5de2cff7c67`, integrated as `2bd92fb`.
- **03 Cloud product:** the request TUI handles per-request authorization refusal after a list was loaded; a paged-view fixture was aligned in P08. `workspace list` now reports controller observation current, stale, or unknown using member-authorized `controller_status_at` and `updated_at`; READY requires a current controller observation and converged generations. Its documentation states the exact rule and does not invent a wall-clock freshness window. Producer commits: `3e95f08315cdb4d7e13b2e8b84340274c7f74a25`, `3cdb286f6f7f34d0884c8c532cdb9ea4e29a16cd`; integrated as `4e94de0`, `3249471`, and `d2bd1ca`.
- **04 Requests and continuation:** exact Vuoro and Sprintctl request lifecycle candidates preserve owner state and revision checks. AgentOps screens sensitive aliases before owner calls and has a bounded, private local outbox for explicitly staged and manually delivered `publish` operations. It preserves request/idempotency identity, rejects ambiguous JSON, and accepts only a contract-valid owner acknowledgement. It does not provide automatic native wake, cross-machine synchronization, or owner outage reconciliation. AgentOps integration commits include `0d26901`, `16aa385`, `aa03a1a`, and `25aa124`.
- **05 Sovite:** the candidate includes role-scoped credentials, enrollment rotation/revocation, operator-only controls, transactional actor audit events, and demand reconciliation. Review found inhibited bindings could still report replacement demand; `eea0ec1` now reports `inhibited: true` and suppresses demand while preserving eligible-enrollment count. Certificate issuance remains external to Sovite; CSR renewal and remote-host qualification are not implemented.
- **06 Telemetry:** the preserved native309 normalizer, synthetic mutation fixtures, metadata-only receipt projection, and pinned Alloy acceptance harness remain integrated. Optional owner-run correlation failures fail open without losing an accepted owner response; the response-forwarding assertion now verifies no correlation or private-canary log on that path. Cloud correlation remains synthetic/source-side.
- **07 Retention and whole-application recovery:** ingestion entry points and replay-barrier evidence are documented; a store-specific receipt validator checks supplied evidence without authorizing publication. Duplicate JSON keys are rejected in both receipt and recovery-readiness readers. No supported upstream replay barrier was found; retain quarantine and stopped-serving requirements.
- **08 Integration and review:** exact candidate commits are integrated on isolated local branches. An independent review found duplicate-key ambiguity in P07 receipts; both parsers and regression tests were fixed. A follow-up independent review of the later P01/P02/P03/P05 increments found no concrete defects; its diff check and AST parse passed. That reviewer lacked pytest/SQLAlchemy, while the focused suites listed below were run separately.

## Focused verification

| Area | Check | Result |
| --- | --- | --- |
| Vuoro P01 | `PYTHONPATH=packages/vuoro-contracts/src <cloud-venv>/bin/python -m pytest -q --tb=short packages/vuoro-contracts/tests/test_sdk_wheel_install.py tools/contracts/portable_tests/test_namespace_portability.py` | **28 passed** on the exact integration branch. The two-wheel install uses `pip --no-index --no-deps`; ordinary bytecode is created for Python modules, not bundled data. |
| Vuoro P01 | Ruff on the new installed-wheel test; `py_compile`; `git diff --check` | Passed. Ruff on the pre-existing builder module reports four unchanged issues: non-executable shebang, import ordering, and two broad-catch findings. |
| Vuoro Cloud P02 | `PYTHONPATH=src <cloud-venv>/bin/python -m pytest -q --tb=short tests/test_named_backup_evidence.py` | **27 passed, 2 integration skips** on the exact integration branch. Ruff, `py_compile`, and `git diff --check` passed for the parser change. |
| Vuoro Cloud P02 | `PYTHONPATH=src <cloud-venv>/bin/python -m pytest -q --tb=short tests/test_restore_drill.py` | **287 passed** on the exact recovery candidate before the evidence-parser follow-up. |
| Vuoro Cloud P02 | Schema-coordinate unit/client tests; disposable owner PostgreSQL integration | **106 passed** in the unit/client check; **96 passed** on PostgreSQL 17.10 and **96 passed** on PostgreSQL 16.15 for the exact P08 source. The exact Nix gate remains unrun. |
| Vuoro Cloud P03 | Auth-refusal TUI, paged TUI, and public-site tests | **38 passed** on the exact integration branch. |
| Vuoro Cloud P03 | `tests/test_cli_user.py -k 'explains_only_observed or does_not_present_stale'` | **2 passed**; Ruff, `py_compile`, and `git diff --check` passed. A broader `-k workspace_list` attempt had one unrelated existing login test fail because sandbox policy denied binding the loopback OAuth redirect port; the two new freshness/revocation cases passed. |
| Vuoro Cloud P03 | `tests/test_public_site.py` | **25 passed**. The TUI tests use fake owner responses; the shared hosted view, notifications, and service-backed named-client journey remain unqualified. |
| Sprintctl P04 | Request contract/schema tests and application authority test | **20 passed** in schema/contract tests and **1 passed, 125 deselected** in the application test. |
| Sprintctl P08 | Disposable owner PostgreSQL request tests | **5 passed** on PostgreSQL 17.10 and **5 passed** on PostgreSQL 16.15, covering retry after response loss, workspace isolation, concurrent revision CAS, append-only events, and caller rollback. |
| AgentOps P04 | `python -m unittest scripts.tests.test_operator_requests -v` | **14 passed**; `py_compile` and `git diff --check` passed. |
| Sovite P05 | `tests/test_helper_admin_api.py` and `tests/test_model_authority.py -k HELPER_LIFECYCLE` | **1 passed, 1 PostgreSQL skip** in each focused selection on the exact integration branch. Operator dependency chain, bounded certificate input, sanitized errors, audit events, role eligibility, and inhibited-demand behavior are exercised through SQLite/direct route calls. |
| Sovite P05 | HTTP transport attempt | **Unqualified.** A focused `TestClient` HTTP attempt stalled during the SQLite case and was stopped; a previous ASGI attempt also stalled. No HTTP pass is claimed. PostgreSQL lifecycle variants are skipped because `SOVITE_TEST_POSTGRES_URL` is unset. |
| Appservice P06/P07 | Native309 normalizer, recovery readiness, ingestion review, and replay fixture modules | **32 passed** across the four modules (including 6 readiness, 3 ingestion, and 3 replay tests). The P07 retention-receipt validator separately reported **6 passed**. |
| Appservice P06 | Pinned Alloy synthetic acceptance | **62-case matrix passed** (54 exported, 8 refused) plus seven control/mutation pairs on local image `grafana/alloy@sha256:2aa2099af76c0098d4af7a4d6e48f86cb66dc1a000222ad927a1c67c6542d13f`. Receipt SHA-256: `f864098cd0263dd8e5e8e1f8d63a5ae02c6e3f86b45465c82c6a0561ba781a81`. AgentOps metadata projection matched byte-for-byte; 6 projection tests passed. |

Commands above ran against the indicated local candidate worktrees. `<cloud-venv>` refers to `/workspace/.worktrees/vuoro-cloud-programme-03/.venv`; PostgreSQL checks used disposable local databases only.

## Remaining work and workstation gates

- Cloud dispatch and persistent Goal continuation remain unavailable under the enforced network policy; no task identity, selected remote model, or unattended continuation is claimed.
- P01 still needs the pinned Nix/Python 3.13/Node generation workflow, original 257-case zero-skip production gate, generated-wheel build matrix, clean offline installed-consumer test under the pinned toolchain, and cross-language semantic parity. Nix and mise are absent; required pinned wheels are not cached offline.
- P02 still needs the exact pinned Nix checks and completion of disposable source/clone identity and restore-verification tooling. All field source observations and freshness gates remain workstation-only.
- P03 still needs the shared web view, bounded notifications, current authorized request journey against disposable owner services, versioned install/upgrade/export/rollback tooling, and two-tenant/service-backed checks. The MCP access explanation requires a different token audience and keeps downstream owner permission unknown; the exception projection has no current authorized owner-read adapter. Neither is added to the control CLI.
- P04 still needs supported native publication/outage reconciliation, performed-report verification and idempotent resolution delivery, ordinary continuation/work-link consumers, and the full cross-session disposable-owner race matrix. The local outbox is a manual offline publication aid only.
- P05 still needs external-CA CSR/renewal lifecycle, HTTP transport coverage, PostgreSQL route/lifecycle variants, installed package-integrity coverage, remote-host qualification, and the accepted later S4-S6 and Vuoro receipt-adapter work. Chart and source checks do not establish cluster enforcement or live inference.
- P06 synthetic telemetry does not qualify production sinks, actual service traces, activation, or live owner correlation. Run `mise run validate` and the affected `mise run flux-schema` checks when the pinned toolchain is available.
- P07 has no supported replay barrier in the reviewed source evidence. The candidate does not establish replay prevention, historical deletion completeness, physical erasure, or publication permission. Keep serving stopped or quarantined pending supported upstream evidence and operator review of retained isolated state.
- Cross-repository full compatibility and the exact pinned owner repository gates remain incomplete. No source candidate is a deployed-state observation or terminal owner acceptance.

## Ordered workstation review

1. Restore a qualified Cloud submission and persistent Goal path if remote continuation is required; verify task ID, model, repositories, branches, and continuation evidence.
2. Review the six exact candidate branches and the pending independent follow-up review. Run pinned P01 production/installed-wheel gates and P02 backup/recovery checks.
3. Run P02 and Sprintctl owner suites on pinned PostgreSQL 16; exercise P04 unknown-outcome handling and current/revoked authorization against disposable owners.
4. Run P03 against disposable owner services; complete the shared web/notification and release-impact surface; run P05 HTTP/PostgreSQL and CA-lifecycle gates.
5. Re-run P06 pinned Alloy and telemetry validation on the workstation toolchain. Keep P07 quarantined until a supported replay barrier is evidenced and tested.
6. Review migrations, operator rollback packets, candidate hashes, and all remaining field gates before any separately authorized merge or deployment.

No production, tenant, credential, or retained isolated-state access was used in this implementation pass.
