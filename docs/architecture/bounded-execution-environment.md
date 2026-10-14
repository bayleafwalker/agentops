# Bounded execution environment

Status: first slice (estate enablement plan, priority 2). Scope: one repository
(`agentops`), one publication operation, one recovery path, one runner
(`devbox`).

## Goal

A valid request finishes without rediscovering its environment. A superseded or
unauthorized request is refused **at the effect boundary**, before anything is
dispatched, not later at settlement.

Two artifacts carry this:

* **The environment record** (`environment-record/devbox-vm.vuoro-shared.json`,
  schema `environment-record/environment-record.schema.json`) states what the
  runner is (pinned tooling, trust roots, credential-broker binding) and what
  it may do (the `authority` block). `scripts/validate_vuoro_profiles.py`
  validates it. A record with the `unattended-agent-host` role must declare
  `authority` and `tooling`.
* **The effect-boundary check** (`scripts/execution_authority.py`, `decide()`)
  answers allow or refuse, with a stable reason code, immediately before an
  effect is dispatched.

## Three access tiers

| Tier | Record field | Allowed when | Example operations |
|------|--------------|--------------|--------------------|
| 1. Standing read (diagnosis) | `authority.standing_read.operations` | always; no run, grant or repository needed | `work.run.resolve-v1`, `work.effect.attempt-get-v1`, `work.agent.list-v1` |
| 2. Scoped, time-limited execution | `authority.scoped_execution` | the operation is listed, the repository is listed, the grant is within `max_ttl_seconds`, and the run is live and unsuperseded | `work.effect.attempt-*`, `agentops.dispatch.publish-v1`, `agentops.host-adapter.launch-successor-v1` |
| 3. Explicit approval | `authority.explicit_approval[]` | an operator approval reference (`approval:<ref>`) is supplied, plus the repository and run checks | `rollout.resume-*` (transition `rollout-resume`), `agentops.publication.protected-*` and `pr.merge` (transition `protected-publication`) |

Rules the validator enforces:

* An operation pattern is an exact ID or a prefix with one trailing `*`.
* An explicit-approval operation must not also be granted by tier 1 or 2. A
  consequential transition cannot be reached without an approval reference.
* `publication_operation` names exactly one operation, and tier 2 must cover it.
* `max_ttl_seconds` is between 1 and 86400. The devbox value, 3600, matches
  cred-broker's `max_ttl_seconds` for the unattended devbox subject
  `usr_agent_devbox`.

A record with no `authority` block grants nothing. `decide()` returns
`no-authority-block`.

### Refusal codes (`execution_authority.decide`)

| Code | Meaning |
|------|---------|
| `no-authority-block`, `authority-invalid` | The record grants nothing, or its authority block is malformed. |
| `operation-not-in-scope` | No tier covers the operation. |
| `repository-not-in-scope` | The repository is not in `scoped_execution.repositories`. |
| `approval-required` | A tier 3 operation was requested without a valid `approval:` reference. |
| `ttl-exceeds-maximum`, `ttl-expired`, `grant-time-missing` | The grant has no time bound, or that bound is above the maximum or has passed. |
| `run-missing`, `run-superseded` | Supersession: the run has a successor, `work.run.resolve-v1` reports `run-not-found` for this binding, the run resolves to another run, or its `grant_id` was re-issued. |
| `run-unverified`, `owner-unavailable` | The check fails closed when there is no work owner or the owner returns an error. |
| `attempt-missing`, `attempt-state-conflict`, `attempt-already-applied` | The attempt state from `work.effect.attempt-get-v1` does not permit the operation. |

### Supersession source

The check calls the served `work.run.resolve-v1` operation through
`vuoro_client` (`ServedWorkOwner`), the same client sprintctl 0.19.0 uses in
served mode. sprintctl offers no CLI or public Python wrapper for these
operations.

`resolve-v1` returns only the binding: `run_id`, `principal_id`,
`workspace_id`, `client_id`, `grant_id`. It has no `superseded_by` field.
Supersession is therefore inferred from three signals:

* `run-not-found`, which covers an unknown run and a run no longer bound to the
  caller;
* a changed `grant_id`;
* a successor run the caller already knows about, such as the host adapter's
  `predecessor_run_id` link.

Follow-up for sprintctl: add an explicit `superseded_by_run_id` to
`work.run.resolve-v1` so the third signal does not depend on local knowledge.

## Runner release versioning

The devbox record is the single maintained runner composition.

* **Version.** The record's `revision` is the runner release version. It is
  now 3, the first revision with an authority block.
* **Pins.** `tooling[]` pins each component to an immutable digest:
  * `git:` for a source checkout, such as sprintctl `v0.19.0` at commit
    `ad66ddd`, installed as a uv tool with the `remote,served` extras;
  * `nix:` for a store path: opencode 1.18.33, uv 0.12.17, and the NixOS
    system `26.11.20261001.c59305b` (generation 99);
  * `sha256:` for an installed distribution's `RECORD`: vuoro-client 0.1.1.
* **Release rule.** Change the tooling on devbox, then update the pins, then
  bump `revision`. A record whose pins no longer match the host is stale.
  Re-observe it read-only (`ssh devbox-agent`: `sprintctl --version`,
  `opencode --version`, `uv --version`, `readlink -f /run/current-system`)
  before you trust it.
* **Trust roots.** `trust_roots[]` lists the TLS CA bundle (with digest), the
  vuoro-shared endpoint and the credential broker.
* **Credential broker.** `credential_broker` reuses cred-broker's own
  vocabulary: host profile `development-bounded`, subject `usr_agent_devbox`,
  and capability IDs from its `Capability` enum (`repo.read`, `repo.write`,
  `pr.manage`, ...). Each capability carries `bound`. `bound: false` records a
  known gap, described next.

### Known gap: broker binding

The production broker policy (appservice
`clusters/main/kubernetes/apps/cred-broker/app/config.yaml`) binds
`repo_agentops_github` capabilities only to the workstation `usr_operator`.
`usr_agent_devbox` is bound only to `repo_cred_broker_github` and to
`kubernetes.edit` on `agent-access/agent-editor`.

As a result, devbox cannot obtain an agentops push credential, and
`agentops.dispatch.publish-v1` cannot complete there today. The record states
this gap (`bound: false`) instead of hiding it.

Closing the gap is an appservice change, which needs a reviewed PR:

* Add a binding of `repo.read`, `repo.write` and `pr.manage` on
  `repo_agentops_github` for `host_id` devbox and subject `usr_agent_devbox`.
* Then flip `bound` to `true` and bump `revision`.

## The publication operation and the recovery path

**Publication operation: `agentops.dispatch.publish-v1`.** This is
`scripts/dispatch_publish.py`, which publishes a `dispatch/run-*` branch. It
runs inside one sprintctl effect attempt:

1. `work.effect.attempt-open-v1` binds the intent and target and returns the
   `attempt_id` and `authorization_digest`.
2. `work.effect.attempt-redeem-v1` requires attempt state `accepted`. It
   returns `dispatch_permitted`, which is true only on a fresh reply.
3. `agentops.dispatch.publish-v1` is the effect itself. `decide()` requires
   attempt state `redeemed` and no `application_report_received` event.
4. `work.effect.attempt-report-applied-v1` requires attempt state `redeemed`
   and no prior application report. It carries `commit_sha` and `pr_url`.

`decide()` runs before each of steps 1 to 4. Each step therefore checks scope,
TTL and run supersession again.

**Why this operation:**

* It already exists end to end: the sprintctl 0.19.0 attempt operations and
  agentops' native `dispatch_publish.py`, which reads Git itself and never
  trusts agent-relayed JSON.
* Its states (`accepted`, `redeemed`, `sealed_unused`, plus the
  application-report event) are durable and owner-side. That lets the boundary
  check refuse a replayed or duplicate effect without host-local state.
* Publication to a `dispatch/run-*` branch is not protected. Protected
  publication (to `main`, or `pr.merge`) stays tier 3.

**Recovery path: `work.effect.attempt-get-v1`.** After a crash at any point,
the runner reads the attempt (a standing read, always allowed) and resumes
from its state:

| Attempt state | Next step |
|---------------|-----------|
| `accepted` | Redeem, or `attempt-seal-unused-v1` if the work is abandoned. |
| `redeemed`, no application report | Confirm the remote ref with `dispatch_publish_check.py` (`confirm`). If it is present, report applied with that commit SHA. If it is absent, run publication step 3, which `decide()` still permits in this state. |
| `redeemed` with an application report, or `sealed_unused` | Done. Every further effect is refused (`attempt-already-applied` or `attempt-state-conflict`). |

Recovery therefore never needs to rediscover the environment. The attempt ID
and the record are enough.

Alternatives considered and not chosen for this slice:

* Host-adapter launch recovery (`launch-ambiguous`, then `resolve --abandon`).
  Its recovery ends in an operator act, not an automatic resume.
* The generic `work.run.register-v1` retry. It has no effect boundary of its
  own.

## Host adapter

The host adapter (`scripts/host_adapter.py`, PR #343) launches a successor
session. That launch is the tier 2 operation
`agentops.host-adapter.launch-successor-v1`.

The gate is on branch `feat/host-adapter-authority-gate`. The adapter refuses
to launch, both at the decision and again immediately before launch, in two
cases:

* its configured environment record has no `authority` block;
* the message's repository or the launch operation is outside
  `scoped_execution`.
