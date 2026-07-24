# Execution Boundary — Separate Assessment

## Determination

Execution must remain separate from planning and claim replacement. The tested
Windmill configuration is excluded as an R5/R6 authority, but its ability to
run a job is not evidence that an external executor can decide authoritative
completion. The retained claim-gated completion callback is the boundary that
must accept or reject an executor receipt.

## Functional callback contract

`runs/2026-07-23-lane-3-completion-authority/verify_completion_authority.py`
exercised the minimal acceptance logic. It accepted one current, verified
completion and rejected all of the following:

- a duplicate executor delivery;
- a completion from the pre-transfer proof/revision;
- a completion after verification failure;
- a completion from the pre-recovery proof/revision.

This is a requirement harness, not evidence that Windmill, Daytona, Temporal,
or another executor implements these semantics. It demonstrates the narrow
contract an executor must satisfy while Vuoro retains authoritative completion.

## Platform finding

The existing Windmill probe submitted the same `BATCH-02` idempotency key
twice and both jobs completed. That is sufficient to reject the tested
configuration as the standalone idempotency authority. With the callback
contract above, duplicate executor work can occur, but only one current,
verified receipt may have an authoritative effect.

The prior probe also did not establish the required sandbox isolation, and
Daytona was unavailable without an out-of-scope account credential. Therefore
this study does not reopen R5 or R6; it separates the design requirement from
the executor product verdict.

## Design requirements for later Vuoro work

1. Completion input carries an opaque execution ID, claim proof, claim
   revision, and verification result.
2. The authority rejects an already accepted execution ID before any state
   transition.
3. Transfer and recovery rotate a revision/proof so a delayed worker cannot
   complete work it no longer owns.
4. Verification failure is an authoritative rejection, not a successful job
   with a warning.
5. Executor loss or cancellation changes no authoritative work state; recovery
   begins from the claim authority and may submit a new execution.

## Evidence

- [Windmill execution probe](../runs/2026-07-23-lane-3-windmill-daytona/evidence/windmill-execution-probe.md)
- [Lane 3 hard-gate result](../runs/2026-07-23-lane-3-windmill-daytona/hard-gates.yaml)
- [Completion-authority functional harness](../runs/2026-07-23-lane-3-completion-authority/verify_completion_authority.py)
