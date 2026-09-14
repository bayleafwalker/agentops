"""The whole document: test 6 (optional slice absent), M3 = 0, demotion, test 7 (no subprocess) and no previous projection."""

import ast
import json
from pathlib import Path

from fakes import FakeAuthorityClient, MemoryGit, fixture
from operator_projection.cell import is_cell
from operator_projection.generate import Run, attest, generate, row
from operator_projection.sources import Authority, SourceUnavailable
from world import NOW, REGISTRY, TAGS, estate

SRC = Path(__file__).resolve().parents[1] / "src" / "operator_projection"
STRUCTURAL = {"window", "overflow"}
PANELS = ["provenance", "pickup", "hazards", "moves", "ground_tools", "may_do", "blind_spots"]


class DeniedGit(MemoryGit):
    def __init__(self, base: MemoryGit, denied: str):
        super().__init__(base.files, base.history)
        self.denied = denied

    def show(self, repo, commit, path):
        return self._deny(repo) or super().show(repo, commit, path)

    def log(self, repo, ref, paths, since=None, until=None):
        return self._deny(repo) or super().log(repo, ref, paths, since, until)

    def resolve(self, repo, ref, before=None):
        return self._deny(repo) or super().resolve(repo, ref, before)

    def _deny(self, repo):
        if repo == self.denied:
            raise SourceUnavailable(f"{repo} is not readable with the configured GitHub credential")


def uncelled(value, path="panels") -> list[str]:
    """Every rendered leaf sits inside a Cell, or in a row that carries an evidence Cell."""
    if is_cell(value) or (isinstance(value, dict) and is_cell(value.get("evidence"))):
        return []
    if isinstance(value, dict):
        return [p for k, v in value.items() if k not in STRUCTURAL for p in uncelled(v, f"{path}.{k}")]
    if isinstance(value, list):
        return [p for i, v in enumerate(value) for p in uncelled(v, f"{path}[{i}]")]
    return [] if value is None else [path]


def served(credential=True, down=False):
    results = {"work.project.context": fixture("project-context.json"), "work.read.handoff": {"last_checkpoint": None},
               "work.read.context-candidates": {"candidates": []}}
    return Authority(FakeAuthorityClient(results=results, down=down), lambda: credential)


def test_full_document_has_every_panel_and_zero_uncelled_values():
    doc = generate(estate(), served(), REGISTRY, NOW, tags=lambda: TAGS)
    assert doc["schema"] == "operator-projection/v1" and doc["derived"] == "DERIVED — not a record"
    assert list(doc["panels"]) == PANELS and doc["generated_at"] == "2026-09-14T12:00:00Z"
    assert (doc["cadence_s"], doc["stale_after_s"], doc["registry"]["commit"]) == (900, 1800, "f" * 40)
    assert uncelled(doc["panels"]) == []
    assert all(s["degraded"] is None for s in doc["sources"])
    assert doc["panels"]["hazards"]["open"]["value"] == 4 and doc["panels"]["hazards"]["oldest_days"]["value"] == 30
    json.dumps(doc)


def test_optional_slice_absent_gives_a_valid_degraded_document():
    doc = generate(DeniedGit(estate(), "appservice"), served(credential=False, down=True), REGISTRY, NOW, tags=lambda: TAGS)
    assert list(doc["panels"]) == PANELS and uncelled(doc["panels"]) == []
    degraded = {s["id"] for s in doc["sources"] if s["degraded"]}
    assert {"git.appservice", "authority.handshake"} <= degraded
    panels = doc["panels"]
    assert panels["pickup"]["kind"] == "BLIND" and panels["may_do"]["policy"]["kind"] == "BLIND"
    assert panels["moves"]["counts"]["kind"] == "BLIND" and panels["provenance"]["authority"]["kind"] == "BLIND"
    assert all("UNDETERMINED" in r["flags"] for r in panels["hazards"]["rows"])
    assert panels["hazards"]["open"]["value"] == 0
    json.dumps(doc)


def test_unresolved_falsifier_is_demoted_to_claimed_unattested():
    current = Run(estate(), served(), REGISTRY, NOW, lambda: TAGS)
    current.head("agentops")
    good = row("ORPHAN", "work:a", "d", current.declared("work:a", "agentops", "g1"), falsifier="check", sources=["git.agentops"])
    bad = row("ORPHAN", "work:b", "d", current.declared("work:b", "agentops", "g1"), falsifier="check", sources=["git.nowhere"])
    silent = row("ORPHAN", "work:c", "d", current.declared("work:c", "agentops", "g1"), sources=["git.agentops"])
    attest(current, [good, bad, silent])
    assert good["flags"] == [] and good["evidence"]["kind"] == "DECLARED"
    assert bad["flags"] == ["CLAIMED-UNATTESTED"] and bad["evidence"]["kind"] == "BLIND"
    assert silent["flags"] == ["CLAIMED-UNATTESTED"]


def test_package_has_no_subprocess_use():
    forbidden = {"subprocess", "pty", "pexpect"}
    for path in SRC.glob("*.py"):
        tree = ast.parse(path.read_text())
        imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        imported |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        calls = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert not imported & forbidden, path.name
        assert not calls & {"system", "popen", "spawnv", "execv", "create_subprocess_exec", "create_subprocess_shell", "fork"}, path.name


def test_generator_never_reads_a_previous_projection():
    for name in ("generate.py", "sources.py", "replay.py"):
        tree = ast.parse((SRC / name).read_text())
        strings = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        modules = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        assert not any("/v1.json" in s or "v1.txt" in s for s in strings), name
        assert not modules & {"serve", "cli"}, name
