# Contract: Codex Stop audit observations

**Status:** file-backed implementation contract; no served schema is added.

Codex emits a `Stop` hook event after an assistant turn. When the event carries a
nonempty `session_id` and `turn_id`, the shared Stop hook publishes one
`workflow.session` audit observation for that turn with source and actor
`codex-hook`. Its metadata contains only the observed harness (`codex`), session
ID, turn ID, and project label (the basename of event `cwd`, or `unknown` when
`cwd` is absent). The summary identifies a Codex turn; it does not claim that a
session ended.

This event is a per-turn audit observation, not a cumulative session snapshot.
It carries no cost, token, duration, gate, or session-total fields. The hook
must not parse a Codex transcript as a Claude transcript, append a Claude cost
row, or infer session completion. Events missing either required ID are skipped
rather than assigned placeholder identities.

Publication uses the existing auditctl resolver and event-CWD router. Repository
attribution comes only from the existing verified event path; the project label
is descriptive metadata and must not be used to select a repository or store.
The hook remains failure-open for the harness, and publish failures use the
existing audit publish-failure log.
