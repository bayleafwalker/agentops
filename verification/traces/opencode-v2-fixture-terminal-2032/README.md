# Fixture-only terminal closeout qualification

The [portable probe](probe.py) imports three read-only files from `/tmp/fixture`
after verifying SHA-256: host adapter
`d9cf372f2877be8e3502b4b14e775231e63ac3b08244201b1717fce42a123473`, v2 client
`4d9f05e108540ea49db62923c59696b77a3eca05333c37e2f4d6b6ed5096d1a0`, and
profile validator `110a7583802157a446fbd327acb06940916d29334a8fa8772d3fa90dd709cd56`.
It ran twice against pinned OpenCode 2.0.32 with synthetic owner/delegation,
temporary state and a loopback fake provider in a no-egress namespace. The
[sanitized result](result.json) contains no generated credentials.

Success, provider failure and interruption reached the corresponding existing
owner outcomes, with one prompt, one result receipt and one effective
delegation revoke each. A persisted terminal checkpoint recovered during a
simulated native outage without repeating a prompt or native read. A concurrent
cancel request did not override observed success; a same-session queue remained
open without terminal evidence, result or revoke. Five provider requests stayed
on loopback. The owner and delegation were synthetic, not Vuoro RPC.

To rerun, stage the source files at the exact hashes above and mount them
read-only under `/tmp/fixture` in `bwrap --unshare-net` with temporary HOME/XDG.
The observation remains two-snapshot and non-atomic; this test does not qualify
native cancellation writes, permanent session exclusivity, product acceptance
or a deployed service. The phase remains default off and fixture-injected only.
