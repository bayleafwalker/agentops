# Repository delivery consumer (source implementation)

`agentops repository-delivery --spec /protected/project.json --state
/protected/delivery` runs one shared scheduler tick. The committed script lock
pins released Vuoro client 0.1.6. This is the AgentOps project adapter; Sprintctl
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
| `max_repairs` | `0` in this first implementation. Failed checks or uncertain attempts preserve an actionable stop; this source adds no repair launcher. |

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
exact `retained-candidate` receipt. The consumer does not invent a release,
approve output, pick a latest artifact or substitute worker-local files.

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
records the exact payload at the work owner. The released lease outcome operation has no atomic expected-basis field, so
this consumer does not call it as an acceptance shortcut. It writes its exact
payload and SHA256 as an idempotent served session note. Only an existing
work-owner terminal `accept` decision naming the same release and
`<64-character payload SHA256>` in `evidence_digests` advances local scheduling to its
terminal state. Driver results and publication never supply that decision.

A fresh session can reuse the same protected state and current owner binding.
For a newly owner-bound successor, pass its new spec with `--predecessor
<old-run-id>`. The owner's predecessor-context must confirm the link. Only run,
grant, lease, current basis and publication-attempt selectors may change; the
source packet and project policy stay fixed. The old spec is then refused by
the local adapter, and the work owner separately refuses superseded runs across
hosts. This does not claim cross-host fencing from a local file lock.

Local SQLite and driver transcripts are host-persistent scheduling observations.
Sovite/Workspace/work-owner records supply independently reconstructible owner
facts. Git source and CI are cross-host-replicated. End-to-end mutable execution,
interruption, canonical acceptance and second-tenant qualification remain open
under agentops#2868/#2692; the Git/driver tests prove only their declared local
boundaries.
