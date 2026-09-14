# P0 retrospective replay

- Window: 2026-07-15T00:00:00Z → 2026-09-14T00:00:00Z (appservice origin/main db97f32c)
- Registry: `operator-projection/registry/v1-p0`; ground truth committed at `a7d3e2cb`, replay code at `1abb92bb`
- Image tag map: ghcr.io/v2/bayleafwalker/vuoro-service, evaluated 2026-09-14T14:34:20+00:00
- Replayed at 2026-09-14T14:39:54+00:00; window base commit `723e5ae2`
- Run note: run 2: evaluator fixed after run 1 (all-caps audience placeholders; a provider-wide Forgejo audience covers only the repositories registered when its value was set). Post-hoc for the credbroker.binding belief rows, so not independent evidence for them; ground truth unchanged since a7d3e2c.

## Gate: PASS

Recall **0.986** (gate 0.9), precision **1.000** (gate 0.8) over 139 expected and 137 produced move groups.

| vocabulary | expected | produced | recall | precision |
|---|---|---|---|---|
| audit.record_class | 1 | 1 | 1.00 | 1.00 |
| authority.service_release | 59 | 59 | 1.00 | 1.00 |
| composition.release_lock | 48 | 48 | 1.00 | 1.00 |
| credbroker.binding | 18 | 16 | 0.89 | 1.00 |
| credbroker.capability_rule | 5 | 5 | 1.00 | 1.00 |
| credbroker.repository | 6 | 6 | 1.00 | 1.00 |
| durability.store | 2 | 2 | 1.00 | 1.00 |

### Misses: expected, not produced (2)

- `8feff32e` credbroker.binding REGRESSED
- `d2dbccac` credbroker.binding GAINED

### False positives: produced, not expected (0)

- none

### Member disagreements in matched groups (0)

- none

## Questions P0 was asked to resolve

- sprintctl 0.3.0 reached the deployed composition at `32e40991` (2026-08-15).

## Substrate ledger

- 91 boundary commits touched registry sources; 15 moved no enumerated member.
- Undetermined evaluations: 0

## Hazards at window end (present state, not scored)

- DECLARED-UNREACHABLE audit.record_class `decision`
- DECLARED-UNREACHABLE credbroker.binding `workstation|repo_wizard_valley_world_window_forgejo|repo.read`
- DECLARED-UNREACHABLE credbroker.binding `workstation|repo_wizard_valley_world_window_forgejo|repo.write`
- DIVERGED release label at `5bbfe68a`: label vuoro-service-v0.1.52, digest is vuoro-service-v0.1.54
- DIVERGED release label at `2ffa40b2`: label vuoro-service-v0.1.52, digest is vuoro-service-v0.1.54
- DIVERGED release label at `b5aa7870`: label vuoro-service-v0.1.52, digest is vuoro-service-v0.1.55

## Coverage gaps

- `catalog.operation`: membership is the live catalog; no catalog history is stored (composition history is D0)
- `catalog.authority`: derived from the live catalog's required_authority values

## Move list (244 member moves)

| boundary | date | vocabulary | class | members |
|---|---|---|---|---|
| `8908ef43` | 2026-07-19T12:22 | durability.store | DURABILITY-UP | cockpit.reconciliation-state (D2) |
| `6095929f` | 2026-07-22T21:03 | authority.service_release | GAINED | vuoro-shared (vuoro-service-v0.1.0) |
| `6095929f` | 2026-07-22T21:03 | composition.release_lock | GAINED | audit-adapter (0.1.0), execution-adapter (0.1.1), knowledge-adapter (0.1.0), work-adapter (0.2.0) |
| `6095929f` | 2026-07-22T21:03 | audit.record_class | GAINED | observation |
| `3904377b` | 2026-07-22T21:31 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.1) |
| `26684259` | 2026-07-24T14:13 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.2) |
| `26684259` | 2026-07-24T14:13 | composition.release_lock | CONTRACT-CHANGE | work-adapter (0.2.0) |
| `b388b7a3` | 2026-07-24T19:20 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.4) |
| `b388b7a3` | 2026-07-24T19:20 | composition.release_lock | CONTRACT-CHANGE | work-adapter (0.2.0) |
| `ba841bd5` | 2026-07-26T11:16 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.5) |
| `ba841bd5` | 2026-07-26T11:16 | composition.release_lock | CONTRACT-CHANGE | work-adapter (0.2.0) |
| `38639362` | 2026-07-26T14:44 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.6) |
| `38639362` | 2026-07-26T14:44 | composition.release_lock | CONTRACT-CHANGE | knowledge-adapter (0.1.0), work-adapter (0.2.0) |
| `b8bdae08` | 2026-07-26T14:54 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.7) |
| `b8bdae08` | 2026-07-26T14:54 | composition.release_lock | CONTRACT-CHANGE | work-adapter (0.2.0) |
| `a3658bbd` | 2026-07-26T15:01 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.8) |
| `a3658bbd` | 2026-07-26T15:01 | composition.release_lock | CONTRACT-CHANGE | work-adapter (0.2.0) |
| `8e4d00a7` | 2026-07-26T15:21 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.9) |
| `6269a2fc` | 2026-07-26T18:06 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.10) |
| `6269a2fc` | 2026-07-26T18:06 | composition.release_lock | CONTRACT-CHANGE | execution-adapter (0.1.1) |
| `6bb6261b` | 2026-07-26T19:22 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.11) |
| `6bb6261b` | 2026-07-26T19:22 | composition.release_lock | CONTRACT-CHANGE | execution-adapter (0.1.1) |
| `74a283c8` | 2026-07-26T20:56 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.12) |
| `74a283c8` | 2026-07-26T20:56 | composition.release_lock | CONTRACT-CHANGE | work-adapter (0.2.1) |
| `7090a1ea` | 2026-07-26T21:14 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.13) |
| `7090a1ea` | 2026-07-26T21:14 | composition.release_lock | CONTRACT-CHANGE | work-adapter (0.2.2) |
| `a020dfcb` | 2026-07-26T22:03 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.14) |
| `a020dfcb` | 2026-07-26T22:03 | composition.release_lock | CONTRACT-CHANGE | execution-adapter (0.1.2) |
| `1030186b` | 2026-07-26T23:46 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.15) |
| `1030186b` | 2026-07-26T23:46 | composition.release_lock | CONTRACT-CHANGE | work-adapter (0.2.2) |
| `718e568c` | 2026-07-26T23:57 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.16) |
| `718e568c` | 2026-07-26T23:57 | composition.release_lock | CONTRACT-CHANGE | work-adapter (0.2.2) |
| `ebded55a` | 2026-07-27T00:02 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.17) |
| `ebded55a` | 2026-07-27T00:02 | composition.release_lock | CONTRACT-CHANGE | work-adapter (0.2.2) |
| `cf973c58` | 2026-07-28T11:05 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.18) |
| `cf973c58` | 2026-07-28T11:05 | composition.release_lock | CONTRACT-CHANGE | work-adapter (0.2.3) |
| `f3173502` | 2026-07-28T12:03 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.19) |
| `f3173502` | 2026-07-28T12:03 | composition.release_lock | CONTRACT-CHANGE | work-adapter (0.2.4) |
| `0a1de38e` | 2026-07-28T12:25 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.20) |
| `0a1de38e` | 2026-07-28T12:25 | composition.release_lock | CONTRACT-CHANGE | work-adapter (0.2.5) |
| `14182a53` | 2026-07-28T12:40 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.21) |
| `14182a53` | 2026-07-28T12:40 | composition.release_lock | CONTRACT-CHANGE | work-adapter (0.2.6) |
| `d4f66e80` | 2026-07-28T18:11 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.22) |
| `d4f66e80` | 2026-07-28T18:11 | composition.release_lock | CONTRACT-CHANGE | work-adapter (0.2.10) |
| `c96c47a0` | 2026-07-29T09:30 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.23) |
| `c96c47a0` | 2026-07-29T09:30 | composition.release_lock | CONTRACT-CHANGE | execution-adapter (0.1.3) |
| `fc095c73` | 2026-07-29T09:44 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.24) |
| `fc095c73` | 2026-07-29T09:44 | composition.release_lock | CONTRACT-CHANGE | knowledge-adapter (0.1.1) |
| `3d37cc71` | 2026-07-29T11:16 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.25) |
| `3d37cc71` | 2026-07-29T11:16 | composition.release_lock | CONTRACT-CHANGE | execution-adapter (0.1.4) |
| `ccf5107f` | 2026-07-29T19:04 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.26) |
| `ccf5107f` | 2026-07-29T19:04 | composition.release_lock | CONTRACT-CHANGE | execution-adapter (0.1.6) |
| `4e19d094` | 2026-07-30T08:43 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.28) |
| `4e19d094` | 2026-07-30T08:43 | composition.release_lock | CONTRACT-CHANGE | execution-adapter (0.1.7), work-adapter (0.2.11) |
| `620da523` | 2026-07-30T14:34 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.29) |
| `620da523` | 2026-07-30T14:34 | composition.release_lock | CONTRACT-CHANGE | work-adapter (0.2.11) |
| `d24a087b` | 2026-07-30T16:48 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.30) |
| `d24a087b` | 2026-07-30T16:48 | composition.release_lock | CONTRACT-CHANGE | work-adapter (0.2.11) |
| `b78796c5` | 2026-08-02T15:24 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.31) |
| `b78796c5` | 2026-08-02T15:24 | composition.release_lock | CONTRACT-CHANGE | execution-adapter (0.1.14), work-adapter (0.2.12) |
| `747d9b9b` | 2026-08-02T15:38 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.30) |
| `747d9b9b` | 2026-08-02T15:38 | composition.release_lock | CONTRACT-CHANGE | execution-adapter (0.1.7), work-adapter (0.2.11) |
| `172bc740` | 2026-08-02T21:12 | authority.service_release | REGRESSED | vuoro-shared (vuoro-service-v0.1.30) |
| `2265f0d5` | 2026-08-02T21:38 | authority.service_release | GAINED | vuoro-shared (vuoro-service-v0.1.30) |
| `59ce886e` | 2026-08-03T01:34 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.33) |
| `59ce886e` | 2026-08-03T01:34 | composition.release_lock | CONTRACT-CHANGE | execution-adapter (0.1.14), work-adapter (0.2.15) |
| `9fa861b7` | 2026-08-03T01:41 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.30) |
| `9fa861b7` | 2026-08-03T01:41 | composition.release_lock | CONTRACT-CHANGE | execution-adapter (0.1.7), work-adapter (0.2.11) |
| `f03a48e2` | 2026-08-04T13:39 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.35) |
| `f03a48e2` | 2026-08-04T13:39 | composition.release_lock | CONTRACT-CHANGE | execution-adapter (0.1.16), work-adapter (0.2.17) |
| `6287d20f` | 2026-08-08T15:27 | authority.service_release | REGRESSED | vuoro-shared (vuoro-service-v0.1.35) |
| `1722c61a` | 2026-08-08T19:47 | authority.service_release | GAINED | vuoro-shared (vuoro-service-v0.1.35) |
| `b761d24e` | 2026-08-08T23:16 | authority.service_release | REGRESSED | vuoro-shared (vuoro-service-v0.1.40) |
| `b761d24e` | 2026-08-08T23:16 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.40) |
| `b761d24e` | 2026-08-08T23:16 | composition.release_lock | CONTRACT-CHANGE | execution-adapter (0.1.18), work-adapter (0.2.21) |
| `b761d24e` | 2026-08-08T23:16 | composition.release_lock | GAINED | execution-contracts (0.1.1) |
| `83325c39` | 2026-08-09T10:23 | authority.service_release | GAINED | vuoro-shared (vuoro-service-v0.1.40) |
| `16258d58` | 2026-08-09T12:26 | authority.service_release | REGRESSED | vuoro-shared (vuoro-service-v0.1.40) |
| `1f7618f4` | 2026-08-09T13:23 | authority.service_release | GAINED | vuoro-shared (vuoro-service-v0.1.40) |
| `0863591b` | 2026-08-11T16:17 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.41) |
| `0863591b` | 2026-08-11T16:17 | composition.release_lock | CONTRACT-CHANGE | audit-adapter (0.1.0), execution-adapter (0.1.19), execution-contracts (0.1.1), work-adapter (0.2.22) |
| `d295387f` | 2026-08-11T17:52 | credbroker.capability_rule | GAINED | repo.read |
| `d295387f` | 2026-08-11T17:52 | credbroker.repository | GAINED | repo_cred_broker |
| `d295387f` | 2026-08-11T17:52 | durability.store | DURABILITY-UP | credbroker.receipts (D2) |
| `a4180bb6` | 2026-08-11T20:34 | credbroker.repository | GAINED | repo_cred_broker_github |
| `a4180bb6` | 2026-08-11T20:34 | credbroker.binding | GAINED | devbox|repo_cred_broker_github|repo.read |
| `faa226f8` | 2026-08-11T20:37 | credbroker.repository | FORECLOSED | repo_cred_broker_github |
| `faa226f8` | 2026-08-11T20:37 | credbroker.binding | FORECLOSED | devbox|repo_cred_broker_github|repo.read |
| `fd4d53bd` | 2026-08-11T20:43 | credbroker.repository | GAINED | repo_cred_broker_github |
| `fd4d53bd` | 2026-08-11T20:43 | credbroker.binding | GAINED | devbox|repo_cred_broker_github|repo.read |
| `a746760a` | 2026-08-11T21:15 | credbroker.capability_rule | GAINED | repo.write |
| `a746760a` | 2026-08-11T21:15 | credbroker.binding | GAINED | devbox|repo_cred_broker_github|repo.write |
| `33267e48` | 2026-08-11T21:24 | credbroker.capability_rule | GAINED | pr.manage |
| `33267e48` | 2026-08-11T21:24 | credbroker.binding | GAINED | devbox|repo_cred_broker_github|pr.manage |
| `d984d364` | 2026-08-11T22:12 | credbroker.binding | GAINED | workstation|repo_cred_broker_github|pr.manage, workstation|repo_cred_broker_github|repo.read, workstation|repo_cred_broker_github|repo.write |
| `34fffc5c` | 2026-08-11T23:08 | credbroker.binding | GAINED | devbox|repo_cred_broker|repo.read |
| `bce70254` | 2026-08-11T23:18 | credbroker.capability_rule | CONTRACT-CHANGE | repo.write |
| `bce70254` | 2026-08-11T23:18 | credbroker.binding | FORECLOSED | devbox|repo_cred_broker|repo.read |
| `bce70254` | 2026-08-11T23:18 | credbroker.binding | GAINED | workstation|repo_cred_broker|repo.read, workstation|repo_cred_broker|repo.write |
| `1cc1659b` | 2026-08-11T23:40 | credbroker.binding | REGRESSED | workstation|repo_cred_broker_github|pr.manage, workstation|repo_cred_broker_github|repo.read, workstation|repo_cred_broker_github|repo.write, workstation|repo_cred_broker|repo.read, +1 more |
| `80f63ef5` | 2026-08-11T23:42 | credbroker.binding | GAINED | workstation|repo_cred_broker_github|pr.manage, workstation|repo_cred_broker_github|repo.read, workstation|repo_cred_broker_github|repo.write, workstation|repo_cred_broker|repo.read, +1 more |
| `a9b08b39` | 2026-08-13T15:24 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.44) |
| `a9b08b39` | 2026-08-13T15:24 | composition.release_lock | CONTRACT-CHANGE | knowledge-adapter (0.1.2) |
| `a9b08b39` | 2026-08-13T15:24 | composition.release_lock | GAINED | vuoro-adapter-kit (0.1.0) |
| `2d8d8688` | 2026-08-13T21:23 | authority.service_release | REGRESSED | vuoro-shared (vuoro-service-v0.1.44) |
| `e9511adf` | 2026-08-13T21:54 | authority.service_release | GAINED | vuoro-shared (vuoro-service-v0.1.45) |
| `e9511adf` | 2026-08-13T21:54 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.45) |
| `e9511adf` | 2026-08-13T21:54 | composition.release_lock | CONTRACT-CHANGE | audit-adapter (0.1.1), execution-adapter (0.1.21), work-adapter (0.2.24) |
| `352b32f2` | 2026-08-14T08:03 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.46) |
| `352b32f2` | 2026-08-14T08:03 | composition.release_lock | CONTRACT-CHANGE | audit-adapter (0.1.2), execution-adapter (0.1.22), knowledge-adapter (0.1.3) |
| `352b32f2` | 2026-08-14T08:03 | composition.release_lock | GAINED | vuoro-schema-runtime (0.1.0) |
| `e8ede5e8` | 2026-08-15T15:44 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.51) |
| `e8ede5e8` | 2026-08-15T15:44 | composition.release_lock | CONTRACT-CHANGE | execution-adapter (0.1.26) |
| `32e40991` | 2026-08-15T23:36 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.52) |
| `32e40991` | 2026-08-15T23:36 | composition.release_lock | CONTRACT-CHANGE | work-adapter (0.3.0) |
| `5bbfe68a` | 2026-08-28T21:32 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.54) |
| `5bbfe68a` | 2026-08-28T21:32 | composition.release_lock | CONTRACT-CHANGE | execution-adapter (0.1.27), vuoro-adapter-kit (0.1.1), work-adapter (0.3.3) |
| `b5aa7870` | 2026-08-29T10:27 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.55) |
| `b5aa7870` | 2026-08-29T10:27 | composition.release_lock | CONTRACT-CHANGE | work-adapter (0.3.4) |
| `8f534f93` | 2026-08-29T14:58 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.56) |
| `8f534f93` | 2026-08-29T14:58 | composition.release_lock | CONTRACT-CHANGE | work-adapter (0.3.5) |
| `efcc21db` | 2026-08-29T15:51 | credbroker.repository | GAINED | repo_acceptance_lab_github, repo_actionq_github, repo_agentops_github, repo_aligned_equity_github, +11 more |
| `efcc21db` | 2026-08-29T15:51 | credbroker.binding | GAINED | workstation|repo_acceptance_lab_github|pr.manage, workstation|repo_acceptance_lab_github|repo.read, workstation|repo_acceptance_lab_github|repo.write, workstation|repo_actionq_github|pr.manage, +41 more |
| `722ddf60` | 2026-08-29T18:00 | credbroker.repository | GAINED | repo_frontier_weave_forgejo, repo_gitops_nixos_forgejo, repo_knowledge_base_forgejo, repo_litany_forgejo, +4 more |
| `1e47ede4` | 2026-08-29T18:12 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.57) |
| `1e47ede4` | 2026-08-29T18:12 | composition.release_lock | CONTRACT-CHANGE | audit-adapter (0.1.3) |
| `457699ff` | 2026-08-29T20:22 | credbroker.binding | GAINED | workstation|repo_vuoro_cloud_forgejo|repo.read, workstation|repo_vuoro_cloud_forgejo|repo.write |
| `e6467e54` | 2026-08-29T20:28 | credbroker.binding | GAINED | workstation|repo_gitops_nixos_forgejo|repo.read, workstation|repo_gitops_nixos_forgejo|repo.write |
| `5f6f4c74` | 2026-08-29T21:46 | credbroker.binding | GAINED | workstation|repo_frontier_weave_forgejo|repo.read, workstation|repo_frontier_weave_forgejo|repo.write, workstation|repo_knowledge_base_forgejo|repo.read, workstation|repo_knowledge_base_forgejo|repo.write, +6 more |
| `d6064349` | 2026-08-29T22:25 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.58) |
| `d6064349` | 2026-08-29T22:25 | composition.release_lock | CONTRACT-CHANGE | audit-adapter (0.1.5) |
| `93fe0bb1` | 2026-08-29T23:12 | authority.service_release | CONTRACT-CHANGE | vuoro-shared (vuoro-service-v0.1.59) |
| `93fe0bb1` | 2026-08-29T23:12 | composition.release_lock | CONTRACT-CHANGE | audit-adapter (0.1.6) |
| `dba71e9e` | 2026-09-02T22:00 | authority.service_release | REGRESSED | vuoro-shared (vuoro-service-v0.1.59) |
| `bf6b0c5b` | 2026-09-02T23:07 | authority.service_release | GAINED | vuoro-shared (vuoro-service-v0.1.59) |
| `5f708208` | 2026-09-09T10:06 | credbroker.capability_rule | GAINED | pr.merge |
| `8feff32e` | 2026-09-09T10:26 | credbroker.binding | GAINED | workstation|repo_vuoro_cloud_forgejo|pr.merge |
