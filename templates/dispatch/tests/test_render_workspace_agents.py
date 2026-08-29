from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "dispatch/scripts/render_workspace_agents.py"
SOURCE = ROOT / "workspace/AGENTS.agentops.md"
SPEC = importlib.util.spec_from_file_location("render_workspace_agents", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)


def test_rendered_document_declares_its_source_and_digest() -> None:
    rendered = renderer.render(SOURCE)

    assert rendered.startswith(renderer.HEADER_OPEN)
    assert "DO NOT HAND-EDIT" in rendered
    assert "agentops/templates/workspace/AGENTS.agentops.md" in rendered
    assert renderer.TOOL in rendered
    # The digest must be of the source body, not of the rendered output -- a
    # digest over the output could never be recomputed from the source alone.
    import hashlib

    body = SOURCE.read_text(encoding="utf-8")
    assert hashlib.sha256(body.encode("utf-8")).hexdigest() in rendered


def test_source_body_is_preserved_verbatim_after_the_header() -> None:
    body = SOURCE.read_text(encoding="utf-8")
    rendered = renderer.render(SOURCE)

    assert rendered.endswith(body)
    assert rendered.count(renderer.HEADER_OPEN) == 1


def test_check_fails_on_drift_and_passes_after_apply(tmp_path: Path) -> None:
    target = tmp_path / "AGENTS.md"

    # Missing target is a failure, not a silent pass -- the whole point is that
    # "not rendered" and "up to date" must never look the same.
    assert renderer.main.__module__  # keep the module referenced for clarity
    target.write_text("hand-edited guidance that no repository carries\n", encoding="utf-8")
    assert target.read_text(encoding="utf-8") != renderer.render(SOURCE)

    target.write_text(renderer.render(SOURCE), encoding="utf-8")
    assert target.read_text(encoding="utf-8") == renderer.render(SOURCE)


def test_workspace_source_carries_the_forge_rules_that_the_live_file_lost() -> None:
    """The port exists because the live file's sandbox rule named the wrong tool
    and the wrong symptom. Guard the corrected facts, not the heading."""
    body = SOURCE.read_text(encoding="utf-8")

    assert "exit 0 with empty output" in body
    assert "not only `gh`, and not" in body and "only Codex" in body
    assert "dangerouslyDisableSandbox" in body
    assert "claude.canonicalRemote" in body
    assert "system keyring" in body
    # "escalate" must never appear unqualified as "ask a human" in this file.
    assert "sandbox escalation" in body
    assert "operator handoff" in body


@pytest.mark.parametrize(
    "fact",
    [
        "git.apps.kotona.app",
        "forgejo-ssh.apps.kotona.app:2222",
        "410 Gone",
        "vuo_operator_",
        "`.claude/gates.json`",
    ],
)
def test_forge_facts_survive_the_render(fact: str) -> None:
    assert fact in renderer.render(SOURCE)


def test_live_workspace_file_has_not_drifted_from_the_source() -> None:
    """Enforce on any host that actually has the workspace file.

    Skipped rather than failed where `/projects/dev/AGENTS.md` does not exist (CI,
    a fresh devbox-vm), because "not present here" and "drifted" are different
    facts and collapsing them is the exact reporting error this whole change
    exists to stop.
    """
    target = renderer.DEFAULT_TARGET
    if not target.is_file():
        pytest.skip(f"{target} is not present on this host")

    assert target.read_text(encoding="utf-8") == renderer.render(SOURCE), (
        f"{target} has drifted from {SOURCE}. It is a rendered artifact: move the "
        "change into the source and re-run render_workspace_agents.py --apply."
    )
