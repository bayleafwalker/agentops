# Vuoro bulk hybrid named-pilot qualification — 2026-07-28

Status: active named pilot. This is an admission decision for a deliberately
small scope, not a global model qualification or an unattended acceptance
decision.

## Scope

The policy admits only the following pairing as `named_pilot:vuoro-bulk-2026-07-28`:

- repository: `vuoro` (immutable manifest ID `1deb57d0-af6f-479c-811a-b5b7254841f9`)
- route: `bulk`
- worker model: `opencode-go/deepseek-v4-flash`
- host and contained worker identity: devbox / `agentworker`
- workflow: frozen packet, live coordinator claim, cold registered gates,
  independent coordinator review, then human acceptance

Each packet must still satisfy the policy and manifest gates. The worker retains
no Git, sprintctl, deployment, or acceptance authority. The pilot does not
extend to another task class simply because a task is small; packets require a
strong registered command that can falsify the proposed change.

Actionq remains unenabled: it has no fresh-clone gate proof because its clone
cannot resolve `psycopg-binary`. Infrastructure repositories remain excluded:
they define the worker-containment boundary. `substantial`, `escalation`, and
`worker_review_challenger`, and all non-Vuoro repositories, remain unqualified.

## Retained qualification corpus

The two accepted samples are independent worker sessions at different frozen
Vuoro commits with different served coordinator claims and distinct test-only
assertions. Both used the exact configured route model, a contained worker,
no model override, a cold pre-gate and post-gate, and an independent Sol review
before the coordinator committed the candidate.

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
override, missing live claim, or cost-cap breach. Reassess expansion only from
additional retained, independently reviewed evidence; do not infer it from
availability, passing smoke runs, or these two examples alone.
