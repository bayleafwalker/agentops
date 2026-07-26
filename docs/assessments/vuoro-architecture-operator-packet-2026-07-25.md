# Vuoro Architecture Remediation Operator Packet

**Created:** 2026-07-25  
**Reworked:** 2026-07-26

This is the operator entrypoint for the assessment. It coordinates repository-owned work; it does not authorize production, deployment, Kubernetes, Flux, image, or live-data mutations.

## Documents

1. [Findings dossier](/projects/dev/agentops/docs/assessments/vuoro-architecture-findings-2026-07-25.md) - corrected evidence and status.
2. [Implementation plan](/projects/dev/agentops/docs/assessments/vuoro-architecture-implementation-plan-2026-07-25.md) - dependency-aware reasoning units and review gates.
3. [Preflight checklist](/projects/dev/agentops/docs/assessments/vuoro-architecture-preflight-checklist-2026-07-25.md) - authorization, evidence, and safety checks.

## Corrected execution order

- Start claim safety with S0, then S1, S2, and integrated S3. F2 and F7 are inseparable.
- Start F1 with policy unit P1. Do not mass-edit consumer `.envrc` files before the validator policy is approved.
- I1, L1, H1, C0, and O1 may proceed independently when their owners authorize them.
- C1-C3 follow C0. O2 follows O1. P2 follows P1.

## Required roles

Every unit records a decision owner, builder, primary verifier, and independent secondary reviewer. The secondary reviewer must use a fresh Spark-class context, must not have implemented the unit, and must inspect pinned implementation revisions rather than only the planning documents.

## Operator flow

1. Select one reasoning unit and confirm its dependencies.
2. Obtain authorization from every owning repository.
3. Complete the matching preflight section.
4. Record input revisions and the approved contract or policy decision.
5. Dispatch the build in the owning repository; keep separate accountable contexts for separate repositories.
6. Run primary validation and store redacted command evidence.
7. Dispatch a fresh Spark-class secondary implementation review using the unit-specific gate.
8. If the verdict is `FAIL` or `BLOCKED`, stop publication and return a bounded correction to the builder.
9. Publish or close only after `PASS` and owner acceptance of residual risk.

## Secondary-review packet

Give the reviewer:

- unit and finding IDs;
- approved contract/decision;
- input and output revision SHAs;
- implementation diff and affected public contracts;
- required command/fault matrix;
- primary verification record location;
- known residual risks.

Do not give claim tokens or credentials. The reviewer must independently reproduce critical assertions and produce a revision-bound `PASS`, `FAIL`, or `BLOCKED` record.

## Stop conditions

Stop the unit when:

- ownership or authority is ambiguous;
- an implementation expands to an unapproved repository;
- a claim-safety history permits continued execution or settlement after ownership loss;
- validation relies only on wildcard-authorized HTTP success or lexical configuration scans;
- contract projections disagree without a documented subset;
- two migration authorities remain active for one domain;
- evidence cannot be stored without exposing secrets.

## Completion rule

A document update, builder test pass, or self-review is not completion. Closure requires decision evidence, pinned implementation revisions, primary command evidence, a fresh secondary implementation review with `PASS`, and owning-domain acceptance.
