# OpenCode 2.0.32 ascending pagination and active-map evidence

`probe.py` runs against the pinned OpenCode 2.0.32 binary on `devbox-agent`. The server, sessions, HOME/XDG roots and credentials are temporary and synthetic. The fake inference provider listens on loopback; Bubblewrap unshares networking. No real provider config or credentials are read, and no generated password is recorded.

## Cursor ordering and changing transcript

Eighteen completed synthetic turns produced 54 transcript rows. The first request with `limit=50&order=asc` returned 50 rows. Following `cursor.next` with `limit=50` and omitting `order` returned 4 rows, then 0. Known user inputs were in creation order; the oldest input was on page 1 and newest on page 2.

The server rejected combining the cursor with the order parameter: `limit=50&order=asc&cursor=<next>` returned HTTP 400 with `_tag: InvalidCursorError`.

The cursor did not provide a stable snapshot across changes. After reading page 1, the probe began a new held turn and followed the same cursor: page 2 contained 5 rows while active. After the turn completed, following that same cursor returned 7 rows; the same page had gained the assistant and idle records. The page identity set changed. This proves only the observed cursor behavior for this server build and sequence.

## Active map with queued work

With one active held prompt and a queued successor, `/api/session/active` listed one running session. After interrupt returned `{ "interrupted": true }` and the transcript recorded idle outcome `interrupted`, the queued ID remained in the inbox and was absent from the transcript. The active map was empty after terminal idle and remained empty at a second sample two seconds later. Thus an empty active map can coexist with inbox work in this observed state.

These are point-in-time observations from a controlled fixture, not guarantees about other timings, concurrent turns, restarts, or eventual queue processing.

## Assertion negative control

The probe asserts that the same-cursor page identity set changes after the new turn completes. For a forced failure, make a temporary copy of `probe.py` and reverse the assertion condition from `same_cursor_page2_identity_set_changed` to `not same_cursor_page2_identity_set_changed`. Run that copy with the same isolated command; it must exit nonzero at `cursor stability observation mismatch`. The retained probe remains unchanged.
