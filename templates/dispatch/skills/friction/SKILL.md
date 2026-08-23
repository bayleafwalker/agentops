---
name: friction
description: Record a workflow friction note (T-5) as an auditctl workflow.friction event while the annoyance is still fresh. Use when a tool, gate, hook, or hand-off wasted time, when the same manual step is being repeated, or when the user says something is annoying, slow, or keeps breaking. Also use when explicitly invoked as /friction.
---

## Goal

Capture one friction note in the same sink the session telemetry uses, so the release scorecard
(T-6) can read friction alongside turns, cost, gates and rework rather than in someone's memory.

A friction note is worth recording when a person or a session lost time to the *workflow*
rather than to the problem: a gate that failed for an unrelated reason, a hand-off that had to
be redone, a manual step that should be encoded, a tool that had to be invoked three times to
say one thing.

## Steps

1. **Write one sentence that names what cost time.** Not the fix, and not the feeling —
   what happened. "The untracked-file guard failed the packet because settings.local.json is
   untracked" is a friction note; "hooks are annoying" is not.
2. **Record it:**

   ```bash
   auditctl add --type workflow.friction --source friction-skill --actor "$USER" \
     --summary "<one sentence>" \
     --metadata '{"session": "<session id if known>"}' \
     --detail "<optional: what would have avoided it>"
   ```

   `--summary` and `--actor` are required by the CLI; `--detail` is where a proposed fix goes,
   so the summary stays a description of what happened.

   **The session id is not a ref.** auditctl accepts only `wi:`, `ka:`, `ad:`, `sha:`,
   `pr:`, `sprint:` and `capsule:` prefixes and rejects anything else outright — the whole
   `add` fails and the note is lost, so a session-scoped ref must not be attempted. That is
   why the session id travels in `--metadata`, the same place the Stop hook puts it. A `--ref` is worth passing only when the friction is
   about a specific commit or PR (`sha:<hash>`, `pr:<n>`).
3. **Do not open an item, edit a plan, or fix the thing** as part of this skill. The note is
   the deliverable. Deciding what to do about it is the scorecard's job, and batching that
   decision is the point of recording rather than reacting.
4. **Confirm briefly** — one line naming what was recorded. If `auditctl` is not on PATH, say
   so and print the note rather than silently dropping it.

## Notes

- Friction notes are cheap and expected to be numerous; a session that records three is not
  complaining, it is producing the input T-7 uses to detect the workflow getting worse.
- The paired sink is `workflow.session` (written automatically by the Stop hook), and the
  paired detector is the "worse" rule: rework rounds up, escalations up, or frontier turns flat
  while cost rises, for two consecutive releases.
