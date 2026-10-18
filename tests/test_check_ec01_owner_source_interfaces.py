import importlib.util
import json
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts/check_ec01_owner_source_interfaces.py"
spec = importlib.util.spec_from_file_location("checker", SCRIPT)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)

def fixture(tmp_path):
    repos = []
    roots = {}
    for name, owner in (("cred-broker", "cred-broker"), ("datacluster-template", "datacluster"), ("acceptance-lab", "acceptance-lab"), ("homelab-analytics", "homelab-analytics")):
        root = tmp_path / name
        root.mkdir()
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        (root / "contract.txt").write_text(name)
        subprocess.run(["git", "-C", str(root), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "add", "contract.txt"], check=True)
        subprocess.run(["git", "-C", str(root), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"], check=True)
        rev = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
        import hashlib
        sha = hashlib.sha256(name.encode()).hexdigest()
        repos.append({"owner": owner, "repo": name, "source_revision": rev, "visibility_observation": {"value": "public", "observed_at": "2026-10-18"}, "source_files": [{"path": "contract.txt", "sha256": sha}]})
        roots[name] = root
    interfaces = []
    for r in repos:
        interfaces.append({"id": "i-"+r["repo"], "repo":r["repo"], "owner":r["owner"], "source_revision":r["source_revision"], "source_files":r["source_files"], "live_use":"unknown", "configured_consumers":"unknown", "compatibility_cutover_rollback":"unknown", "disposition":"unassigned"})
    doc={"schema":"agentops-estate-owner-source-interfaces/v1","repositories":repos,"interfaces":interfaces}
    return doc, roots

def test_exact_commits_and_explicit_unknowns(tmp_path):
    doc, roots = fixture(tmp_path)
    path = tmp_path/"inventory.json"
    path.write_text(json.dumps(doc))
    checker.check(path, roots)

def test_rejects_mutated_source_bytes(tmp_path):
    doc, roots = fixture(tmp_path)
    doc["repositories"][0]["source_files"][0]["sha256"] = "0" * 64
    path=tmp_path/"inventory.json"; path.write_text(json.dumps(doc))
    try:
        checker.check(path, roots)
    except ValueError as exc:
        assert "source hash mismatch" in str(exc)
        return
    assert False, "mutated source was accepted"

def test_rejects_missing_runtime_unknown(tmp_path):
    doc, roots = fixture(tmp_path)
    doc["interfaces"][0]["live_use"]="measured live use"
    path=tmp_path/"inventory.json"; path.write_text(json.dumps(doc))
    try:
        checker.check(path, roots)
    except ValueError:
        return
    assert False, "unsupported live-use claim was accepted"

def test_rejects_interface_hash_drift(tmp_path):
    doc, roots = fixture(tmp_path)
    doc = json.loads(json.dumps(doc))
    doc["interfaces"][0]["source_files"][0]["sha256"] = "f" * 64
    path=tmp_path/"inventory.json"; path.write_text(json.dumps(doc))
    try:
        checker.check(path, roots)
    except ValueError as exc:
        assert "path/hash" in str(exc)
        return
    assert False, "per-interface hash drift was accepted"

def test_rejects_empty_interface_evidence(tmp_path):
    doc, roots = fixture(tmp_path)
    doc["interfaces"][0]["source_files"] = []
    path=tmp_path/"inventory.json"; path.write_text(json.dumps(doc))
    try:
        checker.check(path, roots)
    except ValueError as exc:
        assert "must not be empty" in str(exc)
        return
    assert False, "empty interface evidence was accepted"

def test_rejects_duplicate_repository_record(tmp_path):
    doc, roots = fixture(tmp_path)
    doc["repositories"].append(doc["repositories"][0])
    path=tmp_path/"inventory.json"; path.write_text(json.dumps(doc))
    try:
        checker.check(path, roots)
    except ValueError as exc:
        assert "must not be duplicated" in str(exc)
        return
    assert False, "duplicate repository record was accepted"
