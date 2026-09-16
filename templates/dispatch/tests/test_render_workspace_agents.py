from __future__ import annotations

import importlib.util
import os
from pathlib import Path

try:
    import pytest
except ImportError as exc:  # pragma: no cover - depends on the host interpreter
    # These are pytest-style tests (fixtures/parametrize). The registered
    # full-suite command is `python -m unittest discover`, which cannot run
    # them and must stay cold-green on a host without pytest: report a skip
    # instead of an import error. Run them with `python -m pytest`.
    import unittest

    raise unittest.SkipTest(f"pytest-style module needs pytest: {exc}") from exc


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


def test_header_carries_an_injected_source_git_sha() -> None:
    rendered = renderer.render(SOURCE, source_git_sha="abc1234")

    assert "source_git_sha: abc1234" in rendered
    assert renderer.extract_source_git_sha(rendered) == "abc1234"


def test_header_omits_source_git_sha_line_without_git() -> None:
    rendered = renderer.render(SOURCE, source_git_sha=None)

    assert "source_git_sha:" not in rendered
    assert renderer.extract_source_git_sha(rendered) is None
    # The rest of the header is unaffected by the omission.
    assert renderer.TOOL in rendered


def test_lookup_source_git_sha_returns_none_outside_a_git_checkout(
    tmp_path: Path,
) -> None:
    stray = tmp_path / "not-a-repo" / "AGENTS.agentops.md"
    stray.parent.mkdir(parents=True)
    stray.write_text("body\n", encoding="utf-8")

    assert renderer.lookup_source_git_sha(stray, repo_root=stray.parent) is None


def test_check_passes_when_only_the_source_git_sha_line_differs(
    tmp_path: Path,
) -> None:
    target = tmp_path / "AGENTS.md"
    target.write_text(renderer.render(SOURCE, source_git_sha="old0000"), encoding="utf-8")
    expected = renderer.render(SOURCE, source_git_sha="new1111")

    assert target.read_text(encoding="utf-8") != expected  # sha lines differ
    assert renderer.strip_source_git_sha(
        target.read_text(encoding="utf-8")
    ) == renderer.strip_source_git_sha(expected)


def test_check_fails_on_content_drift_and_reports_both_shas(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import sys as _sys

    target = tmp_path / "AGENTS.md"
    target.write_text(renderer.render(SOURCE, source_git_sha="old0000"), encoding="utf-8")
    stale = target.read_text(encoding="utf-8") + "\nhand-edited line\n"
    target.write_text(stale, encoding="utf-8")

    argv = [
        "render_workspace_agents.py",
        "--source",
        str(SOURCE),
        "--target",
        str(target),
        "--check",
    ]
    old_argv = _sys.argv
    try:
        _sys.argv = argv
        exit_code = renderer.main()
    finally:
        _sys.argv = old_argv

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "has drifted" in captured.err
    assert "old0000" in captured.err
    assert "stale: rendered from old0000, source now at" in captured.err


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
    """Enforce on any host that actually has the workspace file, when run from
    the checkout that owns rendering into it -- with an explicit opt-in.

    `DEFAULT_TARGET` (`/projects/dev/AGENTS.md`) is outside every git checkout
    and reflects whichever checkout on this host last ran
    `render_workspace_agents.py --apply`. Any checkout other than the
    canonical `/projects/dev/agentops` -- a worktree included -- has no reason
    to expect its own `SOURCE` to match a file some other checkout rendered,
    so this only runs at all when `renderer.REPO_ROOT` (derived from this
    module's own `__file__`, i.e. wherever the currently-executing test file
    actually lives) resolves to that canonical checkout.

    Even there, the live file is not kept in lockstep with every commit -- it
    reflects whenever `--apply` was last run, which is a deploy/operator
    action, not part of `pytest`. The renderer's header records only a
    content digest of `SOURCE`, not a commit marker, so there is no cheaper
    way to distinguish "stale, needs --apply" from "actually wrong" than the
    full comparison this test makes -- which is exactly the noisy, ambient
    environment failure being guarded against. So the comparison additionally
    requires an explicit opt-in
    (`AGENTOPS_LIVE_WORKSPACE_RENDER_CHECK=1`), for a caller who has just run
    `--apply` (or is deliberately checking for drift) to prove it by hand;
    everyone else is skipped, not failed, because "not opted in here" and
    "drifted" are different facts and collapsing them is the exact reporting
    error this whole change exists to stop.
    """
    owning_root = Path("/projects/dev/agentops")
    if renderer.REPO_ROOT.resolve() != owning_root.resolve():
        pytest.skip(
            f"renderer.REPO_ROOT ({renderer.REPO_ROOT}) is not the canonical "
            f"{owning_root} checkout that owns rendering into "
            f"{renderer.DEFAULT_TARGET}; this checkout's source has no claim on "
            "that file's current content"
        )
    if os.environ.get("AGENTOPS_LIVE_WORKSPACE_RENDER_CHECK") != "1":
        pytest.skip(
            "set AGENTOPS_LIVE_WORKSPACE_RENDER_CHECK=1 to compare "
            f"{renderer.DEFAULT_TARGET} against {SOURCE}; unset by default because "
            "the live file reflects whichever checkout last ran --apply, not "
            "necessarily the state of this test run"
        )

    target = renderer.DEFAULT_TARGET
    if not target.is_file():
        pytest.skip(f"{target} is not present on this host")

    # Compare content only, as --check does: the recorded source commit is
    # history, not drift.
    assert renderer.strip_source_git_sha(
        target.read_text(encoding="utf-8")
    ) == renderer.strip_source_git_sha(renderer.render(SOURCE)), (
        f"{target} has drifted from {SOURCE}. It is a rendered artifact: move the "
        "change into the source and re-run render_workspace_agents.py --apply."
    )
