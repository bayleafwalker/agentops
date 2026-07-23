from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "dispatch/scripts/render_environment_context.py"
SPEC = importlib.util.spec_from_file_location("render_environment_context", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)


def test_renders_bounded_block_for_checked_in_production_record() -> None:
    block = renderer.render_environment_context(
        ROOT / "dispatch/environment-record/vuoro-shared.production.json"
    )

    assert renderer.START_MARKER in block
    assert renderer.END_MARKER in block
    assert "vuoro-shared (production)" in block
    assert "production-identities-only" in block
    assert "runbooks" in block.lower()
    assert "/projects/dev/agentops/docs/runbooks/vuoro-workstation-cutover.md" in block


def test_never_renders_roles_capabilities_or_identity_bindings() -> None:
    block = renderer.render_environment_context(
        ROOT / "dispatch/environment-record/vuoro-shared.production.json"
    )

    raw = json.loads(
        (ROOT / "dispatch/environment-record/vuoro-shared.production.json").read_text()
    )
    for role in raw["roles"]:
        assert role not in block
    for capability in raw["capabilities"]:
        assert capability not in block
    for binding in raw["identity_bindings"]:
        assert binding["principal"] not in block


def test_renders_checked_in_devbox_record() -> None:
    block = renderer.render_environment_context(
        ROOT / "dispatch/environment-record/devbox-vm.vuoro-shared.json"
    )

    assert "devbox-vm" in block
    assert "Constraints:" in block
    assert "Runbooks:" in block


def test_invalid_record_raises_profile_error(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"schema_version": "environment-record/v1"}))

    try:
        renderer.render_environment_context(path)
    except renderer.ProfileError:
        pass
    else:
        raise AssertionError("expected ProfileError for an incomplete record")
