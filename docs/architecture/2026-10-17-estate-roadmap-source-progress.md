# Estate roadmap source delivery and qualification boundaries

This continues the [accepted estate roadmap](../plans/agentops/2026-10-17-estate-evolution-plan.md)
and [initial delivery](2026-10-17-estate-evidence-delivery.md). The operator
requested the full planned scope, excluding actual deployment, and authorized
ready source merges. Source implementation, released artifacts, deployment,
measured qualification and owner acceptance remain separate states.

## Delivery record

The initial source PRs are merged: [Appservice #1917](https://github.com/bayleafwalker/appservice/pull/1917),
[NixOS #25](https://github.com/bayleafwalker/gitops-nixos/pull/25),
[Datacluster #3](https://github.com/bayleafwalker/datacluster/pull/3), and
[Agentops #365](https://github.com/bayleafwalker/agentops/pull/365).
They establish source registers, current host guidance, deployment-helper
refusal fixtures and restricted provider-evidence intake. None establishes
current runtime or successful recovery.

Further merged source delivery:

| Result | Evidence | Remaining outcome gate |
|---|---|---|
| [NixOS #23](https://github.com/bayleafwalker/gitops-nixos/pull/23): adds a disabled-by-default delegated-host handoff gate; current pinned client/profile support remains false and launch remains disabled | Source head `1806be49c9b29a5df42d578b29d91302e60c70ab`; Nix 2.20.6 `flake check` evaluated four configurations and built four checks, including `agentops-delegation-gate`, in an isolated network-disabled Debian container | Owner capability releases, immutable qualification evidence, reviewed pin changes and host qualification are still required before enabling delegation; no host activation was performed |
| [Appservice #1919](https://github.com/bayleafwalker/appservice/pull/1919): exact-source release/image/identity observation comparisons | Register/backup and public-exposure fixtures plus both hosted validation gates | No owner runtime observations supplied; catalog and multi-schema expectations remain unknown |
| [Appservice #1918](https://github.com/bayleafwalker/appservice/pull/1918): timestamped observations with per-field expiry and provenance; unknown/stale/current stay distinct | 55 register/backup tests and 23 public-exposure tests; both hosted gates passed | Authorized owner evidence has not been supplied; report contains zero current observed fields |
| [Scribectl #9](https://github.com/bayleafwalker/scribectl/pull/9): recover interrupted canon → receipt → inbox ratification without duplicate facts or receipts | 195 local tests; copied-fixture interruption regressions and hosted CI | Representative human writing/ratification, concurrent devices and support effort |
| [CV Studio #2](https://github.com/bayleafwalker/cv-studio/pull/2): scripted edit/import/HTML-export, accessible control names and local-request observation | 11 unit tests and Chromium walkthrough; hosted CI | Independent nontechnical user and their private data workflow, not simulated by test fixtures |
| [Aligned Equity #5](https://github.com/bayleafwalker/aligned-equity/pull/5): licensed Finnish issuer identity evidence with lineage and bounded decision view | Ruff, mypy, 176 tests, repository validator and hosted Verify | Rights-qualified governance/financial evidence, comparison, actual decision and follow-up; view stays watch/insufficient evidence |
| [Bindery #12](https://github.com/bayleafwalker/bindery-core/pull/12): subject-specific capture gate explanations and deterministic file-permission refusal fixture | Full Go tests, race suite, vet, redaction and hosted CI | ERH-006 two real Windows/RA2 clients, spawner acceptance and post-restart field reconstruction |
| [Auditctl #23](https://github.com/bayleafwalker/auditctl/pull/23): central schema3 guidance and observation/decision versus current authority boundary | Source/migration comparison and append-only CI | Verified S4 real-manifest rehearsal, import and explicit cutover; historical shards remain original authority |
| [Sprintctl #150](https://github.com/bayleafwalker/sprintctl/pull/150): digest-only, exact-run delegated credentials; one live credential per run; revocation serialized with writes | 2,207 fast tests; 1,045 disposable PostgreSQL tests; all four hosted gates; versioned owner context/result | No production migration or release; consuming service and host qualification remain separate |
| [Sprintctl #151](https://github.com/bayleafwalker/sprintctl/pull/151): protected exact-CWD delegation profile and foreign-owner read-only credential support | Python 3.11/3.12 and PostgreSQL hosted gates | Actual protected host/harness installation remains unqualified |
| [Vuoro #242](https://github.com/bayleafwalker/vuoro/pull/242): refuse draft/unreviewed approval pointers and binary revision text before portable import writes; exclude legacy drafts from reader search | Three counterexamples fail before fix; 100 actual PostgreSQL workspace tests; 2,889 full tests and six hosted gates | Real cross-session artifact use, installed storage/recovery and independent-user acceptance remain open |
| [Vuoro #247](https://github.com/bayleafwalker/vuoro/pull/247): atomically publish child PID in the cancellation test fixture | 20 consecutive cancellation tests, 51 protected-Git tests and six hosted gates | Fixes a test readiness race; no new runtime or authority claim |
| [Vuoro #246](https://github.com/bayleafwalker/vuoro/pull/246): reserved-token fail-closed owner lookup and exact hosted/run scope | 2,911 full tests, six hosted gates and final-owner-source HTTP note retry/revoke proof | Released owner pin unchanged; upstream parent revocation does not cascade to an existing child; no installed qualification |
| [Vuoro #245](https://github.com/bayleafwalker/vuoro/pull/245): candidate pinned composition, lifecycle/removal and identity/policy sourcing boundaries | Three contract tests, knowledge validation and all six hosted gates | Candidate remains unsupported; independent installation, recovery, supplier replacement, cost/support and exact-artifact qualification remain open |
| [Vuoro #243](https://github.com/bayleafwalker/vuoro/pull/243): read-only experiment/outcome summary with explicit policy and capture denominators | 109 evidence tests; 2,912 full tests; all hosted gates | No actual accepted population, preregistration authenticity, causal claim or authority writer |
| [Vuoro #244](https://github.com/bayleafwalker/vuoro/pull/244): preserve actual child Git refusal when stdin closes early | 41 focused and 2,795 default tests; six hosted gates | Runtime qualification remains separate |
| [Vuoro Cloud #8](https://github.com/bayleafwalker/vuoro-cloud/pull/8): loader-compatible profile and endpoint preflight, cross-organization design | 1,878 unit and 863 PostgreSQL integration tests | External bootstrap writer package, independent onboarding and tenant activation remain unavailable/unperformed |
| [Auditctl #24](https://github.com/bayleafwalker/auditctl/pull/24): frozen source preflight and current schema3 verification binding | 194 tests including 10 actual PostgreSQL cases; append-only and installed wheel gates | Historical shard import/cutover and legacy result-format repair remain separate |
| [Agentops #368](https://github.com/bayleafwalker/agentops/pull/368): disabled per-run credential handoff with protected backend marker, token-once crash recovery and revoke-before-settlement | 1,658 script tests and 135 focused adapter tests; four hosted gates; versioned context/result | Source staging only; actual owner/client/harness host integration and power-loss durability remain unknown |

Bindery's normal main CI publishes images; its workflow has no deployment step
and no Appservice workload consumer was found in the inspected source. No
cluster, host, household device, provider resource or public-site deployment was
performed by this delivery. Public-site source changes are retained separately
because their main merges would trigger deployment.

## Full roadmap acceptance map

This is a dependency/evidence map, not a replacement work queue or Sprintctl
completion ledger. Plans remain with their owners. Missing operational access
never justifies manufacturing observations, reservations, accepted outcomes or
item IDs.

| Estate entries | Source delivery and next concrete gate |
|---|---|
| EE-01–EE-05 | Owner registers, observation intake, source policy/deploy guards and current guidance exist. [Appservice #1919](https://github.com/bayleafwalker/appservice/pull/1919) adds exact-source release/image/identity comparisons with ambiguous or stale observations left unknown. Current provider resources/access/billing, runtime/schema/image/identity, coherent restore/RPO/RTO/credential/cleanup evidence, canary rollback, actual retired callers and orphan checks still require authorized owner qualification. |
| EE-06 | Vuoro already has disposable PostgreSQL checkoutless native-settlement and interrupted-caller conformance. Installed hosted → native → protected workflow, a named household result, two sessions and fresh-reader reconstruction still require retained real records. Source conformance is not installed acceptance. |
| EE-07 | Merged [Vuoro #242](https://github.com/bayleafwalker/vuoro/pull/242) repairs portable import publication pointers/encoding and reader draft exclusion. Existing workspace owns versions, original bytes, proposals and publication. Actual cross-session reuse, storage/access/recovery and extension discovery remain owner gates; no Kctl revival or second writable knowledge authority. |
| EE-08 | [Sprintctl #150](https://github.com/bayleafwalker/sprintctl/pull/150) merges owner-stored run-scoped delegated credentials, with exact parent/run binding, closed operation allowlist, bounded expiry, token-once replay and serialized revoke/write checks. [Sprintctl #151](https://github.com/bayleafwalker/sprintctl/pull/151) merges protected exact-CWD profile discovery. Merged [Vuoro #246](https://github.com/bayleafwalker/vuoro/pull/246) supplies the consuming shell; merged [Agentops #368](https://github.com/bayleafwalker/agentops/pull/368) and [NixOS #23](https://github.com/bayleafwalker/gitops-nixos/pull/23) supply crash-safe handoff and disabled host gates; the Nix gate is default-off and cannot qualify against the currently pinned client/profile. Vuoro must still compose the released owner capability; no unqualified source dependency becomes a deployed authority. The shared receiving Unix identity is not token confidentiality between sessions: host qualification must establish actual per-session visibility/CWD boundaries, and copied-token/process identity remains a residual risk. Cross-principal or cross-organization authority remains distinct. |
| EE-09 | Existing evidence/claims/receipts/acceptance distinctions remain. [Auditctl #24](https://github.com/bayleafwalker/auditctl/pull/24) merges read-only source preflight for frozen externally hashed manifests, owner envelopes, bytes, collision/gap and filesystem refusals without importing. S4 still requires complete frozen real inventory, original digest domains/provenance, isolated rehearsal, destination chain/reconciliation, absorb gates and explicit cutover. Telemetry never becomes work authority. |
| EE-10 | Workspace export/import and HostProto conformance are source assets. A selected supplier row must actually be replaced and continued by a fresh participant with unchanged work/artifact/decision semantics. Archived/mock/browser examples do not prove a current native supplier swap. |
| EE-11 | Independent-user setup/work/review/recovery and support/capture/cost denominators are unmeasured. A scripted browser route or agent running its own tests cannot satisfy this gate. |
| EE-12 | Merged [Vuoro #245](https://github.com/bayleafwalker/vuoro/pull/245) records a candidate reference composition, current pins, explicit migration/rollback rules, support boundary and conservative retain-by-default removal procedure; it remains unsupported and unqualified. Installed versions, migrations/rollback, backup/export/diagnostics/removal and independent-user support must still be qualified against exact artifacts. |
| EE-13 | [Vuoro Cloud #8](https://github.com/bayleafwalker/vuoro-cloud/pull/8) merges complete profiles verified against actual Sprintctl/Vuoro loaders and refuses malformed endpoints before token/session consumption; writer/persistence and independent onboarding remain distinct. Public guide corrections are reviewable source PRs but their publication is deployment and remains excluded. |
| EE-14 | Vuoro Cloud #8 cross-organization responsibility/threat-model design covers consent, custody, revocation limits, budgets, data separation, support/incidents and recovery. It leaves the operator's authority-for-other-parties decision explicit and unresolved; it activates no organizations, APIs or grants. |
| EE-15 | Merged Vuoro #245 records the current enforcement boundary, open sourcing questions and requirements for authenticated versus reported identities and copied-token/compromised-host risks. No provider/model self-description is attestation. The existing catalog, repository, owner and protected-effect checks remain; no additional evaluator or SPIFFE/SPIRE component is justified by current evidence, and final selection awaits the concrete reference workflow. |
| EE-16 | [Vuoro #243](https://github.com/bayleafwalker/vuoro/pull/243) implements read-only ExperimentRecord inputs over owner acceptance, RunManifest provenance, explicit case/capture denominators and unknown effort/cost. Reviewer thresholds are explicit inputs; no default policy, superiority, causal attribution or authority expansion. Actual accepted-outcome comparison and sustained household responsibility remain unqualified. |
| EE-17–EE-18 | [Kotiakku #16](https://github.com/bayleafwalker/ha-elisa-kotiakku/pull/16) is merged at `83b91adf`; its read-only contract retains monthly estimates, counters and tariff snapshots. [HLA #24](https://github.com/bayleafwalker/homelab-analytics/pull/24) supplies the bounded closed-month review assessment: 17 focused tests and broad local verification passed, with local Storybook watcher limits explicitly unqualified. Its original hosted `verify-fast` passed but Docker smoke failed on the unavailable upstream MinIO image. Separate [HLA #25](https://github.com/bayleafwalker/homelab-analytics/pull/25) is merged at `15aab487` after all four hosted gates passed: it isolates the smoke project and uses a digest-pinned AMD64 GHCR mirror without changing the default installation image. HLA #24 is rebased to `444eac23` and awaits new CI before merge. The independent mirror does not qualify the unavailable default image. Neither source work establishes current household inputs, bill savings, an actual decision, identity-provider readiness or realized result; authorized owner observations and follow-up remain gates. |
| EE-19 | Bindery capture explanations are improved; ERH-001–005 source prerequisites already exist. ERH-006 is a real field run, not another invented simulator or redundant checklist. |
| EE-20 | Frontier FW-0101 automated evidence is explicit. Physical-device and comfort observation remains required before expanding into FW-0102 gameplay. No fabricated comfort score or unqualified slice was added. |
| EE-21 | The Finnish PRH YTJ licensed issuer case supports identity/activity only. The decision view preserves uncertainty and unavailable financial/governance evidence; decision impact stays unmeasured. |
| EE-22 | All named entries are assessed below, including bounded experiments and unresolved content; Rack-parts source is accessible and was qualified separately. No unrelated personal archives were inspected. |
| EE-23 | Learning/source reports expose some denominators and unknown measures. Actual elapsed-to-acceptance, admin/recovery/re-explanation time, provider/storage/egress cost, independent usage and support burden remain unmeasured. Agent tokens, CI counts and configured services are not substitutes. |

## Workspace extension and stewardship requirements

Vuoro product plan C2 remains planned work. Its requirements gates cannot be
filled with invented customer demand. The existing export/import repair does
not imply these extensions are implemented or selected.

| Planned extension | Exact unresolved input and next qualification |
|---|---|
| Approved Git export | Identify the pilot repository-review consumer and export format; then prove stable IDs, versions, relations and approved-only one-way projection. |
| GitHub source ingestion | Inventory selected canonical repositories and permission owners; prove revision/permission refresh and revocation without default whole-repository ingestion. |
| Managed Forgejo adapter | Establish native Git/self-hosting need and operating owner; choose against GitHub using that requirement, then qualify identity mapping, upgrade and restore. No duplicate forge adapter is selected speculatively. |
| Slide/spreadsheet extraction | Supply representative retrieval misses and required slide/sheet/cell anchors; qualify extraction failures, citations and original-byte retrieval. |
| Semantic retrieval | Supply the representative keyword baseline and classified corpus/extraction misses; compare top-k results on the same access-filtered corpus with latency/cost bounds. |
| Review reminders | Name the knowledge owner, useful source-change/staleness signal and acceptable frequency; qualify bounded affected-record notices without automatic publication changes. |
| Item-specific permissions | Map actual audiences against workspace roles; revisit the threat model and test reads, snippets, caches, relations, downloads, exports and feeds before accepting affected material. |
| Live collaborative editing | Measure real proposal/conflict/handoff cost; define concurrency, attribution and recovery only if immutable proposals do not meet that requirement. |

Sustained commitments (product plan H / EE-16) also retain their concrete gate:
select a continuing HLA responsibility and owner, retain its assumptions and
bounded affected decisions in the existing domain/project record, name the
observation that triggers review and how the user amends/stops the responsibility,
and measure intervention and consequence. No new generic commitment authority is
introduced before repeat-use evidence shows value beyond that existing record.

## Smaller tools and experiments

| Entry | Source finding and disposition gate |
|---|---|
| EE-22a Scribectl | Recovery source merged in #9. Human canon authority remains explicit; no automatic ratification. A representative project and actual writer recovery remain qualification. |
| EE-22b CV Studio | Browser qualification merged in #2; copied fixture only. Independent nontechnical use remains required. |
| EE-22c Public guides | [Kotona #27](https://github.com/bayleafwalker/kotona.app/pull/27), [Agentops #366](https://github.com/bayleafwalker/agentops/pull/366) and [#367](https://github.com/bayleafwalker/agentops/pull/367) remain unmerged because publication follows main. Kotona source tests/build passed; unrelated household page freshness is overdue and its date was not advanced. Scoped exact-name repository discovery found no separate Operator's Atlas repository. Kotona's existing `/explore/` page and `KnowledgeMap.astro` call themselves a curated knowledge atlas of published notes/projects; this is the nearest source match, not evidence of a distinct Operator's Atlas product or domain/mail-policy access. |
| EE-22d HostProto / Browser Workbench | HostProto's archived spec validator passed 166 checks. Browser source/mock/Python/Chrome checks pass, but [Browser Workbench #2](https://github.com/bayleafwalker/browser-workbench/pull/2) records 102 archive checksum mismatches and absent current native qualification. Native WebKit/Servo/Playwright toolchains and a real workflow/swap remain gates. |
| EE-22e Acceptance Lab / Counterfactual Ops | Scoped owner source is confirmed: [Counterfactual Ops](https://github.com/bayleafwalker/counterfactual-ops/tree/c47f148ff449cbe2088a92f4ed7e848627eb8492) at `c47f148`. Its 39 unit/web tests passed (loopback permission enabled), `scripts/check_evidence.py --history` verified 16 source events, `--base HEAD^` passed, and `scripts/evaluate.py` reproduced 13 automated worker result records with paired control/intervention observations: split-write and exact-retention-boundary counterexamples, atomic bounded support, related-decision reuse without another run, and changed-version reassessment. This is not a participant comparison; human effort/maintenance/value remain null/unmeasured. Acceptance Lab's 56 tests and schema/demo validation passed. It scores recorded candidate observations against versioned acceptance checks; Counterfactual Ops runs decision-relevant retry experiments and tracks exact applicability/reuse/withdrawal. Both preserve evidence, but have distinct contracts and no real Vuoro/HLA accepted-outcome consumer here. Keep them separate and experiment-only. Next gate: a domain owner nominates an actual accepted Vuoro or HLA outcome/source and competent ordinary comparator, then a preregistered paired use measures decision errors and active investigation/maintenance burden. No real outcome or participant was available; no adoption/integration/retirement decision or source change is justified yet. Acceptance Lab's two-real-consumer extraction gate also remains unmet. Earlier app discovery was incomplete, not proof of absent source. |
| EE-22f FlowLab | Three tests, campaign reproduction and baseline comparison pass. Available campaign has two sanitized measurable sessions (demo three), below the ten-session gate. No extra sessions were invented and no adopt/retire decision inferred. |
| EE-22g Box/templates | Exact public Box scaffold's fast gate passes (Ruff, mypy, five tests, contracts/scenarios/Compose). No implemented service/simulator consumer or actual reconciliation exists. A concrete workload and owner reuse/merge/retire decision remain required. |
| EE-22h Rack-parts | [Rack-parts #1](https://github.com/bayleafwalker/rack-parts/pull/1) is merged (source-only guide/CLI correction; no repository workflows/deployment trigger). Rebuilt STEP exports matched the 18 current tracked counterparts by imported B-rep volume, bounding box, solid/face/edge counts; arithmetic validation also passes. Repository contains no print, slicer, assembly, physical fit/load, or tolerance-measurement evidence; source comments' 1.5 mm shelf and 12 mm setback measurements lack provenance. Keep physical fit/load unqualified until actual evidence is supplied. |
| EE-22i q-spec | The exact named Git repository advertises no HEAD, branch or tag; a historical host-local bundle hash/review reference is not available content or a disposition decision. [ActionQ Dispatch #5](https://github.com/bayleafwalker/actionq-dispatch/pull/5) removes misleading live sibling-source guidance. Purpose/publication remains with its owner. |
| EE-22j Retired lineage | Agentops source confirms the cockpit is deleted and the dispatcher is fail-closed; its dispatch-manifest note labels the old API historical. Outctl source README and 2026-08-16 decision mark the product killed/frozen for maintenance, and `outctl.dispatch.json` is absent (removed at `e743e16`). No current dispatcher/cockpit source caller was found in Outctl; [Outctl #7](https://github.com/bayleafwalker/outctl/pull/7) removes its stale CI check for the deleted manifest. Host/systemd/package callers and deployed residue remain unknown; this source review does not reactivate retired components. |

## Verification limits and handoff

Some local tools required isolated setup: PostgreSQL16 fixture tools, Nix2.20.6,
Kustomize and project environments. No production credential was used. Exact
owner PRs carry commands, failures and fixture limits; hosted checks are checked
at their source heads before source merges. Baseline failures discovered by
broader testing are repaired separately rather than hidden as passing tests.
The dedicated loopback-only PostgreSQL fixture and its anonymous Docker volume
were removed after the exact-owner service proof completed; retained source
packets carry the result, not a dependency on a running test database.

Live Sprintctl profiles/credentials are unavailable in this workspace. Existing
owner items and reservations must be reconciled through their real authority
before scheduling deployment or closing outcomes. The present source work does
not fabricate a parallel writable tracking ledger or waive any acceptance gate.
