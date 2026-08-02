---
name: golden-child
description: Escalate semantic guidance conflicts that deterministic project rendering cannot express. Use when project baseline and repository-specific guidance require human judgment about ownership, precedence, or restructuring; do not use for ordinary missing, stale, or hand-edited generated files or for canonical dispatch-skill synchronization.
---

# Golden Child Semantic Escalation

Use this skill only after the deterministic project renderer cannot represent the
required guidance as project baseline followed by one additive repository override.

## Triage

1. Run or inspect `render_project.py check` evidence.
2. Route mechanical findings back to the owning tool:
   - missing, stale, or hand-edited `.agents/project.generated.md` -> project renderer;
   - missing or drifted shared skill trees -> `sync_skills.py`;
   - malformed project bindings or source frontmatter -> project contract owner.
3. Continue only when the conflict requires semantic judgment that an additive
   baseline and member override cannot encode safely.

## Reconcile

Read the project source fragments, the member override, the member's authored
`AGENTS.md`, and the governing project-binding decision. Identify:

- the exact statements that conflict;
- which repository or integration-policy owner is authoritative;
- why source selection plus an additive override is insufficient;
- the smallest authored-source change that resolves the conflict.

Never hand-edit `.agents/project.generated.md`. Never replace a repository's
authored guidance with a copied project baseline. If a build action authorizes
the semantic repair, edit the owning baseline fragment or repository override,
then run the renderer and commit generated outputs separately as `chore(render)`.

## Report

Return the conflict, compared sources, authority owner, why deterministic render
is insufficient, proposed semantic change, and required verification. If no
semantic conflict remains, stop and route the work to the mechanical tool.
