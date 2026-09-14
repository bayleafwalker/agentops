"""Test 3: the recall invariant; an UNDETERMINED boundary lands in misses, never in quiet."""

import json
from datetime import datetime

from fakes import MemoryGit
from operator_projection.replay import Replay, recall
from operator_projection.sources import ImageTags

DIGEST = "sha256:" + "b" * 64
REGISTRY = {
    "sources": {"shared_deployment": "dep.yaml", "shared_ks": "ks.yaml", "broker_config": "cfg.yaml",
                "broker_pvc": "bpvc.yaml", "cockpit_pvc": "cpvc.yaml"},
    "external": {"pins": {"repo": "vuoro", "path": "pins.json"}, "record_classes": {"repo": "auditctl", "path": "v.py"}},
}
POLICY = {"receipt_path": "/r", "repositories": [{"repository_id": "r", "provider": "github"}], "providers": {"github": {"app": "x"}},
          "policy": {"hosts": [{"host_id": "h"}], "bindings": [{"host_id": "h", "repository_id": "r", "capabilities": ["repo.read"]}], "capabilities": {}}}
CONFIG = "data:\n  production.json: '" + json.dumps(POLICY) + "'\n"
DEPLOYMENT = f"spec:\n  replicas: 1\n  image: ghcr.io/x/vuoro-service@{DIGEST}\n"


def history():
    base = {"dep.yaml": DEPLOYMENT, "cfg.yaml": CONFIG}
    files = {
        "appservice": {
            "c0": base,
            "c1": base | {"bpvc.yaml": "kind: PersistentVolumeClaim\n"},  # receipts D0 -> D2
            "c2": base | {"bpvc.yaml": "kind: PersistentVolumeClaim\n", "cfg.yaml": "data: [unparseable\n"},
            "c3": base | {"bpvc.yaml": "kind: PersistentVolumeClaim\n", "ks.yaml": "# comment only\n"},
        },
        "vuoro": {"v1": {"pins.json": json.dumps({"release_locks": [{"lock_id": "audit-adapter", "source_revision": "a1"}]})}},
        "auditctl": {"a1": {"v.py": 'RECORD_CLASSES = ("observation",)\n'}, "a2": {"v.py": 'RECORD_CLASSES = ("observation",)\n'}},
    }
    dates = [("c0", "2026-08-01T00:00:00+00:00"), ("c1", "2026-09-01T00:00:00+00:00"),
             ("c2", "2026-09-02T00:00:00+00:00"), ("c3", "2026-09-03T00:00:00+00:00")]
    return MemoryGit(files, {"appservice": dates, "vuoro": [("v1", "2026-07-01T00:00:00+00:00")], "auditctl": [("a1", "2026-07-01T00:00:00+00:00"), ("a2", "2026-07-02T00:00:00+00:00")]})


def test_undetermined_boundary_is_a_miss_and_the_invariant_holds():
    tags = ImageTags({"tags": {"sha-v1": DIGEST, "vuoro-service-v0.1.0": DIGEST}})
    result = Replay(REGISTRY, history(), tags).run(datetime.fromisoformat("2026-08-15T00:00:00+00:00"), datetime.fromisoformat("2026-09-14T00:00:00+00:00"))
    assert [(m.boundary, m.cls, m.member) for m in result["moves"]] == [("c1", "DURABILITY-UP", "credbroker.receipts")]
    assert result["misses"] == ["c2"] and result["quiet"] == ["c3"]
    summary = recall(result)
    assert summary == {"boundary_commits": 3, "mapped": 2, "misses": ["c2"]}
    assert summary["mapped"] + len(summary["misses"]) == summary["boundary_commits"]
