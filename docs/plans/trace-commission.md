## Verdict

**There is enough value to build a constrained experiment. There is not yet enough value to create a first-class `tracectl` domain.**

The useful product is not a general time-travel debugger. It is:

> **A runtime-evidence producer and read-only projection that tells an automated reviewer which changed behaviour was actually exercised, what returned, and where execution failed.**

The final framing in the discussion—**a kctl-shaped projection over an actionq-shaped event source**—is directionally right. The recorder remains outside Vuoro’s authority boundary; Vuoro merely accepts a digest-addressed evidence bundle. 

My recommendation is to build this as an incubating package called something like `traceq`, not immediately as `tracectl`.

---

## What the discussion gets right

### 1. The missing evidence layer is real

Today the chain is roughly:

```text
work authorized
  → code changed
  → tests exited 0
  → reviewer infers behaviour from diff and output
```

The missing link is:

```text
tests exited 0
  → these changed branches executed
  → these functions returned these bounded summaries
  → these exceptions occurred and were handled here
```

That is useful primarily for:

1. automated review;
2. failed or flaky test investigation;
3. runtime architecture-contract checking.

It is substantially less useful as a general human debugger. Humans already have debuggers, profilers and sufficiently creative profanity.

### 2. Producer and projection should be separate

The correct boundary is:

```text
pytest / runtime
    │
    ▼
trace producer ── writes immutable trace bundle
    │
    ▼
traceq ── read-only projection and context renderer
    │
    ▼
Vuoro evidence reference ── digest, metadata, work-item association
```

Vuoro does not enable tracing, configure tracing or control the process. It only knows:

```json
{
  "evidence_type": "execution-trace",
  "digest": "sha256:...",
  "schema_version": "trace.v1",
  "producer": "pytest-trace-evidence",
  "work_item": "..."
}
```

That preserves execution neutrality.

### 3. Python has adequate capture primitives

`sys.monitoring` can observe Python function starts and returns, calls, line events, instructions, jumps, branches and exceptions. Return callbacks receive the return value. Events can also be enabled for specific code objects rather than indiscriminately across the process. ([Python documentation][1])

Pytest hook wrappers can bracket individual test execution, making per-test trace attribution practical without replacing the pytest runner. ([pytest][2])

---

## Where the current concept overreaches

### “One recording, unlimited questions”

Only questions supported by recorded facts are answerable.

A recording of calls, returns and branches can answer:

* Was this function entered?
* Which test called it?
* What bounded summary did it return?
* Which observed branch was taken?
* Where did an exception propagate?

It cannot retroactively answer:

* What was every local variable at line 142?
* What object previously held this reference?
* What exact value was overwritten?
* What would have happened under another scheduling order?

That requires snapshotting frames, heap state or genuine deterministic replay.

### “All writes to `self._cache`”

Do not promise this in the MVP.

`sys.monitoring` can report that a VM instruction is about to execute, but its instruction callback only receives the code object and instruction offset. It does not hand over the operand stack or resulting assigned value. Generic attribute-write reconstruction therefore becomes bytecode instrumentation or debugger-grade frame inspection. ([Python documentation][1])

Support explicit write evidence later through one of:

```python
trace.observe_write("cache", key=key, value=value)
```

or instrumented wrappers:

```python
self._cache = TracedMapping(self._cache, channel="scheduler.cache")
```

Trying to infer arbitrary Python mutations from bytecode in v1 is how a small evidence plugin becomes an accidental dissertation.

### “Why was this line never reached?”

That is not a raw trace query. It is a derived analysis combining:

1. static control-flow possibilities;
2. observed incoming branch decisions;
3. the nearest executed dominator;
4. possibly test inputs.

The first useful answer should be modest:

```text
worker.py:142 was not reached.
The nearest observed divergence was worker.py:137:
condition `attempt < retry_limit` followed the false branch.
```

Do not claim semantic causality such as “because retry_limit was zero” unless that value was explicitly captured.

### Tracing every successful run

That will create a warehouse of immaculate evidence nobody reads.

Default capture should be selective:

* project-owned code only;
* changed modules and their immediate call neighbourhood;
* failed tests;
* explicitly requested tests;
* sampled successful review runs.

Coverage.py already records line and branch execution and supports measurement contexts, including associating execution with contexts. Reuse that capability rather than rebuilding coverage from monitoring callbacks. ([Coverage][3])

---

# Recommended construction

## Components

Use three packages, even if initially kept in one repository.

```text
tracefmt
├── versioned schemas
├── canonical serialization
├── redaction/value summarization
└── bundle validation

pytest-trace-evidence
├── pytest lifecycle hooks
├── coverage collection
├── sys.monitoring capture
├── filtering and budgets
└── immutable bundle writer

traceq
├── index builder
├── structured queries
├── changed-code analysis
├── context renderer
└── bundle comparison
```

`tracefmt` is the critical component. The recorder is replaceable. The projection is rebuildable. The format is the cross-boundary contract.

---

## Authoritative trace bundle

```text
trace-<run-id>/
├── manifest.json
├── events.ndjson.zst
├── coverage.json
├── tests.json
├── sources.json
└── digest
```

A disposable local projection may add:

```text
.traceq/indexes/<digest>.sqlite
```

The SQLite index is never evidence and never ingested. Delete it freely.

### Manifest

```json
{
  "schema": "trace.bundle.v1",
  "run_id": "01J...",
  "created_at": "2026-07-22T16:45:00Z",
  "producer": {
    "name": "pytest-trace-evidence",
    "version": "0.1.0"
  },
  "runtime": {
    "implementation": "cpython",
    "version": "3.14.0",
    "platform": "linux-x86_64"
  },
  "repository": {
    "commit": "29c2d9f6588b...",
    "dirty_diff_digest": "sha256:...",
    "repo_id": "..."
  },
  "selection": {
    "tests": ["tests/test_sync.py::test_retry"],
    "source_roots": ["src/"],
    "changed_files_only": true
  },
  "capture": {
    "calls": true,
    "returns": true,
    "exceptions": true,
    "branches": "coverage.py",
    "values": "safe-summary",
    "max_events": 250000
  },
  "redaction_policy": "default-v1"
}
```

### Event envelope

```json
{
  "schema": "trace.event.v1",
  "seq": 1824,
  "monotonic_ns": 4720091831,
  "test_nodeid": "tests/test_sync.py::test_retry",
  "pid": 8124,
  "thread_id": 8124,
  "task_id": null,
  "kind": "py_return",
  "symbol": {
    "module": "app.scheduler",
    "qualname": "Scheduler.enqueue",
    "file": "src/app/scheduler.py",
    "line": 88
  },
  "span_id": "s-192",
  "parent_span_id": "s-164",
  "value": {
    "type": "QueueEntry",
    "summary": "<QueueEntry id=…>",
    "truncated": false
  }
}
```

Do not store arbitrary `repr()` output without controls. It can:

* expose tokens and personal data;
* invoke expensive or faulty custom `__repr__`;
* produce enormous output;
* vary nondeterministically.

Default value capture should be:

```text
None / bool / bounded numbers
bounded strings after secret scanning
collection type + length
dataclass field allowlist
otherwise type + object identity token
```

---

# Construction plan

## Stage 0 — Define the hypothesis

The hypothesis should be narrow:

> Providing changed-code execution evidence to an automated reviewer detects materially useful issues that diff, test output and ordinary coverage do not.

Create a fixed evaluation corpus:

* several normal changes;
* several deliberately injected behavioural faults;
* at least a few async or concurrency-heavy tests;
* historical flaky failures where available.

Capture the current reviewer’s conclusions without trace evidence. This becomes the baseline.

Do not evaluate “was the generated trace interesting?” Evaluate whether it changed a decision correctly.

---

## Stage 1 — Build the format first

Implement `tracefmt` with:

* JSON Schema or equivalent typed models;
* explicit `schema_version`;
* canonical JSON serialization;
* streaming NDJSON validation;
* bundle-level SHA-256 digest;
* forward-compatible unknown fields;
* declared capture limitations;
* redaction-policy identifier.

Validation commands:

```bash
tracefmt validate ./trace-bundle
tracefmt digest ./trace-bundle
tracefmt inspect ./trace-bundle
```

Contract tests:

```text
producer output validates
unknown optional fields remain readable
unknown major schema version fails clearly
truncated shard fails validation
event sequence gaps are reported
reingesting identical bundle is idempotent
```

Avoid putting Vuoro types into `tracefmt`. The dependency direction must remain:

```text
Vuoro adapter → tracefmt
```

never:

```text
tracefmt → Vuoro
```

---

## Stage 2 — Implement a deliberately weak recorder

The first recorder should collect only:

* pytest node ID and phase;
* exit outcome;
* project-code function start and return;
* exception raise, handle and unwind;
* bounded return summaries;
* coverage.py line/branch data;
* stdout/stderr references already available from the test run.

Do not initially collect:

* every instruction;
* arbitrary local variables;
* object writes;
* third-party library internals;
* database payloads;
* network bodies;
* full function arguments.

Example invocation:

```bash
pytest \
  tests/test_sync.py::test_retry \
  --trace-evidence \
  --trace-scope=changed \
  --trace-output=.artifacts/traces
```

Example configuration:

```toml
[tool.trace_evidence]
source = ["src"]
exclude = [
  "src/generated/**",
  "src/migrations/**"
]
capture = ["calls", "returns", "exceptions"]
value_policy = "safe-summary"
max_events = 250000
max_bundle_mb = 50
on_limit = "degrade"
```

`degrade` should stop detailed event capture but preserve:

* test result;
* coverage;
* event count;
* truncation reason.

A partial trace explicitly marked partial is better than an OOM-shaped epistemology.

---

## Stage 3 — Build structured queries, not natural-language magic

Initial CLI:

```bash
traceq summary <digest-or-path>

traceq tests <digest-or-path>

traceq calls <digest-or-path> \
  --symbol app.scheduler.Scheduler.enqueue

traceq returns <digest-or-path> \
  --symbol app.scheduler.Scheduler.enqueue

traceq exceptions <digest-or-path>

traceq changed-coverage <digest-or-path> \
  --diff-base origin/main

traceq path <digest-or-path> \
  --to src/app/worker.py:142

traceq render <digest-or-path> \
  --format context \
  --diff-base origin/main \
  --budget 12000
```

The internal query API should use typed predicates:

```python
query.events(
    kinds={EventKind.PY_RETURN},
    symbol="app.scheduler.Scheduler.enqueue",
    test_nodeid="tests/test_sync.py::test_retry",
)
```

An LLM can translate a question into these predicates later. Do not make the LLM the query engine. Otherwise every answer becomes an expensive interpretation of a large NDJSON haystack.

---

## Stage 4 — Make the renderer the product

The highest-value output is not an interactive trace shell. It is a bounded review context.

Example:

```text
EXECUTION EVIDENCE

Run:
- commit: 29c2d9f
- tests: 8 passed
- trace complete: yes
- changed executable lines: 31
- changed lines executed: 24
- changed branches observed: 7/9

Unexercised changed behaviour:
- src/app/worker.py:141-146
- src/app/scheduler.py:92 false branch

Observed changed symbols:
- Scheduler.enqueue: called 6 times by 2 tests
- Scheduler.retry: called 1 time
- Worker.abort: not called

Notable returns:
- Scheduler.enqueue → QueueEntry, 6 occurrences
- Scheduler.retry → False, 1 occurrence

Exceptions:
- RetryableError raised and handled once
- no unhandled exceptions

Evidence limitations:
- arguments were not captured
- third-party modules were excluded
- attribute writes were not recorded
```

This gives a reviewer facts without flooding its context window with a miniature operating system audit log.

---

## Stage 5 — Integrate with dispatch-review

Add trace generation after relevant tests and before review:

```text
implementation
  → select affected tests
  → execute tests with evidence capture
  → ingest bundle by digest
  → render bounded context
  → provide diff + test report + trace context to reviewer
```

Reviewer instructions should require explicit separation:

```text
1. Findings supported by execution evidence
2. Findings inferred from code
3. Behaviour not exercised by the supplied tests
```

This is important. Trace evidence should reduce unsupported inference, not merely give the reviewer more material with which to hallucinate confidently.

Store review telemetry:

```json
{
  "trace_digest": "sha256:...",
  "trace_queried": true,
  "queries_used": [
    "changed-coverage",
    "returns:Scheduler.enqueue"
  ],
  "review_changed_after_trace": true,
  "finding_ids": ["F-03"]
}
```

That tells you whether the read side actually exists.

---

## Stage 6 — Add failed-run capture

Only after the normal review slice works, enable CI failure capture.

Policy:

```yaml
trace_evidence:
  successful_runs:
    mode: changed-tests
    retention: short
  failed_runs:
    mode: full-project-code
    retention: extended
  flaky_retries:
    preserve_each_attempt: true
```

Each retry must receive a separate run ID and digest. Do not overwrite the first failing trace with the passing retry; that would reproduce precisely the evidence evaporation the tool is meant to prevent.

For multiprocessing or `xdist`, start with independent child bundles:

```text
run/
├── worker-gw0/
├── worker-gw1/
└── aggregate-manifest.json
```

Merge only in the projection. Avoid pretending distributed event order is total when it is not.

---

## Stage 7 — Add derived “why not reached” analysis

Implement this only after the raw queries are trusted.

Algorithm:

1. parse the target file;
2. construct a control-flow graph;
3. find the target’s immediate dominators;
4. identify the nearest executed dominator;
5. locate observed outgoing branch;
6. report the divergence without inventing unrecorded values.

Output:

```text
Target src/app/worker.py:142 was not executed.

Nearest observed control-flow divergence:
- location: src/app/worker.py:137
- observed edge: bytecode offset 84 → 110
- target requires alternate edge: 84 → 86
- tests observing divergence:
  - tests/test_worker.py::test_no_retry

No operand values were recorded, so the condition's semantic cause
cannot be established from this trace.
```

That is defensible. “The line was skipped because the retry count was exhausted” may not be.

---

# Promotion criteria

Promote this into a durable `tracectl`-class tool only when all of these are true:

* reviewers actually request trace-derived views;
* trace evidence finds issues not already obvious from diff plus coverage;
* the context renderer remains bounded and stable;
* capture overhead is acceptable under representative tests;
* secret scanning finds no uncontrolled leakage;
* at least one flaky or irreproducible failure is materially shortened;
* another runtime producer could feasibly implement `tracefmt`.

Suggested quantitative gates:

```text
Capture overhead:
- median ≤ 20%
- p95 ≤ 50% for selected tests

Storage:
- median bundle ≤ 10 MB
- hard default cap 50 MB

Use:
- trace consulted in ≥ 30% of eligible reviews

Value:
- at least 3 materially correct review changes
  across the evaluation corpus

Safety:
- zero known plaintext secrets in test corpus bundles
```

The review-use threshold matters more than the technical thresholds. A perfectly engineered trace nobody asks about is just observability-themed hoarding.

## Kill criteria

Stop or reduce the project to ordinary coverage evidence when:

* reviewers rarely use anything beyond changed-line coverage;
* call and return evidence does not alter findings;
* trace output mainly increases review tokens;
* value capture requires arbitrary argument/local-variable recording;
* async and subprocess correlation dominates the implementation;
* the format becomes coupled to Vuoro lifecycle concepts.

In that case, retain only:

```text
coverage context
changed-branch report
test-to-symbol mapping
exception summary
```

That smaller result may still be worthwhile.

---

# Rollback design

The architecture should make rollback boring:

1. disable `--trace-evidence`;
2. remove the dispatch-review renderer input;
3. delete derived SQLite indexes;
4. optionally expire trace bundles;
5. leave existing Vuoro evidence records as historical references.

No authority state, sprint lifecycle or work ownership should depend on trace availability.

Feature flags:

```toml
[tool.dispatch.review]
execution_evidence = "optional"
execution_evidence_failure = "continue"
```

Tracing failure must initially be non-blocking:

```text
test failure → blocks as usual
trace capture failure → warning, review continues
```

Only schema corruption or secret-policy violations should reject evidence ingestion.

---

## Recommended first vertical slice

Build precisely this:

```text
pytest plugin
  ├── per-test attribution
  ├── coverage.py contexts
  ├── project-code calls
  ├── bounded return summaries
  └── exception events

trace bundle v1
  ├── manifest
  ├── compressed events
  └── coverage

traceq render --format context
  ├── changed code exercised
  ├── changed code not exercised
  ├── changed symbols called
  ├── return summaries
  └── exception summary

dispatch-review
  └── consumes rendered context
```

Explicitly defer:

* generic object-write tracking;
* deterministic replay;
* arbitrary natural-language queries;
* cockpit UI;
* multi-language tracing;
* trace-driven lifecycle decisions;
* a new Vuoro domain.

That slice is coherent, falsifiable and architecturally reversible. Build it. Do not yet build the grand unified observatory for everything that has ever happened inside a process.

[1]: https://docs.python.org/3/library/sys.monitoring.html "sys.monitoring — Execution event monitoring — Python 3.14.6 documentation"
[2]: https://docs.pytest.org/en/stable/how-to/writing_hook_functions.html?utm_source=chatgpt.com "Writing hook functions"
[3]: https://coverage.readthedocs.io/en/latest/branch.html?utm_source=chatgpt.com "Branch coverage measurement"
