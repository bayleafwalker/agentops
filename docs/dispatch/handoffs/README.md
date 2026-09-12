# Structured handoffs (handoff/v1)

Machine-readable session handoffs live here as `<date>-<slug>.v<N>.json`, each
with a rendered `<date>-<slug>.v<N>.md` beside it and, when sprintctl was
available, a `<date>-<slug>.v<N>.sprintctl-bundle.json` referenced by digest.

**The JSON is canonical.** The `.md` is for humans and is regenerated from the
JSON (`agentops handoff render <file>`); nothing reads it back. The ack guard,
the validator and the SessionStart injection all parse the JSON.

This is the machine half of the prose convention in `../handover-*.md`, not a
replacement for it: prose carries narrative a schema cannot, and a handover
document remains the right artifact for a session close that is not launching a
successor.

| Command | Purpose |
|---|---|
| `agentops handoff create` | gather repo state, write the pair |
| `agentops handoff validate <file>` | schema, paths, head, `diff_sha256` **now**, non-empty `next_action` |
| `agentops handoff prompt <file>` | the successor's first prompt |
| `agentops handoff ack <file> --session-id <id>` | claim it; refuses if already claimed |
| `agentops handoff render <file>` | regenerate the `.md` |

Schema: `../../../schemas/handoff.schema.json`.
Implementation: `../../../templates/dispatch/scripts/handoff.py`.
Skill: `/projects/dev/.claude/skills/handoff/SKILL.md`.
Acceptance procedure: `../../verification/handoff-v1-successor-isolation.md`.

`diff_sha256` is sha256 over the bytes of `git diff HEAD` followed by the bytes
of `git status --porcelain`, both run in the repo path. It is what lets a
successor prove the working tree is the one the predecessor left; a mismatch is
a refusal, never a warning.

An acknowledged handoff stays here as the record of the transfer. Do not edit one
by hand — `create` writes `.v<N+1>` rather than overwriting.
