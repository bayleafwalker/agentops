#!/usr/bin/env python3
"""Reviewed one-tick M2c qualification runner; inert unless --execute is explicit.

The normal adapter daemon/CLI is not modified. Execution is designed for a
root-reviewed protected transient systemd unit using the immutable installed
adapter file, a narrowly scoped root-owned policy, and a fresh dedicated state
directory. This script must never be run against production state.
"""
from __future__ import annotations

import argparse
import errno
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import Any

RUNNER_VERSION = "m2c-runner/v1"
QUAL_STATE_ROOT = Path("/var/lib/agentops-m2c-qualification")
ALLOWED_CHECKPOINTS = frozenset({
    "ingested", "run_registered_persisted", "run_linked_sent",
    "launch_intent_persisted", "session_created", "finished_persisted",
})
ALLOWED_OWNER_FAULTS = frozenset({"duplicate-read-page", "result-linked-after-commit"})


class RunnerRefusal(Exception):
    pass


class InjectedInterruption(BaseException):
    """Intentional checkpoint stop; output is a fixed marker, no exception detail."""


class OwnerBoundaryFault:
    """Fault after a real OwnerPort call, preserving the real owner's commit/result.

    duplicate-read-page makes two actual calls with identical arguments and merges
    their identical owner rows. result-linked-after-commit lets the actual owner
    commit its append-only receipt, then reports a caller-boundary transport error.
    It manufactures no owner response or domain record.
    """

    def __init__(self, delegate: Any, mode: str | None, owner_error: type[Exception] | None = None) -> None:
        if mode is not None and mode not in ALLOWED_OWNER_FAULTS:
            raise RunnerRefusal("unsupported owner fault")
        self._delegate = delegate
        self._mode = mode
        self._owner_error = owner_error
        self._fired = False

    def __getattr__(self, name: str) -> Any:
        target = getattr(self._delegate, name)
        if not callable(target):
            return target

        def call(*args: Any, **kwargs: Any) -> Any:
            if self._fired or self._mode is None:
                return target(*args, **kwargs)
            if self._mode == "duplicate-read-page" and name == "message_read":
                first = target(*args, **kwargs)
                second = target(*args, **kwargs)
                if not isinstance(first, dict) or not isinstance(second, dict):
                    raise RunnerRefusal("owner read response shape changed")
                rows1, rows2 = first.get("messages") or [], second.get("messages") or []
                if rows1 != rows2 or first.get("next_after_seq") != second.get("next_after_seq"):
                    raise RunnerRefusal("repeated actual owner read was not identical")
                self._fired = True
                result = dict(first)
                result["messages"] = rows1 + rows2
                return result
            if (self._mode == "result-linked-after-commit" and name == "message_receipt"
                    and kwargs.get("kind") == "result-linked"):
                result = target(*args, **kwargs)
                self._fired = True
                # This models loss after the real call returned successfully.
                from_module = sys.modules.get(self._delegate.__class__.__module__)
                owner_error = self._owner_error or getattr(from_module, "OwnerError", None)
                if owner_error is None:
                    raise RunnerRefusal("exact adapter OwnerError class unavailable")
                raise owner_error("transport", "qualification caller-boundary response lost after owner commit")
            return target(*args, **kwargs)

        return call


class InterruptOnce:
    def __init__(self, hook: str | None) -> None:
        if hook is not None and hook not in ALLOWED_CHECKPOINTS:
            raise RunnerRefusal("unsupported checkpoint")
        self.hook = hook
        self.fired = False

    def __call__(self, name: str) -> None:
        if self.hook == name and not self.fired:
            self.fired = True
            raise InjectedInterruption("qualification interruption")


def load_exact_adapter(path: Path, expected_sha256: str):
    resolved = path.resolve(strict=True)
    if not str(resolved).startswith("/nix/store/"):
        raise RunnerRefusal("adapter must be an immutable /nix/store path")
    st = resolved.stat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o222:
        raise RunnerRefusal("adapter file must be root-owned, regular, and immutable")
    verify_adapter_digest(resolved, expected_sha256)
    spec = importlib.util.spec_from_file_location("m2c_installed_adapter", resolved)
    if spec is None or spec.loader is None:
        raise RunnerRefusal("cannot load installed adapter")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, resolved


def verify_adapter_digest(path: Path, expected_sha256: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise RunnerRefusal("expected adapter digest must be lowercase SHA-256")
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise RunnerRefusal("installed adapter bytes do not match reviewed candidate digest")


def _reject_acl(path: Path, attr: str) -> None:
    try:
        value = os.getxattr(path, attr, follow_symlinks=False)
    except OSError as exc:
        if exc.errno in (errno.ENODATA, errno.ENOTSUP, errno.EOPNOTSUPP):
            return
        raise RunnerRefusal("cannot verify qualification directory ACLs") from exc
    if value:
        raise RunnerRefusal("qualification directory ACLs are not permitted")


def test_rooted_state_path(state_id: str, *, expected_uid: int, session_uid: int,
                           root: Path = QUAL_STATE_ROOT, root_owner_uid: int = 0,
                           trusted_ancestors: bool = True) -> Path:
    if expected_uid <= 0 or session_uid <= 0 or expected_uid == session_uid:
        raise RunnerRefusal("protected adapter and session UIDs must be distinct positive UIDs")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,63}", state_id):
        raise RunnerRefusal("invalid qualification state id")
    if not root.is_absolute():
        raise RunnerRefusal("qualification root must be absolute")
    ancestry = list(reversed((root, *root.parents)))
    for ancestor in ancestry:
        try:
            st = ancestor.lstat()
        except OSError as exc:
            raise RunnerRefusal("qualification path ancestry is missing") from exc
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
            raise RunnerRefusal("qualification path ancestry must contain real directories only")
        if trusted_ancestors and ancestor != root and st.st_uid != 0:
            raise RunnerRefusal("qualification root ancestry has a foreign owner")
    root_st = root.lstat()
    if root_st.st_uid != root_owner_uid:
        raise RunnerRefusal("qualification state root has an unapproved owner")
    if root_st.st_mode & 0o022:
        raise RunnerRefusal("qualification state root is group/world writable")
    if root_st.st_mode & 0o077 and root_owner_uid == expected_uid:
        raise RunnerRefusal("protected-owned qualification root must be private from session UID")
    _reject_acl(root, "system.posix_acl_access")
    _reject_acl(root, "system.posix_acl_default")

    path = root / state_id
    try:
        st = path.lstat()
    except OSError as exc:
        raise RunnerRefusal("root must pre-create the dedicated qualification state directory") from exc
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise RunnerRefusal("qualification state path must be a real directory")
    if st.st_uid != expected_uid:
        raise RunnerRefusal("qualification state directory must belong to protected adapter UID")
    if st.st_mode & 0o077:
        raise RunnerRefusal("qualification state directory must be private from session UID")
    _reject_acl(path, "system.posix_acl_access")
    _reject_acl(path, "system.posix_acl_default")
    if not os.access(path, os.R_OK | os.W_OK | os.X_OK):
        raise RunnerRefusal("protected adapter UID cannot access qualification state directory")
    return path


def check_test_policy(module: Any, policy_path: Path, scope_repo: str, scope_sender: str):
    policy = module.load_policy(policy_path, trusted=True)
    if policy.error or not policy.trusted:
        raise RunnerRefusal("trusted qualification policy is unreadable or untrusted")
    if tuple(policy.allowed_repos) != (scope_repo,):
        raise RunnerRefusal("policy must allow exactly the named disposable repository")
    if tuple(policy.allowed_senders) != (scope_sender,):
        raise RunnerRefusal("policy must allow exactly the named qualification sender")
    if not policy.enabled or not policy.launches_enabled or not policy.run_delegation_qualified:
        raise RunnerRefusal("policy does not enable the reviewed continuation flow")
    if set(policy.harness) != set(module._HARNESS_KEYS):
        raise RunnerRefusal("qualification harness configuration is incomplete")
    return policy


def execute(args: argparse.Namespace) -> int:
    if args.expected_uid <= 0 or args.session_uid <= 0 or args.expected_uid == args.session_uid:
        raise RunnerRefusal("protected adapter and session UIDs must be distinct positive UIDs")
    if os.geteuid() != args.expected_uid:
        raise RunnerRefusal("effective UID does not match reviewed protected runner UID")
    cred_dir = os.environ.get("CREDENTIALS_DIRECTORY")
    if not cred_dir or Path(args.password_file).resolve(strict=True).parent != Path(cred_dir).resolve(strict=True):
        raise RunnerRefusal("password file must be a systemd LoadCredential in this unit")
    state_path = test_rooted_state_path(
        args.state_id, expected_uid=args.expected_uid, session_uid=args.session_uid)

    adapter, adapter_path = load_exact_adapter(Path(args.adapter_path), args.expected_adapter_sha256)
    policy = check_test_policy(adapter, Path(args.policy), args.scope_repo, args.scope_sender)
    password = Path(args.password_file).read_text(encoding="utf-8").strip()
    if not password:
        raise RunnerRefusal("systemd OpenCode credential is empty")

    state = adapter.State(state_path)
    owner_real = adapter.VuoroOwner(args.profile)
    owner = OwnerBoundaryFault(owner_real, args.owner_fault, adapter.OwnerError)
    harness = adapter.OpenCodeServe("http://127.0.0.1:4096", password=password, username="opencode")
    config = adapter.Config(
        poll_interval=15,
        directory="/projects/dev/agentops",
        host_class="devbox",
        read_limit=50,
        trusted_config=True,
        run_root="/var/lib/agentops-runs",
        adapter_profile=args.profile,
    )
    interrupt = InterruptOnce(args.interrupt_at)
    instance_id = None
    try:
        runner = adapter.Adapter(
            owner=owner, harness=harness, state=state, policy_path=args.policy,
            config=config, checkpoint=interrupt, log=lambda _message: None,
        )
        instance_id = runner.instance_id
        if not re.fullmatch(r"ins_[0-9A-HJKMNP-TV-Z]{26}", args.production_instance_id):
            raise RunnerRefusal("production instance ID is malformed")
        if instance_id == args.production_instance_id:
            raise RunnerRefusal("test state reused the production adapter instance ID")
        try:
            runner.tick()
        except InjectedInterruption:
            pass
        fired = interrupt.fired
        fault_fired = owner._fired
        print(json.dumps({
            "schema": RUNNER_VERSION,
            "result": "interrupted" if fired else "one_tick_complete",
            "adapter_path": str(adapter_path),
            "adapter_sha256": hashlib.sha256(adapter_path.read_bytes()).hexdigest(),
            "policy_sha256": hashlib.sha256(Path(args.policy).read_bytes()).hexdigest(),
            "scope_repo": args.scope_repo,
            "scope_sender": args.scope_sender,
            "state_id": args.state_id,
            "instance_id": instance_id,
            "interrupt_at": args.interrupt_at,
            "interrupt_fired": fired,
            "owner_fault": args.owner_fault,
            "owner_fault_fired": fault_fired,
        }, sort_keys=True))
        return 75 if fired else 0
    finally:
        state.close()
        owner_real.close()


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("offline-check", help="validate runner fault-boundary primitives; no network or credentials")
    run = sub.add_parser("execute", help="one protected tick against a disposable, exactly scoped policy")
    run.add_argument("--execute", action="store_true", required=True,
                     help="explicit opt-in; absent execution is impossible")
    run.add_argument("--adapter-path", required=True)
    run.add_argument("--expected-adapter-sha256", required=True)
    run.add_argument("--policy", required=True)
    run.add_argument("--profile", required=True)
    run.add_argument("--password-file", required=True)
    run.add_argument("--expected-uid", required=True, type=int)
    run.add_argument("--session-uid", required=True, type=int)
    run.add_argument("--state-id", required=True)
    run.add_argument("--scope-repo", required=True)
    run.add_argument("--scope-sender", required=True)
    run.add_argument("--production-instance-id", required=True)
    run.add_argument("--interrupt-at", choices=sorted(ALLOWED_CHECKPOINTS))
    run.add_argument("--owner-fault", choices=sorted(ALLOWED_OWNER_FAULTS))
    return p


def offline_check() -> None:
    """Offline checks are mechanics-only and never evidence about owner behavior."""
    class OwnerError(Exception):
        def __init__(self, code: str, message: str = "") -> None:
            super().__init__(code)
            self.code = code
            self.message = message

    class Delegate:
        def __init__(self):
            self.calls = 0
            self.commits = 0

        def message_receipt(self, *args, **kwargs):
            self.calls += 1
            self.commits += 1
            return {"receipt": {"kind": kwargs.get("kind"), "recorded": True}}

    d = Delegate()
    wrapped = OwnerBoundaryFault(d, "result-linked-after-commit", OwnerError)
    try:
        wrapped.message_receipt("repo", kind="result-linked")
    except OwnerError as exc:
        assert exc.code == "transport"
        assert "after owner commit" in exc.message
    else:
        raise AssertionError("after-commit fault did not surface")
    assert d.calls == 1 and d.commits == 1 and wrapped._fired
    assert wrapped.message_receipt("repo", kind="result-linked")["receipt"]["recorded"]
    assert d.calls == 2 and d.commits == 2

    class FailedDelegate:
        def __init__(self, error):
            self.error = error

        def message_receipt(self, *args, **kwargs):
            raise self.error

    original = ValueError("owner refusal preserved")
    failed = OwnerBoundaryFault(FailedDelegate(original), "result-linked-after-commit", OwnerError)
    try:
        failed.message_receipt("repo", kind="result-linked")
    except ValueError as exc:
        assert exc is original and not failed._fired
    else:
        raise AssertionError("original owner exception was not preserved")

    calls = 0
    def actual_read(*args, **kwargs):
        nonlocal calls
        calls += 1
        return {"messages": [{"message_id": "synthetic-offline-case", "inbox_seq": 1}],
                "next_after_seq": 1}
    class ReadDelegate:
        message_read = actual_read
    duplicate = OwnerBoundaryFault(ReadDelegate(), "duplicate-read-page")
    page = duplicate.message_read("repo", after_seq=0, limit=50, instance_id="instance")
    assert calls == 2 and len(page["messages"]) == 2 and duplicate._fired

    hook = InterruptOnce("session_created")
    try:
        hook("session_created")
    except InjectedInterruption:
        pass
    else:
        raise AssertionError("checkpoint did not interrupt")
    hook("session_created")
    assert hook.fired
    try:
        InterruptOnce("not-a-real-hook")
    except RunnerRefusal:
        pass
    else:
        raise AssertionError("unknown checkpoint was accepted")
    try:
        OwnerBoundaryFault(d, "arbitrary-operation")
    except RunnerRefusal:
        pass
    else:
        raise AssertionError("unknown owner fault was accepted")

    protected_uid = os.geteuid()
    session_uid = 65534 if protected_uid != 65534 else 65533
    with tempfile.TemporaryDirectory(prefix="m2c-runner-offline-") as temp:
        tmp = Path(temp)
        private_root = tmp / "qual"
        private_root.mkdir(mode=0o700)
        child = private_root / "case-01"
        child.mkdir(mode=0o700)
        assert test_rooted_state_path(
            "case-01", expected_uid=protected_uid, session_uid=session_uid,
            root=private_root, root_owner_uid=protected_uid, trusted_ancestors=False) == child

        link = tmp / "qual-link"
        link.symlink_to(private_root, target_is_directory=True)
        try:
            test_rooted_state_path(
                "case-01", expected_uid=protected_uid, session_uid=session_uid,
                root=link, root_owner_uid=protected_uid, trusted_ancestors=False)
        except RunnerRefusal:
            pass
        else:
            raise AssertionError("symlink qualification root was accepted")

        child.chmod(0o750)
        try:
            test_rooted_state_path(
                "case-01", expected_uid=protected_uid, session_uid=session_uid,
                root=private_root, root_owner_uid=protected_uid, trusted_ancestors=False)
        except RunnerRefusal:
            pass
        else:
            raise AssertionError("session-accessible state directory was accepted")

        child.chmod(0o700)
        private_root.chmod(0o770)
        try:
            test_rooted_state_path(
                "case-01", expected_uid=protected_uid, session_uid=session_uid,
                root=private_root, root_owner_uid=protected_uid, trusted_ancestors=False)
        except RunnerRefusal:
            pass
        else:
            raise AssertionError("group/world-writable root was accepted")

        package = tmp / "candidate.py"
        package.write_bytes(b"candidate bytes\n")
        verify_adapter_digest(package, hashlib.sha256(package.read_bytes()).hexdigest())
        try:
            verify_adapter_digest(package, "0" * 64)
        except RunnerRefusal:
            pass
        else:
            raise AssertionError("wrong adapter digest was accepted")

    for bad_uid in (0, protected_uid):
        try:
            test_rooted_state_path(
                "case-01", expected_uid=bad_uid, session_uid=bad_uid,
                root=QUAL_STATE_ROOT)
        except RunnerRefusal:
            pass
        else:
            raise AssertionError("invalid protected/session UID pairing was accepted")
    print(json.dumps({
        "schema": RUNNER_VERSION,
        "result": "offline-tooling-checks-passed",
        "live_owner_or_harness_calls": 0,
        "credentials_read": False,
        "checks": [
            "after-commit error is injected only after one delegated call",
            "original target is called again normally after one-shot injection",
            "original owner error propagates unchanged without marking fault fired",
            "duplicate page is composed only from two actual delegate return values",
            "known checkpoint interrupts once",
            "unknown checkpoint and owner fault refuse",
            "wrong adapter digest and invalid UID pairing refuse",
            "symlinked, writable, and session-accessible state paths refuse",
        ],
        "synthetic_values_are_mechanics_only": True,
    }, sort_keys=True))


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "offline-check":
            offline_check()
            return 0
        return execute(args)
    except RunnerRefusal as exc:
        print(json.dumps({"schema": RUNNER_VERSION, "result": "refused", "reason": str(exc)}), file=sys.stderr)
        return 2
    except Exception as exc:  # do not expose owner/client exception bodies in captured output
        print(json.dumps({
            "schema": RUNNER_VERSION,
            "result": "error",
            "error_type": type(exc).__name__,
            "detail": "inspect protected local state and owner records; exception text is suppressed",
        }), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
