# M2c native inbox continuation evidence

Status as of 2026-10-18: the listed owner histories and source-specific cases
have been reviewed, but the M2c exit condition remains **open**. The ordinary
production instance and final protected-runtime rollout still require a fresh
normal-instance qualification. This record is not a completion decision.

## What the records establish

The tested path used Agentops' native host adapter to receive one explicitly
targeted continuation, register a successor run, perform a bounded owner
operation, and link the result to the originating message. A separate auditor
run read the successor's owner context and joined its nonempty session note.
The owner records, not a session transcript, establish message selection,
run/delegation linkage, item result, and note identity.

The current-source success case used adapter file SHA-256
`460c8a7cfd60f31dabc27a47f796c7071069f4a1b4fe0d7620d3ceb845186cb9`, runner
SHA-256 `a6b62400d278b1f9efd71be7bba2933ab1dc7490af88c4632b68c6b7f11a2a8e`,
and disposable qualification policy SHA-256
`63a1ab454845dd6bdd5a16e5b7d1081488e9060bb9e53ea511df973478d5769a`. The
case-specific template digest is
`39afeb21fcad6f23aa0e058e8fbfb56476e77a9c0cb887de1032d5a2fd610833`.
These hashes identify the tested files; they do not by themselves prove a
production service deployment.

The core success joined message `msg_01M57J0S9Z2A7QJ422RK1T19HW` at inbox
sequence 25 to sender run `run_TPV5N7Z3A6BGC5GYVCGSPSB4GF`, recipient run
`run_MQP9DTQQ21DQR580HNGPASWVFW`, delegation
`dlg_XFZZWVCHZHF3Q55E7NTRRTAST4`, and item 2776. The sender's note ID was 44.
The auditor registered as `run_GE1XVW0JRTBS98KJMH3FHT5CEN` and reconstructed
recipient note 45 with SHA-256
`5f7fe5b4a8bc17f3375f13c89b039b180055ec6b811f0217ffc2f4d430c77860`. The
envelope digest was
`696f92ae3429ecc4e24a67d1a3ff04b39228f9633fda6834630f43a45f9463af`. The
core receipt digest is
`22a4b4056dd473c5a7b1f140f2b2e97b7d2b7015a4d23228bbd2cc5f54e03aff`; its
independent review digest is
`3581cbcc1f28cfb9f8599f0917f6fe0b021c45dca25d655d6620c9aea8db04b6`.

An authorization-change case under the same current adapter source returned
`kind-not-allowed` before execution. It joined message
`msg_01M57K610MP6EX64KQ52G6GVTC` (sequence 26), recipient run
`run_5XGHEVQBB7FBSVKV37RMWZAFT6`, and pending item 2777. No harness session or
delegation was created for that denied execution. The root review recorded
`PASS_CURRENT_POLICY_DENIAL_BEFORE_EXECUTION_AND_CLEANUP`; its receipt digest is
`3b6375084bd1e8745d0ec215d00b5920ae37dadc6c87eb32f4e573a096d1e020` and the
review-file digest is
`22b27f459893f803c641adda1cf634efffa35b096ab702d23a18289fcca49d91`.

The supported abandonment case joined message
`msg_01M57BXK61MGW8V9D6SFXH2MHJ` (sequence 20), successor run
`run_812PPJZYV9BH3QTPRP0B5Q50X5`, delegation
`dlg_G38ZSKPRQFJT6KE094TME58DD6`, and item 2760. The durable owner result was
`abandoned`, with no prompt or session created. Its receipt digest is
`7bad5f39c4e002856b6b92d804bffbbf41aa95d7b23eb0a321192c745d264ef5`; the
review digest is
`b46c22b4573e4f312b09122e42b8af5a3f3468a04917cecf6b4fbe740953e449`.

In the cancellation-race case, the sender requested cancellation while the
recipient was busy. The final owner result was **completed**, not cancelled.
Message `msg_01M57MXFDTXXNKB2BFC7CGH13T` (sequence 27) joined sender run
`run_JJAEQBB56EGX8AD5WVZ4R91HT4`, recipient run
`run_BZWTHGQ9J8WR2MKSFT8A0867J5`, delegation
`dlg_F3EPFJ7X5DM1S15TA0QHZJZE29`, and item 2782. The auditor run was
`run_DZ28Z3TWTT719BVJPQ6YT2JSTP`; it reconstructed note 47 with SHA-256
`ece02ee12dfea9a71646cdb70adbcb0482ed8b01176ebd322b5299fb1bc722b0`. The
review confirmed one cancellation request, an observer acknowledgement, the
completed result, delegation revocation, local closure, and cleanup. This does
not demonstrate rollback or cancellation of an already completed effect.
Final-receipt digest:
`5352c0804b301a1d3049641803a74283fbd37f076dd74d5060b1eb34634801db`; root
review digest:
`da65aa510e412f9c80d1743b34acbffd57edcf5932ceca04300c8e296bf08921`.
Served update on agentops#2654 is event 5629.

## Source and CI provenance

The qualification runner source is Agentops PR [#379](https://github.com/bayleafwalker/agentops/pull/379),
merged as `f205cdd67669242612f2c1d10294657a1c8def42`; the PR's protected-paths,
template-allowlist, append-only-shards and script-test checks passed. Its
implementation is at [`scripts/qualify_inbox_m2c.py`](https://github.com/bayleafwalker/agentops/blob/f205cdd67669242612f2c1d10294657a1c8def42/scripts/qualify_inbox_m2c.py).
The associated CI runs were [39113727215](https://github.com/bayleafwalker/agentops/actions/runs/39113727215),
[39113734393](https://github.com/bayleafwalker/agentops/actions/runs/39113734393),
and [39113729904](https://github.com/bayleafwalker/agentops/actions/runs/39113729904); all required
checks passed.

The current adapter source is Agentops PR [#384](https://github.com/bayleafwalker/agentops/pull/384),
merged as `7aa1f71dcd27fafe0ecbefb052b7da72a04b91b7`; all checks on that
PR passed. The tested adapter file hash above is distinct from its Git commit
identity. The change makes operator abandonment resumable and re-raises
`_advance` failures after recording the diagnostic state; ordinary revoke-key
behavior remains unchanged. The prior source is Agentops PR [#376](https://github.com/bayleafwalker/agentops/pull/376),
merged as `e8d1d73653230d1df052631e3b2218ad9da2ef0e`, with its required checks
passing. The PR #384 checks were recorded by CI runs
[39126473532](https://github.com/bayleafwalker/agentops/actions/runs/39126473532)
and [39126475133](https://github.com/bayleafwalker/agentops/actions/runs/39126475133).
The PR #376 checks were recorded by runs
[39039625858](https://github.com/bayleafwalker/agentops/actions/runs/39039625858),
[39039697752](https://github.com/bayleafwalker/agentops/actions/runs/39039697752),
and [39039625821](https://github.com/bayleafwalker/agentops/actions/runs/39039625821).
All checks on both PRs passed.

The previous adapter file hash was
`32b4f0365aaabbb61c59ee7b04114ecb312edd0335f2ef414db9c3141d61955a`; the
current file hash is `460c8a7cfd60f31dabc27a47f796c7071069f4a1b4fe0d7620d3ceb845186cb9`.
Evidence is deliberately source-versioned: prior duplicate-delivery, crash,
uncertain-sender-response, committed-result-response-loss, and gateway histories
remain attributed to the earlier `32b4` source where they ran. They are not
relabelled as tests of `460`. The later source-specific success, supported
abandonment, current-policy denial and cancellation-result cases exercise the
changed paths on `460`. The review found no roadmap requirement to rerun every
unchanged historical path for this narrow source delta; prior caller-visible
tick-exit behavior is not claimed for `460`.

Supporting current-source evidence was reviewed under served event 5629 on
agentops#2654. This public page contains exact owner identifiers and digests
for the summarized cases, but not raw operational receipts, host paths,
credentials, transcripts or unrestricted owner exports. The receipts remain
restricted supporting evidence; the digest values here are anchors, not links
to those private files.

## Limits and remaining gate

- A prior continuation attempt returned provider HTTP 401 and is retained as a
  failure, not counted as a successful run. Later success is tied to the
  `460` source hash above.
- Reservation-overlap evidence is from the legacy advisory path. Reservations
  can overlap and do not establish exclusive ownership or effect authority.
  No native-v1 reservation qualification is claimed.
- The cancellation-race case records a requested cancel followed by an actual
  completed outcome. It does not support a rollback claim.
- These are disposable qualification cases. They do not prove that the ordinary
  production instance is enabled or qualified, nor do they qualify an ordinary
  production release, an operator pilot, or a rollback procedure. The final
  protected-runtime rollout and normal-instance proof remain open as of this
  record and must be added through a reviewed update before M2c is called
  complete.
- No terminal Decision is recorded for agentops#2654. The item remains active;
  this evidence does not close it.

The runner's source-level contract and isolation limits are documented in
[`docs/architecture/m2c-live-qualification-runner.md`](../../architecture/m2c-live-qualification-runner.md).
