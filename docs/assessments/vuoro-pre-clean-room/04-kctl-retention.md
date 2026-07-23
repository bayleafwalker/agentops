# Output 4 — kctl Retention Recommendation

Workstream 6, executed retrospectively against all live kctl stores.

## Data

| Store | Candidates | Outcomes | Entries | Window |
|---|---|---|---|---|
| homelab-analytics `.kctl` | 195 | 125 published (121 durable + 4 coordination) · 28 approved · 42 rejected | 125 | 2026-03 → 2026-07 (extraction: Mar 65, Apr 124, Jul 6) |
| central `~/.kctl` | 26 | 1 published · 10 approved · 10 rejected · 5 pending | 1 | 2026-07-14 → 07-19 |
| aligned-equity | 39 | — | 39 | — |
| box | 7 | — | 7 | — |
| sprintctl `.kctl` | 8 | — | 5 | — |

Review latency (homelab-analytics, extract→review): **168 of 195 under 1 day,
27 within 7 days, none beyond**. Review is batched into sprint close (the
sprint-close / item-done skills), not left to accumulate.

Consumption evidence: rendered `docs/knowledge/knowledge-base.md` (1,010
lines) is referenced from homelab-analytics `AGENTS.md`, runbooks, and
training docs — i.e., it enters agent context every session. 12 committed KB
publication commits across sprints. The knowledge-artifact/v1 export is the
cockpit's knowledge pane source.

## Retrospective policy tests (per plan)

| Policy | % candidates expired | Useful knowledge lost | Review burden reduced |
|---|---|---|---|
| 14-day expiry (unreviewed) | ~0% in homelab-analytics (review <7 d always); would have expired the 5 central candidates pending since 2026-07-14/19 | Low — the 5 pending are July-migration notes still recoverable from events | Negligible — there is no review backlog to reduce |
| 30-day expiry (unreviewed) | 0% | None | None |
| Expire unless repeated ×2 | Not directly computable (repetition not tracked in schema). Proxy: coordination-failure events (37) show ≥3 recurrences of the claim-proof-loss pattern → repetition-based promotion has real candidates | — | — |
| Expire unless tied to failed execution / operator intervention | Would retain all 4 published coordination entries (all recovery-linked); would expire most of the 12 rejected coordination candidates *before* review | None observed | ~55–62% of coordination review decisions avoided |

## Findings

1. **Candidate expiry solves a problem this workflow does not have.** Because
   review is fused to the sprint-close boundary, candidates never rot. All
   four tested expiry policies are no-ops on the durable stream.
2. **The coordination stream is the weak semantic.** 22 candidates ecosystem-
   wide, 55–62% rejected, 4 published. Its intake (claim-handoff /
   coordination-failure / ambiguity events) is mostly routine churn. Verdict
   per the plan's taxonomy: *useful semantic with poor retention policy* —
   the signal (recurring failure patterns) is real but buried in routine.
3. **The actual bottleneck is publication, not retention.** Central store:
   10 approved vs 1 published. Publish demands body + category authoring —
   the expensive authoring step is deferred out of the hot-context window,
   which is exactly when the item-done skill says knowledge should be
   captured. The two-step approve→publish split is lifecycle ceremony
   (*useful semantic with excessive lifecycle ceremony*).
4. **Published knowledge has no decay or compaction path.** Append-only,
   supersession exists but is unused; the rendered KB grows monotonically
   (1,010 lines and climbing) and is loaded into context. Unbounded growth
   will eventually convert the KB from asset to context tax.

## Recommended policy

1. **Durable stream: no candidate expiry.** Keep extract→review fused to
   sprint close. (Tested: expiry gains nothing.)
2. **Merge approve+publish for the durable stream.** Approval requires the
   publishable body and category at review time (while context is hot). One
   command, one decision. Estimated effect: removes the approved-unpublished
   backlog class entirely; saves one round-trip per candidate (~26 pending
   ecosystem-wide today).
3. **Coordination stream: 30-day expiry unless (a) linked to a failed
   execution or operator intervention, or (b) operator-promoted.** Estimated
   from live data: expires ~60% of coordination intake unreviewed, loses
   nothing observed, and keeps the recovery-linked entries that were the only
   coordination knowledge ever published.
4. **Add a size budget + supersession-driven compaction to the rendered KB.**
   When the KB exceeds the budget (suggest: 600 lines rendered), oldest
   entries must be superseded/merged before new publications render. This
   makes the existing (unused) supersession semantic load-bearing instead of
   inventing a new one.
5. **High-severity bypass** (per plan): recovery-related and operator-promoted
   items bypass expiry — already implied by rule 3(a).

Estimated review-burden change: −55–62% of coordination reviews; durable
review unchanged (it is not a burden today); publication effort moved, not
added. Estimated loss: none observable in the retrospective record.
