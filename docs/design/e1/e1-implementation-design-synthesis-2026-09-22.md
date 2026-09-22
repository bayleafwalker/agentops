# E1 Public Read-Only MCP Surface — Single Ordered Implementation Plan

*Scope note: this session investigated and designed only; no files were created, edited or deleted. Every line reference below was read from the working tree at /projects/dev/vuoro, /projects/dev/vuoro-cloud and /projects/dev/agentops today. Claims marked INFERRED were not verified live because network calls to the estate were not made in this pass.*

---

## 0. The decision this plan is built around, and the three contradictions it resolves

**Contradiction 1 — auth mode vs. everything downstream.** The connector's demand evidence is supposed to come from a `hosted-client` bearer token registered on a claude.ai custom connector. That registration path (`static_headers` / "Request headers") is **beta-gated to "a limited set of organizations"**, and connector authentication **cannot be changed after the connector is added**. If the operator's account does not have the beta, there is no way to register an authenticated claude.ai connector at all, and the cluster work (tunnel, DNS, NetworkPolicy, promotion) would be built for a client that cannot authenticate to it.

**Resolution:** the free, non-destructive availability check (§3.1) gates *all* vendor and cluster work, but gates *none* of the substrate code work. Everything in Phase 1 and Phase 2 below is worth doing regardless of which way that check lands, because the fallback path — Claude Managed Agents with a `static_bearer` vault credential — consumes the identical surface, the identical token model and the identical journal. Only the registration step differs.

**Contradiction 2 — the work-source adapter maps fields the disclosure audit says must not be emitted.** The ReadyWorkSource plan spends most of its mapping table on `description`, `provenance`, `prior_attempts` and `tier`; the disclosure audit shows those fields carry internal hostnames, absolute kubeconfig paths, credential names, an unremediated security finding stated as an exploit (agentops#2490), and 31 imperative constructions including runnable `kubectl`/`aws`/`sprintctl` command lines. Worse, sprintctl has **no** tier/acceptance/provenance/prior_attempts columns — they are `^Name:` prose sections inside `description`, so "map acceptance" means "parse the risky body and re-emit a slice of it".

**Resolution:** the adapter does **no parsing of the internal description body, ever**. The pilot workspace is new and authoritative from the start, so its items are authored external-facing from day one. The adapter emits only fields the pilot workspace authors as such. This shrinks the adapter to roughly a quarter of the originally planned mapping and removes the injection-shaped content at the only place the substrate actually controls: which bytes it emits.

**Contradiction 3 — per-token labels were sold as satisfying "a prompted setup/smoke call must not count as demand". They do not.** The way one smoke-tests a claude.ai connector is to open claude.ai and type a prompt. That call arrives on the connector's own token, from Anthropic's egress, with the hosted label. The operator-probe token only separates `curl` from connector, and `curl` was never the ambiguous case.

**Resolution:** attribution needs a **phase boundary**, not a label. A required, explicit `trial_started_at` timestamp is the clock; the token label decides which calls *count* once the clock has started. Both mechanisms are needed; neither alone is sufficient.

---

## 1. Signals that cannot fail — the disqualifying list

Every one of these is a check whose green state is structurally guaranteed. Each is fixed by a numbered step below; none may be deferred past the trial start.

| # | Can't-fail signal | Why it is structurally green | Fixed in |
|---|---|---|---|
| S1 | Traffic-triggered trial clock (the originally recommended `TrialClock` auto-arming on the first hosted call) | If no hosted client ever calls, the clock never arms, the month never elapses, deletion never fires. Survival *by* the absence the stop condition exists to punish. | §2.5 |
| S2 | In-process counters only | `CallJournal` holds plain attributes; one Flux reconcile, image bump or OOM zeroes the month. Verdict reads "no demand" regardless of truth. | §2.6 |
| S3 | Optional `trial_started_at` | Unset → phase is `setup` forever → demand counter pinned at zero → delete by inattention. | §2.5 |
| S4 | Empty operator-network set | `classify_caller` (mcp_journal.py:69-96) returns `hosted` for every parseable address when no operator networks are configured. The address veto becomes dead code and today's classification is biased toward **keep**. | §2.5 |
| S5 | Auth failures recorded nowhere | A missing or mis-mounted token Secret 401s every request and journals nothing — the single most likely misconfiguration produces the exact signature of "nobody came". | §2.7 |
| S6 | Demand counted only on `outcome == "ok"` (mcp_journal.py:261-264) | A backend outage or revoked token during the trial converts real demand into silence, and the operator deletes on evidence produced by their own downtime. | §2.6 |
| S7 | No evidence path at all | There is no log aggregation on the estate (`grep -rniE 'loki\|promtail\|vector\|fluent'` over platform/ and clusters/ returns nothing), `mcp_surface` registers no `/metrics` route, and `platform/observability/monitoring.yaml` scopes its ServiceMonitor to `namespaceSelector: {matchNames: [vuoro-system]}` with a name-In selector of `[vuoro-control, vuoro-gateway]`. Nothing can write the counter the verdict reads. | §2.8, §2.9, §5.2 |
| S8 | `CallJournal.record` is never called | `grep -n 'journal\|Journal' mcp_surface.py` returns nothing. The module and its 22 tests guard nothing today. | §2.7 |
| S9 | Blocked-item filter in the adapter | `get_ready_items` discards the blocked branch (`_ = item_with_deps  # not included in ready list`, db.py:2318-2319) and hardcodes `unresolved_blockers: 0` (db.py:2309). A filter on it can never be false. | §2.10 |
| S10 | `prior_attempt_count` | No attempt event type exists; a brand-new pilot workspace with no lane loop yields 0 for the entire trial. A value with no reachable negative case. | Not built — §8 |
| S11 | Removal-test positive control `[[ $run1 == 0 && $run2 != 0 ]]` | Any breakage — typo'd hostname, missing binary, expired token, sandboxed call — exits non-zero and satisfies the gate, including the sandbox failure the control exists to catch. | §4.3 |
| S12 | `grep -rn "mcp"` as a removal assertion | "Returns nothing but incidental prose" has no defined failing state; also `create_mcp_app` already exists unrelated at packages/vuoro-worker/src/vuoro_worker/mcp_server.py:55. | §4.3 |
| S13 | New container outside the digest-pin allowlist | `scripts/validate-deployment-distribution.py:166-170` filters to `{control, migration, gateway, tenant-controller}`; a container named otherwise is never regex-checked, its `imagePullSecrets` assertion is skipped by the `if owned and ...` gate at :182, and its digest never enters `pinned_digests`. The validator prints nothing and exits 0. | §3.4 |

**Rule for all of the above: each guard is forced into its failure case before it is trusted.** Point the manifest at a wrong digest and confirm non-zero exit. Start the app with empty operator networks and confirm it refuses. Drive the demand counter to 1 and back to a fresh journal before the clock starts. A guard that has never rejected anything is not known to work.

---

## 2. Phase 1 — substrate code, no operator involvement, independently valuable

All of this lives in `/projects/dev/vuoro` and is testable offline. **Nothing here touches `app.py` or `composition.py`** — verified: `grep -rn 'mcp_surface\|mcp_journal'` over packages/ matches only the two source files and their two test files. Deleting the connector stays a complete removal.

Baseline to protect: `uv run --package vuoro-service --extra test pytest packages/vuoro-service/tests/test_mcp_surface.py packages/vuoro-service/tests/test_mcp_journal.py -q` → **51 passed** (29 + 22).

### 2.1 Narrow the emitted payloads (do this first — it is the only real injection control)

In `packages/vuoro-service/src/vuoro_service/mcp_surface.py`:

- `WorkReleaseSummary` (:118-125) → `{work_id, title, priority}`. **Drop `repo_id`** (all 26 pending items share one value; it names internal repos). **Drop `tier`** — it is compound prose in reality ("fast-build for the rework to memo D2-D8; operator for the cluster deploy"), median 120 / max 840 chars, and states authority policy ("ATTENDED-SESSION-ONLY in authority"). No honest single-enum mapping exists; a mapper with "drop anything unmatched" is silent lossy misclassification.
- `priority: int` (:123) → **`int | None`**, and omit the key when None. Verified: real items carry `None`, and sprintctl defines NULL as *unprioritized, sorting after any explicit priority* (db.py:517-526; sort key at db.py:2320-2327). Mapping NULL→9 both invents a band and collides with genuine p9.
- `WorkReleaseDetail` (:127-136) → `{work_id, title, objective, acceptance}`. **Drop `description`, `repo_id`, `provenance`, `prior_attempts`.** Truncation is not a fix: #2490's exploit statement is in the first paragraph, #2395's credential list is mid-body, #2465's hostnames are at the end. There is no reliably safe prefix.
- Enforce caps **inside `_summary_payload` (:154-161) and `_detail_payload` (:164-174)**, not in the adapter — the two builders are the single chokepoint both tools pass through and a cap there cannot be regressed by a future `ReadyWorkSource`.
  - `title`: single-lined, capped at **160** (not 120 — 5 of 26 real titles exceed 120 and would truncate mid-sentence). State in a comment that this is a payload budget, **not a confidentiality control**: agentops#2490 discloses an unremediated exploit in 93 characters.
  - `objective`: ≤500 chars. `acceptance`: ≤5 entries × 200 chars.
  - Strip C0/C1 control characters, bidi overrides and zero-width joiners from every emitted string. Narrow, cheap, no false positives.
- **Collapse the double emission.** Today the full JSON goes out twice — `structuredContent` plus `json.dumps` into `content[0].text` (:392-401, :423-432) — so the whole record lands in the model's context even for clients that ignore structured output. Make `content[0].text` a bare reference ("3 ready work items; see structuredContent"). Verified free: no test asserts `content[0].text`.
- Drop the `repr`'d echo of caller input in the not-found branch (:411-416); emit a fixed string, id in `structuredContent` only.
- **Server-side limit** on `list_ready_work` (:386-391): default 20, hard max 50, applied whether or not the caller supplies `limit`. Today an omitted `limit` returns the entire ready set. Verified compatible with `test_list_ready_work_respects_limit` (:294) and the 2-item listing assertion (:289-290).

**Breaks, named:** the fixture at `tests/test_mcp_surface.py:20-42` constructs `WorkReleaseDetail(... description=..., provenance=..., prior_attempts=...)` and `WorkReleaseSummary(... repo_id=...)`. Update it in the same commit.

New tests: `test_title_is_capped_and_single_lined`, `test_control_characters_are_stripped`, `test_null_priority_omits_the_key`, `test_list_ready_work_applies_default_limit_when_none_supplied`, `test_text_block_does_not_duplicate_structured_content`.

### 2.2 `WorkSourceUnavailable` — backend down must never render as "no ready work"

Verified gap: `_call_tool` (:383-402) renders an empty list as `isError: False`, structurally identical to a healthy idle surface.

```python
class WorkSourceUnavailable(Exception):
    def __init__(self, code: str = "work-source-unavailable",
                 message: str = "...", *, retryable: bool = True) -> None: ...
```

`_call_tool` catches it in both branches and returns `isError: True`, `structuredContent = {"error": {"code", "message", "retryable"}}`, **ttl 0** so nothing caches an outage. This is a tool-level error, not a JSON-RPC transport error: the call was well-formed and authorised. The `ReadyWorkSource` Protocol docstring (:138) gains one line: implementations MUST raise this rather than return `()`/`None` when the backend is unreachable. `_EmptyWorkSource` (:147-151) is unchanged — "nothing configured" is a different, honest answer.

Test: `test_work_source_unavailable_is_distinguishable_from_empty` with a source that always raises.

### 2.3 `BearerGrant` gains a label — with a default

`mcp_surface.py:281-283` today is `scopes` only. Add **`label: str = "unlabelled"`**. A defaulted field on a frozen dataclass is source-compatible with the three construction sites (`tests/test_mcp_surface.py:47, :436, :456`), all of which pass `scopes=` by keyword. **Do not add `counts_as_demand`** — two fields encoding one fact can disagree with no defined resolution, and a hosted-labelled grant with `counts_as_demand=False` would silently disarm the counter.

### 2.4 Protocol conformance (dual-era stays; the modern half is not conformant today)

- Add **`2025-11-25`** to `LEGACY_PROTOCOL_VERSIONS` (:78-80, verified to contain only `2024-11-05, 2025-03-26, 2025-06-18`). The spec defines legacy as "2025-11-25 and earlier"; today the most likely legacy client falls through the membership check at :537 and is answered `protocolVersion: "2026-07-28"` — telling a session-based client it is on a sessionless revision.
- Make `server/discover` conformant **additively**: keep the existing `tools` array (`test_server_discover_current_era_no_initialize_needed` at :237 asserts it) and **add** `supportedVersions` (sorted list), `capabilities`, and `_meta['io.modelcontextprotocol/serverInfo']`.
- Implement `UnsupportedProtocolVersionError` (**-32022**) with `data.supported` / `data.requested`, and validate the `MCP-Protocol-Version` header against `SUPPORTED_PROTOCOL_VERSIONS` on **every** request. Today that constant is read at exactly one site (:83, :537) and `_header_body_mismatches` (:344-378) checks header-vs-body agreement only, never membership — so every non-initialize request is served whatever version it claims.
- **Keep both eras.** The spec's matrix lists Legacy-client/Modern-server as "Fails — legacy clients have no fall-forward mechanism", dual-era is "MAY", and deprecated features live ≥12 months. No deadline forces the question. Which revision Anthropic's hosted clients actually emit is unstated in every vendor doc; the trial answers it empirically (§2.6).

Tests: `test_2025_11_25_initialize_is_answered_as_legacy`, `test_server_discover_advertises_supported_versions`, `test_unsupported_protocol_version_header_is_rejected_with_32022`, `test_supported_protocol_version_header_is_accepted`.

### 2.5 The clock: a pure function, a required date, and two hard refusals

Delete the `TrialClock` idea entirely (S1). In `mcp_journal.py`:

```python
PHASE_SETUP = "setup"
PHASE_TRIAL = "trial"
LABEL_HOSTED_CLIENT = "hosted-client"
LABEL_OPERATOR_PROBE = "operator-probe"

def phase_at(now: datetime, trial_started_at: datetime | None) -> str:
    if trial_started_at is None:
        raise ValueError("trial_started_at is required")
    return PHASE_TRIAL if now >= trial_started_at else PHASE_SETUP
```

No mutable state, nothing lost on restart, and the month runs from a date in git **whether or not anyone calls**. The clock's independence from traffic *is* the correction: a traffic-triggered clock cannot express "nobody came".

`CallerIdentity` (:49-67) gains `token_label: str | None = None`, `phase: str = PHASE_SETUP`, `protocol_version: str | None = None`, `era: str | None = None` — all four added to `as_log_fields()` (:59-67) so the durable line carries them. `caller_from_request` (:300-329) gains matching kwargs; the cf-connecting-ip → leftmost x-forwarded-for → peer chain at :316-321 is unchanged. `era` is `"legacy"` when the call arrived as `initialize`, `"modern"` for `server/discover` and `_meta`-carrying requests — this is what makes the client-revision question a query at month end rather than more research now.

In `create_mcp_app` (:299-307), append **optional** kwargs (`_app(**kwargs)` at tests:44-50 setdefaults only `tokens` and `work_source` and forwards the rest — any *required* new kwarg breaks all 29 tests):

```python
journal: CallJournal | None = None,
operator_networks: tuple[IPv4Network | IPv6Network, ...] = (),
trial_started_at: datetime | None = None,
```

and two refusals in the body, both fixing can't-fail signals:

```python
if journal is not None:
    if trial_started_at is None:
        raise ValueError("journalling requires trial_started_at; the stop "
                         "condition cannot run on a clock that never starts")
    if not operator_networks:
        raise ValueError("journalling requires operator networks; with none, "
                         "every caller classifies hosted and the falsifier cannot fail")
```

Note the type change: **operator networks are an already-resolved tuple, not an `OperatorNetworks` object consulted per request.** `OperatorNetworks.networks()` (:155-158) can hit `_refresh` → `_default_resolver` → `socket.getaddrinfo` (:197-199), a synchronous blocking DNS call — never on the event loop, never on the request path. Resolve at construction or on a background refresh.

`journal=None` keeps all 29 surface tests byte-identical (no log lines, no counters).

Tests: `test_journal_without_trial_start_refuses_to_build`, `test_journal_without_operator_networks_refuses_to_build`, `test_phase_at_before_and_after_start`.

### 2.6 Counters that can show both polarities, and that survive a restart

`CallJournal.record` (:242-282), replacing the increment at :261-262:

```python
if caller.phase == PHASE_TRIAL and caller.token_label in self._demand_labels \
        and caller.caller_class != CALLER_OPERATOR and tool is not None:
    self._demand_tool_calls_attempted += 1
    if outcome == "ok":
        self._demand_tool_calls_ok += 1
elif caller.phase == PHASE_SETUP and tool is not None and outcome == "ok":
    self._setup_tool_calls += 1
```

- **Attempted vs. ok is load-bearing** (S6): the stop condition reads *attempted*; `ok` is the health signal. `attempted > 0, ok == 0` is an outage report, not a deletion trigger.
- `demand_labels: frozenset[str] = frozenset({LABEL_HOSTED_CLIENT})` as a new `__init__` kwarg (:226-241). Label is primary attribution; `caller_class != CALLER_OPERATOR` is a **veto only**, reachable because §2.5 refuses to start with an empty network set.
- Day bucket (:265-266) becomes `f"{caller.phase}:{caller.token_label or 'none'}:{caller.caller_class}:{tool or method}"` so setup and trial are separable per day without re-reading the log.
- `_started_on` (:250-252) is set by the first `record()` of **any** kind today, which is exactly refinement (a) failing — a setup smoke call starts the month. It is no longer the clock; keep it only as an observability field, clearly named `first_record_on`.
- `JournalSnapshot` (:202-216): rename `hosted_tool_calls` → `demand_tool_calls_ok` (the meaning changed; the old name misleads), add `demand_tool_calls_attempted`, `setup_tool_calls`, `unauthenticated_calls`, `process_started_at`, `restart_count`. `hosted_runtime_ever_reached()` (:212) returns `demand_tool_calls_attempted > 0` and gains a docstring stating the authoritative month-end answer is the durable log query, not this value.

**Durability (S2).** Add an append-only JSONL sink: `CallJournal(..., store_path: Path | None = None)`. On every `record()`, append one line; at construction, replay the file to rebuild counters and increment `restart_count`. Mount it at `/var/lib/vuoro-mcp/journal.jsonl` on a small PVC. Without this the verdict is computed from a counter that a Flux reconcile resets to zero — on a single-node k3s cluster where reconciles are routine. The month-end verdict is computed by a script over the JSONL (§6), not from process memory; the in-memory snapshot is corroboration only.

**Test helper breakage, named (S8/defect 2 of topic 1):** `tests/test_mcp_journal.py:31-32` `_caller(caller_class)` sets neither phase nor label, so the new condition flips `test_stop_condition_is_true_after_a_hosted_tool_call` (:102-111) to failing — leaving the file with five negative assertions and **no positive case** for the counter, which is the same disqualifying shape inverted. Extend the helper to `_caller(caller_class, *, phase=PHASE_TRIAL, token_label=LABEL_HOSTED_CLIENT)`, update the five existing stop-condition tests explicitly, and **add both polarities**: `test_setup_phase_hosted_call_does_not_count_but_increments_setup_tool_calls`, `test_operator_probe_label_in_trial_does_not_count`, `test_operator_classified_caller_with_hosted_label_does_not_count`, `test_attempted_increments_when_outcome_is_not_ok`, `test_counters_survive_a_restart_from_the_store`.

### 2.7 Wire the journal — one record per request, in the one wrapper

Do **not** instrument the seventeen return sites in `_handle` (verified at :453, 466, 477, 491, 496, 508, 519, 553, 557, 574, 583, 588, 599, 611, 625, 628, 630, plus :641 and :653 in the 405 handlers). Instrument `mcp_endpoint` (:444-449):

```python
@dataclass
class _CallRecord:
    method: str = "unknown"
    tool: str | None = None
    outcome: str | None = None

@app.post(MCP_PATH, include_in_schema=False)
async def mcp_endpoint(request: Request) -> Response:
    stop_timer = metrics.start_timer()
    record = _CallRecord()
    status = 500
    try:
        response = await _handle(request, record)
        status = response.status_code
        return response
    except Exception:
        record.outcome = "exception"
        raise
    finally:
        stop_timer(status >= 500)
        try:
            _journal_record(request, record, status)
        except Exception:
            LOGGER.exception("journalling failed")
```

Three corrections are baked in: the inner `try/except` is **mandatory** — an exception raised inside a bare `finally` replaces the return value, so telemetry would gain the power to turn a served 200 into a 500. The explicit `except Exception: record.outcome = "exception"; raise` is what makes an unhandled escape distinguishable from a handled 500 at :611 (the two cases with the most diagnostic value); without it `status` stays at its initialiser and the outcome map yields the same `"error"` for both.

`_handle(request, record)` gains exactly **two** assignments: `record.method = method` after the validity check at :507-515 (so the -32020 header/body-mismatch path at :519 carries the real method — intentional), and `record.tool = name` immediately before the `try:` that follows the name check at :586-594. An unknown or missing tool name stays `tool=None` and can therefore never reach the demand counter.

`_journal_record` sits next to `_resolve_grant` (:325-329):

```python
def _journal_record(request, record, status) -> None:
    if journal is None:
        return
    grant = _resolve_grant(request)          # headers only, cheap
    label = grant.label if grant is not None else None
    outcome = record.outcome or _OUTCOME_BY_STATUS.get(status, "error")
    caller = caller_from_request(
        client_host=request.client.host if request.client else None,
        headers=request.headers,
        operator_networks=operator_networks,   # pre-resolved tuple
        token_label=label,
        phase=phase_at(_now(), trial_started_at),
        protocol_version=request.headers.get("mcp-protocol-version"),
        era=_era_for(record.method),
    )
    journal.record(method=record.method, tool=record.tool,
                   caller=caller, outcome=outcome)
```

with `_OUTCOME_BY_STATUS = {200: "ok", 202: "ok", 400: "bad_request", 401: "unauthenticated", 403: "origin_rejected", 404: "method_not_found", 405: "method_not_allowed", 429: "rate_limited", 500: "error"}` placed near the error-code block at :95-105.

- **401s are recorded** (S5). A missing or mis-mounted token Secret now shows as a month of `unauthenticated` with zero demand — a configuration alarm, not a delete verdict.
- The 405 handlers (:639-660) get `request: Request` and record once each with `method="http/GET"` / `"http/DELETE"` — **namespaced**, so HTTP verbs never collide with JSON-RPC method names in the day buckets.
- Ordering stays: origin (:452) and rate limit (:463-473) run **before** auth (:475), so journalled 403/429 records carry no label. Correct, and it must stay — the journal must not become a reason to resolve credentials earlier than the surface does.
- One deliberate coarseness, comment it so nobody "fixes" it: `describe_work`'s not-found answer is HTTP 200 with `isError: True` (:407-421, :625) and journals as `"ok"`. That is right for "was the substrate reached".

Tests in `test_mcp_surface.py` (the 29 existing stay untouched), via `_app(journal=..., operator_networks=(ip_network("127.0.0.0/8"),), trial_started_at=...)`: `test_one_record_per_request_for_each_rejection_path` (403, 429, 401, 400 bad JSON, 404 unknown method, 200 tools/call — assert `snapshot().total_calls == 1` each), `test_unknown_tool_name_records_tool_none`, `test_get_and_delete_each_record_once_as_http_verbs`, `test_call_before_trial_start_counts_as_setup`, `test_call_after_trial_start_counts_as_demand`, `test_failing_journal_does_not_change_http_status`.

**Sandbox/test note:** httpx's ASGITransport sets `scope["client"] = ("127.0.0.1", 123)` (.venv/…/httpx/_transports/asgi.py:92,117), so under test every caller classifies `hosted` unless `127.0.0.0/8` is passed as an operator network. Tests wanting an operator-classified call must pass it.

### 2.8 A metrics/snapshot read path on a second port

`mcp_surface` registers routes only on `MCP_PATH` (:444 POST, :639 GET, :651 DELETE). Nothing exposes `JournalSnapshot`. Add a **second ASGI app on a second container port** serving `/metrics` (Prometheus text, series labelled `{token_label, caller_class, phase, tool, outcome, era}`) and `/journal/snapshot` under a separate scope (`vuoro:journal.read`) on a separate token. The second port is **never routed by the tunnel**, so it is not publicly reachable. Without this, the one-month decision has no evidence source but a log file nobody retains (S7).

### 2.9 `vuoro-service serve-mcp` — the entrypoint that does not exist today

Verified: `packages/vuoro-service/src/vuoro_service/cli.py:28-37` has exactly one serve path, `uvicorn.run("vuoro_service.composition:create_composed_app", factory=True, ...)`. There is no MCP ASGI module and no config plumbing. A Deployment written today would have nothing to invoke — or would run the full composed app and expose the wrong surface publicly.

Add a `serve-mcp` subcommand with a **function-local import** of `mcp_surface` (keeps `app.py`/`composition.py` clean and keeps the module off the composed app's import path). Config, all fail-fast:

`VUORO_MCP_TOKENS_FILE` (mounted Secret → `token → (scopes, label)`), `VUORO_MCP_TRIAL_STARTED_AT` (**required**), `VUORO_MCP_OPERATOR_NETWORKS` (**required, non-empty**), `VUORO_MCP_JOURNAL_PATH`, `VUORO_MCP_ALLOWED_ORIGINS` (**required, non-empty**), `VUORO_MCP_RATE_LIMIT`, `VUORO_MCP_GATEWAY_ENDPOINT`, `VUORO_MCP_WORKSPACE_TOKEN_FILE`, `VUORO_MCP_REPO_ID`, `VUORO_MCP_SPRINT_ID` (optional).

**Refuse to start on an empty or malformed token map** — an empty `tokens` mapping 401s every request and is indistinguishable from "deployed and idle". **Construct a `RateLimiter`** (`vuoro_service.rate_limit`, already imported at mcp_surface.py:63) and pass non-empty `allowed_origins`: `create_mcp_app`'s `rate_limiter` defaults to None and is used only under `if rate_limiter is not None` (:304, :462), and cloudflared routes the hostname **straight to the MCP pod**, bypassing the gateway's 1200/min `public-api` bucket (gateway.py:210-231) entirely. An unlimited public JSON-RPC endpoint on the estate's only public door is not an acceptable trial posture.

Tests: `test_serve_mcp_refuses_empty_token_map`, `test_serve_mcp_refuses_missing_trial_start`, `test_serve_mcp_refuses_empty_operator_networks`, `test_serve_mcp_requires_allowed_origins`.

### 2.10 `packages/vuoro-mcp-edge` — the adapter, in its own deletable package

```
packages/vuoro-mcp-edge/
  pyproject.toml                 # deps: vuoro-service, httpx
  src/vuoro_mcp_edge/{__init__,work_source,composition,__main__}.py
  tests/{test_work_source,test_composition}.py
```

Not in vuoro-service (which does not own domain state, mcp_surface.py:106-114), not in sprintctl (this is a client-side projection over the served API, and sprintctl must not depend on the MCP dataclasses).

**Data path, verified end to end and adopted unchanged:** in-cluster `POST http://vuoro-gateway.vuoro-system.svc.cluster.local:8080/api/invoke/v1` with an ordinary workspace API token (`vuo_pat_...`, security.py:13). Not a DSN — adapter-kit's `build()` (adapters/work.py:18-24) is DSN-only and requires both `dsn` and `repository_id`. Not a direct ClusterIP call to the tenant runtime — it would be refused twice, at the network layer (tenant.py:328-361 admits only the `vuoro-gateway` pod) and at the identity layer (composition.py:890-926 accepts only gateway-signed assertions and refuses to combine with a static registry). The gateway mints the assertion and applies every tenancy, read_only, maintenance and membership check (auth.py:24-69, gateway.py:693-766). **The MCP process holds no database credential and no signing key** — only a revocable workspace token scoped to the pilot workspace.

```python
class ServedWorkSource:
    def __init__(self, *, endpoint: str, token: str, repo_id: str,
                 sprint_id: int | None = None, list_ttl_seconds: float = 15.0,
                 request_timeout: float = 5.0, max_items: int = 50,
                 transport: httpx.BaseTransport | None = None) -> None: ...
    def list_ready_work(self) -> Sequence[WorkReleaseSummary]: ...
    def describe_work(self, work_id: str) -> WorkReleaseDetail | None: ...
    def close(self) -> None: ...
```

- **Sync `httpx.Client`**, not `AsyncVuoroClient`: `_call_tool` (:383-434) is synchronous and the Protocol methods are sync. Reimplementing ~40 lines of envelope POST is cheaper and more honest than running an event loop inside a sync callback. State plainly what is lost: JSON-Schema validation of arguments and results (client.py:200, :240). Compensate with one contract test asserting parsed fields against the `work.read.next-work` / `work.read.item` result schemas captured from a live `GET /api/catalog/v1`, so catalog drift fails a test rather than silently emptying fields.
- Handshake + catalog fetch once at construction; on a `409 stale-catalog` envelope, refetch once and retry **exactly** once (client.py:222-228 clears the cache but does not retry).
- Envelope carries `repo_id` — required for envelope-level authorization of every non-`work.project.*` operation (vuoro_adapter.py:1378-1383).
- **No re-sorting.** `get_ready_items` already returns priority/created_at/id order (db.py:2320-2327) and `application_common.py:339` preserves it. Re-sorting can only diverge from the owner.
- **No blocked-item filter** (S9), or a hard assertion that raises `WorkSourceUnavailable` on a missing or non-zero `unresolved_blockers` so an upstream change is loud. A silent filter that can never be false reads as protection and gives none.
- `describe_work`: `work_id.rsplit("#", 1)` — **not** `split`; repo ids are opaque strings and a `#` in one would silently mis-parse into a wrong repo/id pair. Wrong repo or non-positive-integer id → `None` (genuine not-found, no backend call). Upstream not-found → `None`. **Every other failure raises `WorkSourceUnavailable`** with the upstream `error.code` preserved: timeouts, transport errors, non-JSON bodies, `status != "accepted"`, 5xx, `429 rate-limit-exceeded`, `503 workspace-not-ready` / `workspace-maintenance` / `mutations-frozen`, `401/403 identity-revoked`.
- Cache the 15 s list **success only** — never a failure, never a stale success after a failure. That would launder an outage into a normal answer, the same corruption as answering empty. It matches the advertised `ttlMs = 15_000` (:92-93) and caps gateway load at ~4 req/min/tool. **Cut** the 64-entry detail LRU and the injectable clock — over-engineering for one operator and one month.
- **The mapping is INFERRED, not verified.** The field evidence available here is sprintctl's SQLite DDL (db.py:108-119); the hosted runtime composes `WorkApplication.postgres` over `VUORO_WORK_RUNTIME_DSN` (composition.py:927-929). Confirm with one authenticated `GET /api/catalog/v1` plus one `work.read.next-work` against the live pilot workspace **before** operation names are written into anything irreversible (§3.2).

Tests with `httpx.MockTransport`, no network: `test_ready_list_maps_fields`, `test_null_priority_passes_through_as_none`, `test_detail_not_found_returns_none`, `test_unknown_repo_prefix_returns_none_without_a_call`, `test_timeout_raises_work_source_unavailable`, `test_mutations_frozen_preserves_upstream_code`, `test_stale_catalog_retries_once_then_raises`, `test_failure_is_never_cached`, `test_stale_success_is_not_served_after_a_failure`.

---

## 3. Phase 2 — repo-only cloud work, written and validated but not promoted

Still no operator hardware. Everything here is `git`-side and runs against local validators.

### 3.1 Decide the shape: own namespace, own tunnel, own image

- **Own namespace `vuoro-mcp`**, replicas 1. Namespace deletion is one atomic cascade under Flux `prune: true` (clusters/bootstrap/poc/resources.yaml:49-50).
- **Own Cloudflare Tunnel and own cloudflared Deployment inside `apps/mcp/`**, not a fourth entry in the shared ingress list. The shared ConfigMap is mounted with `subPath` (platform/cloudflared/deployment.yaml:17), so kubelet **never** propagates changes into the container: a shared-tunnel teardown requires a manual `kubectl rollout restart deployment/cloudflared -n vuoro-system` that produces no error when forgotten and leaves the route live indefinitely. A dedicated tunnel removes that silent step and makes the E1 claim literally true — deleting the vendor-side connector revokes the credentials the connector authenticates with, and there is no other door: the Hetzner firewall admits only UDP/51820 from operator CIDRs inbound (terraform/modules/hetzner-k3s-node/main.tf:14-62, every other rule `direction = "out"`), and there is no LoadBalancer, NodePort, Ingress, hostNetwork or hostPort anywhere in apps/, platform/, clusters/ or src/.
  - **One unverified vendor assumption, test it cheaply:** create a throwaway tunnel, run cloudflared against it, delete the tunnel, watch the connector die. Do this before relying on the property.
- **Own GHCR image**, built from `vuoro-mcp-edge`. Do **not** reuse the tenant runtime image: `config/compatibility.json:13` pins `vuoro-service-v0.1.52@sha256:f5c9c6f…` and that same digest is what `verify-runtime-pin.py:65-68` requires inside `VUORO_CLOUD_RUNTIME_IMAGE`, while `packages/vuoro-service/pyproject.toml:7` is at 0.1.71 and `mcp_surface.py` landed after 0.1.52. Making them "the same build" means shipping MCP code inside the image every tenant workspace runs — precisely the objection used to reject folding the surface into the vuoro-cloud replica, and it destroys clean deletion.
- **SOPS Secret goes in `platform/runtime-secrets/`**, accepting a second removal site. The alternative — adding `decryption: {provider: sops, secretRef: {name: sops-age}}` to the apps Kustomization — is a hand-applied change to `clusters/bootstrap/`, a path **nothing reconciles** (the three reconciled paths are ./clusters/operators, ./clusters/vuoro-cloud-poc, ./clusters/vuoro-cloud-poc-apps). That is permanent unreviewed drift between cluster and git for a trial that may be deleted in a month. One extra file in the teardown runbook, asserted by the removal test, is the cheaper risk.
- **Dedicated hostname `mcp.vuoro.cloud`**, not a path under api.vuoro.cloud — a path would require editing the gateway's reserved-prefix guard (gateway.py:693-712), which breaks deletion-is-complete-removal. Cost: the edge WAF guard is scoped to a single `HOST = "api.vuoro.cloud"` constant (scripts/apply-cloudflare-edge-rules.py:34, :77-91), so the new hostname is **unguarded at the edge** unless a matching rule is added — and removed at teardown.

### 3.2 Files to write

Inside `apps/mcp/` (one directory): Namespace, Deployment (own image, **digest-pinned**, `imagePullSecrets: [vuoro-ghcr-pull]`, envFrom the token Secret, probes, securityContext, PVC mount at `/var/lib/vuoro-mcp`), Service (:8080 + metrics port), PVC, ServiceAccount, NetworkPolicies (default-deny; ingress cloudflared-mcp → app:8080; ingress Prometheus → metrics port; egress DNS + TCP 8080 to vuoro-system for the gateway + 443/UDP-7844 for the dedicated cloudflared), cloudflared-mcp Deployment + ConfigMap, ServiceMonitor scoped to `vuoro-mcp`, PrometheusRule for the call-count series.

Note a correction to an earlier claim: an egress policy is required **because** the workload gets its own namespace. In `vuoro-system`, `allow-platform-egress` (network-policies.yaml:26-38, `podSelector: {}`) already grants every pod DNS, 5432 and namespace-wide 8080.

Outside the directory (the permanent removal checklist): one line in `clusters/vuoro-cloud-poc-apps/kustomization.yaml`; the SOPS Secret in `platform/runtime-secrets/` plus its kustomization line; the Secret tuple in `secrets/KUBERNETES-SECRET-CONTRACT.md` and in `scripts/preflight-cluster.py` `REQUIRED_SECRETS` (:9-21, verified); and the new pin class in `scripts/validate-deployment-distribution.py`.

### 3.3 Digest-pin enforcement — a third named class, forced into failure

Add a class for the MCP container with its own digest-pinned regex, **excluded** from the single-identical-digest invariant (:86-92) and from the promotion-tag-agreement checks (:127-146), but **required** to be digest-pinned and to carry `imagePullSecrets`. The `if owned and ...` gate at :182 must be widened to the new class, or the pull-secret assertion still silently skips it.

Then **force it**: point the manifest at a deliberately wrong digest, confirm non-zero exit, revert. The file's own comments at :99-102 record that a tagless checkout once silently passed a candidate — "the very disagreement it exists to catch". An unenforced new container is the same failure wearing a different hat.

### 3.4 The removal test, written now, arm-half runnable only while live

`scripts/mcp-removal-test.sh`, two phases.

**Phase A (arm, run while live):**
- A-1 OPEN: `POST https://mcp.vuoro.cloud/mcp` with the **operator-probe** bearer and a valid `initialize` body → **HTTP 200** with a `protocolVersion` in the result. Record status, body sha256, UTC timestamp. If not 200, the harness is broken and any later "closed" result is void.
- A-2 DISCRIMINATION: same request, garbage bearer → **HTTP 401 with `WWW-Authenticate: Bearer` AND a JSON-RPC body whose `error.code == -32001`**. Assert the pair. *(The original plan asserted HTTP 200 here; verified wrong — mcp_surface.py:476-485 returns `JSONResponse(..., status_code=401, headers={"WWW-Authenticate": "Bearer"})`. Origin reject is 403 at :459, rate limit 429 at :472, parse error 400 at :493. A correct live endpoint would have failed the arm gate as originally written, and the likely repair under time pressure is to loosen the assertion — destroying the one discrimination the whole test rests on.)*
- A-3 CONTROL BASELINE against api.vuoro.cloud.
- A-4 Use the operator-probe token only, never the hosted one — this test must not manufacture demand.

**Phase B (assert closed):**
- B-1 `dig +short mcp.vuoro.cloud` → empty/NXDOMAIN.
- B-2 force-resolve past DNS caching; assert the **outcome class**: no 200, no JSON-RPC body of any shape, **including no -32001**. A -32001 means the workload is alive and merely rejecting the caller — that is not closed, and a naive "did I get a 200?" assertion calls it a pass. Do not assert on 1033 specifically; with the CNAME gone the edge may answer 1016, 403, 404 or a TLS/SNI rejection. B-5 is the authoritative vendor proof; B-2 corroborates.
- B-3 `kubectl get ns vuoro-mcp` → NotFound **while** `kubectl get ns vuoro-system` succeeds in the same invocation, so a broken kubeconfig cannot masquerade as removal.
- B-4 in-cluster probe to `vuoro-mcp.vuoro-mcp.svc.cluster.local:8080` fails to resolve.
- B-5 Cloudflare API: tunnel absent, DNS record count zero, WAF rule ref absent.
- B-6 **machine-checkable file assertions**, replacing the grep (S12): `test ! -d apps/mcp`; `grep -q 'apps/mcp' clusters/vuoro-cloud-poc-apps/kustomization.yaml` must **fail**; the MCP container name absent from the owned set in validate-deployment-distribution.py; the MCP tuple absent from preflight-cluster.py `REQUIRED_SECRETS`; `platform/runtime-secrets/<mcp secret>` absent; and **both** `scripts/validate-deployment-distribution.py` and `scripts/preflight-cluster.py` exit 0 after removal.

**Positive control, corrected (S11):** run Phase B twice with the hostname as the only variable. Run 2 targets the still-live api.vuoro.cloud and must **pass its own positive assertions** — `dig +short` returns a non-empty answer **and** an HTTPS request returns a real HTTP status line with a body — before Run 1's closed result may be trusted. "Exited non-zero" is not a control; a typo, a missing binary or an expired token satisfies it.

**Sandbox rule, mandatory:** every network step runs with `dangerouslyDisableSandbox: true`. A sandboxed call returns exit 0 with **empty output**, which a naive assertion reads as CLOSED against a fully live endpoint. This is exactly why the positive control is required rather than nice-to-have.

---

## 4. Phase 3 — operator actions that need no YubiKey

### 4.1 The free availability check (do this first, in parallel with Phase 1)

**Action:** in a browser, sign in to claude.ai → Settings → Connectors → Add custom connector (Team/Enterprise owners: Organization settings → Connectors → Add → Custom). Enter any placeholder HTTPS URL and continue to the second step **without saving**.
**Precondition to verify:** the dialog is the two-step version (name/URL, then Authentication).
**Expected result:** a **Request headers** section is either present or absent under the Authentication choices.
**Send back:** which one; the account plan (Pro / Max / Team / Enterprise); whether the dialog was one-step or two-step. **Do not click Add.**

**If present:** register **one** claude.ai custom connector — Authentication **No sign-in**, request header name `authorization`, value `Bearer <token>` (the leading `Bearer ` and its space are mandatory; Claude adds no scheme), marked **Required** so a missing credential fails the connection rather than hitting the surface unauthenticated. One registration reaches claude.ai, Desktop, mobile and Cowork. It forecloses nothing: immutability is per-connector, the OpenAI Responses path needs no registration at all, and Managed Agents keeps auth in a vault per session.

**If absent:** **do not register an authless connector as a substitute** — a No-sign-in connector with no header is a different threat model entirely. Instead prove the surface with **Managed Agents** and a `static_bearer` vault credential (Anthropic-hosted, rotatable, no wrong-first-choice penalty), and request request-header beta access through Claude support in parallel.

**Do not lead with the OpenAI Responses API.** It is the cheapest to try and the least informative — no registration, no immutability, and no evidence about the Anthropic surfaces the substrate actually runs on. Keep it as a second prover. ChatGPT developer mode is out entirely: it supports only OAuth / no-auth / mixed, with no static-header field.

### 4.2 Confirm the catalog before the adapter's operation names are relied on

**Action:** one authenticated `GET /api/catalog/v1` through the gateway for the pilot workspace, plus one `work.read.next-work` invocation.
**Precondition:** the workspace API token's actor is an **active member** — `auth.py:24-69` fails closed on a missing user record (500 `principal-unknown`) and on non-active membership (401 `identity-revoked`), checked per request with no cache.
**Expected result:** the `work-api/v1` catalog is composed and both operations appear with the argument/result schemas the adapter assumes.
**Send back:** the catalog revision and the two operations' result-schema field lists.

### 4.3 Cloudflare and credentials

- Create the **dedicated tunnel**, its credentials JSON, the `mcp.vuoro.cloud` CNAME, and a **WAF rule** for the new hostname mirroring the shape in `scripts/apply-cloudflare-edge-rules.py:130-158`. Send back `dig +short mcp.vuoro.cloud`.
- Mint **one** `vuo_pat_` workspace API token (active member) and **two** MCP bearer tokens labelled `hosted-client` and `operator-probe` (a third if Managed Agents is wired). All as mounted Secrets, never env literals. Send back token ids only.
- **If the Anthropic egress allowlist (160.79.104.0/21) is applied at Cloudflare, include the operator's own WAN address in the same rule.** Otherwise the operator-probe token becomes unusable, out-of-band liveness checking dies, and a broken surface becomes indistinguishable from an unused one — which turns an outage into a delete verdict. Re-read the published range the day it is applied, and remove the rule deliberately if a non-Anthropic prover is ever introduced.

### 4.4 Decisions the operator owns

Which workspace and `repo_id` the pilot slice lives in; pinned `sprint_id` or active sprint; **who may create items in the pilot workspace** (this is the strongest available injection control and it is policy, not code — an injection payload has to get into the record before it can get out); and whether to raise with the gateway owner that `mutations-frozen` (gateway.py:244-259) blacks out these *reads*, because the invocation envelope is a POST. Either exempt catalog-bucket `read` operations, or accept that freezing mutations dark-fails the trial surface and let it surface as the preserved error code.

---

## 5. Phase 4 — the one step that requires hardware

Promotion. `clusters/bootstrap/poc/resources.yaml:6-12` defines the GitRepository with `verify: {mode: TagAndHEAD, secretRef: {name: vuoro-cloud-promotion-keys}}`; Flux will not fetch a revision unless both tag and HEAD carry a signature from a key in that Secret, and the only key there is hardware-held (YubiKey 22905026, touch-to-sign) — the former software key CF88DB9B was retired from both trust points on 2026-09-12 (commits 0e223fe, f6d2c42). `scripts/promote-release.sh:30-34` states flatly it "is not a fallback". Two signatures per release: expect one PIN prompt and **two touches**, and merge fast-forward (no squash) so the signature survives.

**Consequence: batch MCP changes.** Budget one or two promotions for setup and no more. Everything up to the signature is automatable; the signature never is.

---

## 6. Phase 5 — setup phase: force every check into its failure case, then start the clock

The trial clock does **not** start until all of the following have been observed, in this order:

1. **Pin check fails on a wrong digest**, then passes on the right one.
2. **The app refuses to start** with no `trial_started_at`, and again with empty operator networks, and again with an empty token map. Three refusals, three observed failures.
3. **Gateway reachability:** `kubectl -n vuoro-mcp exec deploy/vuoro-mcp -- curl -s -o /dev/null -w '%{http_code}' http://vuoro-gateway.vuoro-system.svc.cluster.local:8080/api/meta/v1/handshake` returns **401** (reached, unauthenticated) rather than hanging. Send back that status code.
4. **The evidence path exists.** Make one `operator-probe` tool call and confirm the series appears in Prometheus with `token_label="operator-probe"`, **and** that the line landed in `/var/lib/vuoro-mcp/journal.jsonl`. If either is missing, the evidence path is broken and the clock does not start. This is the single step that prevents a month of guaranteed zero (S7).
5. **Prove the demand counter can increment** (this is the positive case that excluding the smoke call otherwise removes): set `trial_started_at` to yesterday, make one `hosted-client` tool call, observe `demand_tool_calls_attempted` go 0 → 1, then **delete the journal file and reset**. A classification with no observed positive case is as disqualifying as one with no negative case.
6. **Restart the pod and confirm the counters reload** from the store with `restart_count` incremented.
7. Only then: set the real `VUORO_MCP_TRIAL_STARTED_AT`, promote, and write a dated note on **agentops#2465** naming the transition instant and the two token ids.

**Managed Agents counts as a prover, not as demand.** It proves an Anthropic-hosted runtime can reach the surface; it never advances the trial clock. This replaces the earlier "count it only when the session was started by a trigger the operator did not press that day" — the server sees a bearer token, a source address and headers, and cannot know how a session was triggered; a vault credential is bound to a URL at session creation, not per trigger. Encoding it in the label means hand-swapping tokens per invocation forever, which a single operator will not maintain, which means the rule gets silently reinterpreted at the one-month mark — the exact outcome the refinement was accepted to prevent.

---

## 7. Phase 6 — the month-end decision procedure, written down now

At `trial_started_at + 30 days`, run `scripts/mcp-verdict.py` over `/var/lib/vuoro-mcp/journal.jsonl` (the durable record; the in-process snapshot is corroboration only):

- **Refuse to render a verdict** unless `trial_started_at` is set and `days_elapsed >= 28`.
- Count lines with `phase="trial"`, `token_label="hosted-client"`, non-null `tool`. **Zero → DELETE.** The default answer on that date is delete.
- **But:** non-zero `unauthenticated` with zero demand → **configuration alarm, not a delete verdict** (S5). `attempted > 0` with `ok == 0` → **outage report, not a delete verdict** (S6). `restart_count` with a journal file that was ever missing → evidence gap, extend rather than resolve by guess. A non-zero `unknown` caller class, or label/class disagreement, → evidence is ambiguous; extend.
- The same query answers the open protocol question for free: which revision hosted clients emit, and whether they open with `initialize` or go straight to `server/discover`.

Retention: the JSONL on the PVC is the record of truth precisely because there is no log aggregation on this estate. If the PVC is declined, ≥35-day retention for the pod's structured stdout must be arranged **before** the clock starts, or the month has no substrate.

---

## 8. What I would not do, and why

- **Mount the surface into `vuoro_service.app.create_app`.** Explicitly out of scope; it is what makes deletion a complete removal, and that property is verified today.
- **Build the traffic-triggered `TrialClock`.** It reproduces the exact failure it was proposed to avoid: if the hosted client never calls, the clock never arms and the surface survives by the very absence the stop condition exists to punish (S1).
- **Emit `tier`, or build a tier→enum mapper.** Compound prose, no faithful mapping, and its content is authority policy.
- **Emit `prior_attempts` or `prior_attempt_count`.** The text is the highest-density sensitive content in the record (what broke, on which host, with which credential) and the count has no source event type — structurally 0 for the whole trial (S10). If wanted later: define it against one named event type and require a test that produces a non-zero count from real event data before shipping.
- **Parse `acceptance` or `objective` out of an existing internal `description` body.** Measured on the real corpus, Acceptance sections alone (median 368 / max 709 chars) contain `vuoro-shared.apps.kotona.app`, eight distinct absolute paths including `/home/agent/.local/share/lane-loop/implement.md`, and six backticked kubectl/aws/sprintctl/curl/git command lines. Same authors, same risk class, smaller box. If the pilot workspace cannot carry an external-facing authored field, ship `{work_id, title}` and `{work_id, title}` and nothing else — that is the fallback, not the default.
- **Build imperative-stripping, delimiter/fencing schemes, HTML/JSON escaping as an injection defence, or secret-keyword denylists.** The corpus kills all four: 31 imperative constructions appear across 26 *legitimate* items (so a filter mangles real content while an attacker rephrases declaratively); fences require the *consuming* runtime's system prompt to honour them, which the substrate neither controls nor can verify; the consumer is a language model, not a renderer; and the sensitive strings are `hel1.your-objectstorage.com`, `appservice-pgdump-locked` and "does not verify commit or tag signatures", none of which match any secret-shaped keyword. A `contentNotice` field is a hint, include it if wanted, but **never count it as the mitigation**. The only control the substrate owns is which bytes it emits.
- **Reuse the tenant runtime image, or fold the surface into the vuoro-cloud replica.** Both put MCP code in the image tenant workspaces run and destroy clean deletion (§3.1).
- **Change the Flux apps Kustomization to add SOPS decryption.** Permanent unreviewed drift in a path nothing reconciles, for a trial that may be deleted (§3.1).
- **Use a Postgres DSN, or call the tenant runtime directly.** Refused at both the network and identity layers, and it would put a database credential in a publicly-exposed pod.
- **Register an authless claude.ai connector if the beta is unavailable.** Different threat model than the one this design prices.
- **Migrate homelab history, or dual-write into both estates.** Out of scope by the decision already taken; it happens only if the trial proves out.
- **Build per-tool dashboards, alert rules beyond the single call-count series, or a second environment.** One operator maintains this and it may be deleted in a month by design.

---

## 9. Ordered summary

| Order | Work | Needs operator? |
|---|---|---|
| 1 | §4.1 free connector-availability check (browser only) — gates all vendor/cluster work, gates no code | Yes, no hardware |
| 2 | §2.1–2.4 payload narrowing, `WorkSourceUnavailable`, `BearerGrant.label`, protocol conformance | No |
| 3 | §2.5–2.7 phase function, counters with both polarities + durability, journal wiring with the two construction refusals | No |
| 4 | §2.8–2.9 metrics/snapshot port, `serve-mcp` with fail-fast config and a rate limiter | No |
| 5 | §2.10 `vuoro-mcp-edge` adapter + MockTransport tests | No |
| 6 | §4.2 live catalog confirmation (mapping is INFERRED until then) | Yes, no hardware |
| 7 | §3 manifests, third pin class, secret contract, removal-test script — written, validated locally, **not promoted** | No |
| 8 | §4.3 Cloudflare tunnel/DNS/WAF, three tokens, throwaway-tunnel revocation test | Yes, no hardware |
| 9 | §5 promotion | **Yes, YubiKey** |
| 10 | §6 setup phase: force all seven checks into failure, prove the counter increments, reset, then start the clock | Yes, no hardware |
| 11 | §7 month-end verdict; §3.4 removal on DELETE | Yes (R1–R3 vendor cuts need no hardware; R4–R5 do) |

The critical path to a *useful* surface is §2.10, not the manifests: `ReadyWorkSource` is a Protocol with no implementation and `work_source` defaults to `_EmptyWorkSource` (:144, :320), so without it the surface is reachable and answers empty. The critical path to an *honest* trial is §2.5–2.8 and §6: without them the stop condition reads zero for reasons that have nothing to do with demand.