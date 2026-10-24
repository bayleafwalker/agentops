# Cloud programme candidate integration

Snapshot: 2026-10-24. This is a local source-candidate handback for the eight programmes in `docs/dispatch/programmes/2026-10-24/`. It does not assert that a Cloud implementation session or persistent goal started.

## Dispatch and continuation evidence

No Codex Cloud implementation task was accepted, and no task ID was returned. The prior submission failed before task creation because this environment could not tunnel to `chatgpt.com/backend-api/wham/environments`; the environment status endpoint separately reported a connected environment. The available tools do not expose Codex Cloud task submission or a persistent native Goal create/read/update control. Automatic continuation, remote task identity, and the selected model therefore remain unverified. No model was observed for an accepted task.

The eight programme specifications and worker contract were read from AgentOps candidate `b760494dea018794231e197e71927b12e14efa53`. Work proceeded in isolated local Git worktrees. No main merge, deployment, production access, retention-state access, or credential transfer occurred.

## Producer candidates

| Programme | Exact producer candidate(s) |
| --- | --- |
| 01 Contract foundation | Vuoro `ba3523ba91901ef5e39e32c6f2df13e58c39e616` |
| 02 Cloud recovery | Vuoro Cloud `2b6467f20b1b186c93f7a7987266bfeb56bfba67` |
| 03 Cloud product | Vuoro Cloud `ebae8031368f0974484ef3488cc4f55c5bccc3a7` then `cb7a74b2c3ae049905689e64da85d54762a55d89` |
| 04 Requests and continuation | Vuoro `aa42f8b2d47269893e2a1e4cda9a22b9443f7695`; Sprintctl `0f00448ea085b54bb452d2583e10f626c8ab1cd0`; AgentOps `c48e346962ce4cdc28368230126577d47b483e1b` |
| 05 Sovite | Sovite `d1973b27306414f3d0c69289d4e37e67ec2b15fe` |
| 06 Telemetry | Appservice source `04119cd0c5edfd92eeb839ce78d43dc313bb3a0d` plus acceptance `7fabc910445292eb7dd5acbac636f5fd572ebf43`; AgentOps `b4855f2ed45e05f410148a18e4c32d2e9981ef37` |
| 07 Retention | Appservice `815753595619a1c977f81aea5268ce80e5d2ab48`; AgentOps review base `b760494dea018794231e197e71927b12e14efa53` |

The requested seed refs were verified at startup: Vuoro Cloud `a237bbdade2528c6769af666bc84c25e3caa1ca3`, Vuoro contracts `ff5b468a4c977dc098aa1395bbe70f283fdae2c3`, and Appservice native309 `04119cd0c5edfd92eeb839ce78d43dc313bb3a0d`. These are source references, not evidence of deployed state.

## Selected integration candidates

The selected integration branches preserve exact producer commit ancestry. Initial review branches had equivalent source trees made from copied commits; the exact-lineage branches below were rebuilt as merge commits and checked to have identical source trees to those initial integrations.

| Repository | Local branch | Source integration commit | Source tree |
| --- | --- | --- | --- |
| Vuoro | `cloud/20261024/programme-08-integration-vuoro-exact` | `b47de91a33ed39c9f0d3ee1944c93a619f8991a4` | `2489c03cbd0355a58170c9b3c2361fb573f323e4` |
| Vuoro Cloud | `cloud/20261024/programme-08-integration-vuoro-cloud-exact` | `2daa4450c44a77b06c596d2991b0fc8a13bcdf79` | `ee44d743c81a94397deb27db30d089c3df74790c` |
| AgentOps | `cloud/20261024/programme-08-integration-agentops-exact` | `923f42fa706402e22918931a7abb8801b79fabf1` | `1ec1ae04892b61a69affa60a37d49ba13b856ec8` |
| Appservice | `cloud/20261024/programme-08-integration-appservice-exact` | `17c1ceb4274065574b6b1f32ffbd7d3833ad6d28` | `551bb0fde8c510b019619664145f6919c3aa64e1` |
| Sprintctl | `cloud/20261024/programme-04-requests-continuation` | `0f00448ea085b54bb452d2583e10f626c8ab1cd0` | Producer candidate; no separate P08 changes |
| Sovite | `cloud/20261024/programme-05-sovite` | `d1973b27306414f3d0c69289d4e37e67ec2b15fe` | Producer candidate; no separate P08 changes |

The Vuoro integration contains exact P01 and P04 commits. Vuoro Cloud contains exact P02 and P03 commits plus the TUI coverage repair, recorded on the exact-lineage branch as `2daa4450c44a77b06c596d2991b0fc8a13bcdf79`. AgentOps contains exact P04 and P06 commits. Appservice contains exact P06 source and acceptance commits and the P07 candidate. The separate earlier integration branches remain local and unchanged; the `*-exact` branches are the review targets.

This evidence file is committed as a follow-up on the AgentOps integration branch; it does not change the source tree recorded above.

## Implemented source increments

- Contract foundation added deterministic per-contract SDK namespaces, portable namespace cases, and installed resource-root closure while keeping the published `0.1.0` runtime immutable.
- Cloud recovery added generated schema-coordinate owner routes and typed CLI adapters with exact-byte and lossless integer handling.
- Cloud product added the operator request TUI and workspace readiness projection. The TUI now pages request lists and event histories, probes one item beyond its cap, and labels complete, truncated, and unknown coverage separately. It does not present an incomplete collection as empty.
- Requests and continuation added the durable request lifecycle in Sprintctl, client transport operations, and the AgentOps CLI/MCP bridge.
- Sovite scoped control and operator tokens by runtime role in the worker/native harness composition.
- Telemetry preserved the native309 normalizer candidate, added synthetic mutation fixtures and a metadata-only receipt projection, and added a runnable pinned-Alloy acceptance harness.
- Retention recorded ingestion entry points and the replay-barrier review. No supported replay barrier was established; readiness remains quarantined.

These are source increments, not completion of every ordered queue item in the eight programme specifications.

## Verification

| Candidate | Command or check | Result |
| --- | --- | --- |
| Vuoro P01 | `PYTHONPATH=packages/vuoro-contracts/src /workspace/.worktrees/vuoro-cloud-programme-03/.venv/bin/python -m pytest -q tools/contracts/portable_tests/test_namespace_portability.py` (Python 3.12.14) | 26 passed |
| Vuoro P04 | `PYTHONPATH=packages/vuoro-client/src /workspace/.worktrees/vuoro-cloud-programme-03/.venv/bin/python -m pytest -q packages/vuoro-client/tests/test_operator_request_transport.py` | 1 passed |
| Vuoro Cloud P02 | `PYTHONPATH=src /workspace/.worktrees/vuoro-cloud-programme-03/.venv/bin/python -m pytest -q tests/test_cli_schema_coordinate.py tests/test_schema_coordinate_owner_unit.py` | 106 passed; one Starlette deprecation warning |
| Vuoro Cloud P08 TUI | `PYTHONPATH=/workspace/.worktrees/vuoro-cloud-programme-08/src /workspace/.worktrees/vuoro-cloud-programme-03/.venv/bin/python -m pytest -q tests/test_cli_operator_actions.py` | 12 passed using fake owner pages, including exact-cap probes, truncation, malformed cursors, and UI coverage labels |
| Vuoro Cloud P08 TUI | `/workspace/.worktrees/vuoro-cloud-programme-03/.venv/bin/python -m ruff check src/vuoro_cloud_cli/operator_actions.py tests/test_cli_operator_actions.py`; `python3 -m py_compile src/vuoro_cloud_cli/operator_actions.py`; `git diff --check`; `UV_CACHE_DIR=/tmp/codex-uv-cache uv lock --check --offline` | Passed; lock resolved 42 packages |
| Sprintctl P04 | `.venv/bin/python -m pytest -q tests/test_operator_request_contract.py tests/test_operator_request_schema.py` | 19 passed |
| Sprintctl P04 | `.venv/bin/python -m pytest -q tests/test_work_application.py -k operator_request` | 1 passed, 125 deselected |
| AgentOps P06 | `python -m unittest scripts.tests.test_native309_acceptance_projection -v` | 6 passed |
| Appservice P06/P07 | Four native309 normalizer, recovery-readiness, ingestion-review, and replay-counterexample unittest modules | 32 passed |

The tests were run from their candidate worktrees against the exact source trees identified above. Commands shown with a repository-relative `PYTHONPATH` and test path used the corresponding repository worktree as the working directory.

## Blocked or unqualified gates

- Codex Cloud dispatch and persistent Goal continuation are unavailable in this environment. No task identity, remote model, or unattended 30-hour continuation is claimed.
- P01's original 257-case production gate, exact pinned Nix/Python 3.13/Node toolchain, generated-wheel build, and offline installed-wheel consumer/tamper tests remain unrun. This environment provides Python 3.12.14; Nix and mise are absent, and the pinned `pydantic-core==2.46.4` wheel is not cached offline.
- P02 recovery and P04 request lifecycle require disposable PostgreSQL/HTTP integration, including response-loss-after-commit, CAS, audit rollback, and refusal bookkeeping. No PostgreSQL executables are installed and Docker daemon access is denied, so those gates remain unqualified.
- P03 web view, bounded notifications, named-client journey, and owner-service qualification remain outstanding. The new TUI tests use a fake owner; no service-backed run was possible here.
- P05 Helm render/deployment tests are skipped because Helm is absent. The model-authority test run reached two passes and two skips, then could not bind its local `127.0.0.1` test server in this sandbox. No Helm/chart qualification is claimed.
- P06's actual pinned Alloy image acceptance was not run: the Docker client is installed but the daemon socket returns permission denied. The 32 Appservice tests cover local or synthetic behavior only.
- P07 has no supported upstream replay barrier in the reviewed source evidence. Keep serving components stopped or quarantined; do not infer replay prevention, historical deletion completeness, or production retention qualification.

## Workstation review order

1. Confirm Cloud submission and persistent Goal controls are available; verify the task ID, model, repositories, candidate branches, and continuation evidence if a remote run is required.
2. Review the exact-lineage branches and candidate diffs, then run the pinned P01 production and installed-wheel gates.
3. Run disposable PostgreSQL/HTTP owner suites for P02 and P04, including unknown-outcome and concurrent-CAS cases.
4. Run P03 against a disposable owner and complete the remaining product queue; run P05 Helm and loopback-dependent tests in a qualified test environment.
5. Run P06 against the pinned Alloy image and review its mutation results. Keep P07 quarantined until a supported replay barrier is evidenced and tested.
6. Review migrations, operational rollback packets, and source evidence before any separately authorized main merge or deployment.

No production, retained-state, or tenant data was read or changed during this implementation pass.
