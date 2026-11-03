# Fixture-only prompt admission qualification

The [portable probe](probe.py) reads three source files mounted read-only at
`/tmp/fixture` and verifies their SHA-256 digests before import: host adapter
`4e3841968cd06ea8013b093da0425de234c4b9586fcdf333597556fb77a9a4db`, v2
transport `69cb7fd22c4b94a0d8128af68b347425b0ed2df9ba15cd1a1d6af716506ddfce`,
and profile validator
`110a7583802157a446fbd327acb06940916d29334a8fa8772d3fa90dd709cd56`.
It ran twice against pinned OpenCode 2.0.32 with synthetic owner/delegation,
temporary state and a loopback fake provider inside a no-egress namespace.
The [sanitized result](result.json) contains no generated password.

Default-off created no prompt. After explicit fixture opt-in, one input was
submitted; the wrapper discarded a valid acknowledgement, and restart observed
the matching transcript input and recorded admission without resending. A crash
after persisting uncertainty but before the send remained unknown with no retry.
Cancellation after session creation left the run open with no prompt or owner
result. A changed-model binding was rejected. The fake provider received zero
requests: this is admission/readback evidence, not inference completion.

Stage the exact source files with the hashes above on devbox, mount them as
`/tmp/fixture/{host_adapter.py,opencode_v2.py,validate_vuoro_profiles.py}` under
`bwrap --unshare-net` with temporary HOME/XDG, and run this probe. The fixture
marker and injected dependencies are trusted caller input, not proof of a
synthetic environment. The code is default off and has no production switch.
It does not establish atomic session exclusivity, cancellation settlement,
terminal outcome or owner closeout.
