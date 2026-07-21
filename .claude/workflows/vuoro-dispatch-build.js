export const meta = {
  name: 'vuoro-dispatch-build',
  description: 'Tiered claim -> build -> independent verify -> close pipeline for sprintctl items, grouped per repo to avoid worktree conflicts, with model/effort routed to task difficulty instead of one uniform tier for everything.',
  whenToUse: 'Dispatch/execution phase after a plan has set priorities on chain-head items. Invoke with Workflow({scriptPath: "/projects/dev/agentops/.claude/workflows/vuoro-dispatch-build.js"}, {args: {items: [{repo, item_id, description?, tier?: "mechanical"|"standard"|"hard"}], push?: boolean}}). Omit tier to let a cheap triage pass classify it. Independent repos dispatch in parallel; items in the same repo run sequentially through the same build agent.',
  phases: [
    { title: 'Triage' },
    { title: 'Build' },
    { title: 'Verify' },
    { title: 'Close' },
  ],
}

// Mirrors agentops/templates/dispatch/model-routing.json aliases fast-build / hard-build.
// claude-sonnet-5 replaces claude-opus-4-8 for the "hard" tier now that it's available in
// this harness (2026-07-20) — opus-4-8 is no longer the default for hardest bulk build work.
const MODEL_TIERS = {
  mechanical: { model: 'claude-haiku-4-5-20251001', effort: 'low', actor: 'claude-haiku-devbox' },
  standard: { model: undefined, effort: 'medium', actor: 'claude-sonnet-devbox' },
  hard: { model: 'claude-sonnet-5', effort: 'high', actor: 'claude-sonnet-devbox' },
}
const TIER_ORDER = ['mechanical', 'standard', 'hard']

function maxTier(tiers) {
  return tiers.reduce((a, b) => (TIER_ORDER.indexOf(b) > TIER_ORDER.indexOf(a) ? b : a), 'mechanical')
}

const TRIAGE_SCHEMA = {
  type: 'object',
  required: ['repo', 'tier', 'rationale'],
  properties: {
    repo: { type: 'string' },
    tier: { type: 'string', enum: ['mechanical', 'standard', 'hard'] },
    rationale: { type: 'string' },
  },
}

const BUILD_SCHEMA = {
  type: 'object',
  required: ['repo', 'items'],
  properties: {
    repo: { type: 'string' },
    items: {
      type: 'array',
      items: {
        type: 'object',
        required: ['item_id', 'claim_id', 'claim_token', 'commit_sha'],
        properties: {
          item_id: { type: 'string' },
          claim_id: { type: 'string' },
          claim_token: { type: 'string' },
          commit_sha: { type: 'string' },
          files_changed: { type: 'array', items: { type: 'string' } },
          verification_summary: { type: 'string' },
        },
      },
    },
    blocked: { type: 'string' },
  },
}

const VERIFY_SCHEMA = {
  type: 'object',
  required: ['repo', 'results'],
  properties: {
    repo: { type: 'string' },
    results: {
      type: 'array',
      items: {
        type: 'object',
        required: ['item_id', 'verdict', 'summary'],
        properties: {
          item_id: { type: 'string' },
          commit_sha: { type: 'string' },
          verdict: { type: 'string', enum: ['confirmed', 'issues_found', 'inconclusive'] },
          summary: { type: 'string' },
          concerns: { type: 'array', items: { type: 'string' } },
        },
      },
    },
  },
}

const CLOSE_SCHEMA = {
  type: 'object',
  required: ['item_id', 'closed', 'action'],
  properties: {
    item_id: { type: 'string' },
    closed: { type: 'boolean' },
    action: { type: 'string' },
    note: { type: 'string' },
  },
}

function repoPath(repo) {
  return `/projects/dev/${repo}`
}

function groupByRepo(items) {
  const groups = {}
  for (const it of items) {
    if (!groups[it.repo]) groups[it.repo] = []
    groups[it.repo].push(it)
  }
  return Object.entries(groups).map(([repo, groupItems]) => ({ repo, items: groupItems }))
}

function triagePrompt(group) {
  const itemLines = group.items.map(it => `- ${it.item_id}${it.description ? ': ' + it.description : ''}`).join('\n')
  return `Classify the difficulty of this dispatch work for repo ${repoPath(group.repo)}. cd there, skim AGENTS.md and any repo dispatch manifest (\`*.dispatch.json\`, \`risk_surfaces\`) if present, and \`sprintctl item show --id <id> --json\` for each item below if the description isn't enough.

Items:
${itemLines}

Classify as one of:
- "mechanical": rote, low-risk, a single well-understood pattern applied N times (exports, renames, codegen, config bumps, dependency bumps with no behavior change) — a cheap fast model handles this fine.
- "standard": normal feature/bugfix work, moderate scope, no unusual semantic risk.
- "hard": touches state-protocol semantics (queues, claims, leases, retries, idempotency, reconciliation, backend parity), read-path/parity/staleness logic, or anything the repo's dispatch manifest risk_surfaces flags as required_on_change — needs a stronger model and more reasoning effort.

If items in this group differ in difficulty, classify the whole group at its hardest item's level (never round down — a mixed group blocks on the hard item regardless). Return {repo, tier, rationale}.`
}

async function resolveTier(group) {
  const explicit = group.items.map(it => it.tier).filter(Boolean)
  if (explicit.length === group.items.length) {
    return { repo: group.repo, tier: maxTier(explicit), rationale: 'explicit tier(s) supplied by caller' }
  }
  return agent(triagePrompt(group), {
    label: `triage:${group.repo}`,
    phase: 'Triage',
    schema: TRIAGE_SCHEMA,
    model: 'claude-haiku-4-5-20251001',
    effort: 'low',
  })
}

function buildPrompt(group, tierCfg, push) {
  const itemLines = group.items.map(it => `- item_id=${it.item_id}${it.description ? `: ${it.description}` : ''}`).join('\n')
  const pushLine = push
    ? 'After all items in this repo are committed, `git push origin main` once at the end (this session was explicitly asked to push).'
    : 'Do not push — leave commits local (default for this session).'
  return `Repo: ${repoPath(group.repo)} (cd there first — sprintctl scopes by CWD directory name).

First call the Skill tool with skill "dispatch-build" to load the standard implementation procedure. Then process these items IN ORDER, one fully committed before starting the next — same repo means same working tree, stay sequential, do not parallelize within yourself:

${itemLines}

For each item:
1. \`sprintctl claim start --item-id <id> --actor ${tierCfg.actor} --ttl 3600 --branch main --json\` (record claim_id/claim_token).
2. Implement the item's scope only.
3. Call the Skill tool with skill "code-change-verification" and run the repo's real targeted checks yourself, foreground, blocking, before moving on.
4. \`git commit\` locally (one commit per item, or per tight related scope). ${pushLine}
5. Do NOT run \`item status --done\` or \`done-from-claim\`. An independent verifier — a different agent, told not to trust your self-report — checks your work and closes the item afterward. Leave the claim open/active.

If an item's needed change would cross its scope boundary, stop on that item, report the required expansion, and do not guess — but still finish and report items you completed before it (set "blocked" to a short explanation).

Return {repo, items: [one result per completed item: {item_id, claim_id, claim_token, commit_sha, files_changed, verification_summary}], blocked?}.`
}

function verifyPrompt(group, buildResult) {
  const items = buildResult ? buildResult.items : []
  const itemLines = items.map(it => `- item_id=${it.item_id} commit_sha=${it.commit_sha}`).join('\n')
  return `You are an INDEPENDENT verifier for repo ${repoPath(group.repo)} — you did not write this code and must not trust the implementer's self-report of "tests passed" or its verification_summary below (context only, not evidence).

Items just built and committed:
${itemLines}

For EACH item:
1. Isolate: \`git worktree add /tmp/verify-${group.repo}-<item_id> <commit_sha>\` — never touch the shared working tree.
2. Read \`git show <commit_sha>\` and judge whether the diff matches the item's claimed scope (no unrelated files, no silently skipped acceptance criteria).
3. In the isolated worktree, call the Skill tool with skill "code-change-verification" and cold-rerun the real commands yourself.
4. \`git worktree remove\` when done.
5. Verdict: "confirmed" only if scope matches AND your own rerun passed; "issues_found" otherwise with concrete concerns; "inconclusive" if a real check needs infra you don't have (say what and why, don't guess).

Be skeptical — a confirmed verdict is a claim you are making on your own evidence. Return one JSON result per item: {item_id, commit_sha, verdict, summary, concerns[]}.`
}

function closePrompt(group, item, verifyResult) {
  const header = `Repo: ${repoPath(group.repo)}. Independent verification for sprintctl item ${item.item_id} came back "${verifyResult.verdict}": ${verifyResult.summary}${verifyResult.concerns && verifyResult.concerns.length ? '\nConcerns: ' + verifyResult.concerns.join('; ') : ''}

cd into ${repoPath(group.repo)} first (sprintctl scopes by CWD directory name).`

  if (verifyResult.verdict === 'confirmed') {
    return `${header}

First call the Skill tool with skill "item-done" to load the standard closeout procedure. Then close it: \`sprintctl item done-from-claim --id ${item.item_id} --claim-id ${item.claim_id} --claim-token ${item.claim_token}\`. Log any decision/lesson-learned knowledge event the skill calls for, and remove the local claim token file. Report {item_id: "${item.item_id}", closed:true, action:"done-from-claim"}.`
  }
  return `${header}

Do NOT mark the item done. Release the claim (\`sprintctl claim release --claim-id ${item.claim_id} --claim-token ${item.claim_token}\`) and leave a note for human triage: \`sprintctl item note --id ${item.item_id} --type decision --actor claude-sonnet-verify-gate --summary "independent verify failed before close" --detail "${verifyResult.summary}"\` (item note takes --summary/--detail, not --note or --json — check \`sprintctl item note --help\` if this has drifted). Report {item_id: "${item.item_id}", closed:false, action:"left-open-for-triage", note:<what you wrote>}.`
}

const parsedArgs = typeof args === 'string' ? JSON.parse(args) : args

if (!parsedArgs || !Array.isArray(parsedArgs.items) || !parsedArgs.items.length) {
  throw new Error('vuoro-dispatch-build requires args = { items: [{repo, item_id, description?, tier?}], push?: boolean }, got: ' + JSON.stringify(args))
}

const push = !!parsedArgs.push
const groups = groupByRepo(parsedArgs.items)

const perGroup = await pipeline(
  groups,
  async group => {
    const tierInfo = await resolveTier(group)
    const tierCfg = MODEL_TIERS[tierInfo.tier]
    log(`${group.repo}: routed to "${tierInfo.tier}" tier (${tierCfg.model || 'session default model'}, effort=${tierCfg.effort}) — ${tierInfo.rationale}`)
    const buildResult = await agent(buildPrompt(group, tierCfg, push), {
      label: `build:${group.repo}`,
      phase: 'Build',
      schema: BUILD_SCHEMA,
      model: tierCfg.model,
      effort: tierCfg.effort,
    })
    return { tierInfo, buildResult }
  },
  ({ buildResult } = {}, group) => parallel((buildResult ? buildResult.items : []).map(it => () =>
    agent(verifyPrompt(group, { items: [it] }), {
      label: `verify:${group.repo}:${it.item_id}`,
      phase: 'Verify',
      schema: VERIFY_SCHEMA,
      model: 'claude-sonnet-5',
      effort: 'high',
    }).then(v => ({ item: it, result: (v && v.results && v.results[0]) || { item_id: it.item_id, verdict: 'inconclusive', summary: 'verifier returned no result' } }))
  )),
  (verified, group) => parallel((verified || []).map(({ item, result }) => () =>
    agent(closePrompt(group, item, result), {
      label: `close:${group.repo}:${item.item_id}`,
      phase: 'Close',
      schema: CLOSE_SCHEMA,
    }).then(c => ({ ...c, repo: group.repo, verdict: result.verdict, summary: result.summary, concerns: result.concerns }))
  ))
)

const results = perGroup.filter(Boolean).flat().filter(Boolean)
const issues = results.filter(r => r.verdict === 'issues_found')
const inconclusive = results.filter(r => r.verdict === 'inconclusive')
log(`Dispatched ${results.length} item(s) across ${groups.length} repo(s): ${results.length - issues.length - inconclusive.length} closed, ${issues.length} left open (issues found), ${inconclusive.length} left open (inconclusive).`)
log('Commits are local only unless push=true was passed. Log a session-level `sprintctl event add --type decision` summary in the home-repo backlog separately once satisfied with this batch.')

return { results, issues, inconclusive }
