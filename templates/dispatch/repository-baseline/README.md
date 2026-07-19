# Repository dispatch baseline

This directory is the copyable minimum for a repository that owns a queue,
claim, lease, retry, recovery, projection, publication, reconciliation, or
backend-parity boundary.

## Adopt

1. Copy the files to the repository root while preserving their relative paths.
2. Rename `example.dispatch.json` to `<repo-id>.dispatch.json`.
3. Replace `example` and the illustrative source paths with repository-owned values.
4. Write the semantic protocol before claiming executable evidence.
5. Keep context packets data-only and publish results as CI artifacts by default.
6. Run the shared repository gate from the consumer root.

```bash
python /projects/dev/agentops/templates/dispatch/scripts/validate_verification_artifacts.py --root .
```

`required_on_change` is a gate declaration, not repair authority. A dispatcher
or release gate uses `--changed-path`, `--require-results`, and an optional
`--implementation-sha` when it is prepared to enforce execution evidence.

## Python flat-layout packaging

A top-level `verification/` directory is data, not an import package. Projects
using setuptools flat-layout discovery must declare their packages explicitly
or use a `src/` layout. For example:

```toml
[tool.setuptools]
packages = ["example"]
```

Alternatively, constrain package discovery with an include list. A build and
wheel-content check should remain in CI so future data-only top-level
directories cannot enter distribution discovery accidentally.
