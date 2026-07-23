# Lane 1 — Beads + Gas Town R2 Litmus

Pinned Beads source: `d7b9f4fc52deebc86cb25c214107e96cdd512b67`.

Command:

```sh
GOCACHE=/tmp/vuoro-clean-room-lane1-go-cache \
GOMODCACHE=/tmp/vuoro-clean-room-lane1-go-mod \
go test ./cmd/bd -run 'TestEmbeddedUpdate/update_claim|TestEmbeddedUnclaim' -count=1
```

Result: **pass** (`ok github.com/steveyegge/beads/cmd/bd 0.124s`).

The pinned README specifies `bd update <id> --claim` as atomically setting an
assignee and status. Its embedded test `update_claim` verifies exactly that:
assignee is set and status becomes `in_progress`. It does not return a proof
value, and its update/unclaim interface accepts actor/assignee fields rather
than requiring a bearer proof for a later work mutation.

This is a positive R1-style planner-claim result and a negative R2 result. The
R2 conclusion is about authority semantics, not a test failure: an atomic
assignee/status transition cannot meet the frozen proof, rotation, delegation,
and recovery requirements by itself. Gas Town operates above this planner
state, so it cannot make Beads mutations proof-gated without adding a distinct
authority adapter—the composition tested by Lane 2.
