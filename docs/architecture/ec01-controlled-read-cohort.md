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
request, a request after the wall cap, a second request in flight, an oversized
body, a metadata request with a body, an invocation for another repository, or
an unlisted operation or argument. Redirects are never followed: a 3xx is
`http-refused`, and a response carrying followed-redirect history is
`redirect-refused`. A refusal is final: no request is admitted after one, and a
refusal the client swallowed is raised again at the end of the trial. Metadata
JSON that is not an object, nests too deeply or cannot be measured gets a
bounded outcome (`response-shape-refused`, `shape-depth-limit`). A CLI read
that returns more than one message, or a nonzero CLI return code, also stops
the run. Changed plan, source, package, adapter, inventory, release, catalog,
profile or repository bindings are refused too.

## Profile binding

The plan binds one exact profile per mode in `modes.<mode>.profile_binding`:

| Mode | Profile id | Source environment |
|---|---|---|
| `served-cli-inbox-read` | `workstation-inbox-native-vuoro-shared` | `workstation` |
| `host-adapter-metadata` | `devbox-inbox-native-vuoro-shared` | `devbox` |

Each binding pins these fields:

- the profile id and revision;
- the source environment;
- the target endpoint and environment id;
- the required authorities: `work:read` and `work:evidence`.

The whole profile file is not hashed, and its `credential_ref` is neither bound
nor read. Before any request, the collector reads only the `--profile` JSON and
compares those fields with the binding. Any difference ends the run as
`refused` with `profile-binding-mismatch`, with zero requests sent.

This closes the gap behind the first live CLI attempt: the run used the
workstation maintenance profile (`workstation-vuoro-shared`), which has no
principal or workspace inbox, and it ended `incomplete` with 403
`identity-unbound`. That profile is now refused locally, as is either host's
profile used for the other mode.

Report status is one of:

- `complete`: all 5 trials ran, and the requests sent equal the budget.
- `refused`: nothing was admitted to the transport, even if the guard already
  existed.
- `incomplete`: stopped after at least one request. Completed samples are kept,
  and every request that was let through is recorded with its outcome (`ok`, or
  the refusal reason such as `request-timeout` or `http-refused`). An operator
  interrupt (Ctrl-C) after traffic also yields an `incomplete` report, with
  reason `interrupted`. This covers the three forms an interrupt takes: a
  KeyboardInterrupt, click's `Abort` raised from a KeyboardInterrupt during the
  CLI trial, and the cancellation that `asyncio.run` delivers to the request in
  flight. That request is labelled `interrupted`. A bare `Abort` (such as
  `ctx.abort()` or a declined confirm) or an `Abort` from EOF is not an
  interrupt: it ends as `dependency-or-transport-refused` with exit 2. Tests
  cover a raised KeyboardInterrupt, a real SIGINT in the preflight and in a CLI
  trial, and each of the three kinds of `Abort`.

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
implementation and the plan packet. The plan's Sprintctl module hashes match
the published v0.21.0 wheel asset (sha256 `30fa8b14…908d`), and the collector
checks them against whatever is installed on the sampling host. Then, from the
canonical Agentops checkout with its served repository marker, run the CLI mode
on the workstation with its inbox identity:

```sh
python -B scripts/observe_owner_workload.py \
  --plan verification/fixtures/ec01-controlled-read-cohort-2733.json \
  --plan-sha256 <digest-approved-at-review> \
  --mode served-cli-inbox-read \
  --profile environment-record/profiles/workstation-inbox-native-vuoro-shared.json \
  --adapter-script scripts/host_adapter.py
```

Run the metadata mode on devbox, as the adapter's UID, with its existing profile:

```sh
python -B scripts/observe_owner_workload.py \
  --plan <plan path> --plan-sha256 <digest-approved-at-review> \
  --mode host-adapter-metadata \
  --profile /etc/agentops/host-adapter/vuoro-profile.json \
  --adapter-script <installed host_adapter.py>
```

Exit `0` is `complete`. Exit `2` is `refused` or `incomplete`, with a bounded
reason. Exit `130` is an interrupted run, after its report is printed. A non-complete run is evidence about the attempt only. It is not retried
automatically.
