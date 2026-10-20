"""Opt-in private host evidence with digest verification and bounded retention.

This store owns only its UUID directories. It never discovers harness transcripts,
uploads content, or rewrites another producer's capsule or audit record.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import uuid
from urllib.parse import unquote, urlsplit

SCHEMA = "host-harness-evidence/v1"
MAX_BYTES = 64 * 1024 * 1024


def _private(fd: int, *, directory: bool = False) -> None:
    info = os.fstat(fd)
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if not kind(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("evidence must be private and owned by this user")
    if not directory and info.st_nlink != 1:
        raise ValueError("hard-linked evidence is refused")


@contextmanager
def _root(path: Path, *, create: bool = False):
    if create:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        _private(fd, directory=True)
        lock = os.open(".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        try:
            _private(lock)
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield fd
        finally:
            os.close(lock)
    finally:
        os.close(fd)


def _read(directory: int, name: str, limit: int) -> bytes:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
    try:
        _private(fd)
        with os.fdopen(os.dup(fd), "rb") as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError("evidence size bound exceeded")
        return data
    finally:
        os.close(fd)


def _write(directory: int, name: str, data: bytes) -> None:
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _record(directory: int, name: str) -> dict:
    value = json.loads(_read(directory, "record.json", 8192))
    if value.get("schema") != SCHEMA or value.get("object_id") != name:
        raise ValueError("unknown evidence record")
    uuid.UUID(name)
    created = datetime.fromisoformat(value["created_at"])
    if created.utcoffset() != timedelta(0):
        raise ValueError("UTC creation time required")
    days = value["retention_days"]
    if days is None:
        if value.get("indefinite_opt_in") is not True:
            raise ValueError("indefinite retention requires explicit per-object opt-in")
    elif type(days) is not int or not 1 <= days <= 3650:
        raise ValueError("invalid retention period")
    if not isinstance(value.get("transcript_sha256"), str) or len(value["transcript_sha256"]) != 64:
        raise ValueError("invalid digest")
    bytes.fromhex(value["transcript_sha256"])
    return value


def capture(root: Path, source: Path, session_id: str, *, opt_in: bool = False,
            retention_days: int | None = 30, keep_indefinitely: bool = False) -> dict:
    if not opt_in:
        raise ValueError("raw evidence capture requires explicit per-session opt-in")
    if not session_id or len(session_id) > 128:
        raise ValueError("bounded session identifier required")
    if retention_days is None:
        if not keep_indefinitely:
            raise ValueError("indefinite retention requires explicit per-object opt-in")
    elif type(retention_days) is not int or not 1 <= retention_days <= 3650 or keep_indefinitely:
        raise ValueError("invalid retention choice")
    source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        _private(source_fd)
        with os.fdopen(os.dup(source_fd), "rb") as stream:
            data = stream.read(MAX_BYTES + 1)
    finally:
        os.close(source_fd)
    if len(data) > MAX_BYTES:
        raise ValueError("evidence size bound exceeded")
    name = str(uuid.uuid4())
    value = {"schema": SCHEMA, "object_id": name, "session_id": session_id,
             "created_at": datetime.now(timezone.utc).isoformat(), "retention_days": retention_days,
             "indefinite_opt_in": keep_indefinitely, "transcript_sha256": hashlib.sha256(data).hexdigest()}
    with _root(root, create=True) as fd:
        os.mkdir(name, 0o700, dir_fd=fd)
        directory = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
        try:
            _write(directory, "payload", data)
            _write(directory, "record.json", (json.dumps(value, sort_keys=True) + "\n").encode())
            os.fsync(directory)
            os.fsync(fd)
        except BaseException:
            for file in ("payload", "record.json"):
                try:
                    os.unlink(file, dir_fd=directory)
                except FileNotFoundError:
                    pass
            os.rmdir(name, dir_fd=fd)
            raise
        finally:
            os.close(directory)
    return {**value, "evidence_uri": (root.absolute() / name / "payload").as_uri()}


def retrieve(root: Path, evidence_uri: str, transcript_sha256: str) -> bytes:
    locator = urlsplit(evidence_uri)
    path = Path(unquote(locator.path))
    if (locator.scheme != "file" or locator.netloc or locator.query or locator.fragment
            or path.parent.parent != root.absolute() or path.name != "payload"):
        raise ValueError("locator is outside this host store")
    name = path.parent.name
    if str(uuid.UUID(name)) != name:
        raise ValueError("invalid object identifier")
    with _root(root) as fd:
        directory = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
        try:
            _private(directory, directory=True)
            record = _record(directory, name)
            data = _read(directory, "payload", MAX_BYTES)
        finally:
            os.close(directory)
    digest = hashlib.sha256(data).hexdigest()
    if digest != transcript_sha256 or digest != record["transcript_sha256"]:
        raise ValueError("evidence digest mismatch")
    return data


def cleanup(root: Path, *, now: datetime | None = None, object_id: str | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    counts = {"deleted": 0, "retained": 0, "refused": 0}
    if not root.exists() and not root.is_symlink():
        return counts
    if object_id is not None and str(uuid.UUID(object_id)) != object_id:
        raise ValueError("invalid object identifier")
    with _root(root) as fd:
        names = [object_id] if object_id is not None else os.listdir(fd)
        for name in names:
            if name == ".lock":
                continue
            directory = None
            try:
                if str(uuid.UUID(name)) != name:
                    raise ValueError("unowned entry")
                directory = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                _private(directory, directory=True)
                record = _record(directory, name)
                if set(os.listdir(directory)) != {"record.json", "payload"}:
                    raise ValueError("unrecognized files are preserved")
                # Refuse symlinks, hardlinks or unexpected ownership before any unlink.
                payload = os.open("payload", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
                try:
                    _private(payload)
                    if os.fstat(payload).st_size > MAX_BYTES:
                        raise ValueError("evidence size bound exceeded")
                finally:
                    os.close(payload)
                days = record["retention_days"]
                expired = days is not None and now >= datetime.fromisoformat(record["created_at"]) + timedelta(days=days)
                if object_id is None and not expired:
                    counts["retained"] += 1
                    continue
                os.unlink("payload", dir_fd=directory)
                os.unlink("record.json", dir_fd=directory)
                os.rmdir(name, dir_fd=fd)
                os.fsync(fd)
                counts["deleted"] += 1
            except (ValueError, OSError, KeyError, TypeError):
                counts["refused"] += 1
            finally:
                if directory is not None:
                    os.close(directory)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "agentops/harness-evidence")
    sub = parser.add_subparsers(dest="command", required=True)
    put = sub.add_parser("capture")
    put.add_argument("source", type=Path)
    put.add_argument("--session-id", required=True)
    put.add_argument("--opt-in", action="store_true")
    retention = put.add_mutually_exclusive_group()
    retention.add_argument("--retention-days", type=int, default=30)
    retention.add_argument("--keep-indefinitely", action="store_true")
    get = sub.add_parser("verify")
    get.add_argument("evidence_uri")
    get.add_argument("transcript_sha256")
    sub.add_parser("cleanup")
    delete = sub.add_parser("delete")
    delete.add_argument("object_id")
    args = parser.parse_args()
    if args.command == "capture":
        result = capture(args.root, args.source, args.session_id, opt_in=args.opt_in,
                         retention_days=None if args.keep_indefinitely else args.retention_days,
                         keep_indefinitely=args.keep_indefinitely)
    elif args.command == "verify":
        result = {"verified": True, "bytes": len(retrieve(args.root, args.evidence_uri, args.transcript_sha256))}
    else:
        result = cleanup(args.root, object_id=getattr(args, "object_id", None))
    print(json.dumps(result))
    if result.get("refused"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
