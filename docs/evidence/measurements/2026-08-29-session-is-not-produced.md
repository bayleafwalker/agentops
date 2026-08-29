# Session identity, measured in the stores rather than in the schema

**Date:** 2026-08-29 · **Scope:** every audit store reachable under `/projects/dev` **on the
workstation** — 11 stores, 1593 events. devbox holds its own disjoint clone set at the same
paths; nothing here describes it. This is a count of what is on disk, not of what any code
intends.

The contract says Session is the one object of the four that is never *produced*, though
fragments exist. That is a claim about the code. This is the same claim checked against the
data, because the two have disagreed before.

## The typed field is empty everywhere

`runtime_session_id` is a first-class field of the event schema (`schema_version: 1`),
sitting beside `origin_stream_id` and `correlation_id`. Across all 11 stores and all 1593
events it is populated **zero** times. Not sparsely: never.

## The value exists anyway, one line away, in an untyped blob

`metadata.session` is populated in 1258 events. So the producers *have* a session identity
and write it down — they write it into the free-form metadata dictionary rather than into
the field reserved for it.

That 1258 is not the number to quote, and the reason is the reason this page exists:

| `metadata.session` | events | what it is |
|---|---|---|
| uuid-shaped, 35 distinct | **354** | real sessions, across 8 stores |
| `sess-a`, `sess-b`, `sess-poison`, `no-transcript`, `sess-t1`, `smoke3`, `test-1` | 904 | **test fixtures** |
| `session_013QjnAPkGj3yWJqxWN9k2wk` | 4 | a runtime session id — a *different* id shape |

The 904 are the same fixture family that two independent passes previously read as
production residue, and 898 of them sit in the two `agentops` stores, which is consistent
with the suites having written into the live agentops index until `b55df7e` fixed it. They
are historical leakage, not sessions. **The honest figure is 354.**

## What that combination actually says

Session is not missing for lack of data. It is produced 354 times and has nowhere typed to
go, so it lands in a dictionary that validates nothing — and the evidence that this matters
is in the table above, twice over:

- the same key holds real sessions and test fixtures with nothing to tell them apart, which
  is precisely how the fixtures came to be read as production data; and
- it holds **two different identifier shapes** — a uuid and a `session_01…` runtime id —
  because an untyped field cannot refuse either, and nothing reconciles them.

Meanwhile `metadata.runtime_session_id` is populated **zero** times, even though the Stop
hook reads `.runtime_session_id` from its payload and writes the key: the value arrives
empty and is stored empty. So the one identifier that would tie an event to an actual
running session is absent in both the place it belongs and the place it was improvised into.

## Consequence for the four objects

Project, Workspace and Environment have produced artifacts a consumer can read. Session has
354 occurrences of a value in a place where it cannot be validated, joined, or trusted, and
an empty field where it could have been. Making Session a produced object is therefore not
a schema addition — the schema is already there and already empty. It is a question of
which producer owns the value and what entitles it to assert one, which is the same
question the coherent-redirect measurement arrives at from the other side: see
`2026-08-29-coherent-context-redirect.md`, where the missing origin on a misfiled event and
this missing session are the same absence.

## Method note

The first pass of this measurement reported 1258. That number is correct and useless: it
answers "how often is the key present" when the question was "how often is a session
recorded". The fixtures were separated only because this stack has already paid for not
separating them. Pair the count with the population it is a count *of*, before quoting it.
