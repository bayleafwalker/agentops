"""Exercise Sprintctl's protected handoff using real Unix UID/GID checks.

Run this file as stdin to a disposable Python 3.12 container. The container
must mount only the Sprintctl package source read-only at /src/sprintctl.
"""

from __future__ import annotations

import errno
import json
import os
import stat
import sys
import tempfile
from pathlib import Path


def deny(label: str, operation) -> None:
    try:
        operation()
    except OSError as exc:
        if exc.errno not in {errno.EACCES, errno.EPERM}:
            raise
        print(f"PASS: denied {label} with {errno.errorcode[exc.errno]}")
        return
    raise AssertionError(f"agent UID unexpectedly modified {label}")


def mount_info(mountpoint: str) -> tuple[str, set[str]] | None:
    for line in Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines():
        left, separator, right = line.partition(" - ")
        if not separator:
            continue
        fields = left.split()
        if len(fields) > 5 and fields[4] == mountpoint:
            filesystem = right.split()[0]
            return filesystem, set(fields[5].split(","))
    return None


def require_disposable_mounts() -> None:
    if (
        os.environ.get("SPRINTCTL_HANDOFF_TEST_CONTAINER") != "1"
        or not Path("/.dockerenv").is_file()
    ):
        raise SystemExit("refusing to run outside the marked disposable Docker container")
    for path in ("/fixture", "/tmp"):
        mounted = mount_info(path)
        if mounted is None or mounted[0] != "tmpfs" or "rw" not in mounted[1]:
            raise SystemExit(f"refusing to use {path}: expected its own writable tmpfs mount")
    source_mount = mount_info("/src/sprintctl")
    if source_mount is None or "ro" not in source_mount[1]:
        raise SystemExit("refusing to use source that is not mounted read-only at /src/sprintctl")


def main() -> None:
    require_disposable_mounts()
    source = Path("/src")
    sys.path.insert(0, str(source))
    # This workspace snapshot intentionally keeps source unreadable to other
    # host/container users. Import as the privileged fixture preparer, then
    # fork: the actual handoff resolution and file access run as UID/GID 1100.
    # This avoids changing source permissions just to make a test mount readable.
    from sprintctl import backend
    from sprintctl.served import _default_client_credential_resolver
    from sprintctl.vuoro_credentials import (
        CredentialResolutionError,
        resolve_file_credential,
    )

    repo = Path("/fixture/repo")
    adapter_uid, reader_gid = 1110, 1100
    token = "vrd_" + "A" * 52

    # The parent process runs as container root. All test data lives only on
    # the disposable fixture/tmp tmpfs mounts supplied to Docker.
    repo.mkdir(parents=True)
    os.chown(repo, adapter_uid, reader_gid)
    repo.chmod(0o3770)

    marker_dir = repo / ".sprintctl"
    marker_dir.mkdir()
    os.chown(marker_dir, adapter_uid, reader_gid)
    marker_dir.chmod(0o750)
    marker = marker_dir / "backend.json"
    marker.write_text(json.dumps({
        "backend": "served",
        "repo_id": "5f0d8461-c828-4ba2-b89e-123456789abc",
    }), encoding="utf-8")
    os.chown(marker, adapter_uid, reader_gid)
    marker.chmod(0o644)

    vuoro = repo / ".vuoro"
    vuoro.mkdir()
    os.chown(vuoro, adapter_uid, reader_gid)
    vuoro.chmod(0o750)
    profile_path = vuoro / "profile.json"
    credential_path = vuoro / "credential"
    profile_path.write_text(json.dumps({
        "schema_version": "vuoro-client-profile/v1",
        "id": "foreign-uid-fixture",
        "revision": 1,
        "target": {
            "environment_id": "vuoro-dev",
            "environment_class": "development",
            "endpoint": "https://vuoro.example.test",
        },
        "credential_ref": f"file:{credential_path}",
        "required_authorities": ["work:read", "work:evidence"],
        "production_endpoint_denied": False,
    }), encoding="utf-8")
    credential_path.write_text(token, encoding="ascii")
    for path in (profile_path, credential_path):
        os.chown(path, adapter_uid, reader_gid)
    profile_path.chmod(0o644)
    credential_path.chmod(0o640)

    ordinary_dir = Path(tempfile.mkdtemp(prefix="sprintctl-handoff-", dir="/tmp"))
    ordinary_path = ordinary_dir / "foreign-token"
    ordinary_path.write_text(token, encoding="ascii")
    os.chown(ordinary_path, adapter_uid, reader_gid)
    ordinary_path.chmod(0o640)
    os.chown(ordinary_dir, 0, reader_gid)
    ordinary_dir.chmod(0o750)

    # Fork after source imports so handoff resolution and file operations run
    # as the actual receiving Unix identity.
    pid = os.fork()
    if pid == 0:
        try:
            os.setgroups([reader_gid])
            os.setgid(reader_gid)
            os.setuid(reader_gid)
            assert os.getuid() == reader_gid and os.getgid() == reader_gid

            config = backend.load_backend_config(cwd=repo, environ={})
            assert config.mode == "served"
            assert config.repo_id == "5f0d8461-c828-4ba2-b89e-123456789abc"
            profile = config.served_profile
            assert profile is not None and profile.trusted_implicit_delegated
            assert profile.source_path == profile_path
            resolver = _default_client_credential_resolver(profile)
            assert resolver(profile.credential_ref) == token
            print("PASS: actual foreign UID selected served profile and read delegated token")

            deny("profile contents", lambda: profile_path.write_text("tamper"))
            deny("credential contents", lambda: credential_path.write_text("tamper"))
            deny("handoff directory entries", lambda: (vuoro / "attacker-file").write_text("x"))
            deny(
                "adapter-owned handoff directory entry",
                lambda: vuoro.rename(repo / ".vuoro-renamed"),
            )
            assert stat.S_IMODE(repo.stat().st_mode) == 0o3770
            assert stat.S_IMODE(vuoro.stat().st_mode) == 0o750
            assert repo.stat().st_uid == adapter_uid and repo.stat().st_gid == reader_gid
            assert vuoro.stat().st_uid == adapter_uid and vuoro.stat().st_gid == reader_gid
            assert profile_path.is_file() and credential_path.read_text(encoding="ascii") == token
            assert not (vuoro / "attacker-file").exists()
            assert not (repo / ".vuoro-renamed").exists()
            print("PASS: protected handoff ownership/modes remain intact")

            assert ordinary_path.read_bytes() == token.encode("ascii")
            print("PASS: foreign credential bytes are readable through the parent directory")
            try:
                resolve_file_credential(f"file:{ordinary_path}")
            except CredentialResolutionError:
                print("PASS: ordinary owner-only reader rejects foreign mode-0640 credential")
            else:
                raise AssertionError("ordinary credential reader accepted foreign mode-0640 file")
        except BaseException as exc:
            print(f"FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
            os._exit(1)
        os._exit(0)

    _, status = os.waitpid(pid, 0)
    ordinary_path.unlink(missing_ok=True)
    ordinary_dir.rmdir()
    if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
        raise SystemExit(f"foreign UID test child failed: wait status {status}")
    print("RESULT: all foreign UID handoff assertions passed")


if __name__ == "__main__":
    main()
