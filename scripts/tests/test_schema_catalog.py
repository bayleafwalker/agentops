"""Tests for scripts/schema_catalog.py (`agentops schema-catalog`).

Every test builds fixture repositories under tmp_path; nothing reads the sibling
checkouts, so the suite runs in CI where they do not exist.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "schema_catalog.py"
SPEC = importlib.util.spec_from_file_location("schema_catalog", SCRIPT)
assert SPEC and SPEC.loader
catalog = importlib.util.module_from_spec(SPEC)
sys.modules["schema_catalog"] = catalog
SPEC.loader.exec_module(catalog)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_estate(tmp_path: Path) -> list[str]:
    alpha = tmp_path / "alpha"
    write(alpha / "schemas" / "handoff.v1.schema.json", json.dumps({
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://example.test/schemas/handoff.v1.schema.json",
        "properties": {"schema_version": {"const": "handoff/v1"},
                       "lease": {"properties": {"schema": {"const": "alpha-work-lease/v1"}}}},
    }))
    write(alpha / "alpha" / "receipts.py",
          'RECEIPT_SCHEMA = "alpha-receipt/v1"\n'
          'SHARED = "shared-thing/v1"\n'
          'class ReleaseNotes:\n    pass\n'
          'class AttemptLog:\n    pass\n')
    write(alpha / "docs" / "notes.md", "Consumes `beta-intent/v1`.\n")
    write(alpha / "tests" / "test_x.py", 'OTHER = "beta-only-in-tests/v1"\n')
    # Skipped entirely: secrets-looking names and skipped directories.
    write(alpha / ".env", 'TOKEN = "secret-schema/v1"\n')
    write(alpha / "deploy.key", 'KEY = "secret-key-schema/v1"\n')
    write(alpha / "node_modules" / "dep" / "x.py", 'DEP = "vendored-schema/v1"\n')
    write(alpha / "_artifacts" / "a.py", 'ART = "artifact-schema/v1"\n')

    beta = tmp_path / "beta"
    write(beta / "beta" / "intent.py",
          'INTENT_SCHEMA: str = "beta-intent/v1"\n'
          'SHARED = "shared-thing/v1"\n'
          'def build():\n    return {"schema": "beta-emitted/v1", "x": 1}\n'
          'def check(doc):\n    return doc["schema"] == "handoff/v1"\n'
          'class WorkerLease:\n    pass\n')
    write(beta / "contracts" / "main.tsp",
          'model Fence {\n  schema: "beta-fence/v1";\n}\n')
    write(beta / "tests" / "test_y.py", 'X = "alpha-receipt/v1"\n')
    write(beta / "beta" / "only_emit.py", 'def f():\n    return {"schema_version": "alpha-receipt/v1"}\n')
    return [f"alpha={alpha}", f"beta={beta}", f"gamma={tmp_path / 'missing'}"]


def run(tmp_path: Path, *extra: str) -> tuple[int, Path]:
    roots = make_estate(tmp_path)
    out = tmp_path / "out" / "SCHEMA-CATALOG.md"
    args = [arg for root in roots for arg in ("--root", root)] + ["--output", str(out), *extra]
    return catalog.main(args), out


def scan(tmp_path: Path):
    roots = catalog.parse_roots(make_estate(tmp_path))
    return catalog.run_scan(roots), roots


def test_definitions_and_owners(tmp_path):
    result, _ = scan(tmp_path)
    defs = result.definitions
    assert catalog.owners_of("handoff/v1", defs["handoff/v1"]) == ["alpha"]
    assert {kind for kind, _ in defs["handoff/v1"]["alpha"]} == {"schema-file"}
    assert catalog.owners_of("alpha-work-lease/v1", defs["alpha-work-lease/v1"]) == ["alpha"]
    assert catalog.owners_of("beta-intent/v1", defs["beta-intent/v1"]) == ["beta"]
    assert catalog.owners_of("beta-fence/v1", defs["beta-fence/v1"]) == ["beta"]
    assert ("type-literal", "contracts/main.tsp") in defs["beta-fence/v1"]["beta"]
    # An emitter alone owns an id ...
    assert catalog.owners_of("beta-emitted/v1", defs["beta-emitted/v1"]) == ["beta"]
    # ... but loses to a stronger definition elsewhere.
    assert catalog.owners_of("alpha-receipt/v1", defs["alpha-receipt/v1"]) == ["alpha"]
    assert catalog.owners_of("shared-thing/v1", defs["shared-thing/v1"]) == ["alpha", "beta"]


def test_references_are_not_definitions(tmp_path):
    result, _ = scan(tmp_path)
    # docs and tests only reference; a comparison is a consumer, not a definer.
    assert "beta" not in result.definitions["handoff/v1"]
    assert "beta-only-in-tests/v1" not in result.definitions
    assert "alpha" in result.mentions["beta-intent/v1"]
    assert "beta" in result.mentions["handoff/v1"]


def test_skips_secret_names_and_skip_dirs(tmp_path):
    result, _ = scan(tmp_path)
    for sid in ("secret-schema/v1", "secret-key-schema/v1", "vendored-schema/v1",
                "artifact-schema/v1"):
        assert sid not in result.definitions
        assert sid not in result.mentions


def test_missing_root_is_not_available(tmp_path):
    code, out = run(tmp_path)
    assert code == 0
    text = out.read_text()
    assert "| gamma | not available | - | - |" in text
    assert str(tmp_path) not in text  # no absolute paths leak into the catalog


def test_render_flags_multiple_definers_and_references(tmp_path):
    _, out = run(tmp_path)
    text = out.read_text()
    row = next(line for line in text.splitlines() if line.startswith("| `shared-thing/v1`"))
    assert "alpha, beta" in row and row.endswith("| multiple definers |")
    handoff = next(line for line in text.splitlines() if line.startswith("| `handoff/v1`"))
    assert "| beta |" in handoff  # referenced by beta
    assert "secret" not in text


def test_vocabulary(tmp_path):
    result, _ = scan(tmp_path)
    rows = {row["term"]: row for row in catalog.vocabulary(result)}
    # lease: alpha has the head-noun id, beta a head-noun type -> ambiguous.
    assert rows["lease"]["repos"] == ["alpha", "beta"]
    assert rows["lease"]["owner"].startswith("owner undetermined")
    # `ReleaseNotes` does not contain the word "lease".
    assert "alpha" not in rows["lease"]["type_repos"]
    # fence: only beta -> owned by its defining id.
    assert rows["fence"]["owner"] == "beta: `contracts/main.tsp` (`beta-fence/v1`)"
    # receipt: only alpha defines an id named for it.
    assert rows["receipt"]["owner"] == "alpha: `alpha/receipts.py` (`alpha-receipt/v1`)"
    # attempt: a type in one repo only.
    assert rows["attempt"]["owner"] == "alpha: `alpha/receipts.py` (type `AttemptLog`)"
    assert rows["qualification"]["owner"] == "no definitions found"


def test_output_is_deterministic_and_check_mode(tmp_path, capsys):
    code, out = run(tmp_path)
    first = out.read_text()
    assert code == 0
    assert catalog.main(["--root", f"alpha={tmp_path / 'alpha'}", "--root",
                         f"beta={tmp_path / 'beta'}", "--root", f"gamma={tmp_path / 'missing'}",
                         "--output", str(out), "--check"]) == 0
    assert out.read_text() == first
    out.write_text(first + "drift\n")
    assert catalog.main(["--root", f"alpha={tmp_path / 'alpha'}", "--root",
                         f"beta={tmp_path / 'beta'}", "--root", f"gamma={tmp_path / 'missing'}",
                         "--output", str(out), "--check"]) == 1
    assert "stale" in capsys.readouterr().err


def test_catalog_inside_a_root_does_not_feed_itself(tmp_path):
    roots = make_estate(tmp_path)
    out = tmp_path / "alpha" / "docs" / "contracts" / "SCHEMA-CATALOG.md"
    args = [arg for root in roots for arg in ("--root", root)] + ["--output", str(out)]
    assert catalog.main(args) == 0
    first = out.read_text()
    assert catalog.main(args + ["--check"]) == 0
    assert out.read_text() == first


def test_date_stamp_only_when_requested(tmp_path):
    _, out = run(tmp_path)
    assert "Generated on" not in out.read_text()
    _, out = run(tmp_path, "--date", "2026-11-07")
    assert "Generated on 2026-11-07." in out.read_text()


def test_schema_id_from_dollar_id():
    assert catalog.schema_id_from_dollar_id(
        "https://agentops.dev/schemas/blind-review-card.v1.schema.json") == "blind-review-card/v1"
    assert catalog.schema_id_from_dollar_id("https://x.test/handoff/v2") == "handoff/v2"
    assert catalog.schema_id_from_dollar_id("Bearer.json") is None


def test_bad_root_argument():
    try:
        catalog.parse_roots(["no-equals-sign"])
    except SystemExit as exc:
        assert "NAME=PATH" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected SystemExit")


def test_non_owning_definers_stay_visible(tmp_path):
    """A weak emitter outranked by a constant is listed, not dropped from the row."""
    _, out = run(tmp_path)
    row = next(line for line in out.read_text().splitlines()
               if line.startswith("| `alpha-receipt/v1`"))
    cells = [c.strip() for c in row.strip("|").split("|")]
    assert cells[1] == "alpha"
    assert cells[3] == "beta: `beta/only_emit.py` (emitter)"
    assert cells[4] == "-"  # beta is a definer, so not repeated as a referencer


def test_repository_prefix_breaks_definer_ties(tmp_path):
    alpha, beta = tmp_path / "alpha", tmp_path / "beta"
    write(alpha / "a.py", 'X = "beta-shared-intent/v1"\nY = "plain-shared/v1"\n')
    write(beta / "b.py", 'X = "beta-shared-intent/v1"\nY = "plain-shared/v1"\n')
    prefixes = catalog.PREFIX_OWNERS
    catalog.PREFIX_OWNERS = (("beta-", "beta"),)
    try:
        result = catalog.run_scan(catalog.parse_roots([f"alpha={alpha}", f"beta={beta}"]))
        defs = result.definitions
        assert catalog.owners_of("beta-shared-intent/v1", defs["beta-shared-intent/v1"]) == ["beta"]
        assert catalog.owners_of("plain-shared/v1", defs["plain-shared/v1"]) == ["alpha", "beta"]
    finally:
        catalog.PREFIX_OWNERS = prefixes
    assert ("credctl-", "cred-broker") in catalog.PREFIX_OWNERS


GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.test",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.test",
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
}


def sh(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, **GIT_ENV})


@pytest.fixture
def git_sibling(tmp_path, monkeypatch):
    """A sibling clone whose upstream has a commit it has not pulled, plus tracked,
    untracked and ignored files under a `contracts/` subdirectory root."""
    for key, value in GIT_ENV.items():
        monkeypatch.setenv(key, value)
    remote = tmp_path / "remote.git"
    sh("init", "--bare", "-b", "main", str(remote))
    writer = tmp_path / "writer"
    sh("clone", str(remote), str(writer))
    write(writer / "contracts" / "a.py", 'TRACKED = "sib-tracked/v1"\n')
    write(writer / "outside.py", 'OUTSIDE = "sib-outside/v1"\n')
    write(writer / ".gitignore", "ignored.py\n")
    sh("add", "-A", cwd=writer)
    sh("commit", "-m", "one", cwd=writer)
    sh("push", "origin", "main", cwd=writer)
    clone = tmp_path / "clone"
    sh("clone", str(remote), str(clone))
    write(writer / "contracts" / "b.py", 'UPSTREAM = "sib-upstream-only/v1"\n')
    sh("add", "-A", cwd=writer)
    sh("commit", "-m", "two", cwd=writer)
    sh("push", "origin", "main", cwd=writer)
    sh("fetch", "origin", cwd=clone)
    write(clone / "contracts" / "untracked.py", 'LOCAL = "sib-untracked/v1"\n')
    write(clone / "contracts" / "ignored.py", 'IGNORED = "sib-ignored/v1"\n')
    return clone


def test_git_root_reads_upstream_tracked_content(git_sibling):
    roots = catalog.parse_roots([f"sib={git_sibling / 'contracts'}"])
    result = catalog.run_scan(roots)
    assert set(result.definitions) == {"sib-tracked/v1", "sib-upstream-only/v1"}
    assert result.sources["sib"].startswith("origin/main @ ")
    assert result.files_scanned["sib"] == 2


def test_git_root_worktree_mode_skips_untracked_and_ignored(git_sibling):
    roots = catalog.parse_roots([f"sib={git_sibling / 'contracts'}"], ["sib=worktree"])
    result = catalog.run_scan(roots)
    assert set(result.definitions) == {"sib-tracked/v1"}
    assert result.sources["sib"] == "working tree, tracked files"
    for sid in ("sib-untracked/v1", "sib-ignored/v1", "sib-outside/v1"):
        assert sid not in result.mentions


def test_bad_ref_argument():
    with pytest.raises(SystemExit, match="NAME=REF"):
        catalog.parse_roots(None, ["no-equals"])
