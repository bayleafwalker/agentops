# Session completion alert consumer

This is the AgentOps P4 consumer for the ratified
`session.completion-observed/v1` stream. ActionQ remains the owner of the
session fact, producer outbox, served completion log, and ingest authority.
The consumer only reads that served log and writes AgentOps-owned projection
state; it does not claim, settle, renew, cancel, or otherwise mutate ActionQ,
Sprintctl, or deployment state.

## First route and policy

The first route is `cockpit`. A successful route delivery means that the
bounded alert projection was durably written under the AgentOps completion
alert state root. It does not mean a browser was open or that an operator
acknowledged the alert.

The default policy is `cockpit-terminal-v1`, version `1`:

- alert on non-success terminal kinds (`failed`, `cancelled`, `timed-out`,
  `usage-limited`, and `end-inferred`);
- optionally select a validated closed set in `terminal_kinds`, such as
  `['failed']` or `['cancelled', 'timed-out']`; when present it overrides
  `terminal_mode` and preserves those terminal distinctions;
- suppress successful terminal sessions by the named `success-terminal` rule;
- map failure, cancellation, timeout, usage-limit, and inferred-end facts to
  warning/critical severities;
- accept optional project, harness, actor, and direct/dispatch filters;
- support UTC quiet hours as either named suppression or durable pending
  deferral; and
- keep one receipt per `(event_id, route_id)` and preserve every input event;
  repeated failures within the configured coalescing window produce one
  delivered cockpit aggregate, a suppressed `coalesced` outcome/receipt for
  each repeated event, and a durable child projection linked to the aggregate.

Setting `terminal_mode` to `all` is an explicit policy change. Policy changes
apply to new events. A stored outcome is not re-evaluated unless an operator
or recovery procedure explicitly calls `replayEvent(event_id)`.

## Durable state

The consumer uses an explicit `COCKPIT_COMPLETION_ALERT_STATE_ROOT` (default:
`<artifacts-root>/_agentops/completion-alerts`) and atomically writes:

| Record | Purpose |
|---|---|
| `checkpoint.json` | Last server cursor advanced only after a page's inbox/outcomes/receipts are durable |
| `inbox/<event-id>.json` | Idempotent local copy of the validated event and its digest |
| `positions/<stream>--<sequence>.json` | Detects stream-position digest reuse |
| `outcomes/<event-id>.json` | Explicit `delivered`, `suppressed`, `pending`, or `dead-lettered` result |
| `receipts/<event-id>--<route-id>.json` | Per-route retry/ack history and idempotency key |
| `projections/<event-id>.json` | Safe cockpit-only alert fields |
| `quarantine/<event-id>.json` | Poison input or identity conflict; never silently discarded |
| `health.json` | Last poll, cursor, route, lag, and error observations |

Inbox, outcome, receipt, and projection retention are independent finite
configuration values. Compaction is explicit. Pending and dead-lettered
records are never age-pruned by compaction.

All event, stream-position, and route identities used in filenames are closed
lowercase UUID/route identities. They reject separators, absolute paths,
percent-encoded separators, NULs, and dot components before any filesystem
operation. Invalid identities are quarantined under a hash-derived filename;
the raw identity is not used as a path or stored in the quarantine summary.

## Polling, retry, and recovery histories

The consumer polls at a bounded short interval (default one second) with a
bounded request timeout. A server error leaves the checkpoint unchanged and
records degraded health. Route failures advance the inbox cursor and retry
only that route using bounded exponential backoff; other routes and later
events are not blocked. A pending route is retried from the durable inbox on
the next poll, even when the server returns an empty page.

Duplicate pages are safe because event identity and stream-position digest
are checked before policy/delivery. If a server page reports a cursor gap,
the reader re-reads the last durable cursor in replay mode before checkpoint
advancement. A malformed or conflicting event is quarantined and receives a
dead-lettered outcome while valid events in the same page continue.

Quiet-hour deferrals remain pending in the inbox and are released by later
polling. A changed policy does not rewrite delivered or suppressed history;
explicit replay is the only re-evaluation path. Every input therefore has a
queryable outcome, and every attempted route has a queryable receipt.

The cockpit projection read is strictly read-only: a missing or read-only
state root returns an empty projection and health snapshot without creating
directories, checkpoint files, or health files.

## Runtime boundary

`npm run completion-alert-consumer` runs the bounded always-on poller. The
checked-in systemd unit is only a source-level operator template; runtime
credentials, persistence, network policy, and enablement remain Appservice's
separately authorized responsibility. No unit in this repository performs
deployment or cluster reconciliation.
