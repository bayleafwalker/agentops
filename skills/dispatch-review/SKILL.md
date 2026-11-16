---
name: dispatch-review
description: Use when a stable code-bearing scope needs findings-first review before handoff or PR prep. Runs read-only review against the diff and repo overlay.
---

## Goal

Produce a severity-ordered, findings-first review of a stable diff using the repo's selected review checklist and specialists.

## Inputs

- The diff or file list under review.
- The dispatch packet, manifest, and repo overlay.
- Relevant requirements, architecture notes, and verification results.
- Repo-selected specialist prompts, when configured.

## Steps

1. Review an immutable checkpoint: an early critical-path slice when useful, or
   the stable candidate. Bind findings to those exact bytes.
2. Read the repo overlay for review specialists, done criteria, and severity definitions.
3. Assemble the smallest useful review context: immutable candidate diff,
   adversarial acceptance criteria, relevant contracts, and focused
   verification results. Do not replay the worker's full context transcript.
4. Run review read-only. Specialist fan-out is allowed only when the overlay selects specialists for this repo.
5. Consolidate findings by severity: blockers first, then advisories, then watchlist.
6. Include exact file references and the evidence behind each finding.
7. Reject vacuous filter/parity coverage: require excluded records, wrong-order
   matches, mutation-sensitive failures, real calls through the claimed layer,
   and assertions stronger than non-empty/list-only checks.
   Own scenario and oracle tightening independently of implementer limits. Check
   that recorded claims are tied to underlying rows, acknowledgements and process
   observations. Version changes and rerun affected checks without rewriting prior
   evidence or quietly introducing a new product requirement.
   Include one substantive simplification pass: unnecessary mechanisms, duplicated
   responsibilities, avoidable state and test scaffolding. Assess brevity with
   correctness/readability across the solution; prefer an explanatory finding to
   cosmetic nits, a file-size threshold or compressed code.
8. If blockers exist, route back to `dispatch-build` for remediation. If
   approved, return an immutable approval reference suitable for the explicit
   integration or repository-full action; do not merge in the review context.

## Output Contract

- Findings-first markdown with severity ordering.
- Open questions and missing coverage noted explicitly.
- No repo edits.
- Clear statement whether the scope is clear for handoff or blocked.

## Do Not

- Do not review a moving target or carry approval across changed bytes without
  examining the relevant delta. Early checkpoint review need not wait for the
  whole implementation to finish.
- Do not suppress findings to create a clean summary.
- Do not make edits from review mode.
- Do not run specialists that the repo overlay has not selected.
