from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys


SCRIPT = Path(__file__).resolve().parents[1] / "qualify_inbox_m2c.py"
SPEC = importlib.util.spec_from_file_location("qualify_inbox_m2c_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RUNNER
SPEC.loader.exec_module(RUNNER)


def test_help_and_offline_check_do_not_need_execution_inputs() -> None:
    help_result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True, check=False
    )
    assert help_result.returncode == 0
    assert "execute" in help_result.stdout

    offline = subprocess.run(
        [sys.executable, str(SCRIPT), "offline-check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert offline.returncode == 0
    record = json.loads(offline.stdout)
    assert record["result"] == "offline-tooling-checks-passed"
    assert record["live_owner_or_harness_calls"] == 0
    assert record["credentials_read"] is False


def test_execute_requires_explicit_opt_in_before_runtime_arguments() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "execute"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 2
    assert "--execute" in result.stderr
    assert "--adapter-path" in result.stderr


def test_digest_and_state_guards_fail_closed(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_bytes(b"immutable candidate\n")
    correct = RUNNER.hashlib.sha256(candidate.read_bytes()).hexdigest()
    RUNNER.verify_adapter_digest(candidate, correct)
    try:
        RUNNER.verify_adapter_digest(candidate, "0" * 64)
    except RUNNER.RunnerRefusal:
        pass
    else:
        raise AssertionError("mismatched installed bytes were accepted")

    uid = __import__("os").geteuid()
    other_uid = uid + 1
    root = tmp_path / "qualification"
    root.mkdir(mode=0o700)
    state = root / "case-01"
    state.mkdir(mode=0o700)
    assert RUNNER.test_rooted_state_path(
        "case-01", expected_uid=uid, session_uid=other_uid,
        root=root, root_owner_uid=uid, trusted_ancestors=False,
    ) == state

    link = tmp_path / "qualification-link"
    link.symlink_to(root, target_is_directory=True)
    for bad_root in (link,):
        try:
            RUNNER.test_rooted_state_path(
                "case-01", expected_uid=uid, session_uid=other_uid,
                root=bad_root, root_owner_uid=uid, trusted_ancestors=False,
            )
        except RUNNER.RunnerRefusal:
            pass
        else:
            raise AssertionError("symlinked qualification root was accepted")

    state.chmod(0o750)
    try:
        RUNNER.test_rooted_state_path(
            "case-01", expected_uid=uid, session_uid=other_uid,
            root=root, root_owner_uid=uid, trusted_ancestors=False,
        )
    except RUNNER.RunnerRefusal:
        pass
    else:
        raise AssertionError("session-accessible state path was accepted")


def test_after_commit_fault_calls_delegate_once_and_preserves_original_errors() -> None:
    class OwnerError(Exception):
        def __init__(self, code: str, message: str = "") -> None:
            super().__init__(code)
            self.code = code
            self.message = message

    class CommittingOwner:
        def __init__(self) -> None:
            self.calls = 0

        def message_receipt(self, *args, **kwargs):
            self.calls += 1
            return {"receipt": "owner-committed"}

    owner = CommittingOwner()
    wrapped = RUNNER.OwnerBoundaryFault(owner, "result-linked-after-commit", OwnerError)
    try:
        wrapped.message_receipt("repo", kind="result-linked")
    except OwnerError as exc:
        assert exc.code == "transport"
        assert "after owner commit" in exc.message
    else:
        raise AssertionError("caller-boundary response loss was not injected")
    assert owner.calls == 1
    assert wrapped.message_receipt("repo", kind="result-linked") == {"receipt": "owner-committed"}
    assert owner.calls == 2

    original = ValueError("owner rejected operation")

    class RefusingOwner:
        def message_receipt(self, *args, **kwargs):
            raise original

    refusing = RUNNER.OwnerBoundaryFault(RefusingOwner(), "result-linked-after-commit", OwnerError)
    try:
        refusing.message_receipt("repo", kind="result-linked")
    except ValueError as exc:
        assert exc is original
    else:
        raise AssertionError("original owner exception was not preserved")
    assert refusing._fired is False
