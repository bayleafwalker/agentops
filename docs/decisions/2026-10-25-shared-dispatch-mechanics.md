# Shared dispatch mechanics and governed execution

Status: accepted implementation direction, operator instruction 2026-10-25.

The Mars Founder V2.1 driver has measured recovery and deterministic acceptance
behaviour. Reusing its mechanics is preferable to copying project scripts into
other products or replacing the working driver while moving it.

Agentops may own a portable host-side dispatch library: local task/attempt
lifecycle, scheduling, recovery, budget pauses and serialized integration. This
is a narrow amendment to TS-2 and the 2026-10-24 portable-workflow plan's earlier
restriction on a shared dispatcher. It does not transfer domain authority.
Sovite retains eligible model bindings, execution leases and fencing. Sprintctl
retains work authority. Vuoro retains durable coordination and evidence. A
library journal is recoverable execution state, not a replacement owner registry.

Project adapters own immutable task contracts, acceptance oracles, permitted
paths, risk classification and interpretation semantics. Only a repository's
integration driver writes its target branch. Cloud composes preparation,
capabilities and owner-backed observations; customer execution and credentials
remain on external hosts.

Extraction proceeds by equivalence: lift existing mechanics, vendor a digest
and source revision into Mars, and run its existing failure/recovery suite.
The initial package extracts durable state, atomic receipts, process supervision
and cleanup. Scheduling and integration remain in the Mars adapter until a
subsequent extraction proves their equivalence. This is not a claim that the
whole V2.2a engine or a hosted execution service has shipped.

Provider failover is a separate, disabled-by-default step. An eligible provider
change creates a new attempt and a `provider_failover` event, with the immutable
contract and recovered workspace. Reconcile uncertain effects first. Qualification
must establish role equivalence, data authorization, review independence, usage
coverage and explicit cost bounds. Quota exhaustion never authorizes paid
overage or a more expensive binding. Unknown resets stay paused.

Interpretation governance is retrospective and non-blocking. Technical checks
and required independent automated semantic review govern integration. Record
interpretation revisions, prior/new conclusions, evidence and downstream
dependencies immutably. Human acknowledgement, ratification, dispute and
supersession are observations, independent of implementation state. A dispute
creates correction/reevaluation work and preserves original evidence. Do not
reintroduce a blanket operator-approval merge gate. Independently established
effect authorization remains in its existing owner contracts.

V2.2d review-tier changes require historical HIGH-finding replay before relaxing
Opus review. Adaptive routing and selective review-free integration remain V2.3.
