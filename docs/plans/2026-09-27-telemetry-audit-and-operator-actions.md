# Telemetry, audit, evidence and operator actions: one picture, one inbox

- Date: 2026-09-27
- Status: proposal (planning pass, read-only inventory; nothing here is adopted).
  Revised 2026-09-27 to apply the operator decisions on this PR (#256) and on
  #255, listed below.
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
- Split-horizon architecture: agentops PR #255
  (`docs/architecture/2026-09-27-agentic-ecosystem-and-split-horizon.md`,
  proposal) and the operator's answers on it (2026-09-27). The principle is
  **coordination without custody**: vuoro.cloud is the **primary coordination
  plane** (work, runs, evidence, notes, effect proposals, derived views,
  telemetry and operator views); the **protected horizon owns authority**
  (canonicalizing and accepting proposals, credential custody, the reconciler,
  signing and promotion). The two horizons are **public** (vuoro.cloud,
  api.vuoro.cloud, Hetzner) and **protected** (vuoro-shared.apps.kotona.app,
  appservice, workstation, cred-broker, homelab-analytics). vuoro-shared is a
  protected substrate plus an emergency coordination island, not a peer
  production backend. Where this document conflicts with #255 as it is
  finalized, #255 wins.
- Operator decisions this revision applies (2026-09-27):
  - On this PR: **vuoro.cloud owns telemetry** (the authoritative telemetry,
    reports and operator views). homelab-analytics consumes vuoro.cloud
    telemetry and **may also produce operator actions** (and other records in
    its own domain) through the operator-action path, as an attributed,
    audited actor. It never writes vuoro.cloud's telemetry or audit records.
    (The later PR comment corrects the earlier "read-only consumer" one.)
  - On #255: proposals are **untrusted input**; acceptance is protected-side
    and **digest-bound** (it binds the canonical hash of the intent type, exact
    parameters, source run and immutable evidence refs; any change is a new
    proposal with a new digest). Operation classes (Q2): *OIDC anywhere*: read
    status, inspect tenants, inspect audit and health; *OIDC + step-up*:
    `mutations_frozen` / unfreeze; *protected only*: effect acceptance,
    credential/policy change, promotion, key rotation, recovery. Q6 (audit
    capture) is an emphatic (a): restore and verify the hook → auditctl path,
    then treat **last successful authoritative event age** as a hard health
    metric. No active-active dual writing; a degraded-local mode writes under
    a distinct outage epoch that is reconciled into vuoro.cloud on recovery.
  - TS-16 unchanged: cloud callers can only queue effects.

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
the vuoro.cloud coordination plane, created by agents or systems as an
untrusted proposal with a canonical digest; state changes that carry no effect
are operator coordination writes, and anything effectful is accepted only on
the protected side, bound to that digest; (4) **vuoro.cloud as the owner of
telemetry, reports and operator views**, with homelab-analytics as a downstream
consumer that may also raise operator actions under its own attributed
identity; (5) five reports, served as vuoro.cloud operator views; (6) **last
successful authoritative event age** as a hard health metric for every
authoritative audit store. Seventeen backlog items, none of which duplicates PR
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
- **homelab-analytics ingests no agent activity at all**, and its `agent-ops-pilot-consumer-plan.md` explicitly declines to *own* auditctl, actionq or the cockpit. That boundary holds under the operator's decision: it consumes vuoro.cloud telemetry and does not own it. Consuming is not the same as being read-only, though: it may raise operator actions from its own analysis (§3.4).
- **Audit capture freshness disagrees between passes.** PR #255 §5 recorded the newest agentops shard as 2026-08-29 **[INF]**; agentops `origin/main` at this revision carries daily shards through 2026-09-27 (commits `c134945`, `ffb8d12`, `4ddb602`, "append audit shards through 2026-09-27"). Either the #255 reading came from a stale checkout or capture resumed; neither pass measured the hook → auditctl path end to end. That is exactly why Q6 (a) and the freshness metric (§3.6, B16) are needed: the answer should come from a health metric, not from a manual `ls`.
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

TS-16 matters here: when an operator completes an action that *accepts an effect* (promotion, merge, PATCH), that completion is exactly the trusted-side acceptance record the cloud-enablement plan requires (a separately authenticated actor, never the proposer). Today it is not recorded at all, and nothing binds what the operator ran to what was asked: a scratchpad line can change between the ask and the run with no trace. Under #255 the acceptance must bind the exact proposal digest, not a prose description or an id.

### 2.4 Audit tamper-evidence

- auditctl shards: per-event digest and git prefix check only. A writer with the repo can rewrite a shard before commit (four days are uncommitted right now). No chain head is anchored anywhere.
- vuoro-cloud `audit_events`: plain table; a control-plane compromise or DB admin can edit or delete rows silently. Required-before-slice-1 item 10 is unmet.
- sprintctl `event`: documented append-only, no trigger.
- cred-broker receipts: SQLite, no chain, no signature, no verifier; the threat model's INV-005 ("non-secret receipt") holds but a tampered receipt is undetectable.
- vuoro-evidence chain: detects delete/reorder/alter of items within a run; does not detect deletion of the whole run (cascade) and has no signing.
- Silence is undetected everywhere. Tamper-evidence says nothing about a store that stops receiving events: no store exposes the age of its newest successfully written authoritative event, so a broken hook or a stopped exporter looks the same as a quiet day (compare the #255 / this-pass disagreement in §1). The operator's Q6 decision makes that age a hard health metric (§3.6).

### 2.5 The orphaned-tenant class of incident

Recent state shows the pattern: workspace `isolation-proof` kept alive with test grants after its purpose ended; drill PAT and test grants still valid server-side; `blocker12-canary` on runtime 0.1.52 with legacy LOGIN roles; kotona left on 0.1.74 until an operator PATCH. The general class: a tenant whose control record, runtime pod, grants/tokens, backup observations and work-authority binding disagree, with no owner watching. Today the only signals are `vuoro_ws_*` metrics (no alert), the audit rows for individual actions (workspace-scoped, admin-only), and the operator's memory. PR #253 H1-7 covers runtime-digest drift; the existence/ownership consistency check (§5 B9) is missing, and so is routing its finding into an action the operator will see.

### 2.6 Alerting

- Public horizon: eight PrometheusRules, all to one email receiver; nothing for the tenant runtime (not scraped), nothing for the work authority, nothing for cloud-run failures. No acknowledgement state.
- Protected horizon: the live-session-completion alert architecture (`docs/plans/agentops/live-session-completion-alert-architecture.md`) designs an AgentOps consumer with delivery ledger and acknowledgement "as AgentOps operator state"; D15 proved one delivery path. It is not connected to anything in the public horizon.
- Result: an alert and an operator action are different objects with different lifecycles, when in practice most alerts *are* operator actions ("backup stale: run the observation script").

## 3. Target model

### 3.1 One correlation spine

**The spine is `run_id`**, the server-minted `run_[ULID]` from `work.run.register-v1` (sprintctl schema 17). Reasons: it already exists, it is minted by the server, never by the caller (so a hosted runtime cannot forge one), it is the key of the only tamper-evident evidence store, and TS-16 names the run record as the thing a signed commit must chain back to.

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
| **Telemetry** | Volumetric, sampled or aggregated observations with no per-event obligation; loss is acceptable | **vuoro.cloud** (operator decision): the vuoro.cloud Prometheus for public-horizon systems, plus the telemetry summaries protected-side producers publish to it outbound (freshness ages, counts, digests, never raw records); OTel/Langfuse on the protected side stays a local, non-authoritative harness stream until #2394/#2395/#2398 decide its export | homelab-analytics marts (downstream consumer) | `vuoro_gateway_security_events_total`, token counts, latency, `*_last_authoritative_event_age_seconds` |
| **Audit** | Per-event observations of *who did what to which system*, recorded by the system that performed it; loss is a finding | Each system audits itself: vuoro-cloud `audit_events` (pub); auditctl shards (ws, for harness/hook activity, authoritative until S4 per TS-6); cred-broker receipts and the protected acceptance ledger (prot); sprintctl `event` (wherever the work authority runs) | vuoro.cloud operator views read public audit directly and show protected audit as summaries and digests; homelab-analytics may copy what it consumes, with source id and digest | `oauth.grant.revoked`, `dispatch.exit`, credential-issued, `operator_action.accepted` |
| **Evidence** | Observations a run *claims* about its work, registered on the run and chained; the thing a Decision cites | sprintctl `run`/`evidence_item`/`session_note`, served by the coordination plane (vuoro.cloud as primary per #255; vuoro-shared only in degraded-local mode, under an outage epoch) | none (digests may be copied into audit rows and into acceptance canonical forms) | verdicts, test results, `rate_limit_event`, `operator_action.requested` |
| **Operator action** | A request from an agent or system to the operator (an untrusted proposal with a canonical digest), its coordination state, and, for effectful kinds, a protected-side acceptance bound to that digest | Request and coordination state: `operator_action` in the coordination plane (vuoro.cloud). Acceptance of effectful kinds: the protected acceptance ledger (credctl / cred-broker side, trigger append-only). | vuoro.cloud operator inbox view (authoritative for display, not for acceptance); homelab-analytics copies for analysis | promote gen N, PATCH tenant, revoke grant, attach repo, a homelab-analytics "backups stale for 3 d" finding |

Rules:

- A store is authoritative for exactly one class; a derived copy always carries the source's id and digest; telemetry may be dropped, audit and evidence may not.
- vuoro.cloud owns telemetry, reports and operator views. homelab-analytics is authoritative for nothing agent-related and writes neither telemetry nor audit into vuoro.cloud; its only write into the agent estate is raising operator actions under its own identity (§3.4).
- **Nothing originating in the coordination plane becomes an effect merely because the coordination plane says it should** (#255). Every proposal, from a hosted runtime, a local agent, a system check or homelab-analytics, is untrusted input to the protected side.
- **Cross-horizon actions are recorded independently on both sides** (#255 §5 corroboration): the proposal and its coordination state in vuoro.cloud, the acceptance and effect receipt on the protected side, joined by the proposal digest and `run_id`. Corroboration is a property to be earned once protected receipts and the acceptance ledger are tamper-evident (B5, B13); until then it is not claimed.

### 3.3 Where each lives and in which horizon

| Class / object | Horizon | Store | Cross-horizon movement |
|---|---|---|---|
| Public-system audit (`audit_events`), product analytics, backup observations, gateway logs, Prometheus | pub | vuoro-cloud control DB, cluster | Served to the operator in vuoro.cloud operator views (OIDC anywhere, read). homelab-analytics pulls what it needs (operator audit read / export, Prometheus federation) outbound from the protected side; nothing is pushed into the protected horizon. |
| Telemetry summaries of protected stores (freshness ages, counts, receipt and chain-head digests) | prot -> pub | vuoro.cloud Prometheus / telemetry ingest | Published **outbound** by protected-side producers (push gateway or remote-write with a telemetry-only credential); carries no record content, no credential, no command. Loss is acceptable except that its absence itself alerts (§3.6). |
| Evidence (runs, items, notes), work events, decisions | pub (primary), prot (degraded-local island) | sprintctl served by the coordination plane | Written by callers under `vuoro:evidence.record` / work scopes. Local harnesses move to vuoro.cloud after E2 (#255 Q1 b); no dual writing. Degraded-local writes carry an outage epoch and are imported with conflicts surfaced on recovery. |
| Harness audit (auditctl), session cost, handoffs | ws | shards in git; auditctl import into the evidence home is S4 (#2485) | Freshness and counts published as telemetry (above); shards consumed by homelab-analytics from git. |
| cred-broker receipts, acceptance ledger | prot | broker host SQLite (today), acceptance ledger (B2) | Stay protected. Only digests, outcomes and ages cross, outbound, as telemetry and as the acceptance outcome written back to the proposal (below). |
| Operator actions (request + coordination state) | pub (primary) | `operator_action` in the coordination plane | Created by any caller as a proposal; the vuoro.cloud inbox is the operator's view. The protected side **polls** open effectful actions, canonicalizes and hashes them itself, and after acceptance writes an outcome record (`accepted_digest`, acceptor, receipt digest) back outbound. |
| Operator-action acceptance for effectful kinds | prot | acceptance ledger (credctl on the workstation first, #255 Q4 a) | Never on the public horizon. The public side cannot alter what was accepted: the ledger holds the digest, and any edit to the proposal is a new proposal. |
| Reports and dashboards | pub | vuoro.cloud operator views (§4) | homelab-analytics keeps its own derived analyses on the protected side and may turn findings into operator-action proposals; it does not publish reports into vuoro.cloud or write its telemetry. |

This keeps TS-16 intact: the public horizon holds coordination, record and telemetry, and cloud callers can only queue proposals; acceptance, credentials and effects stay protected. The earlier draft kept the operator inbox and all reports off the public horizon; under coordination without custody the inbox and reports are coordination and live in vuoro.cloud, while the part that matters most for authority, the acceptance record, stays protected and is bound to a digest the public side cannot change.

### 3.4 How homelab-analytics consumes and produces

homelab-analytics is a **downstream consumer of vuoro.cloud telemetry** that **may also produce operator actions** under its own design. It is not the owner or system of record of any agent telemetry, audit or evidence.

- **Consume.** A domain `packages/domains/agent_activity/` with sources: `vuoro_cloud_metrics` (the existing Prometheus query pipeline, pointed at the vuoro.cloud Prometheus through the operator tunnel or a federation endpoint), `vuoro_cloud_audit` (operator audit read or export, B6), `auditctl_shards` (git, NDJSON), `session_costs` (jsonl), `sprintctl_runs`/`sprintctl_events` and `operator_actions` (read scopes on the coordination plane), `cred_broker_receipts` (protected, non-secret). Each source has a dataset contract with `source_id`, `source_digest` and `ingested_at`, in keeping with the bronze layer. Silver `activity_unit` (session, cloud session, Routine run, worker lease) keyed by `run_id` where it exists; `reconstructable` = run row exists AND at least one evidence item AND (a PR/commit with a resolvable trailer OR a Decision citing the run); `origin_horizon` recorded.
- **Produce.** homelab-analytics may raise operator actions derived from its analysis (recommended or required: "backup observation age > 72 h on workspace X", "reconstructability fell below N % this week", "tenant Y orphan-suspect"). It does so through the same operator-action path as every other creator: `work.action.create-v1` on the coordination plane, with a dedicated identity (`system:homelab-analytics`, its own client and token, propose/create scope only, no acknowledge/decline/accept scope). Each action it raises cites its evidence (mart row ids, query digest, source digests) in `evidence_refs` and is audited in vuoro.cloud `audit_events` under that identity. It may also keep other records inside its own domain (marts, findings history).
- **Never.** It writes no vuoro.cloud telemetry or audit records, holds no acceptance or receipt scope, and its proposals are untrusted input like any other: an effectful action it raises is accepted only on the protected side against the proposal digest, by the operator or a protected-side policy, and never by homelab-analytics itself (proposer identity is rejected as acceptor).
- The MCP agent (`apps/agent/mcp_server.py`) may answer analysis questions from its marts; "what is open for me" is answered by the vuoro.cloud inbox, so there is still one inbox.

### 3.5 The operator-action inbox as a first-class object

`operator_action` (sprintctl work schema 18, served by the coordination plane; trigger append-only for its state records) and the protected acceptance ledger:

```
operator_action                        (coordination plane: vuoro.cloud)
  action_id            oa_[ULID], server-minted
  repo_id, workspace_id?
  kind                 promote_release | dispatch_workflow | tenant_patch | repo_attach |
                       merge_denied | revoke_credential | place_secret | freeze |
                       decision | run_command | recommendation | other
  authority_class      coordinate | step_up | protected      (derived from kind, §below;
                       the protected side recomputes it and never trusts this field)
  title                one line
  created_by_run_id    the run that asked (nullable for system creators)
  created_by_actor     principal string, server-set from the caller identity
                       (agent principal, system:alertmanager, system:drift-check,
                       system:homelab-analytics)
  required_by          timestamp or null; urgency now|today|week|when_convenient
  precondition         text + precondition_checked_at + precondition_digest
  command              exact command or API call with exact parameters, redacted of secret values
  expected_result      text
  send_back            what the operator should return
  evidence_refs        [ {kind, ref, digest} ]  immutable refs only (evidence items, PR head sha, alert ids, mart row digests)
  blocks               [ item_id | run_id ]
  proposal_digest      sha256(canonical{kind, command, parameters, created_by_run_id, evidence_refs})
  outage_epoch?        set when created in degraded-local mode
  state                proposed | acknowledged | accepted | done | declined | expired | superseded
  supersedes           action_id?
  created_at
  -- the proposal fields are immutable after creation; any change is a new action
  -- with a new proposal_digest that supersedes the old one

operator_action_event                  (coordination plane; one per state change; append-only)
  event_id, action_id, actor, decision  acknowledge | done | decline | expire | supersede | accepted_outcome
  result_text, result_digest            what was sent back (non-secret)
  evidence_refs                         (audit row ids in the target system)
  accepted_digest?, acceptance_receipt_digest?   only on accepted_outcome, written by the protected side
  run_id?, created_at

acceptance                             (protected ledger; append-only; hash-chained per B13)
  acceptance_id, action_id, accepted_digest (recomputed on the protected side from the fetched proposal),
  acceptor (operator via credctl, or policy id + version), classification, receipt_digest, created_at
```

**Classification (from #255 Q2).** The kind decides the authority class; the protected side computes it from its own copy of the table, never from the proposal's field:

| Class | Kinds | Who may move it forward |
|---|---|---|
| *coordinate* (OIDC anywhere) | `recommendation`, `repo_attach`, `decision` without an effect, `run_command` whose command is read-only, any acknowledge/decline/annotate | The operator's OIDC identity in vuoro.cloud (the admin client, never the connector client). Recording `done` with a result is a coordination record, not an acceptance. |
| *step_up* (OIDC + step-up) | `freeze` (`mutations_frozen` / unfreeze) | Operator OIDC plus explicit step-up, with its own client, audience and scopes separate from the connector identity. |
| *protected* | `promote_release`, `merge_denied`, `tenant_patch`, `dispatch_workflow`, `revoke_credential`, `place_secret`, `run_command` with any effect, credential/policy change, key rotation, recovery | Only the protected side: `credctl accept <action_id> --digest <proposal_digest>` on the workstation (#255 Q4 a), later deliberately boring kinds by a protected-side auto-accept policy (Q4 c, after the audit prerequisite). The accept fails if the recomputed digest differs from the one the operator was shown. |

**Lifecycle.** Any creator (a local agent, a hosted runtime, a system check, homelab-analytics) creates `proposed` through `work.action.create-v1`; cloud callers use their existing record/propose scope, so no new cloud-callable effect scope appears and cloud callers still only queue. Hosted runtimes that can only append evidence use `append_evidence(kind="operator_action.requested", ...)`, which the coordination plane turns into an action with `created_by_run_id` (B4). The operator sees one list: the vuoro.cloud inbox (OIDC read), `sprintctl action list --open`, the handoff prompt. Coordination-class actions close with an operator event in vuoro.cloud. Protected-class actions close only when the protected side has polled the proposal, recomputed its digest, recorded an acceptance, performed or authorized the effect, and written the `accepted_outcome` back; the effect's own receipt (cred-broker, Forgejo merge, signed tag) cites the acceptance. The loop back to agents: `next-work --explain` gains a `completed_operator_actions` bucket since the session's last watermark, and `handoff.py ack` refuses to mark an action done without a matching event.

**TS-16 and trust.** A proposal is untrusted whoever raised it: a compromised public tier or a buggy homelab-analytics query can fabricate or corrupt proposals, but cannot alter an accepted effect or exercise protected authority, because the acceptance binds a digest the protected side computed from the exact parameters and immutable evidence refs. The proposer identity is rejected as the acceptor. Auto-accept policies record policy id and version as the acceptor. Automatic completion from target-system audit rows is still rejected (§6).

**Outage semantics.** In degraded-local mode (#255 Q3) actions are created on the vuoro-shared island with an `outage_epoch`; on recovery they are imported into vuoro.cloud, conflicts (the same action progressed on both sides) are surfaced as their own operator actions, never silently merged. Protected acceptances made during the outage are already authoritative in the ledger and are replayed as `accepted_outcome` events.

Sensitivity: commands are stored with secret *values* redacted (`assert_non_secret`-style check borrowed from cred-broker); ids of tokens and grants are allowed because the target systems audit them anyway. Because the inbox now lives on the public horizon, `place_secret` and `revoke_credential` actions name the secret path or token id only; the value never enters the proposal.

### 3.6 Audit freshness as a hard health metric

Per the operator's Q6 decision, every authoritative audit store exposes **last successful authoritative event age**: seconds since the newest event that was durably written to the authoritative store (not attempted, not buffered), per producer stream.

| Store | Metric (published to vuoro.cloud telemetry) | Producer |
|---|---|---|
| auditctl shards (per host, per repo) | `agentops_audit_last_authoritative_event_age_seconds{host,repo,stream}` | a hook-independent exporter reading the newest shard line after fsync (so a dead hook shows up as age growth) |
| vuoro-cloud `audit_events` | `vuoro_audit_last_authoritative_event_age_seconds{source}` | control plane `/metrics` |
| sprintctl `event`, `evidence_item` | `sprintctl_last_authoritative_event_age_seconds{table}` | the served backend |
| cred-broker receipts, acceptance ledger | `credbroker_receipt_last_authoritative_event_age_seconds`, `acceptance_last_authoritative_event_age_seconds` | protected side, outbound push |

"Hard" means: an alert with an expected-activity window per stream (for example auditctl on an active host > 24 h, vuoro-cloud audit > 6 h), a missing series alerts the same as a stale one (`absent()`), the alert raises an operator action through §3.5 (B12), and the metric appears in the fleet-status view (§4). A stale authoritative store is a failed TS-6 invariant, not an observability curiosity.

## 4. Reports and dashboards: the minimal useful set

All five are **vuoro.cloud operator views** (operator decision: vuoro.cloud holds the authoritative telemetry, reports and operator views). Reading them is an *OIDC anywhere* operation (#255 Q2: read status, inspect tenants, inspect audit and health) through the operator's admin identity, never the connector client. Protected-side facts appear as the summaries and digests published outbound (§3.3); detail that must stay protected (receipt payloads, acceptance ledger) is viewed on the protected side and linked by digest. homelab-analytics may build its own analyses over the same data (for example joining agent activity with its household-infrastructure datasets) and turn findings into operator-action proposals, but the operator's reports of record are these.

| Report | Question | Sources (by inventory #) | Where |
|---|---|---|---|
| **Fleet / generation status** | Which generation is live, which candidate is signed, which tenants are on which runtime, which drifted, which are orphan-suspect, and how old the newest authoritative event of each audit store is (§3.6) | 12 (`vuoro_ws_*`), 10 (`tenant.*`, `workspace.*`), promotion evidence items (6), H1-7 drift rows, §3.6 freshness metrics | vuoro.cloud operator view `fleet-status` (Grafana panels for the live numbers) |
| **Reconstructability %** | TS-16's control question, split by horizon (local, cloud session, Routine, worker) and by week | runs and evidence (6), gateway `mcp_exchange` (13), local session units (1, 2, published as counts), cloud runs (5/16 via B8), PR trailers | vuoro.cloud operator view computed on the coordination plane, where runs and evidence now live (H1-4 + B7); the number goes into the weekly lane check-up |
| **Credit burn per cloud run** | Which `cse_`/`trig_` run cost what, on which bucket, and what it produced (PRs, evidence) | 16 via a durable `cloud.run` observation (B8), 6, PR data | vuoro.cloud operator view; sits beside `cost_per_release.py` output |
| **Open operator actions** | What waits on the operator, ordered by `required_by` and what it blocks, with its authority class and proposal digest; what was completed or accepted in the last 7 days with result | `operator_action`, its events, acceptance outcomes (§3.5) | the vuoro.cloud inbox; `sprintctl action list`; handoff prompt. Acceptance itself happens on the protected side (`credctl accept`), not in this view |
| **Security events** | Gateway security events by kind, OAuth scope rejections, grant/token create/revoke/reuse-detected, operator-path rejections, cred-broker denials (as published counts), classifier denials on privileged commands, orphan-suspect tenants | 12, 10, 14 (summary), 1 (`harness.gate`, `dispatch.preflight_rejected`, as counts) | vuoro.cloud operator view + Grafana |

Deliberately not in the minimal set: per-model token dashboards (TS-15 says measure producers before contracts; wait for OTel), per-tenant product analytics (already served by the operator route), and a "cockpit" rewrite.

## 5. Proposed backlog items

Checked against PR #253 (H1-1..H3-8) and sprint 559 pending items (#2394, #2395, #2398, #2428, #2433, #2441, #2472, #2479..#2489, #2492, #2502, #2504, #2513, #2518..#2520). Overlaps are called out; nothing below re-proposes an existing item. Sizes: S (a session), M (2-4 sessions), L (a wave). Dispatch fit follows the cloud-enablement plan: Cloud for GitHub-authoritative repos without credentials (agentops, vuoro, sprintctl), Local for Forgejo-authoritative vuoro-cloud and homelab-analytics and for anything touching tokens; Operator where a privileged step is unavoidable.

| Id | Title | Evidence (why now) | Outcome | Repos | Depends | Size | Security notes | Dispatch |
|---|---|---|---|---|---|---|---|---|
| **B1** | Correlation spine v1: fill `correlation_id`/`causation_id` from the session binding, register a run at SessionStart | §2.2: the shard schema already has the fields; they are null on all 2,442 hook events; #2479 asks for the run at session start but has no owner | `session-binding.sh` registers a run (served) and exports `AGENTOPS_RUN_ID`; every hook event sets `correlation_id=run_id`, subagent exits set `causation_id`; `session-costs.jsonl` carries `run_id`; a `prepare-commit-msg` hook adds `Vuoro-Run` | agentops, sprintctl (`run.origin_session_id`, nullable `work_item_id`) | #2479 (closes it), schema 17 | M | Served write from the workstation identity only; no token in hooks beyond the existing profile | Cloud (sprintctl column + agentops hooks), Local verify |
| **B2** | `operator_action`, its event log and the protected acceptance ledger + `sprintctl action` / `credctl accept` | §2.3, §3.5; the convention exists in three places and no store; #255 requires digest-bound acceptance | Schema 18 tables in the coordination plane (proposal fields immutable, events trigger append-only, server-computed `proposal_digest`, server-set `created_by_actor`); served operations `work.action.create/list/event-v1`; CLI `action create\|list\|ack\|done\|decline`; protected `credctl accept <action_id> --digest <d>` that polls, recomputes the canonical digest, classifies by kind from its own table, records the acceptance and writes `accepted_outcome` back; proposer rejected as acceptor; `next-work --explain` gains `completed_operator_actions`; `handoff.py` renders open actions from the store | sprintctl, vuoro (served op + vuoro.cloud inbox read), cred-broker/credctl, agentops | B1 (for `created_by_run_id`), #2482 (actor binding) helps but not required | L | Coordination writes need the operator's OIDC admin identity; `freeze` needs step-up; protected kinds are accepted only by credctl on the workstation; no cloud-callable accept scope exists; commands pass a non-secret check | Cloud (sprintctl, vuoro), Local (credctl, agentops handoff wiring) |
| **B3** | Bridge: `operator_actions` field in handoff/v1 and a validator, migrating `OPERATOR-ACTIONS.md` | Until B2 lands, actions still rot with scratchpads; the handoff already carries an `OPERATOR LIST` string | handoff/v1.1 `operator_actions[]` with the §3.5 fields (state limited to proposed/done), `handoff.py validate` rejects prose-only lists, `render` prints the inbox; B2 imports these on landing | agentops | none | S | Secret-value check on `command` | Cloud |
| **B4** | Hosted-runtime request path: `operator_action.requested` evidence kind turned into an action | A Routine or cloud session that hits a 403 or a classifier denial has no way to ask except a PR body | Evidence kind with the §3.5 proposal fields; the coordination plane creates the `proposed` action with `created_by_run_id` and the run's actor, and records the action id as a digest on the run's evidence | vuoro (evidence kind + conversion), sprintctl | B2, PR #253 H1-3 | M | No new cloud scope (uses `vuoro:evidence.record`); the result is still only a proposal; acceptance of protected kinds is B2's protected path | Cloud (vuoro, sprintctl) |
| **B5** | Tamper-evidence for auditctl shards: prev-hash chain and an anchored daily head | §2.4; cloud-enablement required item 10; four days uncommitted; `check_append_only_shards.py` docstring disclaims chains | auditctl adds `prev_hash` (chain per `origin_stream_id`), `auditctl verify` and `auditctl head`; a daily job commits shards and appends the head digest as a sprintctl evidence item on the day's maintenance run; the CI prefix check additionally verifies the chain | auditctl, agentops | #2480 (decision on the authoritative capture) should cite this as the "repo shard" option's integrity story; not blocked by it | M | Signing deferred: git commit signing on the shard commit already binds the head to a key | Cloud (auditctl is GitHub), Local for the commit job |
| **B6** | vuoro-cloud operator-wide audit read and export | §1 row 10: workspace-less rows unreadable; no operator route; controller rows uncorrelated | `GET /operator/audit-events` (cursor, filter by action/actor/since, includes workspace-less rows) behind the operator admin identity as an *OIDC anywhere* read; controller threads the originating `request_id` from the outbox row; `mcp_exchange` and access log gain `request_id`; a digest-recorded NDJSON export that homelab-analytics can pull; an `action` enum module replaces string literals; audit rows for `work.action.*` calls | vuoro-cloud | none | M | Read-only route; export contains subjects and ids, no secrets; store the export digest as evidence | Local (Forgejo) |
| **B7** | Reconstructability, local leg: `activity_unit` definition and computation for harness sessions | §2.1; H1-4 covers hosted only | Extends H1-4's script (or the homelab-analytics silver model, once B10 exists) with local sessions from `session.binding`/`workflow.session`, subagents, and the numerator rule in §3.4; reports by horizon and week | agentops | B1, PR #253 H1-4 | S | Read-only | Cloud |
| **B8** | Durable `cloud.run` observation replacing `CLOUD-RUNS.md` | §1 row 16: credit burn is untracked; the USD 250 credit is finite | A small wrapper for `claude --cloud` / follow-ups that publishes an auditctl `cloud.run` event (`cse_`, `trig_`, brief digest, repo, branch, billing origin/bucket from `get_session`, later PR urls) and a `cloud.run.exit` on completion; `cost_per_release.py` learns the join | agentops | none | S | No vendor credentials stored; ids only | Cloud |
| **B9** | Orphaned-tenant consistency check as a system creator of operator actions | §2.5; H1-7 is digest drift, not existence/ownership | A controller or cron pass compares workspaces, runtime pods, grants/tokens (age, last use), backup observations and the work-authority repo binding; each inconsistency becomes an audit row `tenant.consistency.violation` and (via B2, or before B2 an Alertmanager alert) an operator action with the exact remediation (`DELETE .../grants/<id>`, `PATCH desired_state`) | vuoro-cloud | PR #253 H1-7 (share the pass), B2 for the inbox | M | The remediation stays a proposal of a *protected* class (credential change / tenant mutation); no auto-delete | Local (Forgejo) |
| **B10** | homelab-analytics `agent_activity` domain: consume vuoro.cloud telemetry and agent records | §3.4; nothing ingests agent activity; the Prometheus/HA pipeline pattern exists | Bronze sources for vuoro.cloud Prometheus (federation / tunnel), vuoro-cloud audit export (B6), auditctl shards, session costs, runs/events and operator actions (coordination-plane read), cred-broker receipts; dataset contracts with source digests; silver `activity_unit`; `make verify-fast` green | homelab-analytics | B6 for the cloud audit source (others can start now) | M | Read tokens only for consumption; the analytics schema is separate from household data | Local |
| **B11** | vuoro.cloud operator views for §4 | §4; operator decision: vuoro.cloud holds reports and operator views | `fleet-status`, reconstructability, cloud-run cost, operator inbox and security-events views in the vuoro.cloud operator surface (admin OIDC, read) plus Grafana panels; protected facts shown from the outbound summaries of §3.3 | vuoro-cloud, vuoro (inbox read) | B2 for the inbox, B1/B7 for reconstructability, B16 for freshness, B8 for cost | M | Read-only views under the admin identity; no accept or effect control in the view | Local (Forgejo) |
| **B12** | Alertmanager to operator-action creation, and resolve as an event | §2.6: eight rules to one mailbox; the completion-alert architecture already defines ack as operator state | A receiver in the coordination plane (same cluster as Alertmanager, so no cross-horizon hop) that turns an alert into a B2 action (`system:alertmanager`, kind by rule, dedup on fingerprint), records a `resolve` event on the alert's resolve, and triggers delivery via the D15 path; email stays as fallback | vuoro-cloud (receiver + AlertmanagerConfig), agentops (D15 delivery wiring) | B2 | M | Receiver has create scope only; alert-raised actions are proposals like any other; no cluster write-back | Local |
| **B13** | Retention and immutability decisions for the audit stores | §1: no retention anywhere except `product_events`; `evidence_item` cascade-deletes with `run`; `event` has no trigger; receipts unsigned | One decision doc + implementation: `run` deletes forbidden (trigger), `event` gets the append-only trigger, receipts and the acceptance ledger get `prev_hash`, shards and exports get a stated retention (proposal: keep forever, redact by policy), pod logs 30 d | sprintctl, cred-broker, vuoro-cloud, agentops | none | S-M | Retention "forever" is acceptable only because stores are non-secret by construction; the decision must say so | Cloud (sprintctl, cred-broker if GitHub), Local (vuoro-cloud) |
| **B14** | Promotion and generation as evidence and as a digest-bound acceptance | §2.2 last row: generation is in nothing structured; `release_digest` is always null | A `promote_release` action whose proposal names `{generation, tag, image_digest, candidate_pr}`; the operator's `credctl accept --digest` precedes the YubiKey step; the signed-tag step records `{generation, tag, image_digest, candidate_pr, signer, accepted_digest}` as an evidence item on the promoting session's run (B1) and the acceptance outcome on the action (B2); `fleet-status` reads it | vuoro-cloud (script), agentops (runbook), credctl | B1, B2 | S | Promotion stays protected-only and the YubiKey step stays the operator's; the script only records | Local + Operator |
| **B15** | homelab-analytics as an operator-action producer | Operator decision on this PR: it may prescribe recommended or required operator actions from its analysis, as an attributed, audited actor | A `system:homelab-analytics` identity (own client and token, `work.action.create` + read scopes only); a findings-to-action rule set (backup age, reconstructability drop, orphan-suspect, freshness) that creates `recommendation` or typed actions with mart-row and query digests in `evidence_refs`, deduplicated on a finding key; findings history kept in its own domain | homelab-analytics, vuoro (identity/scope registration), vuoro-cloud (audit of the calls) | B2, B10 | M | Propose-only: no acknowledge/decline/accept scope; writes no vuoro.cloud telemetry or audit; its protected-class proposals go through B2's digest-bound acceptance; the proposer is rejected as acceptor | Local |
| **B16** | Audit capture health: restore hook → auditctl capture (Q6 a) and publish last successful authoritative event age | #255 Q6 decided (a), emphatically; §1 and §2.4: the two passes disagree on shard freshness and no metric exists; #2480's authoritative-capture decision now has its answer for the interim | End-to-end check that a hook event reaches a fsynced shard line on each agent host (a canary event per session start); the §3.6 metrics for auditctl, vuoro-cloud `audit_events`, sprintctl, cred-broker and the acceptance ledger, published to vuoro.cloud; `absent()`+staleness alerts that raise operator actions (B12) | agentops, auditctl, vuoro-cloud, sprintctl, cred-broker | none for auditctl and vuoro-cloud (start now); B2 for the acceptance ledger | M | Metrics carry ages and stream labels only; protected producers push outbound with a telemetry-only credential | Local (hooks, cred-broker), Cloud (auditctl, sprintctl) |
| **B17** | Degraded-local outage epoch for operator actions and evidence | #255: no active-active dual writing; the island needs defined rejoin semantics before local harnesses move to vuoro.cloud | `outage_epoch` on actions, events and runs created on the vuoro-shared island; an import into vuoro.cloud that surfaces conflicts as operator actions and never merges silently; replay of protected acceptances as `accepted_outcome` | sprintctl, vuoro | B2 | M | The island never accepts on behalf of the public side; the acceptance ledger stays the only authority | Cloud |

Sequencing suggestion: B16, B3 and B8 now (B16 is the operator's emphatic Q6 answer; B3 and B8 are small and unblock the operator today); B1 and B2 as the next wave (the spine and the inbox with digest-bound acceptance are the two objects everything else keys on); B5, B6, B13 as the integrity wave (they satisfy required-before-slice-1 item 10 together, and are the precondition for claiming cross-horizon corroboration); B11 once B1, B2 and B16 exist; B10 and B15 once B2 exists; B4, B9, B12, B14, B17 close the loops.

## 6. Rejected ideas

- **OpenTelemetry trace ids as the spine.** OTel is emit-only and inert (TS-15; endpoint unset); a trace id is minted client-side, so a hosted runtime could forge it, and it cannot be cited by a Decision. Keep OTel for telemetry; do not make audit or evidence depend on it.
- **vuoro-cloud `audit_events` as the one audit store.** Each system audits itself; the acceptance ledger and cred-broker receipts are protected-horizon authority records and must not depend on the hosted perimeter (TS-16; cloud-enablement plan §acceptance; #255). `audit_events` stays authoritative for public-system audit only; vuoro.cloud shows protected audit as summaries and digests.
- **A SIEM or hosted log product.** Adds a third horizon and a credential holder for the most sensitive stream; the volume (3,047 shard lines in two months) does not justify it.
- **Signing every audit event.** Per-event signatures on the workstation require a key in the hook path; a chained head anchored by a signed git commit (B5) gives tamper-evidence without that exposure. Revisit if the evidence home (S4) moves off git.
- **GitHub or Forgejo issues as the operator inbox.** They are effect-capable systems in the public horizon (GitHub) or reachable only locally (Forgejo); an action would be freely editable after the ask, with no immutable proposal digest, and completion would not be a Decision-class record.
- **Signal / email as the system of record for actions.** They remain delivery paths (D15, `operator-email`); the record is B2.
- **Keeping operator actions in handoff JSON permanently.** B3 is a bridge only: handoffs are session-scoped and the same action would be copied forward by every successor, as the `OPERATOR LIST` line already is.
- **homelab-analytics as the owner or system of record for agent telemetry, reports or the inbox.** Rejected by the operator's decision on this PR: vuoro.cloud owns telemetry, reports and operator views. homelab-analytics consumes, and may raise operator actions as a proposer (B15); it does not own auditctl, the inbox or any vuoro.cloud telemetry or audit record.
- **homelab-analytics as strictly read-only.** The earlier operator comment on this PR said read-only; the later correction replaces it. Forbidding every write would push its findings back into chat and scratchpads, the exact failure of §2.3. The constraint that matters is narrower: create-only on the proposal path, no acceptance.
- **Keeping the operator inbox and reports on the protected side only** (this document's earlier draft). Superseded by coordination without custody: the inbox and reports are coordination, so they live in vuoro.cloud. The worry behind the earlier choice, a browser write path that turns into an effect, is answered by construction instead of by location: the vuoro.cloud inbox has no accept control for protected kinds, and acceptance binds a digest the protected side recomputes.
- **Accepting effectful actions in the vuoro.cloud inbox, even with step-up.** Step-up is reserved for `mutations_frozen` / unfreeze (#255 Q2); effect acceptance, credential or policy change, promotion, key rotation and recovery are protected only.
- **Accepting by action id.** An id names a mutable record; acceptance binds the canonical proposal digest (#255 Q4 amendment), so a changed proposal cannot inherit an earlier acceptance.
- **Automatic completion of actions from target-system audit rows** (e.g. mark `revoke_credential` done when `token.revoked` appears). Tempting, but it makes the receipt automatic; the audit row should be attached as receipt evidence by a trusted actor, not substitute for the receipt. An auto-accept policy (H2-4) may do this later on the protected side, for deliberately boring kinds, with its policy id and version as the acceptor.
