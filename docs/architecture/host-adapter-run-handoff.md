# Host-adapter run-scoped handoff protocol

Status: **source protocol and example-tested recovery only**. The policy
`run_delegation_qualified` remains false by default; this source change does not
qualify, enable, or launch a live host run. Sprintctl owns the run and
delegation contract in
[`vuoro/docs/architecture/run-scoped-delegation.md`](https://github.com/bayleafwalker/vuoro/blob/main/docs/architecture/run-scoped-delegation.md).

## State and authorities

- Sprintctl is authoritative for the registered run and delegation status,
  expiry, and revocation. The owner returns a delegation token once.
- The adapter's SQLite row is a recovery journal for the inbox/run link and
  `delegation_id`, expiry, mint generation, and handoff state. It never stores
  a token. It is not authority to use the delegation.
- The per-run working directory is adapter-created below the trusted run
  root. `.sprintctl/backend.json` selects the served backend and owner-provided
  repository identity for Sprintctl's exact-CWD client lookup; it carries no
  credential, authority, work state, or Git-checkout claim. The protected
  `.vuoro/profile.json` points only at the sibling per-run credential file and
  the adapter-profile target. The token is the sole secret file.
- The harness session is an external effect. A committed launch intent with no
  session id has an unknown outcome until exact-title search and permission
  inspection either find one session to adopt or fail to establish one.

## Ordered protocol

1. A message and trusted policy must pass the existing acceptance checks. The
   run is registered idempotently and the owner records `run-linked` before
   launch work. Immediately before delegation and again before crossing into
   harness launch, the adapter re-reads policy and cancellation state.
2. Delegation requires `run_delegation_qualified=true`, a trusted per-run root,
   and a trusted adapter source profile. Otherwise the adapter settles
   `not-started`; it never falls back to the inbox or decision credential.
3. Before minting a token, the adapter creates or verifies the run's
   `.sprintctl/backend.json` marker in the exact session working directory. It
   is adapter-owned, mode `0644`, under an adapter-owned `.sprintctl` directory
   mode `0750` with the run directory's inherited group. The marker must equal
   the canonical `{"backend":"served","repo_id":<owner repo id>}` metadata.
   A symlink, wrong owner/group/mode, malformed or different content refuses;
   existing content is never overwritten.
4. The requested TTL is the positive integer minimum of policy
   `max_run_seconds` and four hours; Sprintctl independently enforces its
   parent-run expiry and ceiling. The idempotency key binds message, run, and
   mint generation. Mint only the allowlisted delegated operations.
5. After the one-time owner response, the adapter journals delegation id,
   expiry, and state `minted`, then validates the token's exact `vrd_` plus 52
   base32-character format before creating handoff files. It writes the token
   as adapter-owned mode `0640`, then the profile as adapter-owned mode `0644`,
   both with the run directory's inherited group. It fsyncs both files and the
   `.vuoro` directory before journaling state `installed`. The token is never
   written to SQLite, logs, receipts, prompts, or result records.
6. Only after a final policy/cancellation check does the adapter commit
   `launch_intent` and ask the harness to create the session in the same run
   directory. On restart, exactly one title match with the expected
   permission rules is adopted without relaunch and keeps its delegation. If
   no verifiable session exists, the adapter revokes the delegation before
   recording launch ambiguity. It never relaunches an ambiguous run.
7. On settlement, explicit adapter revocation precedes `result-linked`. A
   failed revoke remains in closing state for retry; the adapter does not
   claim settlement while it is outstanding. Sprintctl also revokes
   independently when it accepts `result-linked`. Handoff files are removed
   only after closure is safe; they are retained while a session remains live
   or recoverable. The served backend marker is non-secret routing metadata
   and remains in the run directory.

## Crash and retry boundary

There is no transaction spanning Sprintctl, SQLite, the filesystem, and the
harness. A crash after mint but before the response is persisted can replay
the same key, but Sprintctl deliberately omits the already-returned token.
Metadata-only replay therefore triggers revoke, a durable generation advance,
and a new mint under the next key; the token file is never reread. A crash
after metadata persistence or during/after file creation follows the same
revoke-and-remint path. A completed handoff is usable only when the journal,
marker, profile, and credential pass their ownership, type, mode, and content
checks. These source tests exercise bounded injected crash points and fixtures;
they do not establish power-loss durability, host-filesystem ACL behavior,
Sprintctl service availability, or live-session qualification.
