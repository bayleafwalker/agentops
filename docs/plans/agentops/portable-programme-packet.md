# Portable programme packet v1

The local `scripts/prepare_portable_batch.py` command composes an explicit
programme request with local Git observations into a reviewable dry-run packet.
The input and output contracts are
[`portable-programme-run-request/v1`](../../../schemas/portable-programme-run-request.v1.schema.json)
and
[`portable-programme-packet/v1`](../../../schemas/portable-programme-packet.v1.schema.json).

## Architecture choices

- The request is caller-authored and closed-schema. It names the goal, completion
  evidence, repositories, source branch and commit, target branch, permitted
  paths, access class, requested harness/model, explicit dependencies, bounds,
  readiness observations, review policy, and candidate-only landing policy.
- A source repository is locally qualified only when its `repository_id` in
  `host/namespace/repository` form matches the credential-free host/path parsed
  from the local `remote.origin.url`, the exact source commit exists, and the
  named local source branch still points at it with a clean worktree. The
  origin URL is read from local Git config only; the command never connects to
  it and never prints it. The target branch is reported when present but is
  never treated as a grant or landing approval.
- A dependency is a single Git blob pinned by owner, commit, path, and SHA-256.
  The verifier reads it from the local object database with Git lazy fetch
  disabled. It does not follow URLs or retrieve missing objects.
- The checked-in portable feature batch pin manifest is also verified: each
  pinned commit object, exact local branch tip, draft path, and draft SHA-256
  must match. The manifest is a source reference, not owner acceptance or a
  release receipt.
- Remote repository identity/authenticity, owner readiness, runtime/model
  resolution, network and credential capability, submission/startup, progress,
  usage coverage, and review/landing receipts remain explicit caller-provided
  or unknown facts.
  A supplied readiness observation is always marked
  `caller-provided-unverified`, even when it references a locally verified blob.
- `prepared-for-review` means only that declared source and dependency pins
  matched local Git objects. It is not dispatch-ready and grants no access.
  The packet hard-codes no grant change, no dispatch authority, candidate-only
  landing, and deployment excluded.

## Use

Create a request JSON that follows the schema, then map every owner to its local
repository. For example:

```sh
python scripts/prepare_portable_batch.py \
  --request ./portable-programme-request.json \
  --repo vuoro=/path/to/vuoro \
  --repo sprintctl=/path/to/sprintctl \
  --repo agentops=/path/to/agentops \
  --repo sovite=/path/to/sovite \
  --repo appservice=/path/to/appservice \
  --repo vuoro-cloud=/path/to/vuoro-cloud
```

All owner repositories named by the request and by the local pin manifest need
a `--repo OWNER=PATH` mapping. Use `--pin-manifest` only for a reviewed local
manifest revision; it must be a local file and its pinned branch tips are still
checked against the selected local repository objects.

The output is deterministic for the same request and local Git state. Use
`--format text` for a concise operator summary. `--format prompt` renders a
bounded user-launch prompt from the same validated packet. It is
`SELF-CONTAINED-USER-LAUNCH-PROMPT` only when all source and pin checks pass and
the request has zero dependencies. If any source is blocked or any dependency
is present, it emits `BLOCKED-CONTEXT` and says to stop before launch. It never
copies dependency bytes or fetches them; dependency refs remain explicit and an
operator must separately supply and authorize the bytes. Unsafe prompt text
that resembles a local path, remote URL, or credential is not echoed.

The prompt states user launch only, unknown provider capability, separate
manual receipt phases, and no dispatch, grant change, landing, or deployment.
Use the closed
[`portable-manual-launch-observation/v1`](../../../schemas/portable-manual-launch-observation.v1.schema.json)
schema to record `intent`, `submitted`, `acknowledged`, `started`, and
`useful_progress` as separate observations. Phases after `intent` require a
platform-issued task ID, actual resolved model and environment, and exact source
refs; missing values stay unknown. A prompt or URL is not a task receipt.

Exit status `0` means JSON/text source observations match or a prompt is
self-contained; `1` means observations are blocked or the prompt must stop;
`2` means the request or repository mapping is malformed. No command mode
contacts an owner, changes a repository, dispatches or creates a task, starts a
session, changes grants, lands work, or deploys.

## Readiness rules

The packet distinguishes a prepared source envelope from operational
readiness. Its readiness observations are input claims only. Current owner
records, actual resolved caller capability, native task submission and startup,
actual spend, and candidate verification must be reconstructed by their owners
or supplied as separately authenticated receipts. Missing facts remain
`unknown`; missing usage is never zero. A copied packet grants no access and
cannot continue or wake a native session.

The request's deadline is recorded but this local preparer does not compare it
to the current clock. The review operator must reconcile deadline freshness at
the time of use. The preparer similarly does not establish deployed/released
versions, canonical remote identity, branch protection, or source reachability.
