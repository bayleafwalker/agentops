import importlib.util
from pathlib import Path

root = Path("/tmp/route-compare-20261103/task2")
spec = importlib.util.spec_from_file_location("audit_model_routing", root / "scripts/audit_model_routing.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

for primary in [None, "", "   "]:
    rows = module.audit({"aliases": {"build": {"codex": {"model": primary, "verified": True}}}}, {"codex": set()})
    assert rows[0]["issues"] == ["primary-unconfigured"], (primary, rows)
rows = module.audit({"aliases": {"build": {"codex": {"model": "missing", "verified": True}}}}, {"codex": set()})
assert rows[0]["issues"] == ["primary-not-observed"], rows
rows = module.audit({"aliases": {"build": {"codex": {"verified": False}}}}, {"codex": set()})
assert rows[0]["issues"] == ["primary-unverified", "primary-unconfigured"], rows
print("task2 oracle passed")
