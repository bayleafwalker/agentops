# Telemetry, audit, evidence and operator actions: one picture, one inbox

- Date: 2026-09-27
- Status: proposal (planning pass, read-only inventory; nothing here is adopted)
- Scope: how telemetry, reporting, audit events, evidence and "operator required
  actions" flow through agentops, vuoro / sprintctl (vuoro-shared), vuoro-cloud,
  cred-broker and homelab-analytics, and what it takes for the operator to see
  one coherent picture and one action inbox.
- Governing: `docs/plans/2026-09-17-target-state.md` (TS-1, TS-4, TS-5, TS-6,
  TS-7, TS-13, TS-15, TS-16), `docs/plans/2026-09-26-cloud-enablement-plan.md`
  (TS-16 unamended; acceptance only on the trusted side; required-before-slice-1
  items 2 and 10), `docs/plans/agentops/state-event-command-matrix.md`
  (observation / authority command / remote decision).
- Related: agentops PR #253 `docs/plans/2026-09-27-backlog-ideation.md`
  (H1-4 reconstructability metric, H1-7 drift report, H2-3 pending intents,
  H3-2 provenance resolver, H3-3 consumption ledger, H3-5 settlement view).
  This document does not repeat those; §5 says where it leans on them.
- Split-horizon architecture: the operator's direction is that vuoro.cloud
  becomes the primary endpoint for the whole agentic workflow, with
  supplemental vuoro-shared / self-hosted endpoints for horizon-protected
  services. A separate session documents that split; this document refers to
  it as the **split-horizon design** and assumes only its two horizons:
  **public** (vuoro.cloud, api.vuoro.cloud, Hetzner) and **protected**
  (vuoro-shared.apps.kotona.app, appservice, workstation, homelab-analytics).
  No governing document for it exists in any repo yet (checked vuoro-cloud
  origin/main, agentops docs/plans; the nearest material is
  `_artifacts/agentops/session-notes/2026-09-12-vuoro-planning/HANDOFF.md`
  lines 339-346). Where this document's horizon assignment conflicts with the
  split-horizon design when it lands, that design wins.

## 0. Summary

Eleven stores already record agent activity. None of them shares an
identifier with the next one, only two are tamper-evident (the vuoro-evidence
chain and, at the git level, the committed auditctl shards), nothing computes
TS-16's control question, and the operator's action list lives in a scratchpad
markdown file and chat. Alerts go to one email address.

The proposal is: (1) one correlation spine, the server-minted `run_id`, carried
by every store that already has a free field for it; (2) a four-class event
taxonomy (telemetry, audit, evidence, operator action) with one authoritative
home per class and everything else derived; (3) an `operator_action` object in
the work owner, created by agents or systems, closed by a trusted-side
completion receipt that is a Decision-class record; (4) homelab-analytics as
the single reporting consumer, pulling from both horizons and never writing
back; (5) five reports. Fourteen backlog items, none of which duplicates PR
#253 or sprint 559.

## 1. Inventory

Legend for **Integrity**: `A` append-only by convention or API only, `A+` append-only enforced (trigger or CI), `H` hash-chained, `S` signed, `-` none. **Horizon**: `pub` = public vuoro.cloud, `prot` = protected self-hosted, `ws` = workstation/local only.

| # | Source | What it records (schema sketch) | Where it lands | Retention | Integrity | Sensitivity | Current consumers | Horizon |
|---|---|---|---|---|---|---|---|---|
| 1 | **auditctl shards** (`_artifacts/agentops/audit/events-YYYY-MM-DD.ndjson`, `.auditctl/auditctl.db`) | 24 keys: `id, ts, type, actor, source, summary, detail, refs, metadata, created_at, schema_version, record_class, origin_stream_id, origin_seq, event_id, event_type, occurred_at, runtime_session_id, basis_revision, correlation_id, causation_id, payload, payload_sha256, resolved_context`. Types by volume: `dispatch.exit` 2001, `workflow.session` 878, `dispatch.packet.reviewed`, `session.binding`, `dispatch.preflight_rejected`, `workflow.escalation`, `harness.gate`, `model.claim`, `incident`. `correlation_id`/`causation_id` are **null on every hook-written event**. | NDJSON shard per UTC day (locked append + fsync), then SQLite; shards git-tracked in agentops (21 files; 09-23 modified and 09-24..27 uncommitted at inventory time) | none defined (3,047 lines since 2026-07-23) | `A+` at git level only: `scripts/check_append_only_shards.py` (line-prefix check in `protected-paths.yml`); per-event `payload_sha256`; **no prev-hash chain, no signature** | low-medium (session ids, paths, cost) | `auditctl rebuild`, `check_producers.py`, `schema_check.py`, `maintenance_lane_report.py`, `metanarrative.py`; `handoff.py` digest v4 deliberately excludes them | ws (git-tracked to GitHub) |
| 2 | **Session cost log** (`/projects/dev/.claude/session-costs.jsonl`, written by Stop hook `hooks/log-session-cost.sh`) | session_id, tokens in/out, `cost_usd`, `handed_off_to`; also published as a cumulative `workflow.session` audit event | jsonl (1 MB), plus source 1 | none | `-` | low | cockpit `apps/web/lib/cockpit/costs.js`; `scripts/cost_per_release.py` (TS-7 derived query) | ws |
| 3 | **Harness evidence OTel** (`scripts/harness_evidence/`, `docs/architecture/harness-evidence-policy.md`, attribute allowlist `schemas/harness-evidence-attributes.schema.json`) | metrics to Prometheus, spans to Langfuse; transcripts by digest only | **nowhere**: `OTEL_EXPORTER_OTLP_ENDPOINT` unset until #2394/#2395/#2398 | n/a | n/a | policy-limited | none | (prot, planned) |
| 4 | **Handoff records** (`docs/dispatch/handoffs/*.vN.json`, `scripts/handoff.py`, handoff/v1) | `handoff_id, version, created_at, origin_host/path/cwd, track, predecessor, objective, constraints, decisions, rejected, state{repos, digest_version, diff_sha256, tracker_watermark}, unresolved, evidence, sprintctl_bundle_ref, next_action, successor` | git-tracked JSON (93 files) | forever (git) | `-` (validated shape; digests of repo state) | medium: contains operator-action prose, session ids | `hooks/handoff-session-start.sh` (successor prompt), `log-session-cost.sh`, `handoff.py ack/validate` | ws (git) |
| 5 | **Operator action lists** | scratchpad `OPERATOR-ACTIONS.md`, `CLOUD-RUNS.md`, chat messages, the `OPERATOR LIST` line in handoff `state`, `vuoro-cloud/docs/runbooks/operator-actions.md` (prose checklist). Shape by convention: command, checked precondition, expected result, what to send back | `/tmp/claude-1000/.../scratchpad/` (session-scoped), chat | lost with the scratchpad | `-` | **high**: token ids, grant ids, workspace ids, exact privileged commands | the operator, by reading | ws |
| 6 | **sprintctl work schema 17** (`run`, `evidence_item`, `session_note`, `work_idempotency_ledger`; on main since PR #97, v0.8.0) | `run(repo_id, run_id ^run_[ULID]$, principal_id, workspace_id, client_id, grant_id, idempotency_key, request_digest, harness_id, harness_build, model_id, recipe_id, observed_profile, grant_ids, claim_ids, created_at)`; `evidence_item(run_id, item_id, chain_seq, chain_prev_digest, kind, ref, digest, collector, validity, claims, provenance)` UNIQUE(run_id, chain_seq); `session_note(run_id, note_id, note)`; ledger PK `(repo_id, workspace_id, principal_id, tool, idempotency_key)`. **No FK from run to work_item or sprint.** | vuoro-shared-db (CNPG, appservice); served as `work.run.register-v1`, `work.run.resolve-v1`, `work.evidence.append-v1` (409 on chain conflict), `work.evidence.tail-v1`, `work.session-note.write-v1`; reachable from the public edge under `vuoro:evidence.record` (client `claude-connector`, gen 47) | none defined; `evidence_item` and `session_note` **cascade-delete with run** | `H` (vuoro-evidence chain: `entry_digest = sha256{item_id, digest, chain_seq, chain_prev_digest}`); **no immutability trigger, no signature** | medium | nothing reads them yet except the edge tools | prot (served); writes reachable from pub |
| 7 | **sprintctl `event`** (`pg.py:152`) | `repo_id, id, sprint_id, work_item_id, source_type actor/daemon/system, actor, event_type, payload, created_at` | vuoro-shared-db | forever | `A` (documented append-only; **no trigger** — triggers exist only on `ingest_record`, `authority_decision`, `terminal_recovery_*`, `maintenance_*`, `work_decision`) | medium | `sprintctl event list`, `cost_per_release.py --events-json`, kctl extraction | prot |
| 8 | **sprintctl `work_decision`** | `kind accept/reject/withdraw/supersede/revise, work_item_id XOR sprint_id, release_digest, evidence_digests[], rationale, actor, superseded_by_item_id` | vuoro-shared-db | forever | `A+` (trigger) | medium | item lifecycle, TS-5 | prot |
| 9 | **kctl knowledge events** (`knowledge_candidate`, `knowledge_review`, `knowledge_entry`, `knowledge_publication_reference`) | candidate keyed by `source_event_id` (a sprintctl event), `content_digest`, `basis_git_revision`; review `decision, reviewed_by`; publication `document_id, git_revision, digest` | local SQLite + central Postgres | forever | `A` (immutable-identity imports rejected on differing evidence) | low | kctl CLI; TS-13 says fold into Evidence kinds (#2489) | prot |
| 10 | **vuoro-cloud `audit_events`** (`migrations/001_control.sql:173`) | `id ULID, workspace_id?, actor, action, target, request_id, details jsonb, created_at`. ~45 string-literal actions in `control.py`, `gateway.py`, `controller.py`: `auth.session.created`, `oauth.scope.rejected_requested`, `oauth.grant.*`, `tenant.drain.started`, `tenant.migration.*`, `backup.observation.created`, `service.controls.updated`, `token.*`, `membership.*`, `connector.enrolled`, `connector.state.changed`, `tenant.verification.completed`, ... **No enum.** Controller rows use a fresh ULID as `request_id` (uncorrelated). | Postgres in `vuoro-data` (CNPG); backed up with the control DB (D-044 restore drill) | forever (no DELETE); `product_events` 90 d, `rate_limit_buckets` 7 d | `-` (no chain, no signature, no immutability trigger) | medium-high (subjects, grant/token ids; no secrets) | only `GET /api/control/v1/workspaces/{id}/audit-events` (workspace admins); **workspace-less rows are unreadable through any API**; no operator-wide read | pub |
| 11 | **vuoro-cloud product analytics + backup observations** | `GET /operator/product-analytics` (`vuoro-product-analytics/v1`: events by name/path with distinct `visitor_hash`, invite_request counts, abuse buckets); `POST /operator/backup-observations` (`scope, backup_id, status, completed_at, evidence_digest, details`) -> metric `vuoro_backup_observation_age_seconds`; no GET list | control DB | 90 d / forever | `-` | low | operator (bearer + source CIDR), Prometheus | pub |
| 12 | **vuoro-cloud observability** (kube-prometheus-stack 88.3.0, `platform/observability/`) | control + gateway `/metrics` every 30 s (`vuoro_control_http_requests_total`, `vuoro_workspaces`, `vuoro_provisioning_outbox`, `vuoro_gateway_security_events_total{kind}`, per-workspace `vuoro_ws_*`); **tenant runtime not scraped**; 8 PrometheusRules (`BackupStale`, `ProvisioningFailures`, `InviteRequestPending`, `NoBackupObservation`, `AuthenticationRejectionBurst`, `UnexpectedRouteScan`, `RateLimitBurst`, `OperatorPathRejected`) | in-cluster Prometheus; Alertmanager -> receiver `operator-email` only (Scaleway TEM) | Prometheus default | `-` | low | the operator's mailbox | pub |
| 13 | **vuoro-cloud request ids and logs** | `X-Request-ID` ULID minted or echoed by control/gateway middleware, embedded in the signed `X-Vuoro-Identity` assertion (`request_id=`), stored in every control/gateway audit row; gateway `mcp_exchange` log line; access log has `cf_ray` but **not `request_id`**; no traceparent/OTel | pod logs | short (`docs/runbooks/security-observability.md:43` asks for explicit retention) | `-` | medium | kubectl logs | pub |
| 14 | **cred-broker decision receipts** (`src/cred_broker/receipts.py`) | `receipts(sequence, event_id UNIQUE, event_type decision|credential-issued, decision_id, occurred_at, payload_json)`; decision payload `decision_id, outcome, delivery, subject_id, session_id, host_id, project_id, repository_id, capability, provider_authority, ttl_seconds, policy_revision, reason_codes, issued_at, expires_at`; `assert_non_secret` before insert | local SQLite, mode 0600 | none defined | `A` (API only; no trigger, **no signature, no chain, no verifier**) | medium | `list_payloads()` only | prot |
| 15 | **homelab-analytics** | bronze/silver/gold; Postgres control plane (`source_systems, dataset_contracts, ingestion_definitions/runs/issues, publication_audit, auth_audit_events, service_tokens`), DuckDB warehouse (~83 tables); `internal_platform_ingestion.py` already pulls Prometheus queries, Home Assistant states and Kubernetes resource usage | analytics namespace (appservice) | per dataset contract | `-` | household data (high, unrelated) | `/reports`, `apps/web/frontend` (`ingest-summary`, `scenarios`), MCP agent | prot |
| 16 | **Cloud-run billing** | `claude --cloud` sessions (`cse_...`) bill origin `claude_code_cli` bucket `ccr_promotional` (USD 250 credit); Routines (`trig_...`) bill the `five_hour` plan window; verified with `get_session`; tracked only in scratchpad `CLOUD-RUNS.md` | nowhere durable | lost | `-` | low | the operator | (vendor) |

Facts worth restating because the design depends on them:

- **No two stores share an identifier today.** The harness `session_id` is in sources 1, 2, 4; the cloud `cse_` id is in 5 and 16 only; `request_id` is in 10 and 13 only; `run_id` is in 6 only (and no caller has written one yet, per PR #253 §1); the git commit and generation tag are in nothing structured.
- **Tamper-evidence exists only in the vuoro-evidence chain (source 6) and in git history for source 1.** The cloud-enablement plan's required-before-slice-1 item 10 ("insert-only, tamper-evident audit storage") is unmet for sources 7, 10 and 14; `evidence_item` cascade-deletes with its run, which contradicts "append-only with one home" (TS-6).
- **homelab-analytics ingests no agent activity at all**, and its `agent-ops-pilot-consumer-plan.md` explicitly declines to *own* auditctl, actionq or the cockpit. That is the right boundary: it should consume, not own.
- **Operator actions have no system of record.** The convention (command, checked precondition, expected result, what to send back) is good and is already in three places (scratchpad file, handoff `state`, cloud-enablement plan §"Operator actions"), but nothing tracks state, completion or the result the operator sent back.

## 2. Gaps

### 2.1 TS-16 reconstructability: can we compute it today? No.

TS-16: "The control question is what proportion of automated activity is reconstructable; for hosted runtimes today it is zero." To compute a proportion we need a denominator (units of automated activity) and a numerator (units with a resolvable chain). Today:

- Denominator candidates exist but are scattered: local harness sessions (`session.binding` events, 26; `workflow.session`, 878), subagent exits (`dispatch.exit`, 2001), cloud sessions (`cse_` ids in a scratchpad), Routine runs (`trig_` ids), worker leases (in-memory only). None is de-duplicated against another.
- Numerator: zero rows in `run` (E2 landed 2026-09-27 in gen 47; no caller has registered a run). The reconciler that would produce `Vuoro-Run` trailers is tests-only.
- PR #253 H1-4 proposes the hosted-runtime leg (gateway `mcp_exchange` counts and Routine PRs joined to `run`). It does not cover local harness sessions, which are the bulk of activity. §5 item B7 extends it rather than duplicating it.

Answer: not computable today; computable for the hosted leg after H1-3/H1-4; computable for the whole after B1 (spine) and B7.

### 2.2 Correlation IDs across the chain

| Hop | Id today | Carried to the next hop? |
|---|---|---|
| Harness session | Claude Code `session_id` (`session.binding`, `workflow.session`, `session-costs.jsonl`) | to handoff (`successor.session_id`), nowhere else |
| Cloud run | `cse_...` session id, `trig_...` trigger id | only in scratchpad and PR bodies by hand |
| Gateway request | `X-Request-ID` ULID | into the signed assertion and audit rows; **not** into the access log, **not** into anything the runtime stores |
| Runtime tool call | `request_id` from the assertion; `idempotency_key` from the caller | `work_idempotency_ledger` keeps `idempotency_key` + `request_digest`; `request_id` is dropped |
| sprintctl run / evidence | `run_id` (server-minted), `chain_seq` | to nothing: no FK to `work_item`, no field for the session or cloud ids (the `run` row has `harness_id`, `harness_build`, `model_id`, `recipe_id`, `observed_profile`; no `origin_session_id`) |
| sprintctl event / decision | `event.id`, `work_decision.id`, `release_digest` | kctl candidate `source_event_id` |
| git commit / PR | sha, PR number | `Vuoro-Run`/`Vuoro-Intent` trailers designed (reconciler), never produced |
| Release / generation | `v0.1.0-poc.N` signed tag, image digest, `work_decision.release_digest` (always null so far) | nothing |

The audit shard schema already has `correlation_id` and `causation_id`; they are null. The vuoro-cloud audit row has `details jsonb`; nothing puts a run id in it. The fix is therefore mostly *filling existing fields*, not new tables (§3.1).

### 2.3 Operator-required actions have no system of record

Examples from 2026-09-26/27: the YubiKey-signed promotion (`scripts/promote-release.sh <digest> <gen>`, "RUN NOW"), the promote-deployment dispatch, the kotona tenant `PATCH desired_state=READY`, attaching repos to a cloud session on a push 403, merges denied by the classifier (`[External System Writes]`, `[Production Deploy]`), token/grant revocations, marking Forgejo PRs manually-merged, reinstalling sprintctl. Each was written to a scratchpad or said in chat; each closes when the operator pastes the result back into a session, and the session that asked is often not the session that receives the answer. Consequences: actions rot when the scratchpad is discarded; the same action is re-derived by successor sessions (the `OPERATOR LIST` line in handoff v2 is a copy of the file); there is no record that a privileged action *was* taken, by whom, with what result, except where the target system happens to audit it (vuoro-cloud `tenant.drain.started`, `token.revoked`); and nothing computes "open actions" for the operator.

TS-16 matters here: when an operator completes an action that *accepts an effect* (promotion, merge, PATCH), that completion is exactly the trusted-side acceptance record the cloud-enablement plan requires (a separately authenticated actor, never the proposer). Today it is not recorded at all.

### 2.4 Audit tamper-evidence

- auditctl shards: per-event digest and git prefix check only. A writer with the repo can rewrite a shard before commit (four days are uncommitted right now). No chain head is anchored anywhere.
- vuoro-cloud `audit_events`: plain table; a control-plane compromise or DB admin can edit or delete rows silently. Required-before-slice-1 item 10 is unmet.
- sprintctl `event`: documented append-only, no trigger.
- cred-broker receipts: SQLite, no chain, no signature, no verifier; the threat model's INV-005 ("non-secret receipt") holds but a tampered receipt is undetectable.
- vuoro-evidence chain: detects delete/reorder/alter of items within a run; does not detect deletion of the whole run (cascade) and has no signing.

### 2.5 The orphaned-tenant class of incident

Recent state shows the pattern: workspace `isolation-proof` kept alive with test grants after its purpose ended; drill PAT and test grants still valid server-side; `blocker12-canary` on runtime 0.1.52 with legacy LOGIN roles; kotona left on 0.1.74 until an operator PATCH. The general class: a tenant whose control record, runtime pod, grants/tokens, backup observations and work-authority binding disagree, with no owner watching. Today the only signals are `vuoro_ws_*` metrics (no alert), the audit rows for individual actions (workspace-scoped, admin-only), and the operator's memory. PR #253 H1-7 covers runtime-digest drift; the existence/ownership consistency check (§5 B9) is missing, and so is routing its finding into an action the operator will see.

### 2.6 Alerting

- Public horizon: eight PrometheusRules, all to one email receiver; nothing for the tenant runtime (not scraped), nothing for the work authority, nothing for cloud-run failures. No acknowledgement state.
- Protected horizon: the live-session-completion alert architecture (`docs/plans/agentops/live-session-completion-alert-architecture.md`) designs an AgentOps consumer with delivery ledger and acknowledgement "as AgentOps operator state"; D15 proved one delivery path. It is not connected to anything in the public horizon.
- Result: an alert and an operator action are different objects with different lifecycles, when in practice most alerts *are* operator actions ("backup stale: run the observation script").

## 3. Target model

### 3.1 One correlation spine

**The spine is `run_id`**, the server-minted `run_[ULID]` from `work.run.register-v1` (sprintctl schema 17). Reasons: it already exists, it is minted by the trusted side (so a hosted runtime cannot forge one), it is the key of the only tamper-evident evidence store, and TS-16 names the run record as the thing a signed commit must chain back to.

Hop-level ids stay what they are; each is recorded *on the run* or carries the run id:

| Hop | Rule |
|---|---|
| Harness session (local) | `session-binding.sh` calls `work.run.register-v1` at SessionStart (TS-4; #2479 already asks for this) and writes `run_id` into the `session.binding` event, into `correlation_id` of every later hook event of that session, and into `session-costs.jsonl`. Subagents (`dispatch.exit`) set `causation_id` to the parent's `run_id`. |
| Cloud session / Routine | The Routine or `claude --cloud` brief must `register_run` first (PR #253 H1-3); the run's `observed_profile`/`provenance` records `cse_`/`trig_` ids as `origin_session_id`. The PR body carries `Vuoro-Run: <run_id>`. |
| Gateway request | Unchanged (`X-Request-ID`), but the `mcp_exchange` log line and the access log both include `request_id`, and `register_run` audit rows put `run_id` in `details`. The `run` row keeps the registering `request_id` (new nullable column or inside `provenance`). |
| Runtime tool call | `append_evidence` items already carry `run_id`; the idempotency ledger keeps `request_digest`. Add `request_id` to `provenance`. |
| sprintctl event / decision | Events written during a run get `payload.run_id`; `work_decision.evidence_digests` reference evidence items by digest (already the design). Add nullable `run.work_item_id` so a run can be attributed to an item without inventing a new join (today the only bridge is the lane-loop tick window in `cost_per_release.py`). |
| Commit / PR | `Vuoro-Run` (and `Vuoro-Intent` when applicable) trailers; for local agents the same trailer via `prepare-commit-msg` from the session binding. |
| Release / generation | vuoro-cloud promotion records `generation, tag, digest, promoted_by, run_id-of-the-candidate-PR` as an evidence item on the run and as `work_decision.release_digest`. |
| Operator action | `operator_action.created_by_run_id` and the completion receipt's `run_id` of the completing session (if any). |

`handoff_id` remains the cross-session link (predecessor/successor); a handoff records the run ids it closes and opens.

### 3.2 Event taxonomy

Built on the state/event/command matrix classes (observation, authority command, remote decision):

| Class | Definition | Authoritative store | Derived copies | Examples |
|---|---|---|---|---|
| **Telemetry** | Volumetric, sampled or aggregated observations with no per-event obligation; loss is acceptable | Prometheus (pub), OTel/Langfuse (prot, when enabled) | homelab-analytics marts | `vuoro_gateway_security_events_total`, token counts, latency |
| **Audit** | Per-event observations of *who did what to which system*, recorded by the system that performed it; loss is a finding | vuoro-cloud `audit_events` (pub, for public-horizon systems); auditctl shards (ws, for harness/hook activity); cred-broker receipts (prot); sprintctl `event` (prot) | homelab-analytics `agent_activity` bronze copies, with digests | `oauth.grant.revoked`, `dispatch.exit`, credential-issued |
| **Evidence** | Observations a run *claims* about its work, registered on the run and chained; the thing a Decision cites | sprintctl `run`/`evidence_item`/`session_note` (prot, served; writes reachable from pub under `vuoro:evidence.record`) | none (digests may be copied into audit rows) | verdicts, test results, `rate_limit_event`, `operator_action.requested` |
| **Operator action** | An authority command from an agent or system to the operator (request), plus the operator's remote decision (completion receipt). The receipt is a Decision-class record. | sprintctl `operator_action` + `operator_action_receipt` (prot, trigger append-only); requests may also exist as evidence items (the run's own record that it asked) | dashboard/inbox projections (prot first; pub read-only projection is a later option) | promote gen N, PATCH tenant, revoke grant, attach repo |

Rules: a store is authoritative for exactly one class; homelab-analytics is authoritative for nothing agent-related; a derived copy always carries the source's id and digest; telemetry may be dropped, audit and evidence may not; nothing in the public horizon is authoritative for evidence or operator actions.

### 3.3 Where each lives and in which horizon

| Class / object | Horizon | Store | Cross-horizon movement |
|---|---|---|---|
| Public-system audit (`audit_events`), product analytics, backup observations, gateway logs, Prometheus | pub | vuoro-cloud control DB, cluster | **Exported to protected** by a pull job (operator route + operator token, or a signed nightly dump next to the CNPG backup) into homelab-analytics bronze; digests recorded as evidence. Never the other way. |
| Evidence (runs, items, notes), work events, decisions | prot | vuoro-shared-db (served) | Reachable from pub only through the tenant runtime under `vuoro:work.read` / `vuoro:evidence.record` (exists). |
| Harness audit (auditctl), session cost, handoffs | ws -> prot | shards in git; auditctl import into the evidence home is S4 (#2485) | Exported to homelab-analytics bronze from git. |
| cred-broker receipts | prot | broker host SQLite | Exported (non-secret by construction) to homelab-analytics bronze. |
| Operator actions and receipts | prot | sprintctl (served on vuoro-shared) | Requests from hosted runtimes arrive as evidence items (`operator_action.requested`) and are *promoted* into the inbox by a trusted-side process; a read-only projection in the vuoro.cloud dashboard is optional and later (PR #253 H3-5's "safe next actions" panel would read it). |
| Reports and dashboards | prot | homelab-analytics gold + `/reports`; Grafana for public telemetry | The operator reads on the protected side; nothing in a report writes back. |

The public horizon therefore holds *only* the audit of its own systems plus telemetry. That matches TS-16 (evidence may cross out; effects and credentials may not) and keeps the record that matters most, the operator's own decisions, out of the hosted perimeter.

### 3.4 How homelab-analytics consumes and reports

- A new domain `packages/domains/agent_activity/` with sources: `auditctl_shards` (git, NDJSON), `session_costs` (jsonl), `sprintctl_events` and `sprintctl_runs` (served read, `work.*-v1`, own service token), `vuoro_cloud_audit` (operator export), `vuoro_cloud_metrics` (already-existing Prometheus query pipeline, pointed at the public Prometheus through the operator tunnel or a federation endpoint), `cred_broker_receipts`, `operator_actions` (served read). Each source has a dataset contract with `source_id`, `source_digest` and `ingested_at`, in keeping with the bronze layer.
- Silver: one `activity_unit` table (session, cloud session, Routine run, worker lease) keyed by `run_id` where it exists, with `reconstructable` computed as: run row exists AND at least one evidence item AND (a PR/commit with a resolvable trailer OR a Decision citing the run). The unit's `origin_horizon` is recorded.
- Gold marts feed §4. homelab-analytics reads only; it never calls a write operation and holds no token with a write scope.
- The MCP agent (`apps/agent/mcp_server.py`) may answer "what is open for me" from the gold `open_operator_actions` mart, which gives the operator a chat-shaped view without a second inbox.

### 3.5 The operator-action inbox as a first-class object

`operator_action` (sprintctl work schema 18, served; trigger append-only together with its receipts):

```
operator_action
  action_id            oa_[ULID], server-minted
  repo_id, workspace_id?
  kind                 promote_release | dispatch_workflow | tenant_patch | repo_attach |
                       merge_denied | revoke_credential | place_secret | decision |
                       run_command | other
  title                one line
  created_by_run_id    the run that asked (nullable for system creators)
  created_by_actor     principal string (agent, system:alertmanager, system:drift-check)
  required_by          timestamp or null; urgency now|today|week|when_convenient
  precondition         text + precondition_checked_at + precondition_digest
  command              exact command or API call, redacted of secret values
  expected_result      text
  send_back            what the operator should return
  evidence_refs        [ {kind, ref, digest} ]  (the run's evidence items, PR urls, alert ids)
  blocks               [ item_id | run_id ]  (what waits on this)
  state                proposed | acknowledged | done | declined | expired | superseded
  supersedes           action_id?
  created_at

operator_action_receipt   (Decision-class; one per state change; append-only)
  receipt_id, action_id, actor (a trusted-side identity: operator token, credctl),
  decision  acknowledge | done | decline | expire | supersede
  result_text          what was sent back (non-secret), result_digest
  evidence_refs        [ {kind, ref, digest} ]  (audit row ids in the target system,
                       e.g. vuoro-cloud audit id for tenant.drain.started)
  run_id?              the session that recorded the completion, if an agent did
  created_at
```

Lifecycle: an agent (local, via served write) or a hosted runtime (via `append_evidence(kind="operator_action.requested", ...)`, promoted by a trusted-side sweep) or a system (Alertmanager webhook, drift check, classifier denial hook) creates `proposed`. The operator sees one list (`sprintctl action list --open`, the handoff prompt, homelab-analytics `/reports/operator-inbox`, later the vuoro.cloud dashboard read-only). The operator, or an agent acting on the operator's pasted result, records the receipt. The receipt closes the loop back to the agent: `next-work --explain` gains a `completed_operator_actions` bucket listing receipts since the session's last watermark, and `handoff.py ack` refuses to mark an action done without a receipt.

TS-16 treatment: creating an action is a *propose*-class operation and may be reached from the public horizon only through the evidence record scope (no new cloud-callable scope); recording a receipt is a trusted-side authority command that only an operator-bound identity may perform, and for kinds that accept an effect (`promote_release`, `merge_denied`, `tenant_patch`, `decision`) the receipt *is* the acceptance record the cloud-enablement plan requires. It is never automatic, and the proposer identity is rejected as the receipt actor. Auto-accept policies, when they exist (PR #253 H2-4), write the policy id and version as the receipt actor.

Sensitivity: commands are stored with secret *values* redacted (`assert_non_secret`-style check borrowed from cred-broker); ids of tokens and grants are allowed because the target systems audit them anyway.

## 4. Reports and dashboards: the minimal useful set

| Report | Question | Sources (by inventory #) | Where |
|---|---|---|---|
| **Fleet / generation status** | Which generation is live, which candidate is signed, which tenants are on which runtime, which drifted, which are orphan-suspect | 12 (`vuoro_ws_*`), 10 (`tenant.*`, `workspace.*`), promotion evidence items (6), H1-7 drift rows | homelab-analytics gold `fleet_status`; Grafana panel for the live numbers |
| **Reconstructability %** | TS-16's control question, split by horizon (local, cloud session, Routine, worker) and by week | silver `activity_unit` (1, 2, 5/16, 6, PR trailers) | gold `reconstructability_weekly`; the number goes into the weekly lane check-up |
| **Credit burn per cloud run** | Which `cse_`/`trig_` run cost what, on which bucket, and what it produced (PRs, evidence) | 16 via a durable `cloud.run` observation (B8), 6, PR data | gold `cloud_run_cost`; sits beside `cost_per_release.py` output |
| **Open operator actions** | What waits on the operator, ordered by `required_by` and what it blocks; what was completed in the last 7 days with result | `operator_action` (§3.5) | `sprintctl action list`, handoff prompt, `/reports/operator-inbox`, MCP agent |
| **Security events** | Gateway security events by kind, OAuth scope rejections, grant/token create/revoke/reuse-detected, operator-path rejections, cred-broker denials, classifier denials on privileged commands, orphan-suspect tenants | 12, 10, 14, 1 (`harness.gate`, `dispatch.preflight_rejected`) | Grafana (public telemetry, live) + homelab-analytics gold `security_events_daily` (joined across horizons) |

Deliberately not in the minimal set: per-model token dashboards (TS-15 says measure producers before contracts; wait for OTel), per-tenant product analytics (already served by the operator route), and a "cockpit" rewrite.

## 5. Proposed backlog items

Checked against PR #253 (H1-1..H3-8) and sprint 559 pending items (#2394, #2395, #2398, #2428, #2433, #2441, #2472, #2479..#2489, #2492, #2502, #2504, #2513, #2518..#2520). Overlaps are called out; nothing below re-proposes an existing item. Sizes: S (a session), M (2-4 sessions), L (a wave). Dispatch fit follows the cloud-enablement plan: Cloud for GitHub-authoritative repos without credentials (agentops, vuoro, sprintctl), Local for Forgejo-authoritative vuoro-cloud and homelab-analytics and for anything touching tokens; Operator where a privileged step is unavoidable.

| Id | Title | Evidence (why now) | Outcome | Repos | Depends | Size | Security notes | Dispatch |
|---|---|---|---|---|---|---|---|---|
| **B1** | Correlation spine v1: fill `correlation_id`/`causation_id` from the session binding, register a run at SessionStart | §2.2: the shard schema already has the fields; they are null on all 2,442 hook events; #2479 asks for the run at session start but has no owner | `session-binding.sh` registers a run (served) and exports `AGENTOPS_RUN_ID`; every hook event sets `correlation_id=run_id`, subagent exits set `causation_id`; `session-costs.jsonl` carries `run_id`; a `prepare-commit-msg` hook adds `Vuoro-Run` | agentops, sprintctl (`run.origin_session_id`, nullable `work_item_id`) | #2479 (closes it), schema 17 | M | Served write from the workstation identity only; no token in hooks beyond the existing profile | Cloud (sprintctl column + agentops hooks), Local verify |
| **B2** | `operator_action` and `operator_action_receipt` in sprintctl schema 18 + `sprintctl action` CLI | §2.3, §3.5; the convention exists in three places and no store | Tables (trigger append-only), served operations `work.action.create/list/receipt-v1`, CLI `action create|list|ack|done|decline`; receipt actor must differ from creator; `next-work --explain` gains `completed_operator_actions`; `handoff.py` renders open actions from the store instead of prose | sprintctl, agentops | B1 (for `created_by_run_id`), #2482 (actor binding) helps but not required | L | Receipt is an authority command: served identity with an `operator` role only; commands stored with non-secret check; no cloud-callable scope | Cloud (sprintctl), Local (agentops handoff wiring) |
| **B3** | Bridge: `operator_actions` field in handoff/v1 and a validator, migrating `OPERATOR-ACTIONS.md` | Until B2 lands, actions still rot with scratchpads; the handoff already carries an `OPERATOR LIST` string | handoff/v1.1 `operator_actions[]` with the §3.5 fields (state limited to proposed/done), `handoff.py validate` rejects prose-only lists, `render` prints the inbox; B2 imports these on landing | agentops | none | S | Secret-value check on `command` | Cloud |
| **B4** | Hosted-runtime request path: `operator_action.requested` evidence kind and the trusted-side promotion sweep | A Routine or cloud session that hits a 403 or a classifier denial has no way to ask except a PR body | Evidence kind with the §3.5 request fields; a served-shell sweep (cron on appservice) promotes them into B2 `proposed` with `created_by_run_id`; the run's evidence gets a `promoted` marker digest | vuoro (evidence kind), sprintctl (sweep), vuoro-cloud (no scope change: uses `vuoro:evidence.record`) | B2, PR #253 H1-3 | M | No new cloud scope; the sweep runs with a trusted identity | Cloud (vuoro, sprintctl) |
| **B5** | Tamper-evidence for auditctl shards: prev-hash chain and an anchored daily head | §2.4; cloud-enablement required item 10; four days uncommitted; `check_append_only_shards.py` docstring disclaims chains | auditctl adds `prev_hash` (chain per `origin_stream_id`), `auditctl verify` and `auditctl head`; a daily job commits shards and appends the head digest as a sprintctl evidence item on the day's maintenance run; the CI prefix check additionally verifies the chain | auditctl, agentops | #2480 (decision on the authoritative capture) should cite this as the "repo shard" option's integrity story; not blocked by it | M | Signing deferred: git commit signing on the shard commit already binds the head to a key | Cloud (auditctl is GitHub), Local for the commit job |
| **B6** | vuoro-cloud audit export and operator-wide read | §1 row 10: workspace-less rows unreadable; no operator route; controller rows uncorrelated | `GET /operator/audit-events` (cursor, filter by action/actor/since, includes workspace-less rows); controller threads the originating `request_id` from the outbox row; `mcp_exchange` and access log gain `request_id`; a `scripts/export_audit_events.py` writes a digest-recorded NDJSON for homelab-analytics; an `action` enum module replaces string literals | vuoro-cloud | none | M | Operator bearer + source CIDR as today; export contains subjects and ids, no secrets; store the export digest as evidence | Local (Forgejo) |
| **B7** | Reconstructability, local leg: `activity_unit` definition and computation for harness sessions | §2.1; H1-4 covers hosted only | Extends H1-4's script (or the homelab-analytics silver model, once B10 exists) with local sessions from `session.binding`/`workflow.session`, subagents, and the numerator rule in §3.4; reports by horizon and week | agentops | B1, PR #253 H1-4 | S | Read-only | Cloud |
| **B8** | Durable `cloud.run` observation replacing `CLOUD-RUNS.md` | §1 row 16: credit burn is untracked; the USD 250 credit is finite | A small wrapper for `claude --cloud` / follow-ups that publishes an auditctl `cloud.run` event (`cse_`, `trig_`, brief digest, repo, branch, billing origin/bucket from `get_session`, later PR urls) and a `cloud.run.exit` on completion; `cost_per_release.py` learns the join | agentops | none | S | No vendor credentials stored; ids only | Cloud |
| **B9** | Orphaned-tenant consistency check as a system creator of operator actions | §2.5; H1-7 is digest drift, not existence/ownership | A controller or cron pass compares workspaces, runtime pods, grants/tokens (age, last use), backup observations and the work-authority repo binding; each inconsistency becomes an audit row `tenant.consistency.violation` and (via B4/B2 or, before B2, an Alertmanager alert) an operator action with the exact remediation (`DELETE .../grants/<id>`, `PATCH desired_state`) | vuoro-cloud, sprintctl (B4 sweep) | PR #253 H1-7 (share the pass), B2/B4 for the inbox | M | The remediation stays a proposal; no auto-delete | Local (Forgejo) |
| **B10** | homelab-analytics `agent_activity` domain: bronze sources and dataset contracts | §3.4; nothing ingests agent activity; the Prometheus/HA pipeline pattern exists | Sources for auditctl shards, session costs, sprintctl events/runs (served read with a read-only service token), vuoro-cloud audit export (B6), cred-broker receipts, operator actions; contracts with source digests; `make verify-fast` green | homelab-analytics | B6 for the cloud source (others can start now) | M | Read-only token scoped to `work.read`; no household data mixing (separate schema) | Local |
| **B11** | homelab-analytics gold marts and `/reports` for §4 | §4 | `fleet_status`, `reconstructability_weekly`, `cloud_run_cost`, `open_operator_actions`, `security_events_daily`, each with a report page and an MCP-agent query | homelab-analytics | B10, B1/B7 for the reconstructability number | M | Read-only | Local |
| **B12** | Alertmanager webhook to operator-action creation, and acknowledgement as receipt | §2.6: eight rules to one mailbox; the completion-alert architecture already defines ack as operator state | A protected-side receiver (appservice) that turns an alert into a B2 action (`system:alertmanager`, kind by rule, dedup on fingerprint), resolves it on the alert's resolve, and delivers via the D15 path; email stays as fallback | vuoro-cloud (AlertmanagerConfig receiver over the operator tunnel or a public webhook with a shared secret), appservice/agentops (receiver) | B2 | M | Webhook secret in SOPS; receiver validates the Alertmanager payload; no cluster write-back | Local + Operator (secret placement) |
| **B13** | Retention and immutability decisions for the audit stores | §1: no retention anywhere except `product_events`; `evidence_item` cascade-deletes with `run`; `event` has no trigger; receipts unsigned | One decision doc + implementation: `run` deletes forbidden (trigger), `event` gets the append-only trigger, receipts get `prev_hash`, shards and exports get a stated retention (proposal: keep forever, redact by policy), pod logs 30 d | sprintctl, cred-broker, vuoro-cloud, agentops | none | S-M | Retention "forever" is acceptable only because stores are non-secret by construction; the decision must say so | Cloud (sprintctl, cred-broker if GitHub), Local (vuoro-cloud) |
| **B14** | Promotion and generation as evidence: `promote-release.sh` and the promote workflow register the generation on a run | §2.2 last row: generation is in nothing structured; `release_digest` is always null | The signed-tag step records `{generation, tag, image_digest, candidate_pr, signer}` as an evidence item on the promoting session's run (B1) and as an operator-action receipt (B2, kind `promote_release`); `fleet_status` reads it | vuoro-cloud (script), agentops (runbook) | B1, B2 | S | The YubiKey step stays the operator's; the script only records | Local + Operator |

Sequencing suggestion: B3 and B8 now (small, unblock the operator today); B1 and B2 as the next wave (the spine and the inbox are the two objects everything else keys on); B5, B6, B13 as the integrity wave (they satisfy required-before-slice-1 item 10 together); B10/B11 once B1 and B6 exist; B4, B9, B12, B14 close the loops.

## 6. Rejected ideas

- **OpenTelemetry trace ids as the spine.** OTel is emit-only and inert (TS-15; endpoint unset); a trace id is minted client-side, so a hosted runtime could forge it, and it cannot be cited by a Decision. Keep OTel for telemetry; do not make audit or evidence depend on it.
- **vuoro-cloud `audit_events` as the one audit store.** It sits in the public horizon; the operator's own acceptance records must not depend on the hosted perimeter (TS-16; cloud-enablement plan §acceptance). It stays authoritative for public-system audit only.
- **A SIEM or hosted log product.** Adds a third horizon and a credential holder for the most sensitive stream; the volume (3,047 shard lines in two months) does not justify it.
- **Signing every audit event.** Per-event signatures on the workstation require a key in the hook path; a chained head anchored by a signed git commit (B5) gives tamper-evidence without that exposure. Revisit if the evidence home (S4) moves off git.
- **GitHub or Forgejo issues as the operator inbox.** They are effect-capable systems in the public horizon (GitHub) or reachable only locally (Forgejo); an action would then live where a cloud session can edit it, and completion would not be a Decision-class record.
- **Signal / email as the system of record for actions.** They remain delivery paths (D15, `operator-email`); the record is B2.
- **Keeping operator actions in handoff JSON permanently.** B3 is a bridge only: handoffs are session-scoped and the same action would be copied forward by every successor, as the `OPERATOR LIST` line already is.
- **homelab-analytics owning auditctl or the inbox.** Its own pilot-consumer plan declines this, correctly; it consumes and reports.
- **A public read-only "operator inbox" panel on vuoro.cloud first.** Useful later (PR #253 H3-5), but it would tempt a write path from the browser; the inbox must exist on the protected side before any projection.
- **Automatic completion of actions from target-system audit rows** (e.g. mark `revoke_credential` done when `token.revoked` appears). Tempting, but it makes the receipt automatic; the audit row should be attached as receipt evidence by a trusted actor, not substitute for the receipt. An auto-accept policy (H2-4) may do this later with its policy id as the actor.
