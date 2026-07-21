export const meta = {
  name: 'vuoro-dispatch-verify',
  description: 'Independent verification pass over sprintctl item diffs — a different agent re-reads each diff and reruns tests cold in an isolated worktree, instead of trusting the implementer\'s self-report.',
  whenToUse: 'Use as a pre-close gate (mode: "gate", needs claim_id/claim_token per item so it can call done-from-claim on a confirmed verdict) or as a retroactive audit of work already merged/pushed (mode: "audit", default — files a triage note instead of closing anything). Invoke with Workflow({scriptPath: "/projects/dev/agentops/.claude/workflows/vuoro-dispatch-verify.js"}, {args: {mode, items: [{repo, item_id, commit_sha?, claim_id?, claim_token?}]}}).',
  phases: [
    { title: 'Verify' },
    { title: 'Close' },
  ],
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

function verifyPrompt(mode, group) {
  const itemLines = group.items
    .map(it => `- item_id=${it.item_id}${it.commit_sha ? ` commit_sha=${it.commit_sha}` : ' (find the commit yourself)'}`)
    .join('\n')
  return `You are an INDEPENDENT verifier — you did not write this code and must not trust anyone's self-report of "tests passed." Repo: ${repoPath(group.repo)} (cd there first).

First call the Skill tool with skill "code-change-verification" to load the standard verification procedure for this repo, and skim AGENTS.md if present.

Items to verify in this repo (mode=${mode}):
${itemLines}

For EACH item:
1. Identify its commit(s). If commit_sha is not given, use \`sprintctl item show --id <item_id> --json\` (cd into the repo dir first — sprintctl scopes by CWD directory name) and/or \`git log\` to find it.
2. Create an isolated worktree so you never touch the shared working tree: \`git worktree add /tmp/verify-${group.repo}-<item_id> <sha>\`. Read the full diff there (\`git show <sha>\`) and judge whether it matches the item's claimed scope — no unrelated file changes, no silently skipped acceptance criteria.
3. In that worktree, cold-run the repo's real test/verification commands (the ones code-change-verification tells you to use). Do not assume any prior reported pass/fail was correct — rerun them yourself.
4. Remove the worktree when done (\`git worktree remove\`).
5. Record a verdict: "confirmed" only if the diff matches scope AND your own cold rerun passed; "issues_found" if either check fails, with concrete concerns; "inconclusive" if you could not run the real check (e.g. needs infra you don't have, like a Postgres test DB) — say exactly what was skipped and why, do not guess.

Be skeptical. A confirmed verdict is a claim you are making on your own evidence, not a relay of someone else's claim. Return one JSON result per item.`
}

function closePrompt(mode, group, item, verifyResult) {
  const actor = mode === 'gate' ? 'claude-sonnet-verify-gate' : 'claude-sonnet-verify-audit'
  const header = `Repo: ${repoPath(group.repo)}. Independent verification for sprintctl item ${item.item_id} came back "${verifyResult.verdict}": ${verifyResult.summary}${verifyResult.concerns && verifyResult.concerns.length ? '\nConcerns: ' + verifyResult.concerns.join('; ') : ''}

cd into ${repoPath(group.repo)} first (sprintctl scopes by CWD directory name).`

  if (mode === 'gate') {
    if (verifyResult.verdict === 'confirmed') {
      return `${header}

First call the Skill tool with skill "item-done" to load the standard closeout procedure. Then close it: \`sprintctl item done-from-claim --id ${item.item_id} --claim-id ${item.claim_id} --claim-token ${item.claim_token}\`. Log any decision/lesson-learned knowledge event the skill calls for, and remove the local claim token file. Report {item_id: "${item.item_id}", closed:true, action:"done-from-claim"}.`
    }
    return `${header}

Do NOT mark the item done. Release the claim (\`sprintctl claim release --claim-id ${item.claim_id} --claim-token ${item.claim_token}\` if still held) and leave a note for human triage: \`sprintctl item note --id ${item.item_id} --type decision --actor ${actor} --summary "independent verify failed before close" --detail "${verifyResult.summary}"\` (item note takes --summary/--detail, not --note or --json — check \`sprintctl item note --help\` if this has drifted). Report {item_id: "${item.item_id}", closed:false, action:"left-open-for-triage", note:<what you wrote>}.`
  }

  // audit mode — item is already closed and shipped; file findings instead of closing anything.
  if (verifyResult.verdict === 'confirmed') {
    return `${header}

This item was already marked done and pushed. No action needed beyond a lightweight confirmation: \`sprintctl item note --id ${item.item_id} --type decision --actor ${actor} --summary "post-hoc independent verify: confirmed" --detail "${verifyResult.summary}"\` (item note takes --summary/--detail, not --note or --json — check \`sprintctl item note --help\` if this has drifted). Report {item_id: "${item.item_id}", closed:false, action:"noted-confirmed"}.`
  }
  return `${header}

This item was already marked done and pushed, before independent verification existed for it. File this for human triage — do not attempt to revert or hotfix it yourself: \`sprintctl item note --id ${item.item_id} --type decision --actor ${actor} --summary "post-hoc independent verify: ISSUES FOUND" --detail "${verifyResult.summary}. ${(verifyResult.concerns || []).join('; ')}"\` (item note takes --summary/--detail, not --note or --json — check \`sprintctl item note --help\` if this has drifted). Report {item_id: "${item.item_id}", closed:false, action:"flagged-for-triage", note:<what you wrote>}.`
}

const parsedArgs = typeof args === 'string' ? JSON.parse(args) : args

if (!parsedArgs || !Array.isArray(parsedArgs.items) || !parsedArgs.items.length) {
  throw new Error('vuoro-dispatch-verify requires args = { mode?: "audit"|"gate", items: [{repo, item_id, commit_sha?, claim_id?, claim_token?}] }, got: ' + JSON.stringify(args))
}

const mode = parsedArgs.mode === 'gate' ? 'gate' : 'audit'
const groups = groupByRepo(parsedArgs.items)

phase('Verify')
const perGroup = await pipeline(
  groups,
  group => agent(verifyPrompt(mode, group), {
    label: `verify:${group.repo}`,
    phase: 'Verify',
    schema: VERIFY_SCHEMA,
    model: 'claude-sonnet-5',
    effort: 'high',
  }),
  (verifyResult, group) => parallel((verifyResult ? verifyResult.results : []).map(r => () => {
    const item = group.items.find(it => it.item_id === r.item_id) || { item_id: r.item_id }
    return agent(closePrompt(mode, group, item, r), {
      label: `close:${group.repo}:${r.item_id}`,
      phase: 'Close',
      schema: CLOSE_SCHEMA,
    }).then(c => ({ ...c, repo: group.repo, verdict: r.verdict, summary: r.summary, concerns: r.concerns }))
  }))
)

const results = perGroup.filter(Boolean).flat().filter(Boolean)
const issues = results.filter(r => r.verdict === 'issues_found')
const inconclusive = results.filter(r => r.verdict === 'inconclusive')
log(`Verified ${results.length} item(s) across ${groups.length} repo(s): ${results.length - issues.length - inconclusive.length} confirmed, ${issues.length} issues found, ${inconclusive.length} inconclusive.`)

return { mode, results, issues, inconclusive }
