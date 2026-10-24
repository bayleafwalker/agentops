# Local exact-candidate review packet

This AgentOps utility creates a deterministic, local-only packet for a human
review of one exact candidate commit. It observes the requested branch tip,
commit/tree objects, clean worktree, local origin identity, and local target
branch tip. Target ancestry is an observation from local objects and can be
stale. The packet never resolves refs remotely.

## Input and invocation

The bounded `portable-candidate-review-request/v1` schema accepts a candidate
owner, canonical repository ID, branch, full commit ID, target branch, and
author ID; required check names; and zero to 128 supplied receipts. Receipt
records bind an asserted result, time interval, reviewer or check name, and
evidence SHA256 to a full commit and tree ID. Request size is capped at 1 MiB.

Run from the AgentOps repository:

```sh
python scripts/review_portable_candidate.py \
  --request /path/to/candidate-review-request.json \
  --repo agentops=/path/to/local/agentops \
  --format json
```

The command only reads the request and local Git metadata/objects. JSON output
uses the closed `portable-candidate-review-packet/v1` schema. Its SHA256 is
computed over canonical sorted compact JSON before adding `packet_sha256`.
Text output presents the same observations for a person. Neither format
echoes request/receipt IDs or reviewer/author identities, and neither contains
a repository filesystem path, remote URL, credential, or file list.

## Evidence and authority limits

Receipt matching detects a different commit/tree, future timestamps, stale
receipts, non-passing results, and an author reviewing their own change. It
also reports absent or duplicate required-check receipts. `evidence_sha256`,
issuer authenticity, reviewer identity, and the truth of the asserted result
are not independently verified; matching receipts are explicitly marked
`caller-supplied-unverified`. The packet may report
`metadata-consistent-for-manual-review`, which is not landing approval or a
claim that the candidate is ready to land. Landing protection and required
policy remain unknown.

Manual actions are ordered to confirm the trusted source identity, inspect the
complete exact commit diff, authenticate receipts, inspect current target
policy, and make a human landing decision. Merge, push, fetch, dispatch, grant
changes, and deployment are unavailable or excluded. Deployment remains a
separate decision and operation.
