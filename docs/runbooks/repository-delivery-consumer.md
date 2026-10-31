# Repository delivery consumer (source implementation)

`agentops repository-delivery --spec /protected/project.json --state
/protected/delivery` runs one shared scheduler tick. The committed script lock
pins released Vuoro client 0.1.6 and contract runtime 0.2.0. This is the AgentOps project adapter; Sprintctl
owns work/basis/settlement, Sovite owns mutable attempts/fences, Workspace owns
artifact versions/membership, and the repository's existing publication path
owns integration. Local scheduling state grants none of those authorities.

The source is uninstalled and unqualified. A host must explicitly compose the
Sovite mutable profile and candidate publication service, enroll current
principals, provide private retained storage, and qualify the separate check and
review drivers. No infrastructure is provisioned or activated by this command.
The existing offline `repository-delivery-qualification` demo still has a
simulated owner and supplies no service acceptance.

## Trusted host configuration

The JSON spec uses `schema_version: agentops-repository-delivery/v1`. Keep it
outside candidate-writable state. It contains selectors and exact owner facts,
never credentials or agent-written authority claims:

| Fields | Source |
| --- | --- |
| `repo_id`, `item_id`, `run_id`, `grant_id`, `lease_id` | Existing current work-owner binding and lease. The command never takes over a lease. |
| `basis` | Exact `delta.current` with a non-null 64-character current release digest from `work.run.continuation-delta-v1`, including release, decision and reference digests. |
| `packet` | Existing `portable-work/v1` Sovite packet: workspace/repository/executor IDs, full base SHA, cost, deadline and concurrency. `goal` must equal the current full work item description; longer-than-contract tasks require owner refinement. |
| `repository_id`, `canonical_url`, `allowed_areas` | Project-owner configuration and current admitted source. Public unauthenticated Git is the first supported retrieval path; do not weaken sanitized Git to inherit private credentials. |
| `sovite_endpoint`, `sovite_principal`, `sovite_credential_ref` | Commissioned execution API and caller. Server verification of the principal-bound preview prevents a changed credential from silently replaying submission as another caller. |
| `work_profile`, `workspace_profile` | Released Vuoro client profile paths. Membership and run identity are checked at their owners; filenames are not identity proof. |
| `workspace_endpoint`, `workspace_id`, `workspace_destination`, `allowed_classes` | Current reader policy for the exact private retained destination. Destination spelling is `workspace-<Workspace ULID>`. The owner-returned receipt must match all fields before download. |
| `acceptance` | Qualified private acceptance profile: `qualification_ref`, timezone-aware `expires_at`, `allowed_classes`, separate `check` and `review` driver records. Each driver has an absolute protected executable `path`, exact `sha256`, and bounded `timeout_seconds`. |
| `authority_environment`, `publication_attempt_id` | Existing trusted environment record and owner-issued redeemed publication attempt for the exact commit. Start with `publication_attempt_id: null`; after review, the protected host may update only this selector to the actual issued attempt, without changing the source/work binding. The existing `dispatch-publish` authority check remains mandatory. |
| `max_repairs` | Integer `0..3`; `0` disables repairs. The installed Sovite owner independently enforces its own repair cap, lineage, deadline and aggregate root budget. |
| `repair` | Required when repairs are enabled: `feedback_contract_id`, lowerable finite `max_cost_usd`, and `owner_contract` containing protected absolute generated bundle `root`, exact `integrity_sha256`, and immutable owner provenance `source_ref` URL. |
| `repair_feedback` | Optional real `{parent_run_id, release_id}` selector when the actual caller cannot approve under the configured output procedure. Change it only while blocked; it grants no approval. |

Acceptance drivers receive a separate clean checkout path, base SHA and exact
candidate SHA. The configured, separately qualified driver owns its sandbox and
resource/network isolation. The consumer supplies no inherited credentials and
checks the executable digest, candidate HEAD and cleanliness before/after it.
A passing exit is check/review evidence; Sprintctl still applies its effective
verification profile. Higher verification bars remain the work owner's responsibility. Do not claim settlement from driver exits.

## Progression and recovery

The shared scheduler first checks current work/run/lease/requirements. Before
submission it persists the exact Sovite packet, preview and idempotency key.
An absent submission acknowledgement retries that same intent through the real
owner API. A completed run is held until its real owner history contains an
exact `retained-candidate` receipt. The consumer requires an actual owner release and selects no latest artifact or worker-local substitute.

The consumer downloads only the specified ready Workspace version, checks the
outer digest/size and the receipt/bundle/patch identities, fetches the canonical
base, imports the bundle into a new repository, and checks linear history,
allowed areas and regular file modes. Candidate Git config, hooks, replacement
objects, global filters and inherited Git environment do not select bytes.
It preserves the original exported JSON bytes outside the disposable worker.

Check and review use separate clean checkouts. A changed basis, driver or
candidate refuses progress. Missing driver results are unknown outcomes: an
existing driver directory is never silently rerun. A partial import is a named
reconciliation stop; a complete unchanged checkout is reusable after restart.

After review, publication requires the existing exact-target effect authority.
Branch/PR creation remains pending until canonical main actually contains the
verified candidate. The consumer then rechecks current work authority and
records the exact payload at the work owner. It detects `work.lease.report-outcome-v2`
in the actual current catalog, requires that operation's mandatory checkpoint,
and persists its exact outcome body/key before HTTP. The owner atomically
compares the full checkpoint and applies current verification policy. The
consumer matches the returned lease/run, principal, item, outcome, summary,
payload and checks, then uses the owner's `payload_digest` to match the terminal
exact-Release accept Decision. That digest covers the whole outcome; it is not
the hash of raw payload alone. A lost successful reply is recovered from current
owner reports before checking the now-ended lease, and never creates another
accept Decision.

Without that actual catalog operation, the consumer preserves the legacy served
session-note path and stops at `owner-exact-basis-operation-unavailable`; it never
calls v1 as an exact-basis shortcut. Released owners 0.26.0 and 0.27.0 already
return bound goal/Release lease fields, so a version label or those fields alone
cannot establish full reference/Decision settlement semantics. Every active
execution path also requires the actual lease's captured full revision and
Release digest to equal the current owner Release.

## Bounded owner repairs

Only a definite failed qualified check/review result may start a repair. A
missing result, a timeout/process-control exit, execution failure, changed input
or uncertain native outcome requires reconciliation. Completed fsynced driver
results survive lost scheduler acknowledgements and are validated without
rerunning the driver. Failed candidate bytes, receipts, checkouts and transcripts
remain under their original generation; children use `candidate-N`,
`retained-export-N.json` and separate `driver-check-N` / `driver-review-N` paths.

The consumer reads only the owner-issued feedback context for its own completed
parent and installed feedback contract. This read does not approve anything.
An eligible actual machine caller uses the existing output-approval API under
that contract's configured procedure, with exact qualified driver evidence. The
exact approval body is durable before HTTP; each retry reacquires identical
owned-parent context. Ineligible callers stop at
`repair-feedback-release-required`. The protected host can then select a real
already-approved release for that parent; there is no universal human gate and
no operator credential in this consumer.

The generated owner contract validates feedback, context and repair wire bodies.
The exact principal-bound repair preview, all selectors, lowerable cost and
idempotency key are durable before submission. Lost replies replay the same
intent. Sovite reconstructs the original packet, preserving the full current
goal, canonical base, grant, generation and deadline; the consumer never appends
feedback to the goal. Sovite owns exact candidate/feedback model disclosure,
retained seed recovery, one successor per parent, shared usage and unresolved
budget reservations. Acknowledged children reenter the shared scheduler and
clean trusted verification. Local caps create no additional repair authority.

A commissioned installation must pin a released owner contract/runtime tuple,
not an unreleased source checkout. The source qualification gate pins Sovite
`e5f392eb1717a5f4f6b8c4fa0f7fc777ee6608b8` and Sprintctl
`cd5ba9bb817e6e7b3fbd65fdf817999505f11883` while the corresponding published
contract/runtime is pending. Its generated repair data integrity is
`3690da2ebd4fb8ffb5ddac04749e2cb1a191f3821fe4b1e466b95e01426d94e2`.
The provenance URL and integrity pin are contract identity, not installation or
execution approval.

On a definite stale Work run, requirements, full basis or lease observation,
the consumer persists a stop/cancel intent and asks the actual execution owner
to cancel its owned run. Lost submission acknowledgement is reconciled only by
current owner history's exact idempotency key; it never creates work to discover
whether earlier work exists. Missing/ambiguous bounded history remains unknown.
Cancellation is owner-controlled and may encounter already-admitted in-flight
work. Polling is a bounded controller response, not instantaneous resource
currentness. D3 remains open until a separately qualified project-specific Work
guard checks actual immutable lease/checkpoint binding at every applicable paid,
native and resource admission; generic Sovite has no hard Sprintctl dependency.

A fresh session can reuse the same protected state and current owner binding.
For a newly owner-bound successor, pass its new spec with `--predecessor
<old-run-id>`. The owner's predecessor-context must confirm the link. Only run,
grant, lease, current basis, feedback-release and publication-attempt selectors may change; the
source packet and project policy stay fixed. The old spec is then refused by
the local adapter, and the work owner separately refuses superseded runs across
hosts. This does not claim cross-host fencing from a local file lock.

Local SQLite and driver transcripts are host-persistent scheduling observations.
Sovite/Workspace/work-owner records supply independently reconstructible owner
facts. Git source and CI are cross-host-replicated. End-to-end mutable execution,
interruption, canonical acceptance and second-tenant qualification remain open
under agentops#2868/#2692; the ordinary Git/driver tests prove their declared local boundaries. The explicit
`repository_delivery_owners.py` gate adds actual PostgreSQL Work/Sovite owners,
Sovite/released-Workspace HTTP, owner-admitted repair, lost acknowledgements,
retained child import, independent verification, bounded cancellation and exact
settlement. Its mutable callback is deterministic; it neither qualifies a native
driver nor exercises a real forge publication/production deployment.
