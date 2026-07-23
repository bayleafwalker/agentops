# Lane 0 td control rerun

After Lane B was locked, a fresh clone of the locked sprintctl corpus commit
`f22132c21ca17ad79d347ca1f43df8b3fe636c66` was initialized as a disposable
td project. The control tasks referenced `CR-01`'s dependency-gate test and
`CR-03`'s proof-gated-mutation test.

`td dep add` recorded the dependency, but `TD_CONTEXT_ID=actor-blocked td
start <CR-03>` returned an `action: started` receipt while the CR-01 proxy
task remained open. A later start from a separate actor context also returned
success. The receipt contains an implementer-session label, not a transferable
proof that gates mutation.

The rerun confirms the expected control result without relying on the earlier
out-of-order discovery: td is useful for local task/session structure, but it
does not meet frozen R1, R2, or R6 authority requirements.
