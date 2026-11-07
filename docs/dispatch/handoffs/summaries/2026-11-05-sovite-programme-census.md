# Sovite programme census, 2026-11-05

Session-local; canonical source clone /tmp/sovite-programme-20261105, base 33d6fef6df4d306afca29628b1dd6c75b5c964a8 / tree fc28885e7afee6158a68452bf516c15ecea3c8a4. This is source inspection, not proof of deployment, field execution or parent acceptance. Requirements: docs/plans/2026-10-24-portable-agent-workflows.md SV-PW1–5 and agentops docs/dispatch/programmes/2026-10-24/05-sovite.md.

## Owner and callers

- `sovite/lease_service.py` owns reserve, start, bounded recovery, claim, renew, handback and finish; its local trusted caller `sovite/worker.py` wraps these and owns `run_once`/execution. Direct reserve invokes bounded recovery on its fresh-reservation guard; `claim` also invokes recovery.
- `sovite/execution_api.py` owns authenticated internal pull/start/renew/status/handback/complete/lookup routes; `sovite/remote_execution.py` handles remote mutation/status/lookup, and `sovite/execution_client.py` is the client. The external pull/start wire chooses `agent-http-v1`; it is not a repository execution profile. Shared generated wire changes remain Vuoro-owner work.
- `sovite/repository_runs.py` owns explicitly composed repository capability/submit/cancel/recover and executor/budget paths. `sovite/repository_currentness.py` checks and rechecks installed owner hooks; it explicitly says network reads and local commits are not atomic. Native VM implementation in `sovite/repository_native_vm.py` is guarded by fixed Cloud-owned descriptor/observer, source/config checks and signed qualification; fixtures do not qualify a real host. Candidate export/recovery modules are separate seams, not independent execution authority.

## Confirmed queue fairness findings

- Canonical `LeaseService._reserve_once` selects first 100 eligible-time Jobs globally by `(created_at,id)` before checking compute pool and profile. With 101 real producer-admitted foreign-pool Jobs before one eligible local Job, an ordinary local reserve returns idle. A test in the candidate checkout fails on clean canonical base and passes on proposed foreign-pool prefilter, both SQLite and PostgreSQL. It verifies foreign Jobs remain queued without leases.
- Partial fix prefilters using existing recovery scope SQL, which conservatively retains malformed/unknown compute identities, before the same ordered 100-row lock window. It does not change owner API, journal or fence. Independent source/backend review and exact CI remain required.
- This is not general dispatch fairness: a separate isolated negative probe `/tmp/test_sovite_fairness_residual.py` shows 101 earlier same-pool repository jobs cause ordinary local answer worker to return idle while an eligible local answer Job remains. Saturated or otherwise repeatedly skipped rows can likewise occupy the bounded window. This requires separately reviewed bounded scan/progress semantics; simply expanding a limit is not fairness. Avoid unreviewed cursor, denial or wire changes.

## SV-PW profile status and open qualification

SV-PW1: capability discovery and local currentness hook are implemented; current external execution profile is answer-only and shared generated progress/renewal extension remains a Vuoro-owner dependency. No full adapter capability/evidence freeze is inferred.
SV-PW2/3: repository workspace, native VM driver, attempt-budget and recovery source seams exist; real qualified native host, exact predecessor quiescence and ambiguous effect histories require owner and field evidence. No native launch or provider-resume qualification inferred from code.
SV-PW4: protected Cloud observer/descriptor and qualification checks exist in source. No inference of an enrolled, commissioned host, capacity or live host identity.
SV-PW5: candidate/export and exact-copy recovery seams exist in source; full capture lineage, unknown cost/usage, complete export scan and release under exact recipient/source/destination still need evidence-backed qualification. Wire and raw-log access remain closed.

Do not infer delivered work, currentness, native capacity, effect cessation, field qualification or acceptance from a source slice. Work31 actual phases remain unbound; no production/grant/migration/shared effects in this exercise.
