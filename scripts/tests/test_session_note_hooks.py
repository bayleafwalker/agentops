"""Real-checkout replay of the opt-in semantic-note hook boundaries."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "session_notes.py"
SPEC = importlib.util.spec_from_file_location("session_notes_hooks_under_test", SCRIPT)
NOTES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(NOTES)


def git(repo, *args):
    result = subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture", "-c",
                             "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false", *args],
                            check=True, capture_output=True, text=True)
    return result.stdout


@pytest.fixture
def fixture(tmp_path):
    repo = tmp_path / "project"
    repo.mkdir()
    git(repo, "init", "--quiet")
    (repo / "canon.md").write_text("The bridge collapsed.\n")
    git(repo, "add", "canon.md")
    git(repo, "commit", "--quiet", "-m", "initial canon")
    roots = [tmp_path / "notes"]
    state = tmp_path / "state"
    event = {"session_id": "native-session-1", "cwd": str(repo)}
    return repo, roots, state, event


def start(fixture, **extra):
    repo, roots, state, event = fixture
    return NOTES.session_start_hook({**event, **extra}, roots=roots, repo_root=repo, state_root=state)


def stop(fixture, **extra):
    repo, roots, state, event = fixture
    return NOTES.stop_gate_hook({**event, **extra}, roots=roots, repo_root=repo, state_root=state)


def test_injects_latest_semantic_note_with_stable_sentinel(fixture):
    repo, roots, _, _ = fixture
    note = NOTES.new_note(repo=repo.name, kind="handover", body="Continue the market scene.")
    NOTES.append(roots[0], note)
    response = start(fixture)
    context = response["hookSpecificOutput"]["additionalContext"]
    assert f"== AGENTOPS SESSION NOTE {note['note_id']} ==" in context
    assert note["body"] in context
    assert "grants no authority" in context
    assert response["hookSpecificOutput"]["hookEventName"] == "SessionStart"


def test_clean_session_does_not_block(fixture):
    assert start(fixture) is None
    assert stop(fixture) is None


def test_dirty_work_prompts_once_and_does_not_write_a_note(fixture):
    repo, roots, _, _ = fixture
    start(fixture)
    (repo / "scene.md").write_text("A new scene.")
    assert stop(fixture)["decision"] == "block"
    assert stop(fixture) is None
    assert NOTES.load_notes(roots[0]) == []


def test_committed_work_since_start_prompts_even_when_clean(fixture):
    repo, _, _, _ = fixture
    start(fixture)
    (repo / "canon.md").write_text("The eastern bridge collapsed.\n")
    git(repo, "add", "canon.md")
    git(repo, "commit", "--quiet", "-m", "correct location")
    assert stop(fixture)["decision"] == "block"


def test_note_for_current_session_satisfies_reminder(fixture):
    repo, roots, _, event = fixture
    start(fixture)
    (repo / "scene.md").write_text("New work")
    NOTES.append(roots[0], NOTES.new_note(repo=repo.name, kind="outcome", body="Recorded result",
                                        runtime_session_id=event["session_id"]))
    assert stop(fixture) is None


def test_active_stop_hook_never_recurses(fixture):
    repo, _, _, _ = fixture
    start(fixture)
    (repo / "scene.md").write_text("New work")
    assert stop(fixture, stop_hook_active=True) is None
    assert stop(fixture)["decision"] == "block"


def test_concurrent_stop_events_emit_one_prompt(fixture):
    repo, _, _, _ = fixture
    start(fixture)
    (repo / "scene.md").write_text("New work")
    with ThreadPoolExecutor(max_workers=6) as workers:
        responses = list(workers.map(lambda _: stop(fixture), range(12)))
    assert sum(response is not None for response in responses) == 1


def test_missing_native_identity_or_wrong_checkout_does_not_inject(fixture, tmp_path):
    repo, roots, state, event = fixture
    NOTES.append(roots[0], NOTES.new_note(repo=repo.name, kind="handover", body="private project note"))
    assert start(fixture, session_id="") is None
    assert start(fixture, cwd=str(tmp_path)) is None
    assert not state.exists()


def test_resume_does_not_reset_once_per_session_marker(fixture):
    repo, _, _, _ = fixture
    start(fixture)
    (repo / "scene.md").write_text("New work")
    assert stop(fixture)["decision"] == "block"
    start(fixture, source="resume")
    assert stop(fixture) is None


def test_own_note_and_marker_files_do_not_manufacture_work(fixture):
    repo, _, _, event = fixture
    roots = [repo / "_artifacts" / "notes"]
    state = roots[0] / ".session-note-hooks"
    local = (repo, roots, state, event)
    start(local)
    NOTES.append(roots[0], NOTES.new_note(repo=repo.name, kind="handover", body="prior session"))
    assert stop(local) is None


def test_cli_malformed_event_is_diagnostic_not_an_infinite_gate(fixture):
    repo, roots, _, _ = fixture
    result = subprocess.run([sys.executable, str(SCRIPT), "latest", "--hook", "--root", str(roots[0]),
                             "--repo-root", str(repo)], input="not json", text=True, capture_output=True)
    assert result.returncode == 0
    assert result.stdout == ""
    assert "unavailable" in result.stderr


def test_distinct_hook_wrapper_requires_explicit_opt_in(fixture):
    repo, roots, state, event = fixture
    hook = SCRIPT.parent.parent / "hooks" / "session-note-start.sh"
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith("AGENTOPS_SESSION_NOTES_")}
    result = subprocess.run(["bash", str(hook)], input=json.dumps(event), text=True,
                            capture_output=True, env=environment)
    assert result.returncode == 0 and not result.stdout
    note = NOTES.new_note(repo=repo.name, kind="handover", body="injected after opt-in")
    NOTES.append(roots[0], note)
    environment.update(AGENTOPS_SESSION_NOTES_ROOT=str(roots[0]),
                       AGENTOPS_SESSION_NOTES_REPO_ROOT=str(repo),
                       AGENTOPS_SESSION_NOTES_STATE_ROOT=str(state))
    result = subprocess.run(["bash", str(hook)], input=json.dumps(event), text=True,
                            capture_output=True, env=environment)
    assert result.returncode == 0
    assert note["body"] in json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
