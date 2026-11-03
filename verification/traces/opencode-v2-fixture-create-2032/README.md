# Fixture-only adapter session creation

The [portable probe](probe.py) imports three read-only source files from
`/tmp/fixture` and verifies their SHA-256 digests: host adapter
`8d6da847311e09085528d2f9951c16afe77eb5a829290ae561ae135d95d13105`, v2
transport `95b7bca4ad30b304617241fcb7d900c169b9113a546a5066b94623f256346cad`,
and profile validator
`110a7583802157a446fbd327acb06940916d29334a8fa8772d3fa90dd709cd56`.
The [sanitized result](result.json) was produced against the pinned OpenCode
2.0.32 binary with a synthetic owner, synthetic delegation and loopback fake
provider in a no-egress bwrap namespace. The server password was generated
inside the fixture and was not recorded.

After one actual session was created, the fixture discarded the create
response. Restart recovered that same session through discovery and binding
validation, with one create, no prompt, no result receipt and zero provider
requests. An intentionally changed model binding was rejected. Unit tests also
force no-session intent, registration loss, cancellation, duplicate sessions,
version changes and policy drift; a deliberately repeated create failed its
negative control.

To rerun, stage the three source files with the hashes above on devbox, then
bind them read-only as `/tmp/fixture/host_adapter.py`, `/tmp/fixture/opencode_v2.py`
and `/tmp/fixture/validate_vuoro_profiles.py` under `bwrap --unshare-net` with
temporary HOME/XDG and execute this probe. The fixture owner and delegation
are synthetic: no Vuoro RPC, prompt, terminal closeout or deployed service is
qualified. The fixture-only constructor injection is trusted caller input, not
proof that a caller supplied synthetic dependencies.
