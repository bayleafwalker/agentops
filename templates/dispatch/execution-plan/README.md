# Immutable execution-plan compiler

This directory owns the boundary between Sprintctl-owned work snapshots and
ActionQ-owned execution lifecycle. The compiler does not read Sprintctl, call a
network service, resolve mutable Git refs, create ActionQ actions, or carry
claim proofs and credentials.

Compilation has two explicit stages:

1. `dispatch-plan-source/v1` freezes repositories, exact commits, owner work
   revisions, topology, integration membership, and verification policy into
   canonical `dispatch-plan/v1` bytes. The plan reference is
   `artifact:sha256:<sha256(canonical-bytes)>`; it is not embedded in the plan.
   Each source work record carries both `selected_revision` and a freshly read
   `observed_revision`; compilation rejects drift unless they are exactly equal
   and emits their agreed value as the plan's single canonical `revision`.
2. `action-bindings/v1` binds the already-created ActionQ action and attempt
   identities in exact plan order. Realization emits `execution-group/v1` with
   the released, exact six-field `execution-envelope/v1` records.

Generic group realization refuses any plan containing `stacked` entries.
#2036 freezes that topology, but released contracts do not expose a stable
predecessor-result commit binding. The downstream consumer owns staged
resolution and must bind the predecessor candidate commit before execution;
concurrent or source-base realization here would be unsafe.

`integration-results/v1` supplies exact ordered immutable member result refs
for one compiled wave integration. `realize-integration` emits a canonical
`integration-realization/v1` wrapper containing the exact released
`candidate-integration-spec/v1` and `action-creation-request/v1` records.

Arrays whose order defines behavior (`entries`, `member_ids`, `allowed_paths`)
retain authored order. Set-like `required_capabilities` and `acceptance_gates`
must already be sorted and unique. Canonical JSON is compact, UTF-8, key-sorted,
and contains no floats, timestamps, host paths, or self-digest.
Golden JSON files retain the repository's terminal newline; tests remove that
single presentation byte before comparing them with canonical contract bytes.
The plan loader likewise permits only that one repository presentation byte
and always returns/digests the canonical bytes without it.

```bash
python templates/dispatch/scripts/compile_execution_plan.py compile \
  --source templates/dispatch/execution-plan/fixtures/source.json \
  --output /tmp/dispatch-plan.json
python templates/dispatch/scripts/compile_execution_plan.py check \
  --source templates/dispatch/execution-plan/fixtures/source.json \
  --output /tmp/dispatch-plan.json
python templates/dispatch/scripts/compile_execution_plan.py realize \
  --plan /tmp/dispatch-plan.json \
  --bindings templates/dispatch/execution-plan/fixtures/bindings.json \
  --output /tmp/execution-group.json
python templates/dispatch/scripts/compile_execution_plan.py realize-integration \
  --plan /tmp/dispatch-plan.json \
  --results templates/dispatch/execution-plan/fixtures/integration-results.json \
  --output /tmp/integration-realization.json
```

`compile` and `realize` write atomically. `check` writes nothing and exits 0
for exact bytes, 1 for missing/drifted output, and 2 for invalid input. All
commands emit one JSON status object. Optional repeated
`--repo-root REPOSITORY_ID=PATH` checks exact local HEAD, commit existence, and
credential-free origin equivalence without fetching.
