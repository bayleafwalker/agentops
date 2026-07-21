# Workflow Artifact: <short title>

- **Date:** <YYYY-MM-DD>
- **Source session note(s):** <link or "none -- compiled live from conversation/workflow journal">
- **Workflow(s) used:** <script path(s) + run ID(s)>
- **Repos touched:** <list>

## Scenario

<1-3 sentences: what was being dispatched/built/reviewed, and why.>

## Suitability assessment

<Was this workflow shape (tiered dispatch, adversarial verify, pipeline vs
parallel, etc.) a good fit? What would you use again unchanged, what would
you change?>

## Item-level outcomes

| Item | Tier | Build tokens/calls | Verify tokens/calls | Verdict | Closed? | Rework? |
|------|------|---------------------|----------------------|---------|---------|---------|
| repo#id | mechanical/standard/hard | n/n | n/n | confirmed/issues_found/inconclusive | yes/no | describe if any |

## What required rework

<Concretely: which item(s) needed a second pass, why the first pass missed
it, and what it cost (tokens/calls/wall-clock) to fix and re-verify.>

## What was validated vs. not

<Call out anything the verifier could not independently confirm (e.g.
missing test infra) and why -- do not let a caveat get silently dropped.>

## Cost summary

<Total subagent tokens, tool calls, agent count, wall-clock per wave/stage.
Note tier-vs-actual-difficulty mismatches if any tier assignment looks
wrong in hindsight.>

## Follow-up changes named

<Concrete repo-process gaps this run exposed, and whether they were fixed
in this session or left as a recommendation.>
