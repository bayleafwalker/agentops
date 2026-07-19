---
name: kctl-extract
description: Use at sprint close to extract durable knowledge and coordination lessons from sprintctl events into the kctl review pipeline.
---

## Goal

Recover durable knowledge and coordination lessons from sprint events before the sprint goes stale. This is the sprint-close step that feeds the knowledge pipeline.

## Inputs

- A closed or nearly-closed sprint with events logged via `sprintctl event add`.
- A loaded project DB via `.envrc` or exported `SPRINTCTL_DB` and `KCTL_DB`.
- Optional explicit event types when default filtering is not sufficient. Defaults come from `KCTL_EVENT_TYPES` or the tool's built-in durable+coordination set; coordination types worth passing explicitly via `--event-types`: `claim-handoff`, `claim-ownership-corrected`, `claim-ambiguity-detected`, `coordination-failure`.
- Process, coordination, or workflow corrections logged during the sprint when they were discovered, even if extraction waits until sprint close.

## Event Payload Quality

`kctl` extracts candidates from event payloads. A bare event with no payload fields produces a thin candidate: a reminder that something happened, not a durable record. Always include:
- `summary` — one sentence: what was decided or learned. Becomes the candidate title.
- `detail` — reasoning, context, or alternatives considered.
- `tags` — JSON array of topic tags.
- `confidence` — `high`, `medium`, or `low`.

Pass the fields through `--payload` when recording the event:
```bash
sprintctl event add --sprint-id <sprint-id> --item-id <item-id> \
   --type decision --actor <actor> \
   --payload '{"summary":"<decision or lesson>","detail":"<reasoning and alternatives>","tags":["<topic>"],"confidence":"high"}'
```

Log events at the moment a decision is made or a blocker resolves — not retroactively at sprint close, where context is lost.

## Steps

1. Load the project DB via `.envrc` or exported `SPRINTCTL_DB` and `KCTL_DB`.
2. Run `kctl preflight --sprint-id <id>` or `sprintctl maintain check --sprint-id <id>` first so stale-item or sprint-health warnings are visible.
3. Confirm the sprint has meaningful events logged. If none, note that extraction will yield no candidates.
4. Extract:
   - `kctl extract --sprint-id <id>` for the default event set.
   - `kctl extract --sprint-id <id> --event-types ...` for deterministic filtering.
5. Run `kctl review list --kind all` to see all extracted candidates. Use `--json` when consumed by another agent or script.
6. Use `kctl review show --id <n>` for candidates needing closer inspection.
7. For each candidate:
   - `kctl review approve --id <n> --title "<concise title>" --tags '["<tag>"]'` for worth keeping.
   - `kctl review reject --id <n> --reason "<reason>"` for duplicates, noise, or low-signal entries.
8. Run `kctl review list --status approved --kind all` to confirm the promoted set.
9. Run `kctl status --sprint-id <id> --kind all` to confirm no unexpected leftovers.
10. When publication is in scope:
    - `kctl publish --id <n> --body "<detail>" --category <decision|pattern|lesson|risk|reference>`
    - For coordination candidates: `kctl publish --coordination --id <n> --body "<detail>" --category ...`
    - Render: `kctl render --output <repo-knowledge-base-path>`
    - Keep the knowledge-base update as a standalone commit.

## Output Contract

- All extractable events reviewed (approved or rejected).
- No candidates left in `candidate` status at sprint close.
- Remaining approved-but-unpublished entries are intentional and visible via `kctl status`.
- If publication was in scope, the knowledge base reflects the published state.

## Do Not

- Do not extract from an empty sprint and expect useful output.
- Do not skip the `preflight` check — stale items affect extraction quality.
- Do not publish without reviewing candidates first.
