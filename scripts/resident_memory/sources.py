"""Exact bounded file snapshots. All path components reject symlinks."""
from __future__ import annotations

import os
import stat
from fnmatch import fnmatchcase

from .policy import Scope, validate_relative


def read_source(scope: Scope, name: str, limit: int) -> bytes:
    validate_relative(name)
    if not any(len(name.split("/")) == len(pattern.split("/"))
               and all(fnmatchcase(part, allowed) for part, allowed in zip(name.split("/"), pattern.split("/")))
               for pattern in scope.source_paths):
        raise PermissionError("source path is not explicitly allowed")
    # Walk from / with O_NOFOLLOW, rather than resolve-then-open (a symlink race).
    components = (*scope.source_root.parts[1:], *name.split("/"))
    current = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in components[:-1]:
            fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
            os.close(current)
            current = fd
        fd = os.open(components[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=current)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
                raise ValueError("source must be a bounded regular file")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                body = stream.read(limit + 1)
            after = os.fstat(fd)
            if (len(body) > limit or (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                    != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
                raise ValueError("source changed during capture")
            body.decode("utf-8", errors="strict")
            return body
        finally:
            os.close(fd)
    finally:
        os.close(current)
