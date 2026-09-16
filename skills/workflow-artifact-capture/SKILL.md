---
name: workflow-artifact-capture
description: Use at the end of a workflow or session to classify session outputs, promote reusable examples into committed training artifacts, and route sprint-scoped durable lessons into kctl when appropriate.
---

## Goal

Turn raw session history into the right permanent artifact instead of leaving everything in `.agents/sessions/`.
If the current session cannot mutate sprintctl or the repository, classify the artifact and report the intended destination instead of trying to partially capture it.

This skill separates:
- raw session history
- durable repo knowledge
- curated training artifacts
- out-of-scope idea capture

## Inputs

- One or more source notes under `.agents/sessions/` or `.agents/handoffs/`.
- Any related diff, verification output, sprint state, or review findings needed to explain what actually happened.
- Optional live `sprintctl` / `kctl` context when the lessons came from sprint-scoped work.

## Classification rules

### 1. Leave it as session history only

Keep it only in `.agents/sessions/` when it is mainly:
- raw chronology
- prompt phrasing
- transient dead ends
- local shell noise
- branch-specific execution detail with no reusable training value

Session notes are source material, not the permanent teaching surface.

### 2. Promote it into `kctl`

Use `sprintctl event add` and the `kctl-extract` workflow when the artifact is:
- a durable decision, pattern, lesson, risk, or coordination correction
- tied to sprint-scoped execution
- concise enough to survive as structured repo knowledge

Prefer `kctl` for rules and decisions that should become searchable repo memory.

### 3. Promote it into `docs/training/`

Write a committed training artifact when the value is in the worked example itself:
- a reusable workflow example
- a post-session workflow suitability assessment
- a troubleshooting or verification sequence worth preserving
- an agent-coordination pattern that needs narrative context
- a good or bad execution trace that future agents should imitate or avoid

Prefer `docs/training/` when chronology, command sequence, tradeoffs, and artifact links matter more than a one-line lesson.

### 4. Route it to idea capture instead

If the session surfaced a useful idea that is not yet accepted scope and is not mature enough for training:
- add or update a `docs/notes/*.md` note, or
- convert it into sprint scope later with `sprint-packet`

Do not force speculative ideas into `kctl` or `docs/training/`.

## Training artifact shape

Author workflow training artifacts under `docs/training/` using the template in `docs/training/workflow-artifact-TEMPLATE.md`.

Keep them curated:
- summarize the scenario
- cite the source session note(s)
- explain what makes the workflow suitable or unsuitable
- preserve only the commands, failure modes, and decisions that teach something reusable
- name concrete follow-up changes when the workflow exposed a repo-process gap

## Steps

1. Read the source session note(s) and identify candidate lessons, workflow patterns, and reusable command sequences.
2. Classify each candidate using the rules above: session-only, `kctl`, training doc, or idea capture.
3. If a durable sprint-scoped lesson is missing from live state, add a structured `sprintctl event` with `summary`, `detail`, `tags`, and `confidence`.
4. If a curated training document is warranted, write it under `docs/training/` and link the source session note(s).
5. Update `docs/README.md` when you add a new durable training artifact family that should be discoverable.
6. Keep raw session notes and permanent artifacts separate; the training doc should not become a verbatim session dump.

## Output contract

- The session's lasting outputs are classified explicitly.
- Durable structured lessons are routed into `kctl` when they belong there.
- Reusable narrative examples are captured under `docs/training/`.
- Speculative or out-of-scope ideas are kept out of the permanent training surface unless they are intentionally curated.

## Do not

- Do not treat `.agents/sessions/` as the permanent training library.
- Do not copy full prompt transcripts or shell dumps into committed training docs.
- Do not publish thin or speculative ideas to `kctl` just to preserve them somewhere.
- Do not create a training artifact when a short `kctl` entry or a small note would do.
- Do not silently skip capture when the workflow calls for it; if capture is blocked by permissions or session constraints, report that block explicitly.
