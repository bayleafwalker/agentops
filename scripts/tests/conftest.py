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
