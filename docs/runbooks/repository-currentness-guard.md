# Installed repository currentness guard

The fixed AgentOps composition in `scripts/repository_currentness.py` supplies
Sovite's optional installed currentness authorizer. It narrows existing resource
authorization using fresh Work-owner facts; it creates no resource/effect grant,
work ledger, schema router or acceptance decision. The generic Sovite owner has
no Sprintctl dependency. This is source behavior; release publication, schema31
migration, credentials, commissioning and installation remain separate owner
actions.

Publish `repository_currentness_required: true` on the actual Sovite grant used
by the installed repository binding. The owner then refuses plain jobs and new
repository admission when the fixed guard is absent. A persisted guarded job
also refuses active authorization if its guard is removed. A request cannot
select an authorizer, purpose, endpoint or authority flag. Historical run reads,
idempotent reconciliation, cancellation and ready Workspace recovery under a
current reader retain their separate owner checks. They do not acquire active
execution permission from an earlier producer lease.

## Protected composition

Use the fixed `create_app(currentness_config=..., settings=...)` factory, or the
script entrypoint with `--currentness-config`. All config/spec/profile/token
files and every ancestor must pass Sovite's existing no-follow protected-path
reader: root/service-owned ancestors with no unrelated writer, private regular
single-link files, no symlinks. A root-owned sticky temporary ancestor is
supported for isolated tests. Root and the trusted service UID remain trusted;
candidate processes must use the separately confined runtime identity.

The closed config shape is:

```json
{
  "schema_version": "agentops-work-currentness-config/v1",
  "authorization_budget_seconds": 2,
  "watchdog_poll_seconds": 0.25,
  "deliveries": [{
    "spec_path": "/var/lib/agentops/private/delivery.json",
    "currentness_profile": "/var/lib/agentops/private/read-profile.json",
    "operation_sha256": "<qualified actual catalog operation descriptor SHA256>"
  }]
}
```

The profile is the existing released `vuoro-client-profile/v1`, read through the
same protected reader, with `required_authorities: ["work:read"]` and an absolute
`file:` credential reference. Mint its actual owner credential separately,
restricted to exactly `work.lease.currentness-v1` and the delivery's actual Work
run. The guard verifies that exact scope from every successful owner response;
an operator credential, write profile or broader delegation cannot substitute.
The profile must target a qualified HTTPS service and its expected environment.
The guard reuses the actual owner-published operation input/result schemas
through the released Vuoro client and pins the whole operation descriptor.
It defines no competing ContinuationBasis model. Publication of compatible
immutable owner/service/Sovite releases is required before installation; source
CI pins are qualification provenance, not installation releases.

The existing delivery spec supplies the exact full portable packet, Sovite
principal and Work run/lease/checkpoint. Initial admission selects exactly one
protected intent by the actual validated packet, actual caller and existing
`delivery-...` idempotency key. Missing or ambiguous specs refuse. A raw caller
cannot choose another HTTP key to mint a sibling under that intent. Repair
admission uses the actual validated parent job, retains the original Work tuple
and root job, and derives the existing consumer repair key from the exact owner
repair selectors and lower cost policy. The portable goal/base remain unchanged.
The repair owner independently enforces retained evidence, lineage and budgets.

After Sovite mints the job UUID, its generic metadata wrapper binds that UUID,
principal, owner-canonical packet digest and active grant/generation to the
opaque project tuple. The tuple includes the protected spec/profile identity,
Work request, actual Work holder, full requirements digest and original root
job/packet. Work grant/workspace identities are not inferred from Sovite or
Knowledge workspace identifiers. Publication/feedback selectors may change
through the existing delivery flow; changing immutable Work inputs requires a
new protected continuation/composition. No token, observation time or expiry is
persisted as reusable authority.

## Timing and failure semantics

Each active owner authorization invokes the same fixed guard, covering lease,
worker, gateway/model and resource paths through `authorize_existing_job`.
Every call reads one actual owner PostgreSQL snapshot. The owner checks the
exact holder, run/lease status, bound full goal/Release, complete Decision/ref
basis and final captured lease/delegation expiry, returning
`authorizes_effect: false`. A changed goal/ref, ended lease, revoked delegation,
unknown population, lost reply or unavailable owner refuses active work.

The entire recursive authorization shares one monotonic start. The configured
budget is finite and at most 5 seconds; HTTP handshake, schema discovery, bounded
response streaming, the read and final client-time check all consume it. A
native relay's existing passive poll is 0.25 seconds, so an honest cancellation
observation bound is that poll plus the full authorization budget and bounded
local database/observer work. The fixed factory requires worker lease duration
at least three times the authorization budget. Choose a qualified budget that
fits the installed owner latency; the example 2 seconds is not a measured
production latency claim.

A read linearizes at its owner snapshot. A concurrent Work edit/revocation can
commit after that snapshot and before a downstream network call. Already
admitted/in-flight calls can finish; this condition cannot atomically fence a
cross-network side effect or undo one. Later boundaries and native polling
must read again. No cached observation timestamp authorizes another admission,
and no zero-latency revocation promise is made.

The explicit source qualification uses actual disposable Work PostgreSQL,
Vuoro authentication/HTTP and Sovite admission. It covers immutable intent and
Unicode goal binding, exact read-only delegation, stale Work and revocation,
lost read reply, shared deadlines and cleanup access. Generic Sovite tests
separately cover gateway/resource invocation and ready historical reader paths.
Deterministic callbacks and source tests do not qualify a native VM, production
credential boundary or deployment.
