import importlib.util
import json
from pathlib import Path
import subprocess


spec = importlib.util.spec_from_file_location(
    "hook_wiring", Path(__file__).resolve().parents[1] / "check_hook_wiring.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture(tmp_path, command=None):
    workspace, home = tmp_path / "workspace", tmp_path / "home"
    workspace.mkdir()
    home.mkdir()
    canonical = workspace / "agentops/hooks"
    canonical.mkdir(parents=True)
    source = canonical / "guard.sh"
    source.write_text('#!/bin/sh\n# lib/emit-decision.sh\nexit 0\n')
    source.chmod(0o755)
    (canonical / "lib").mkdir()
    (canonical / "lib/emit-decision.sh").write_text('# library\n')
    target = workspace / ".codex/hooks/guard.sh"
    config = workspace / ".codex/hooks.json"
    config.parent.mkdir()
    config.write_text(json.dumps({"hooks": {"PreToolUse": [{"hooks": [
        {"type": "command", "command": command or shlex_quote(target)}]}]}}))
    return workspace, home, canonical, target


def shlex_quote(path):
    import shlex
    return shlex.quote(str(path))


def test_missing_alias_fails_then_repair_is_idempotent(tmp_path):
    workspace, home, canonical, target = fixture(tmp_path)
    count, errors, _ = module.check(workspace, home, canonical)
    assert count == 1 and len(errors) == 1 and "missing hook" in errors[0]
    assert subprocess.run(["sh", "-c", shlex_quote(target)], capture_output=True).returncode == 127
    _, errors, repairs = module.check(workspace, home, canonical, apply=True)
    assert not errors and len(repairs) == 2
    assert target.resolve() == canonical / "guard.sh"
    assert subprocess.run(["sh", "-c", shlex_quote(target)], capture_output=True).returncode == 0
    assert module.check(workspace, home, canonical, apply=True) == (1, [], [])


def test_existing_custom_body_is_never_replaced(tmp_path):
    workspace, home, canonical, target = fixture(tmp_path)
    target.parent.mkdir()
    target.write_text('#!/bin/sh\necho custom\n')
    target.chmod(0o755)
    assert module.check(workspace, home, canonical, apply=True) == (1, [], [])
    assert "custom" in target.read_text() and not target.is_symlink()


def test_library_and_executable_failure_cases(tmp_path):
    workspace, home, canonical, target = fixture(tmp_path)
    target.parent.mkdir()
    target.symlink_to(canonical / "guard.sh")
    assert "missing decision library" in module.check(workspace, home, canonical)[1][0]
    (canonical / "guard.sh").chmod(0o644)
    _, errors, _ = module.check(workspace, home, canonical, apply=True)
    assert len(errors) == 1 and "not executable" in errors[0]


def test_unknown_hook_is_not_invented(tmp_path):
    workspace, home, canonical, _ = fixture(tmp_path, '/missing/custom.sh')
    _, errors, repairs = module.check(workspace, home, canonical, apply=True)
    assert len(errors) == 1 and not repairs


def test_all_projects_and_home_are_checked_even_when_ignored(tmp_path):
    workspace, home, canonical, target = fixture(tmp_path)
    module.check(workspace, home, canonical, apply=True)
    for base in (workspace / "project", home):
        config = base / ".claude/settings.local.json"
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [
            {"type": "command", "command": "/missing/custom.sh"}]}]}}))
    (workspace / ".gitignore").write_text('.claude/\n')
    count, errors, _ = module.check(workspace, home, canonical)
    assert count == 3 and len(errors) == 2


def test_duplicate_global_cost_hook_removed_without_changing_permissions(tmp_path):
    workspace, home, canonical, _ = fixture(tmp_path)
    cost = canonical / "log-session-cost.sh"
    cost.write_text('#!/bin/sh\nexit 0\n')
    cost.chmod(0o755)
    hook = {"type": "command", "command": shlex_quote(cost)}
    global_config = home / ".codex/hooks.json"
    global_config.parent.mkdir()
    global_config.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [hook]}]}}))
    config = workspace / "project/.codex/hooks.json"
    config.parent.mkdir(parents=True)
    data = {"permissions": {"deny": ["original"]}, "hooks": {"Stop": [{"hooks": [hook]}]}}
    config.write_text(json.dumps(data))
    errors, _ = module.duplicate_cost_hooks(workspace, home, canonical)
    assert len(errors) == 1
    assert json.loads(config.read_text()) == data
    errors, repairs = module.duplicate_cost_hooks(workspace, home, canonical, apply=True)
    assert not errors and len(repairs) == 1
    assert json.loads(config.read_text()) == {"permissions": {"deny": ["original"]}, "hooks": {}}
    assert module.duplicate_cost_hooks(workspace, home, canonical, apply=True) == ([], [])
