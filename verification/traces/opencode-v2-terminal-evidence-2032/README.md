# Terminal interval identity qualification

The [probe](probe.py) imported the client at SHA-256
`95b7bca4ad30b304617241fcb7d900c169b9113a546a5066b94623f256346cad`
and exercised the pinned OpenCode 2.0.32 binary with synthetic credentials,
temporary state and a loopback fake provider in a no-egress namespace. The
[sanitized result](result.json) records the outcomes without transcript bodies.

For success, provider failure, interruption and a separate success while
another session had queued work, the returned terminal ID and canonical
interval SHA-256 matched an independently paginated ascending transcript. A
repeat success read produced the same ID and digest. A queue in the observed
session yielded unknown after interruption. This is a bounded comparison,
not proof of causal linkage, atomic exclusion or owner acceptance. The method
remains dormant and does not persist or publish this evidence itself.
