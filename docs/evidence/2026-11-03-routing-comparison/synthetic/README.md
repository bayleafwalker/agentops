# Routing investigation: paired frozen task comparison

Date: 2026-11-03
Durability: this sanitized copy is cross-host replicated in Git; original raw artifacts remain host-persistent and non-authoritative.
Scope: six independently specified, self-contained tasks run once on each arm.

## Method

- Each task has a deterministic oracle derived directly from its prompt. The six prompts cover sequential arithmetic, filter/sort, operator precedence, ordered list transformation, interval scheduling, and a modular sum.
- The exact same user payload was sent on both arms: `Solve this frozen self-contained benchmark task. Do not use tools. ` followed by the task prompt.
- Codex arm: six separate workstation Codex threads, each requested with model `gpt-6.1-terra`; each thread received one task and no tools were requested. Thread IDs and reported elapsed durations are in `results.json`. The model field records the requested route; thread output does not independently attest backend model identity.
- Local arm: direct OpenAI-compatible call to the existing `worker-fast` model at `127.0.0.1:8020`, one sequential request per task, temperature 0, `max_tokens=120`. Endpoint `/v1/models` reported `worker-fast` loaded before the run. HTTP 200 for all six.
- One attempt per task per arm; no retries. Both arms completed all requests. No API key or secret was read or stored. The Codex arm used the existing subscription route; the local arm used the workstation service. No metered API was called.
- T5 independently reproduces a deterministic interval-scheduling task, including half-open boundary and tie-break requirements.

## Results

| Task | Oracle | Codex Terra requested | worker-fast | Outcome |
|---|---:|---:|---:|---|
| T1 sequential arithmetic | `25` | `25` | `13` | Codex correct |
| T2 filter and sort | `date,pear,plum` | `date,pear,plum` | `fig,kiwi,date` | Codex correct |
| T3 precedence | `14` | `14` | `19` | Codex correct |
| T4 dedupe/filter/square/sum | `131` | `131` | `117` | Codex correct |
| T5 interval scheduling | `A,B,D,E` | `A,B,D,E` | no final answer within cap | Codex correct; local incomplete |
| T6 modular sum | `13` | `13` | no final answer within cap | Codex correct; local incomplete |

Observed exact-answer score: Codex requested Terra route 6/6; worker-fast 0/6 under this prompt/cap setup. Local T5 and T6 generated explanatory prose and hit the 120-token cap before returning a final answer; they count as failures under the required answer format. Codex task elapsed durations were 3.24–4.49 s. worker-fast response wall times were 0.147–0.996 s.

## Limitations

This is a six-item pilot, one attempt per item, with a narrow synthetic task set. It measures this exact prompt and generation-cap setup, not broad capability or general routing quality. Model identity on the Codex backend is the requested `gpt-6.1-terra` route, not an independently retrieved serving trace. `max_tokens=120` is a meaningful local-arm constraint and likely explains the two verbose incomplete responses; it was fixed across tasks and not adjusted after observing results. No repeated trials, tool-use cases, code-edit tasks, confidence estimates, or latency distributions were measured. The result supports only these individual observed outcomes.

## Source audit correction

An audit found the initially hand-assembled `results.json` had T1's Terra and worker-fast results transposed. The raw Codex thread returned `25`; the original worker-fast HTTP response returned `13`. `results.json` is corrected, and `source-provenance.json` records the thread ID and local command session ID. The displayed table above already matches those raw results. The corrected exact-answer counts remain Terra 6/6 and worker-fast 0/6.

## OpenCode Go expansion

The separate `opencode-go-results.json` contains six one-shot calls to OpenCode CLI 2.2.1 using the explicit `opencode-go/kimi-k2.7-code` model and the same exact task payloads. Each call set `OPENCODE_PERMISSION='{"*":"deny"}'`; no tool events were observed and no fallback was requested. All six exited 0 and returned session IDs. The model route and successful responses were observed; Go subscription billing/account allocation was **not independently verified** and remains unknown.

| Task | OpenCode Go output | Exact/format match | Oracle present |
|---|---|---:|---:|
| T1 | `25` | pass | pass |
| T2 | `date,pear,plum` | pass | pass |
| T3 | `14` | pass | pass |
| T4 | `131` | pass | pass |
| T5 | `A,B,D,E` | pass | pass |
| T6 | `The final total is **13**.` followed by a breakdown | fail | pass |

OpenCode Go scored 5/6 exact-answer/format matches and 6/6 with the oracle string present. T6 has the right value but violates “Return the final total” by adding a table and explanation. Call durations were 3.95–12.59 s. No errors or tool events were observed. This is a small, one-attempt-per-task comparison and does not establish broader model quality. Billing status is unknown.
