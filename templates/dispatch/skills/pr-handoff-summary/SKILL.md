---
name: pr-handoff-summary
description: Use when preparing a final implementation handoff or reviewer-facing PR summary for completed dispatch work.
---

## Goal

Render a compact reviewer-ready summary of what changed, what was verified, and what still needs attention.

## Inputs

- Final diff or stable changed path list.
- Verification results.
- Review findings and remediation status.
- Dispatch packet refs: action id, work item, sprint, branch, commit, or PR.

## Steps

1. Summarize the implemented outcome, not a file-by-file changelog.
2. Call out the highest-signal files, contracts, or docs for review.
3. Include exact verification commands already run.
4. Include unresolved risks, follow-ups, or skipped checks.
5. Preserve structured refs so actionq, auditctl, and PR tooling can cross-link the work.

## Output Contract

- Short summary.
- Verification section.
- Review or residual-risk section.
- Structured refs when available.

## Do Not

- Do not omit failed or skipped verification.
- Do not substitute this summary for a findings-first review when review is required.
- Do not bury blockers in a general summary.
