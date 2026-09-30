"""Test-wide isolation of the audit store.

Several scripts under test publish to auditctl as a side effect. auditctl resolves its
store by walking up from the CWD, so an unisolated test resolves to *this repository's*
live index and writes fixture events into it.

That is not hypothetical. By 2026-08-29 the agentops index held 36 events that no shard
carried, with `metadata.session` values of `sess-a`, `sess-mixed`, `sess-poison`, `x`,
`y` and `rs-demo` -- fixture names, in the production index. They were index-only rather
than merely spurious because a test that isolates `AUDITCTL_ARTIFACTS_ROOT` but not
`AUDITCTL_DB` splits the write: the shard lands in the temp root and the index row lands
here. `rebuild` then reports them as data loss, and it takes a real investigation to
find out they are not.

Isolating both halves per test is deliberate over isolating one: the two must always be
resolved together, which is the same invariant auditctl itself now enforces
(`resolve_audit_context`). It is autouse rather than opt-in because the failure is
silent, so a test that forgets it produces no signal until someone audits the index.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_audit_store(tmp_path_factory, monkeypatch) -> None:
    store = tmp_path_factory.mktemp("audit-store")
    index = store / ".auditctl"
    index.mkdir()
    (index / "auditctl.db").touch()
    monkeypatch.setenv("AUDITCTL_DB", str(index / "auditctl.db"))
    monkeypatch.setenv("AUDITCTL_ARTIFACTS_ROOT", str(store))


# The saved-workflow harness tests (test_saved_workflows.py) need node. A skip is reported as success by
# pytest, so a verifier running the suite outside the manifest's nix shell would report a pass over tests
# that never ran (#2562, event 4049 finding 3). A skip whose reason is the node requirement is a failure.
_NODE_SKIP_MARKER = "node"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if not report.skipped or call.when not in ("setup", "call"):
        return
    longrepr = report.longrepr
    reason = str(longrepr[2]) if isinstance(longrepr, tuple) and len(longrepr) == 3 else str(longrepr)
    if item.module.__name__.endswith("test_saved_workflows") and _NODE_SKIP_MARKER in reason.lower():
        report.outcome = "failed"
        report.longrepr = f"node is required to run the saved-workflow harness tests and was not found on PATH ({reason}); run them inside the manifest's nix shell"
