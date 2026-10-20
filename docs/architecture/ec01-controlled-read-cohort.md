# EC-01 controlled read cohort

`scripts/observe_owner_workload.py` collects a small, reviewed cohort of owner
reads for agentops item #2733. It is controlled qualification traffic. Its
reports never count as natural workload, workflow success, population
representativeness or estate completeness; each report states those as
`unknown`. The approved plan is
`verification/fixtures/ec01-controlled-read-cohort-2733.json`.

## Modes and request budget

The cohort has exactly two modes:

- `host-adapter-metadata`: `host_adapter.inspect_owner(profile)`, metadata only.
  Each trial is a handshake GET and a catalog GET.
- `served-cli-inbox-read`: the released `sprintctl message read --after-seq 0
  --limit 1`, the exact `work.message.read-v1` envelope with null idempotency
  and basis fields. Output is parsed in memory and discarded.

Sprintctl 0.21.0 (commit `ca3aa1b`, #2822) handshakes a fresh client before every
authenticated invoke: `served._invoke_operation` calls `handshake()` then
`invoke()`, and the released client's `invoke()` fetches the catalog before the
POST. Each CLI trial is therefore handshake GET, catalog GET, invocation POST.
Sprintctl 0.20.0 sent catalog and invocation only. Both the plan and the installed
package must be 0.21.0, and 0.20.0 is refused before any request.

Each mode starts with one metadata preflight (handshake and catalog, with an
exact contract match for the read operation), then runs 5 sequential trials. The
request budget follows from those sequences:

| Mode | Preflight | Per trial | Trials | Budget |
|---|---|---|---|---|
| `host-adapter-metadata` | 2 | 2 | 5 | 12 |
| `served-cli-inbox-read` | 2 | 3 | 5 | 17 |

The code computes the budget from its sequence constants. The plan carries the
same derivation, and a plan that disagrees is refused. Other bounds: one request
in flight at a time, 1 s between trials, 60 s wall cap per mode, 5 s per request
(cut to the remaining wall time when less), 4 KiB request bodies, 2 MiB response
bodies, no retries, `Accept-Encoding: identity` and no encoded responses.

## Guard and report

The guard wraps the released client's own `httpx.AsyncClient.send`, so TLS and
proxy setup are left as the client sets them. It admits only the declared
method and path at each position, on the profile's origin, with no query or
redirect. Anything else is refused before it reaches the transport: an extra or
out-of-order request, a 0.20.0-style trial without a handshake, the 18th
request, a request after the wall cap, an oversized body, or an unlisted
operation or argument. Changed plan, source, package, adapter, inventory,
release, catalog, profile or repository bindings are refused too.

Report status is one of:

- `complete`: all 5 trials ran, and the requests sent equal the budget.
- `refused`: stopped before any request reached the transport.
- `incomplete`: stopped after at least one request. Completed samples are kept,
  and every request that was let through is recorded with its outcome (`ok`, or
  the refusal reason such as `request-timeout` or `http-refused`).

The `window` record holds start and end UTC times, elapsed time, the wall cap,
the budget and its derivation, the number of requests sent and the trials
planned and completed. Events carry phase, trial, method, fixed route, offset,
duration, body byte counts, status, HTTP/TLS version enums and JSON shape
counts. Payloads, keys, scalar values, IDs, cursors, credentials, profile and
endpoint strings, and server error text are never retained.

The collector writes nothing locally: it only prints the report. `run()` turns
off bytecode writes while it imports the adapter and the released modules, then
restores the setting, and the script entry point sets the same flag. The
remaining bytecode is `scripts/__pycache__` from test imports, which is
gitignored.

## What it proves and what it does not

It shows that this exact client, profile and repository binding can complete
the declared read path, within the stated bounds. It records body sizes, shape
classes and five timing samples for that path. These are inputs to EC-00
benchmark case selection.

It does not establish throughput or p95 figures, compression or full wire-byte
sizes, effective authority beyond the one read, MCP, browser, Go or Rust
consumers, mutation workloads, operator workflow success, EC-01 completion or
interface retirement. An empty inbox is recorded as `empty`. It is not evidence
of a populated workload.

## Verification and running

The default scripts suite runs `scripts/tests/test_owner_workload.py`. It uses
fake requests and responses, plus fake `httpx` and `vuoro_client` modules, and
needs no optional client. It covers the budget derivation, the per-request
timeout, the wall cap, the count cap, the handshake sequence, the body caps, and
the `incomplete` and `refused` statuses. It runs with empty, read-only
HOME/XDG/cwd directories and checks that no state or bytecode is written.
`scripts/tests/test_owner_workload_released.py` runs the real Sprintctl 0.21.0
CLI and the real `vuoro-client` 0.1.1 over `httpx.MockTransport`. The default
suite skips it when those packages are absent, and that skip is not
released-client evidence. Run it with the released interpreter:

```sh
/path/to/sprintctl-0.21.0-python -B -m pytest -q scripts/tests/test_owner_workload_released.py
```

Live sampling is not authorized by this change. Before a sample, root reviews the
implementation and the plan packet, and confirms that the installed 0.21.0 module
hashes match the plan bindings. (The bindings were computed from the 0.21.0
release source; installed and git bytes matched for 0.20.0.) Then, from the
canonical Agentops checkout with its served repository marker, once per mode:

```sh
python -B scripts/observe_owner_workload.py \
  --plan verification/fixtures/ec01-controlled-read-cohort-2733.json \
  --plan-sha256 <digest-approved-at-review> \
  --mode served-cli-inbox-read --profile /path/to/existing/profile.json \
  --adapter-script scripts/host_adapter.py
```

Exit `0` is `complete`. Exit `2` is `refused` or `incomplete`, with a bounded
reason. A non-complete run is evidence about the attempt only. It is not retried
automatically.
