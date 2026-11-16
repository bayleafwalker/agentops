# Resident memory and bounded sessions

Status: implementation branch, 2026-11-16. Host activation is gated separately.

## Decision

Use Hindsight v1.2.1 (`0eb02d8c418eac6b489bc63883c993b2257dfac4`, MIT)
with a small downstream policy extension and managed coding-agent adapter.
AgentOps owns source capture, ingestion receipts, context assembly and setup
evaluation metadata. lanectl owns bounded episode execution. Sprintctl remains
the work owner; authored code/canon remains in Git. No additional agenda
database, background planner or publication owner is introduced.

One enduring project identity resumes through fresh bounded episodes. A model
transcript is replaceable. Memory, exact source snapshots, work references,
authored artifacts and checkpoints provide continuity.

## Invariants implemented in the source layer

1. The public memory facade exposes only scoped `memory_search`. Scope, bank,
   tags, source roots and credentials come from protected configuration.
2. Trusted capture preserves exact UTF-8 bytes, semantic kind and content hash.
   Retraction takes effect in the source registry before asynchronous repair.
3. Current source bytes are checked after recall and during context assembly.
   An observation is omitted unless every source fact resolves to a current,
   retained source in the selected scope. Missing lineage fails closed.
4. Ingestion commits an immutable payload and stable UUID before dispatch.
   Acknowledgement, extraction completion and consolidation are distinct.
   Unknown/expired receipts never authorize an automatic replay.
5. Context has a complete serialized byte bound, explicit omitted/blocked
   sections, source references and an immutable digest. It grants no effects.
6. Semantic session notes persist atomically and hooks remain opt-in. Managed
   Hindsight integrations do not independently inject or retain context.
7. lanectl admits one coordinator, records wakes before execution, gates child
   exec on durable admission, bounds execution and fences recovery generations.
8. Candidate-pointer transitions require a separate evaluator receipt and
   matched candidate/configuration/state/boundary digests. This helper does not
   execute candidate code or activate arbitrary supervisor configuration.

## Deployment boundary

The resident has a writable project area. The source registry, memory API,
PostgreSQL, provider credentials, budget gateway, evaluator receipts and launcher
configuration belong to separate protected identities. Unix permissions inside
one agent-owned workspace do not establish this boundary.

The initial profile is disabled. Activation requires observed credential
isolation, egress restrictions, aggregate resource/budget admission, live source
rechecking, and recovery on the actual host. Provider calls from every Hindsight
LLM and embedding operation must pass the approved gateway. Per-process
concurrency and post-call accounting are not hard aggregate budget enforcement.

External effects remain unavailable. Local authored artifacts may be produced;
shared publication and infrastructure changes must use their existing owners.

## Qualification and next increments

The source tests exercise faults with deterministic engines/processes. The
Hindsight extension additionally has a split API/worker test using its public
client. These do not establish host isolation or successful native sessions.

The host pilot is three new sessions: establish story/canon; resume and critique;
correct canon and finish an edition. Retain rumour as rumour and show that the
old canon cannot enter the third context. Then introduce one measured local
setup improvement through an independent evaluation receipt.

After the pilot, add bounded consolidation/learned procedures, approved source
owner resolvers, qualified worker dispatch, and controlled setup activation.
The integration deliberately offers no fake served-work backend when the real
tracker is unavailable.

See [the implementation runbook](../runbooks/resident-memory.md) for executable
commands, transport contracts, remaining commissioning gates and rollback.
