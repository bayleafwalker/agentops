"""A small synthetic estate over the real registry paths. No value here is a real digest, token or record."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from fakes import MemoryGit

REGISTRY = yaml.safe_load((Path(__file__).resolve().parents[1] / "registry.yaml").read_text()) | {"commit": "f" * 40}
NOW = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
D_SHARED, D_OLD = "sha256:" + "1" * 64, "sha256:" + "0" * 64
S = REGISTRY["sources"]
COCKPIT = REGISTRY["divergence"][0]["manifests"]["agent-cockpit sidecar"]
TAGS = {"source": "ghcr.io/v2/synthetic", "evaluated_at": "2026-09-14T11:00:00+00:00",
        "tags": {"sha-v1": D_SHARED, "vuoro-service-v9.9.1": D_SHARED, "sha-v0": D_OLD, "vuoro-service-v9.8.0": D_OLD}}


def policy(bindings: list[dict]) -> dict:
    return {"receipt_path": "/var/lib/receipts.sqlite",
            "repositories": [{"repository_id": "repo_a", "provider": "github"}, {"repository_id": "repo_b", "provider": "github"}],
            "providers": {"github": {"app_id": "12345"}},
            "policy": {"hosts": [{"host_id": "workstation", "trust_profile": "interactive"}, {"host_id": "devbox", "trust_profile": "unattended"}],
                       "bindings": bindings, "capabilities": {"repo.read": {"ttl_seconds": 300}}}}


def config(document: dict, extra: str = "") -> str:
    return "kind: ConfigMap\ndata:\n  production.json: '" + json.dumps(document) + "'\n" + extra


def deployment(digest: str, label: str) -> str:
    return f"metadata:\n  labels:\n    appservice.kotona.app/release: {label}\nspec:\n  replicas: 1\n  image: ghcr.io/x/vuoro-service@{digest}\n"


BINDINGS = [{"host_id": "workstation", "repository_id": "repo_a", "capabilities": ["repo.read", "repo.write"]}]


def estate(moves: bool = True, retired: bool = False) -> MemoryGit:
    base = {S["shared_deployment"]: deployment(D_OLD, "vuoro-service-v9.8.0"), COCKPIT: deployment(D_OLD, "x"),
            S["broker_config"]: config(policy(BINDINGS)), S["broker_pvc"]: "kind: PersistentVolumeClaim\n", S["cockpit_pvc"]: "kind: PersistentVolumeClaim\n",
            "clusters/main/kubernetes/apps/cred-broker/config/production.json": json.dumps(policy([]))}
    rolled = base | {S["shared_deployment"]: deployment(D_SHARED, "vuoro-service-v9.9.1")}
    granted = rolled | {S["broker_config"]: config(policy(BINDINGS + [{"host_id": "devbox", "repository_id": "repo_b", "capabilities": ["repo.read"]}]))}
    history = [("c0", "2026-08-01T00:00:00+00:00"), ("c1", "2026-09-01T00:00:00+00:00"), ("c2", "2026-09-10T00:00:00+00:00")]
    files = {"appservice": {"c0": base, "c1": rolled if moves else base, "c2": granted if moves else base}}
    if retired:  # P4 (appservice #1647): the agent-cockpit component is deleted, sidecar manifest and state PVC together
        history.append(("c3", "2026-09-12T00:00:00+00:00"))
        files["appservice"]["c3"] = {p: t for p, t in granted.items() if p not in (COCKPIT, S["cockpit_pvc"])}
    if not moves:
        history = [("c0", "2026-08-01T00:00:00+00:00"), ("c1", "2026-09-01T00:00:00+00:00")]
        files["appservice"] = {"c0": base, "c1": base}
    pins = lambda audit, work: json.dumps({"release_locks": [  # noqa: E731
        {"lock_id": "audit-adapter", "source_revision": audit[0], "distribution_version": audit[1]},
        {"lock_id": "work-adapter", "source_revision": work[0], "distribution_version": work[1]}]})
    files |= {
        "vuoro": {"v0": {REGISTRY["external"]["pins"]["path"]: pins(("a1", "0.1.0"), ("s1", "0.3.0"))},
                  "v1": {REGISTRY["external"]["pins"]["path"]: pins(("a1", "0.1.0"), ("s1", "0.3.5"))},
                  "v2": {REGISTRY["external"]["pins"]["path"]: pins(("a2", "0.1.1"), ("s1", "0.3.5"))}},
        "auditctl": {"a1": {"auditctl/validation.py": 'raise ValueError("record_class must be observation")\n'},
                     "a2": {"auditctl/validation.py": 'RECORD_CLASSES = ("observation", "decision")\n', "pyproject.toml": '[project]\nversion = "0.1.1"\n'}},
        "sprintctl": {"s2": {"pyproject.toml": '[project]\nversion = "0.3.6"\n'}},
        "agentops": {"g1": {
            REGISTRY["consumer_set"]["profiles"][0]: json.dumps({"required_authorities": ["work:read", "work:claim", "work:pilot-read", "work:project-read"]}),
            REGISTRY["consumer_set"]["profiles"][1]: json.dumps({"required_authorities": ["work:read", "work:claim"]}),
            REGISTRY["consumer_set"]["code"][0]["path"]: 'const a = 1;\nconst b = 2;\nrun(["claim", "list-sprint"]);\n',
            "project.toml": '[[members]]\nrepo_id = "agentops"\n[[members]]\nrepo_id = "vuoro"\n[[members]]\nrepo_id = "sprintctl"\n'}},
    }
    return MemoryGit(files, {"appservice": history, "vuoro": [("v2", "2026-09-05T00:00:00+00:00")],
                             "auditctl": [("a1", "2026-08-01T00:00:00+00:00"), ("a2", "2026-09-01T00:00:00+00:00")],
                             "sprintctl": [("s2", "2026-09-01T00:00:00+00:00")], "agentops": [("g1", "2026-09-01T00:00:00+00:00")]})
