# Evidence bundle: AGENTOPS-1280-session-note-tooling hybrid-dispatch test-drive (2026-08-03)

Captured from the devbox `dispatch-ready-20260802` project cockpit while
delivering AgentOps #1280 (session-note writer/reader tooling + skill).
Dispatched as an explicit test-drive of `hybrid-dispatch` beyond its
documented Vuoro-only pilot scope.

## Files

- `packet.json` — the frozen `agentops-task/v1` packet (route `mechanical_bulk`,
  starting_commit `ab7bc84c20308f4299cd27603083de670c76716d`).
- `1-validate.json` — `hybrid_dispatch.py --packet packet.json validate` output.
  Packet is structurally fit; pre-gates satisfied.
- `2-overlay.json` — the OpenCode worker permission overlay the packet would
  have granted (model `opencode-go/deepseek-v4-flash`, bash restricted to
  exactly the one registered gate command).
- `3-prepare.json` — the actual `prepare` stage receipt. **Exit 2,
  `eligible_for_dispatch: false`.** The cold registered-command run
  (`agentops.session-notes.tests`) failed because the coordinator-authored
  oracle (`templates/dispatch/tests/test_session_notes.py`) necessarily
  imports a `session_notes.py` module that did not exist yet at the frozen
  `starting_commit` — nothing implemented the target module before the
  worker would have run.

## Finding

`hybrid_dispatch.py`'s `prepare` stage requires every command in
`allowed_command_ids` to exit 0 *cold*, at the frozen `starting_commit`,
before a worker is ever dispatched. This makes the `mechanical_bulk` route
structurally unable to support "coordinator writes a failing oracle, worker
implements code to satisfy it" for genuinely new functionality — the oracle
is inherently red before anything exists to make it green. The one real
shipped example packet for this route
(`templates/dispatch/hybrid/example-task-packet.json`, VUORO-1252) fits a
different, narrower shape instead: writing new tests for already-existing,
already-passing behavior, where the cold baseline is trivially green.

Classified as `task_defect` for this packet shape (not a route failure, not
a qualification gap — the live policy already lists `agentops` in the same
named pilot as `vuoro`, contradicting `docs/runbooks/hybrid-dispatch.md`'s
stale "vuoro-only" prose). #1280 was completed coordinator-direct instead,
against this same frozen, unmodified oracle — see
`templates/dispatch/tests/test_session_notes.py` in agentops main
(merged via PR #23, commit `95de345`).

## Related

- AgentOps #1280 (sprintctl item), notes #2306.
- `docs/dispatch/handover-2026-08-03-actionq-2034-2035-status.md` (this
  session's other deliverable, PR #22, merged commit `ea8d15c...95de345`
  range).
- `_artifacts/agentops/audit/events-2026-08-03.ndjson` — auditctl entries
  for this session's incidents.
