# Output 7 — Open Hypotheses

Unresolved propositions carried forward explicitly, per the plan. None of
these were settled by this assessment; the clean-room comparison must not
treat them as decided.

## H1 — "An external planner can provide ~80%"

**Status: untested, and now better-posed.** The assessment reframes it: the
commodity-shaped share of the kernel is R1 (work registry), R4 (event log),
and most of R8 (projection) — plausibly the "80%" by surface area. But the
consequential share concentrates in R2/R3/R5/R6 (claims with proof, conflict-
detecting resume, fenced queue, cross-machine authority), which no surveyed
category of off-the-shelf planner is known to provide together. The clean-room
question is therefore not "can tool X do 80% of features" but "can tool X own
R1+R4 while a narrow adapter owns R2/R3, without splitting authority in a way
that recreates today's reconciliation cost."

## H2 — Do claim semantics live in the planner or in a narrow coordination adapter?

**Open.** Evidence cuts both ways: claim proof gates *planner* mutations
(argues for in-planner), but every consequential claim behaviour observed
(start-conflict, handoff, recovery) touches only item identity + proof — a
small interface an adapter could wrap around any registry with compare-and-set
semantics. The unfenced-terminal-transition gap in actionq shows partial
fencing is livable; that weakens the claim that deep integration is mandatory.

## H3 — Does knowledge extraction belong in the work system or downstream?

**Leaning downstream, not resolved.** The pipeline's only coupling to the work
system is reading the event log at a watermark. Everything else (review,
publish, render, export) is already downstream. If R4's constrained taxonomy
is adopted, extraction needs nothing from the planner but a stable event feed
— which any candidate external tool with webhooks/exports could provide.
Counterpoint: the review-at-sprint-close fusion (which is why retention works,
Output 4) depends on a boundary signal the work system owns.

## H4 — Should audit remain repo-local?

**Yes for now, but the sharper question is whether audit exists.** With 101
events, 87 mirroring kctl, and zero automated consumers, the observed system
has no audit function distinct from its other logs. The central ingest design
is competent and unexercised. Decision needed before any further audit
investment: name the consumer (compliance? incident forensics? cross-repo
timeline?) or fold audit into the event log + git history it currently
duplicates. Repo-local NDJSON is the cheapest way to keep the option open.

## H5 — Does the cockpit have any unique operational role?

**Narrowed, not closed.** Unique = the two joins (sessions⋈items,
dispatches⋈costs) during multi-agent batches, and possibly the reconciliation
review queue *if* its executor is ever safely enabled. Everything else is
replaceable projection. Test that would close it: run one full multi-agent
batch operating only from CLI output and compare supervision cost.

## H6 (new) — Does the served substrate retire the concurrency-defect class?

The strongest steady-state economic argument for Vuoro-the-service is that
five local-first stores generated ≥7 WAL/serialization defects in the window.
If, two months post-cutover, that defect class has not disappeared (or has
been replaced by distributed-systems equivalents at similar rate), the
substrate's cost/benefit must be re-run.

## H7 (new) — Is heartbeat/TTL liveness needed at all in the work domain?

89/91 expired-active claims with zero observed consequence suggests claim
liveness can be event-driven (release/handoff/recovery + queue-side sweep)
rather than time-driven. The clean-room spec (R2) demotes heartbeats and
deliberately does not choose between server-swept expiry and event-driven
invalidation — the evidence rejects client heartbeat upkeep, nothing more.
If a counterexample incident appears before freeze, restore time-based
liveness to the requirement.

## H8 (new) — How much of the burst workflow is Vuoro-shaped vs model-shaped?

The system is tuned to 2026-era agent limitations (context loss, session
death, token discipline). Longer-context, longer-running agents would shrink
the value of R3 (resume) and parts of R2, while R5/R6 (execution safety,
trust boundary) are model-independent.

**Resolution mechanism (fixed at freeze):** each requirement carries a
model-sensitivity tag in the reduced spec's confidence table (R3 High;
R7 Medium-high; R2/R4/R8 Medium; R1/R5/R6 Low). The tags record which
weights to re-evaluate when agent runtimes materially change; during the
clean-room comparison the weights stay frozen. H8 is not a lever for
amending requirements after candidate tools are examined.

## H9 (new) — Do authored session notes add consequential resume value beyond the deterministic bundle, item notes, and decision log?

session-note/v1 (ratified plan, 2026-07) is classified as a **provisional
R3 input surface**, not a ninth requirement. Test during the five timed
resume observations by recording, per resume, which of these held:
(1) the bundle alone was sufficient; (2) an authored note materially
improved the next-action decision; (3) the note restated information
available elsewhere; (4) the note was stale or misleading; (5) meaningful
work produced no note. The plan's coverage metric measures mechanization
success, not product value — the consequential metric is the number of
resumes in which the note changed or materially accelerated the next
action. Promote into the requirements only if notes repeatedly resolve
gaps not reasonably representable in R3/R4; otherwise retain as optional
local convenience or remove the mechanization. Until decided, the scope
fence in R3 holds (no kctl ingestion, no cockpit pane, no new kinds, no
stable served transport, no authority mutation).
