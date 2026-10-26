# AE-01 real-capture handoff

**Status (2026-10-26): blocked; real-capture acceptance remains open.** This is a source inventory and owner handoff, not capture evidence. No native Claude Code or Codex session was recorded, no source bytes were verified, and no live binding was inferred.

## Inspected surfaces

| Required source | Current Agentops or related surface | Gap |
| --- | --- | --- |
| Native stop | `hooks/log-session-cost.sh` accepts Claude Stop fields including `session_id`, `cwd`, and `transcript_path`. Its Claude cost snapshot reads the transcript. The Codex branch records `session_id`, `turn_id`, and a project label through `auditctl add`; it does not read a transcript. | The event has no durable source artifact reference. The checked-in `.claude/settings.json` has permissions but no `hooks` registration. `.codex/` contains role presets but no native hook config. `agentops.dispatch.json` has `provider_adapters: []`. The prescribed `/projects/dev` mount is absent here, and `claude` is unavailable; installed host-level registrations cannot be confirmed. |
| Git commit | The Stop event contains a working-directory string. Agentops's Stop publisher does not read or emit a commit SHA. | A post-hoc `HEAD` lookup would not prove which tree a test used when the worktree was dirty or the test preceded a commit. No event binds a native session to an exact commit/tree. |
| Test result | `hooks/gate-log.sh` records matching Bash commands and derives a heuristic verdict from tool-response text; it records `exit_code` only if the provider supplies it. Compound commands can be unattributable. | The local gate log and its sidecar are not immutable result artifacts or refs. The hook has no tested-tree identity. Test output cannot be treated as a stable result ref or copied into telemetry. |
| Durable delivery | `auditctl add` writes through Auditctl's SQLite plus NDJSON path and assigns an origin stream/sequence. Its write/rebuild protocol covers a crash between those copies. | Each `add` invocation gets a new event ID; Agentops's hook has no stable source key or automatic retry reconciliation. Reinvoking a hook can create another observation. The gate sidecar path is explicitly not an Auditctl artifact ref. |

Related ownership evidence:

- Agentops `docs/plans/agentops/state-event-command-matrix.md` assigns the harness-neutral Tier-0 session wrapper to ActionQ and capsule/exhaust contracts plus cross-domain projection to Agentops.
- ActionQ `HANDOFF.md` records deletion of the session wrapper with the retired execution plane. Its remaining `completion_outbox` is capsule-keyed; `tests/test_completion_outbox.py::test_stream_identity_sequence_and_event_ids_survive_restart` and `::test_lost_ack_retry_digest_quarantine_and_health` cover its own producer semantics, not Agentops native Stop, commit, or test-result capture.
- ActionQ `packages/actionq-runner` has managed-dispatch source and result-artifact contracts. Those contracts are not wired to these interactive native hooks and cannot stand in for their missing references.
- Auditctl `docs/contracts/publisher-subprocess.md` says publishers must not blindly retry `auditctl add`: a fresh invocation may create a second valid observation.

## Smallest owner handoff

1. **Agentops host integration owner:** identify the supported host/configuration and register the existing minimal native Stop hooks for Claude Code and Codex. Return a redacted registration/read-back check and one native event from each harness. The Claude capture must not use `transcript_path` as evidence; the Codex capture must preserve its event as a turn observation rather than claiming session completion.
2. **ActionQ runtime owner:** provide the session-lifecycle capture path assigned by the state-event matrix, or explicitly reassign it. Bind each source observation to the observed native session/turn, exact repository identity, tested commit/tree, and immutable test-result ref plus digest. If the tested tree is dirty, report its bounded diff/tree digest as unknown for commit-based attribution rather than substituting current `HEAD`. Keep the capture producer in its existing owner boundary; do not add an Agentops execution host, queue, or router.
3. **Auditctl publisher owner (only if Auditctl is the chosen durable sink):** agree the stable source identity and recovery path before a caller retries an ambiguous publish. A new `auditctl add` call is not an idempotent retry. Preserve raw prompt, transcript, command output, and absolute paths outside the observation payload; refs and digests must resolve to owner-held bytes.

## Exit evidence still required

- One real Claude Code run and one real Codex run, each with a native Stop ref, a commit/tree ref for the exact tested source, and a retrievable test-result ref/digest.
- A full expected-versus-observed matrix that retains absent hook, commit, or test-result slots as **unknown**. The fixture's simulated missing hook is not a real-run substitute.
- Owner-side restart/retry/outbox evidence: terminate before and after durable append/ack, reopen the producer, retry with the same source identity, show one logical event with stable identity/sequence, and show conflicting reuse is quarantined. A successful local Auditctl append/rebuild test alone does not prove publisher retry semantics.
- Digest re-read verification and privacy checks showing that source refs resolve while transcript, prompt, tool output, credentials, and absolute host paths do not enter the event.

Until those records and tests are supplied, use the fixture replay only for offline denominator, deduplication, conflict, and unknown-slot behavior. Do not mark the two-real-harness, restart, retry, or outbox gates passed.
