"""Protected, fixed-scope policy. This file is not a sandbox implementation."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

IDENTIFIER = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,95}\Z")
KINDS = frozenset({"episode", "canon", "draft", "rumour", "claim", "procedure", "preference"})


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class Scope:
    id: str
    bank: str
    resident: str
    project: str
    branch: str
    source_root: Path
    source_paths: tuple[str, ...]

    @property
    def identity(self) -> dict[str, str]:
        return {"resident": self.resident, "project": self.project, "branch": self.branch}

    @property
    def tags(self) -> list[str]:
        return [f"{key}:{value}" for key, value in self.identity.items()]


@dataclass(frozen=True)
class Principal:
    id: str
    token_sha256: str
    scopes: tuple[str, ...]


@dataclass(frozen=True)
class Policy:
    state_dir: Path
    upstream_url: str
    upstream_token_file: Path
    scopes: dict[str, Scope]
    principals: tuple[Principal, ...]
    policy_sha256: str
    max_source_bytes: int = 65536
    max_result_bytes: int = 32768
    max_request_bytes: int = 8192

    @classmethod
    def load(cls, path: Path) -> "Policy":
        value = json.loads(path.read_bytes())
        if value.get("schema") != "resident-memory-policy/v1":
            raise ValueError("unsupported policy schema")
        allowed = {"schema", "state_dir", "upstream_url", "upstream_token_file", "scopes",
                   "principals", "max_source_bytes", "max_result_bytes", "max_request_bytes"}
        if set(value) - allowed:
            raise ValueError("unknown policy fields")
        url = urlsplit(value["upstream_url"])
        if (url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password
                or url.query or url.fragment or url.path not in {"", "/"}
                or (url.scheme == "http" and url.hostname not in {"127.0.0.1", "::1", "localhost"})):
            raise ValueError("upstream must be fixed HTTPS or loopback HTTP origin")
        scopes: dict[str, Scope] = {}
        for item in value["scopes"]:
            if set(item) != {"id", "bank", "resident", "project", "branch", "source_root", "source_paths"}:
                raise ValueError("invalid scope fields")
            for key in ("id", "bank", "resident", "project"):
                if not isinstance(item[key], str) or not IDENTIFIER.fullmatch(item[key]):
                    raise ValueError(f"invalid scope {key}")
            if not isinstance(item["branch"], str) or not item["branch"] or len(item["branch"]) > 128:
                raise ValueError("invalid branch")
            root = Path(item["source_root"])
            paths = item["source_paths"]
            if not root.is_absolute() or not isinstance(paths, list) or not paths:
                raise ValueError("scope requires absolute source_root and exact source_paths")
            for name in paths:
                validate_relative(name)
                if "**" in name or any("*" in part or "?" in part or "[" in part for part in name.split("/")[:-1]):
                    raise ValueError("source patterns may wildcard only the filename")
            scope = Scope(**{**item, "source_root": root, "source_paths": tuple(paths)})
            if scope.id in scopes:
                raise ValueError("duplicate scope")
            scopes[scope.id] = scope
        if not scopes:
            raise ValueError("at least one scope is required")
        principals = []
        for item in value["principals"]:
            if set(item) != {"id", "token_sha256", "scopes"}:
                raise ValueError("invalid principal")
            if (not IDENTIFIER.fullmatch(item["id"]) or not re.fullmatch(r"[0-9a-f]{64}", item["token_sha256"])
                    or not item["scopes"] or set(item["scopes"]) - scopes.keys()):
                raise ValueError("invalid principal identity or scope")
            principals.append(Principal(item["id"], item["token_sha256"], tuple(item["scopes"])))
        if len({p.id for p in principals}) != len(principals) or len({p.token_sha256 for p in principals}) != len(principals):
            raise ValueError("duplicate principal identity or token")
        state = Path(value["state_dir"])
        token = Path(value["upstream_token_file"])
        if not state.is_absolute() or not token.is_absolute():
            raise ValueError("state and credential paths must be absolute")
        for scope in scopes.values():
            if state.resolve().is_relative_to(scope.source_root.resolve()) or token.resolve().is_relative_to(scope.source_root.resolve()):
                raise ValueError("state and credentials must be outside resident source roots")
        limits = {}
        for name, default in (("max_source_bytes", 65536), ("max_result_bytes", 32768), ("max_request_bytes", 8192)):
            number = value.get(name, default)
            if type(number) is not int or not 1024 <= number <= 1048576:
                raise ValueError(f"invalid {name}")
            limits[name] = number
        return cls(state, value["upstream_url"].rstrip("/"), token, scopes,
                   tuple(principals), digest(canonical(value)), **limits)

    def authenticate(self, token: str, scope_id: str) -> Principal:
        if not isinstance(token, str) or not 24 <= len(token) <= 512:
            raise PermissionError("unauthorized")
        hashed = digest(token.encode())
        for principal in self.principals:
            if hmac.compare_digest(principal.token_sha256, hashed) and scope_id in principal.scopes:
                return principal
        raise PermissionError("unauthorized")


def validate_relative(name: str) -> None:
    if (not isinstance(name, str) or not name or len(name) > 512 or name.startswith("/")
            or any(not part or part.startswith(".") for part in name.split("/"))
            or any(ord(char) < 32 for char in name) or "\\" in name):
        raise ValueError("unsafe source path")
