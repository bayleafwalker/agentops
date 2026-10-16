# Bounded execution environment

Status: first slice of priority 2 in the estate enablement plan. Scope is one
repository (`agentops`), one publication operation, one recovery path and one
runner (`devbox`).

## Goal

A valid request should finish without rediscovering its environment. A
superseded or unauthorized request should be refused **at the effect
boundary**, before anything is dispatched, not later at settlement.

Three pieces implement this:

* **The environment record.** `environment-record/devbox-vm.vuoro-shared.json`
  follows the schema in `environment-record/environment-record.schema.json`.
  It states what the runner is: pinned tooling, trust roots and its
  credential-broker binding. It also states what the runner may do, in the
  `authority` block. `scripts/validate_vuoro_profiles.py` validates the record,
  and the schema mirrors those rules. A record with the role
  `unattended-agent-host` must declare `authority` and `tooling`.
* **The effect-boundary check.** `scripts/execution_authority.py` provides
  `decide()`, plus `authorize()` and a CLI built on it. It answers allow or
  refuse with a stable reason code, and never raises.
* **The ownership model.** The record, the policy and the adapter code must not
  be writable by the uid whose work they bound. The section
  [Ownership model](#ownership-model-who-can-change-the-boundary) covers this.
  Until it is deployed, the checks hold only against a cooperative agent: they
  act as a tripwire, not a boundary.

## Three access tiers

| Tier | Record field | Allowed when | Operations on devbox |
|------|--------------|--------------|----------------------|
| 1. Standing read (diagnosis) | `authority.standing_read.operations` | Always. No run, grant or repository is needed. | `work.run.resolve-v1`, `work.run.predecessor-context-v1`, `work.effect.attempt-get-v1`, `work.agent.list-v1`, `work.agent.describe-v1`, `work.message.status-v1`, `work.read.item-decisions` |
| 2. Scoped, time-limited execution | `authority.scoped_execution` | The operation is listed, the repository is listed, the run still resolves to the request's grant, and the request is within the TTL. Attempt-bound operations also need an attempt in the right state that is bound to the same grant. | the four attempt writes (open, redeem, seal-unused, report-applied), `agentops.dispatch.publish-v1`, `agentops.host-adapter.launch-successor-v1` |
| 3. Explicit approval | `authority.explicit_approval[]` | A served operator decision exists that names this transition, repository and run (see [Approvals](#approvals)). The run checks also apply. | `rollout.resume-*` (`rollout-resume`), `agentops.publication.protected-*` and `pr.merge` (`protected-publication`) |

The validator and the schema enforce these rules:

* **Exact grants.** Tiers 1 and 2 list exact operation IDs, with no wildcards.
  An unlisted attempt operation is therefore never granted by a prefix.
  Tier 3 may use one trailing `*`, because a pattern there only adds
  restrictions.
* **No unapproved route to a tier 3 operation.** An operation that matches a
  tier 3 pattern must not also be granted by tier 1 or 2. Without an approval,
  such an operation can only be refused.
* **One publication operation.** `publication_operation` names exactly one
  operation, and that operation must be listed in tier 2.
* **TTL bounds.** `max_ttl_seconds` and `max_approval_age_seconds` must each be
  between 1 and 86400. Devbox uses 3600 for both. That matches cred-broker's
  `max_ttl_seconds` for the unattended devbox subject `usr_agent_devbox`.

A record without an `authority` block grants nothing; `decide()` returns
`no-authority-block`.

### What each check proves

* **Run and grant.**
  * Tiers 2 and 3 require `run_id` and `grant_id`.
  * `work.run.resolve-v1` resolves the run for the caller's own binding and
    returns that binding: `run_id`, `principal_id`, `workspace_id`,
    `client_id`, `grant_id`.
  * When the run resolves and its `grant_id` equals the request's, two facts
    hold: the caller is still the principal the run was registered to, and its
    grant has not been re-issued since the request was authorized.
  * It does **not** prove that no successor run exists. resolve-v1 has no
    supersession field.
  * So supersession is the union of three signals: `run-not-found` (which
    covers both an unknown run and one no longer bound to the caller), a
    changed `grant_id`, and a successor the caller already knows about
    (`successor_run_id`, for example the host adapter's `predecessor_run_id`
    link).
  * Follow-up for sprintctl: add `superseded_by_run_id` to resolve-v1.
* **TTL.**
  * Where the owner exposes an issue time, the check uses the owner's time and
    ignores the self-attested one. For attempt-bound operations (redeem,
    seal-unused, report-applied and the publication), the window counts from
    the `created_at` of the attempt's `attempt_authorization_accepted` event.
  * resolve-v1 and the grant expose no issue time. So `attempt-open` and the
    host-adapter launch use the caller's `granted_at`, with these checks:
    * it must be finite;
    * it may be at most 60 s ahead of the checker's clock;
    * `ttl_seconds`, if given, must be a positive integer no greater than the
      maximum; there is no defaulting of 0.
  * For those two operations the TTL limits a caller that is honest about
    `granted_at`, but cannot catch one that lies about it.
* **Attempts.**
  * Attempt-bound operations need an `attempt_id` and read
    `work.effect.attempt-get-v1`.
  * The attempt must satisfy all of these:
    * its `authorization.repo_id`, `principal_id` and `grant_id` equal the
      run's binding;
    * its state is the one the operation needs (`accepted` for redeem and
      seal, `redeemed` for report and publish);
    * its history has no `application_report_received` event.
  * Report-applied leaves the state at `redeemed` and adds that third event.
    So a publish or report after a report is refused (`attempt-already-applied`).
  * For the publication, the attempt's `target.operation` must be
    `push_branch` or `open_pull_request`, and `target.commit_sha` must equal
    the commit being published.
  * The authorization carries no `run_id`. "Belongs to the run" therefore means
    "carries the same principal and grant as the run's binding".
* **Fail closed.**
  * These all refuse: no owner, any `OwnerRefusal`, any client exception, a
    malformed payload, or an owner timestamp without a timezone.
  * The refusal codes are `run-unverified`, `owner-unavailable` and
    `internal-error`.
  * The output is a JSON decision, never a traceback.

### Approvals

A tier 3 operation needs `approval_ref = decision:<work item id>:<decision id>`.
That reference names a `work.decision.record` row, read back through the
standing read `work.read.item-decisions`. The decision counts only if all of
these hold:

* its `kind` is `accept`;
* its `actor` is one of the entry's `approvers` (devbox: `workstation-vuoro`,
  the operator workstation's Vuoro identity, which differs from
  `devbox-agent-vuoro`);
* its rationale contains the exact line
  `approve <transition> repo=<repo> run=<run_id> commit=<sha>` or
  `... pr=<url>`, and the request names that same `commit_sha` or `pr_url`;
* its owner-side `created_at` is less than `max_approval_age_seconds` old;
* it has not been used for any other effect (below).

So an approval is bound to one transition, one repository, one run and one
commit or PR. It expires, and it can be used once.

**Single use.** When every other check passes, `decide()` consumes the decision
before it allows the effect. It writes a session note on the run through
`work.session-note.write-v1` with the idempotency key
`approval-consume.<decision id>`. The note's content is the use: decision,
transition, repository, run, operation and commit or PR. The owner's
idempotency ledger then enforces single use:

* a retry of the same use (same key, same content) replays and is allowed
  again, so a crash between consumption and the effect does not strand the
  approval;
* any other use (same key, different content) gets `idempotency-conflict` and
  is refused as `approval-already-used`;
* if the write fails for any other reason, the check refuses
  (`owner-unavailable`).

The ledger is scoped to the caller's principal. A different principal cannot
reuse the approval either, because the approval is bound to a run and resolving
that run requires the run's own binding.

This is the strongest form the served operations support today:

* sprintctl has no signed approval object.
* sprintctl cannot look up a decision by ID; it lists an item's decisions.
* Recording a decision needs only `work:lifecycle`.

Two limits follow:

* Any session that runs as `workstation-vuoro` can record an approval. The
  check binds approvals to the operator's *identity*, not to a human act.
* The binding lives in free text (the rationale line), not in structured
  fields.

A served `work.approval.record` with structured fields
(`transition`, `repo_id`, `run_id`, `expires_at`) would remove both limits.

### Refusal codes

| Code | Meaning |
|------|---------|
| `no-authority-block` | The record grants nothing. |
| `authority-invalid`, `environment-invalid` | The record is malformed. |
| `operation-not-in-scope` | No tier lists the operation. |
| `repository-not-in-scope` | The repository is outside the record's scope. |
| `ttl-invalid`, `ttl-exceeds-maximum`, `ttl-expired` | The requested TTL is bad, too long, or already over. |
| `grant-time-missing`, `grant-time-invalid`, `grant-time-in-future` | The self-attested issue time is absent, not finite, or too far ahead. |
| `run-missing`, `grant-id-missing` | The request lacks a run or grant. |
| `run-superseded` | See "Run and grant" above. |
| `attempt-missing`, `attempt-state-conflict`, `attempt-already-applied`, `attempt-binding-mismatch`, `commit-missing` | Attempt checks failed. |
| `approval-required`, `approval-invalid`, `approval-expired`, `approval-already-used` | Tier 3 approval is missing, does not qualify, is too old, or was already used for another effect. |
| `publication-branch-not-allowed` | The attempt's target branch is not a `dispatch/publish-*` branch (tier 2 never writes `main`). |
| `run-unverified`, `owner-unavailable`, `internal-error` | The check failed closed. |

## Runner release versioning

The devbox record is the single maintained runner composition.

* **Version:** the record's `revision` is the runner release.
  * Revision 3 was the first that carries authority, observed on the host.
  * Revision 4 is the composition that gitops-nixos #23 (the bounded system
    service) builds.
* **Pins:** `tooling[]` pins every component to an immutable digest:
  * `nix:` for store paths: sprintctl 0.19.0 (packaged from `v0.19.0`
    `ad66ddd` with the `remote,served` extras), opencode 1.19.0 and uv 0.13.0;
  * `git:` for sources: vuoro-client 0.1.1 (`8b8428e`) and nixpkgs
    `7fd4004`;
  * `sha256:` for a release wheel: vuoro-adapter-kit 0.2.2.
* **Why nixpkgs instead of the toplevel:** the record pins nixpkgs, not the
  NixOS toplevel. The toplevel contains the record, through the pinned agentops
  source, so it cannot be pinned from inside the record. The gitops-nixos
  commit that deploys a revision pins the toplevel.
* **Release rule:**
  1. Build the composition in gitops-nixos.
  2. Update the pins here from the built closure.
  3. Bump `revision`.
  4. Re-pin gitops-nixos to the agentops commit that carries the revision.
  5. Switch the host.
* **Stale records:** until the switch, the host runs the previous revision.
  A record whose pins do not match the host is stale. Before trusting it,
  re-observe the host read-only over `ssh devbox-agent`: `sprintctl
  --version`, `opencode --version`, `uv --version` and
  `readlink -f /run/current-system`.
* **Trust roots:** `trust_roots[]` lists the TLS CA bundle (with its digest),
  the vuoro-shared endpoint and the credential broker.
* **Credential broker:** `credential_broker` reuses cred-broker's own
  vocabulary: host profile `development-bounded`, subject `usr_agent_devbox`,
  and capability IDs from its `Capability` enum.

### Known gaps

* **No broker binding for agentops on devbox.** The production broker policy
  (appservice `clusters/main/kubernetes/apps/cred-broker/app/config.yaml`)
  binds `repo_agentops_github` only to `usr_operator`, so the record says
  `bound: false`. Devbox cannot get an agentops push credential. To close the
  gap, an appservice PR must bind `repo.read`, `repo.write` and `pr.manage` on
  `repo_agentops_github` to host devbox and subject `usr_agent_devbox`.
* **Devbox's Vuoro profile cannot read attempts.** Every attempt operation,
  `attempt-get` included, requires the Vuoro authority
  `work.effect.mark-applied` (sprintctl `effect_attempt.OPERATION_AUTHORITIES`).
  The devbox profiles do not hold it. Until they do, every attempt-bound check
  on devbox refuses with `owner-unavailable`, which fails closed.

## The publication operation and the recovery path

**Publication operation: `agentops.dispatch.publish-v1`.** This is
`scripts/dispatch_publish.py`. It publishes a verified `dispatch/run-*` tip.
If no protected path is touched, it pushes the tip to `origin/main`. Otherwise
it pushes a `dispatch/publish-*` branch and opens a PR for a hand pass.

It was chosen because it is the publication that agentops actually runs today:
it is the native step of `.claude/workflows/vuoro-dispatch-build.js`. It
already reads Git itself and never trusts agent-relayed JSON.

The intended sequence wraps it in one sprintctl effect attempt. `decide()` runs
before every step, so scope, TTL and supersession are rechecked each time:

1. `work.effect.attempt-open-v1`
2. `work.effect.attempt-redeem-v1`, which needs state `accepted`
3. `agentops.dispatch.publish-v1`, which needs `redeemed`, no report yet, and
   the same commit as the attempt's target
4. `work.effect.attempt-report-applied-v1`, which needs `redeemed` and no report
   yet

**What is wired today:**

* **Step 3 is gated.** `dispatch_publish.py --authority-environment <record>
  --run-id --grant-id --attempt-id [--profile]` runs `authorize()` before any
  Git or PR effect. The gate passes the resolved tip as `commit_sha`. A refusal
  prints `publish-refused` and exits 1. Tests are in
  `scripts/tests/test_dispatch_publish.py`.
* **The gate is opt-in.** Without `--authority-environment`, behaviour is
  unchanged. The dispatch workflow does not pass the flag yet.
* **Steps 1, 2 and 4 are not driven by agentops.** No agentops caller opens,
  redeems or reports attempts today. Whatever implements them must call
  `decide()` with the attempt operation before each step.
* **The destination is bound.** A tier 2 publication never writes
  `refs/heads/main`.
  * `decide()` allows the publication only when the attempt's
    `target.branch` starts with `dispatch/publish-`. sprintctl's
    `canonical_target` makes it end in `/<intent_id>`, for example
    `dispatch/publish-batch/<intent_id>`.
  * On allow, `decide()` returns that target. With the gate on,
    `dispatch_publish` skips the main push entirely.
  * It pushes the tip to exactly `target.branch`, and only when the tip equals
    `target.commit_sha`.
  * For `open_pull_request` it opens the PR against `target.base_branch`.
    For `push_branch` it stops after the push (`branch-pushed`).
  * Publishing to `main`, or merging, is protected publication and stays in
    tier 3.

**Recovery path: `work.effect.attempt-get-v1`.** After a crash at any point,
the runner reads the attempt (a standing read) and resumes from its state:

| Attempt state | Next step |
|---------------|-----------|
| `accepted` | Redeem it, or call `attempt-seal-unused-v1` if the work is abandoned. |
| `redeemed`, no application report | Run `dispatch_publish_check.py` (`confirm`) for the attempt's commit. If the commit is on origin, report it applied. If not, re-run step 3; `decide()` still permits it in this state, and `dispatch_publish` treats a tip already on origin as `already-on-origin`. |
| `redeemed` with a report, or `sealed_unused` | Done. Every further effect is refused. |

The attempt ID plus the record is enough to resume, so recovery never
rediscovers the environment.

Two alternatives were not chosen:

* **Host-adapter launch recovery** (`launch-ambiguous`, then
  `resolve --abandon`). It ends in an operator act rather than a resume.
* **The `work.run.register-v1` retry.** It has no effect boundary.

## Ownership model: who can change the boundary

A check that the checked party can edit is a tripwire, not a boundary.

Today on devbox, everything runs as the `agent` uid, and that uid owns all of
it: the adapter code (`/home/agent/work/agentops-host-adapter`), its policy
(`~/.config/agentops/host-adapter/policy.json`), the environment record, and
the user units `agentops-host-adapter.service` and
`opencode-serve-inbox.service`. In that setup the checks bind only a
cooperative agent.

The target model is the `profiles.agentopsHostAdapter` module in gitops-nixos:

| Thing | Owner | Where |
|-------|-------|-------|
| Adapter code and `execution_authority.py` | root, read-only | the Nix store; agentops fetched with `fetchgit` at a pinned revision |
| Environment record | root, read-only | `/etc/agentops/environment-record/devbox-vm.vuoro-shared.json`, taken from the same pinned agentops revision |
| Adapter policy | root, read-only | `/etc/agentops/host-adapter/policy.json`, generated from the NixOS configuration; `environment_record` points at the path above |
| Adapter process | system user `agentops-adapter` | `agentops-host-adapter.service` (a system unit), state in `/var/lib/agentops-adapter` |
| Adapter Vuoro credential | `agentops-adapter`, mode 0600 | a sops-nix secret; the unit does not start until it exists |
| Sessions | `agent` | `opencode-serve-inbox.service` (a system unit, `User=agent`) on loopback; the adapter only calls its HTTP API |

The adapter runs with `--trusted-config`. In that mode, before every decision
and every launch, it refuses unless the policy and the environment record are
owned by root and are not writable by group, by others, or by its own uid. A
record writable by the uid it bounds is therefore never trusted.

Changing the authority means changing gitops-nixos and agentops at a pinned
revision: a reviewed commit, not a file edit by the agent.
