import importlib.util
from pathlib import Path

root = Path("/tmp/route-compare-20261103/task1")
spec = importlib.util.spec_from_file_location("audit_model_routing", root / "scripts/audit_model_routing.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

assert module.observed_models({"models": [{"slug": "visible", "visibility": "list"}, {"slug": "hidden", "visibility": "hide"}]}) == {"visible"}
for bad in [
    {"models": [{"slug": "ok"}, {"slug": ""}]},
    {"models": [{"slug": "ok"}, {"slug": "  "}]},
    {"models": [{"slug": "ok"}, {"visibility": "hide"}]},
]:
    try:
        module.observed_models(bad)
    except ValueError:
        pass
    else:
        raise AssertionError(f"malformed catalogue accepted: {bad!r}")
assert module.observed_models([{"success": True, "observed_models": ["probe"]}]) == {"probe"}
print("task1 oracle passed")
