# Failure, Security, and Trust Boundaries

## Failure policy

| Path | Service unavailable | Rationale |
|---|---|---|
| Session/user/subagent projection | fail open; emit no context; record local error | context enrichment must not brick the harness |
| Recognized mutation precheck | fail closed by default | prevents blind mutation when current revision cannot be checked |
| Authoritative mutation API | fail closed | final correctness boundary |
| Post-mutation reinjection | fail open; mutation result still contains new revision | write already occurred; do not fabricate context |
| Cursor update | fail open and allow duplicate next time | cursor is disposable |

An emergency environment flag may make the local precheck fail open, but it must not bypass authoritative CAS.

## Hook bypass

Assume hooks can be disabled, skipped by unsupported hosted tools, bypassed by scripts, or fail to recognize complex shell. Therefore:

- mutation endpoints require expected revisions;
- actor identity and idempotency are verified server-side;
- hooks never grant authority unavailable to the caller;
- validation endpoints do not leak resources outside the dispatch binding.

## Prompt-injection resistance

Provider values may contain malicious or accidental instructions. The projector must:

- emit a fixed structured envelope;
- label values as untrusted data;
- JSON-escape all strings;
- allowlist provider fields;
- remove terminal control characters;
- never concatenate provider content into system instructions;
- avoid arbitrary command-defined providers in repo-owned configuration;
- keep source URI and revision outside provider-controlled text.

This is not a claim that JSON is holy water. It merely stops the projector from volunteering as an instruction blender.

## Secrets and sensitive data

Do not inject:

- credentials, API tokens, kubeconfigs, session cookies, private keys;
- unrestricted environment dumps;
- raw customer/employer data;
- full logs when a bounded status/evidence reference is sufficient;
- internal endpoints unnecessary for the task.

Provider renderers must implement explicit field allowlists and redaction. Hook output may be persisted in transcripts or temporary spill files, so “it is only ephemeral context” is not a secrecy control.

## Endpoint authentication

The local adapter should authenticate to the served endpoint using the existing agent identity/credential broker. Bind authorization to:

- dispatch ID;
- actor/session identity;
- repo UUID;
- allowed provider IDs;
- allowed mutation resource IDs.

Do not accept an arbitrary `dispatch_id` from an untrusted repository without verifying the caller identity and queue-row ownership.

## Timeouts and latency

Suggested initial budgets:

- delta validation: 150 ms p95;
- full session projection: 500 ms p95;
- mutation precheck: 150 ms p95;
- adapter total timeout: 2 seconds for reads, 3 seconds for mutation validation.

Use bounded retries only for snapshot instability, not general network failure. Hook storms are an unimpressive substitute for availability engineering.

## Data retention

- cursor rows: TTL shortly after session/dispatch end;
- projection audit metadata: retain according to normal operations policy;
- raw projection body: do not log by default;
- hand-start fallback binding: expiry required; identifiers only;
- harness transcripts: governed separately by harness retention settings.
