# Dormant v2 session transport qualification

The [probe](session-transport-probe.py) exercised the exact transport module
at SHA-256 `13bbcf6f74e41670d7de32dbf3c7a199ef19b42d444577012dbf8c67343990f0`
against the pinned devbox OpenCode 2.0.32 binary, in a disposable bwrap
network namespace with temporary HOME/XDG, synthetic authentication and no
prompts. The [sanitized result](session-transport-result.json) records the
observed shapes. The probe expects that module mounted read-only at
`/tmp/opencode_v2.py` inside the namespace.

Create and GET returned the expected session binding, including the server's
`default` model variant. A changed model, changed permissions and a wrong
expected directory each failed validation. Directory mutation was not tested.
Discovery traversed 111 substring hits over four pages, including the empty
terminal page, and selected the exact title and directory; duplicate exact
matches were rejected even when on different pages. An incorrect directory
returned no matches. The unit tests also cover lost responses, redirect,
oversized and malformed responses and pagination failure. As a negative
control, removing binding validation caused all three binding-drift tests to
fail.

This establishes the tested session operations only. No prompt was submitted;
it does not qualify launch, owner settlement, tool containment or deployment.
The module is not connected to the adapter runtime.
