# Vuoro mechanical-bulk hybrid named-pilot qualification — 2026-07-28

Status: active named tooling admission, narrowed after the Sprintctl
parity-fixture session exposed the semantic-oracle boundary. This authorizes
low-ambiguity mechanical implementation across the Vuoro tooling ecosystem; it
does not authorize the worker to define correctness.

## Scope

The policy admits `mechanical_bulk` packets as
`named_pilot:vuoro-tooling-bulk-2026-07-28`
for AgentOps, Vuoro, Sprintctl, Kctl, and ActionQ, subject to each repository's
own hybrid manifest and packet protections.

- route: `mechanical_bulk`
- worker model: `opencode-go/deepseek-v4-flash`
- host and contained worker identity: devbox / `agentworker`
- workflow: frozen packet, live coordinator claim, cold registered gates,
  independent coordinator review, then human acceptance

Each packet must have frozen interfaces and acceptance semantics, low semantic
risk, an externally defined oracle that the worker cannot modify, and at least
one deterministic failure condition for every relevant requirement. The worker
retains no correctness-definition, Git, sprintctl, deployment, or acceptance
authority. Size is not an admission criterion: a large repetitive migration can
fit while a tiny parity fixture can remain coordinator-only.

Explicit exclusions are test-oracle and parity-fixture construction; tests as
the primary deliverable; adversarial verification and cross-layer behavioural
proof; contradictory or materially underspecified packets; tracker settlement;
authority, release, deployment, compatibility, migration, and recovery
decisions.

Infrastructure repositories remain excluded because they define the worker
containment boundary. Bounded semantic work and adversarial verification remain
coordinator-owned. Kimi K2.7 is assessment-only, GLM has no escalation role, and
Kimi K3 is benchmark-only. A repository without its own hybrid manifest is not
dispatchable until it declares registered gates and protected paths.

## Retained qualification corpus

The two accepted samples are independent worker sessions at different frozen
Vuoro commits with different served coordinator claims and distinct test-only
assertions. Both used the exact configured route model, a contained worker,
no model override, a cold pre-gate and post-gate, and an independent Sol review
before the coordinator committed the candidate. They support mechanical
implementation behind coordinator-owned oracles; they do not support worker
authorship of tests, parity fixtures, or semantic proof.

| Packet | Live claim | Evidence | Result | Worker spend |
|---|---:|---|---|---:|
| `VUORO-2022-live-claim-qualification` | 291 (re-attested as 292 before candidate) | prepare `266fa519f7ec9d0c397c5e2b5775451ae239715b2b9d4c6775e46ae2d864d9e1`; run `a8937fe420a15f6782c936ba9bbd20d7964d79d0f7a806804ba3e0d57e24ea49`; candidate gate `ef600b0744904c69b1d1fdee4e9eb907f3b807cf73e919d56091e7c1bb77e9d6` | Vuoro `2fef5a4`, immutable release-wheel URL test | $0.003381 / 118,281 tokens |
| `VUORO-2023-immutable-provenance-qualification` | 293 | prepare `0f453d7ec4b64fec013c18b1e3b5a75a3f1c3af00cce75740985d919593fa16f`; run `ab7c16a0031714b33dc45f51d252e3b512eda198615807d791cbfb9c6635c36b`; candidate gate `19cc16ffe3e15cc3bdc4acd8dad9f512308c7c742b5ece512bbad0b09b6ca02b` | Vuoro `a1b59f3`, source-revision provenance test | $0.002656 / 66,448 tokens |

The retained JSON receipts reside on devbox under
`/var/lib/agentops/hybrid-dispatch/evidence/`, named from each packet and stage.
They are the source of the hashes above. The two run receipts total
**$0.006037** and **184,729 tokens**.

## Entry and exit conditions

Entry requires the deployed policy to match this repository, `agentworker`
containment to pass, actual configured worker credentials to be present, and
the packet to pass every live claim and cold-gate check. A candidate still
requires independent review and human acceptance.

Suspend this pilot immediately on a containment breach, unauthorized tool or
network use, coordinator-tree mutation, failed cold gate, provider model
override, missing live claim, hard token ceiling, or cost-cap breach. One
rejected worker attempt ends the packet; another attempt requires a materially
revised coordinator packet or an assessment protocol. Reassess expansion only
from additional retained, independently reviewed evidence.
