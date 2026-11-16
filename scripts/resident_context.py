"""Bounded, source-bound context packets for an explicitly episodic resident.

This module assembles observations. It grants no authority, launches no process,
and never queries memory or source owners. The caller supplies a trusted current
source snapshot after performing access checks. A snapshot only establishes
currentness at that observation; later actions still need their owner checks.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Callable
import uuid


SCHEMA = "resident-context/v1"
MAX_PACKET_BYTES = 16 * 1024 * 1024
_HASH = re.compile(r"^[0-9a-f]{64}$")
_SCOPE = {"resident", "project", "branch"}
_CURRENT_STATES = {"current", "advisory", "provisional", "supported", "disputed", "observation", "candidate"}
_SECTIONS = ("instructions", "current_work", "required_sources", "orientation", "memories", "worker_outputs")


class ContextBudgetError(ValueError):
    """Mandatory context or its diagnostic envelope cannot fit the actual budget."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _copy(value: Any) -> Any:
    return json.loads(_canonical(value))


def _text(value: Any, name: str, *, limit: int | None = None) -> str:
    if not isinstance(value, str) or not value.strip() or (limit is not None and len(value) > limit):
        raise ValueError(f"{name} must be nonempty text within its bound")
    return value


def _scope(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != _SCOPE:
        raise ValueError("scope requires exactly resident, project and branch")
    return {key: _text(value[key], f"scope.{key}", limit=256) for key in sorted(_SCOPE)}


def _reference(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"source_id", "revision", "sha256"}:
        raise ValueError("source reference requires source_id, revision and sha256")
    source_id = _text(value["source_id"], "source_id", limit=512)
    revision = _text(value["revision"], "revision", limit=512)
    digest = value["sha256"]
    if not isinstance(digest, str) or not _HASH.fullmatch(digest):
        raise ValueError("source sha256 must be a lowercase SHA-256 digest")
    return {"source_id": source_id, "revision": revision, "sha256": digest}


def _entry(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("context entry must be an object")
    refs = value.get("source_refs", [])
    if not isinstance(refs, list) or len(refs) > 64:
        raise ValueError("entry source_refs must contain at most 64 references")
    result = {
        "id": _text(value.get("id"), "entry.id", limit=256),
        "content": _text(value.get("content"), "entry.content"),
        "source_refs": [_reference(ref) for ref in refs],
        "status": _text(value.get("status", "provisional"), "entry.status", limit=64),
    }
    if "scope" in value:
        result["scope"] = _scope(value["scope"])
    return result


def _source_issue(reference: dict[str, str], current_sources: dict[str, Any]) -> str | None:
    current = current_sources.get(reference["source_id"])
    if not isinstance(current, dict) or current.get("available") is not True:
        return "source-unavailable"
    if current.get("revision") != reference["revision"] or current.get("sha256") != reference["sha256"]:
        return "source-changed"
    return None


def _entry_issue(entry: dict[str, Any], *, scope: dict[str, str], current_sources: dict[str, Any],
                 scoped: bool) -> str | None:
    if scoped and "scope" not in entry:
        return "scope-unavailable"
    if "scope" in entry and entry["scope"] != scope:
        return "scope-mismatch"
    if entry["status"] not in _CURRENT_STATES:
        return "inactive-or-unsupported-status"
    if not entry["source_refs"]:
        return "source-basis-unavailable"
    for reference in entry["source_refs"]:
        issue = _source_issue(reference, current_sources)
        if issue:
            return issue
    return None


def _seal(payload: dict[str, Any]) -> dict[str, Any]:
    sources: dict[tuple[str, str, str], dict[str, str]] = {}
    for section in payload["sections"]:
        for item in section["items"]:
            for ref in item.get("source_refs", []):
                sources[(ref["source_id"], ref["revision"], ref["sha256"])] = ref
    payload["source_refs"] = [sources[key] for key in sorted(sources)]
    content = _copy(payload)
    content.pop("digest", None)
    return {**content, "digest": hashlib.sha256(_canonical(content)).hexdigest()}


def build_context(
    *,
    instructions: str,
    current_work: dict[str, Any] | str,
    required_sources: list[dict[str, Any]],
    scope: dict[str, str],
    current_sources: dict[str, Any],
    orientation: str = "",
    memories: list[dict[str, Any]] | tuple = (),
    worker_outputs: list[dict[str, Any]] | tuple = (),
    max_bytes: int = 65536,
    max_tokens: int | None = None,
    token_counter: Callable[[str], int] | None = None,
) -> dict[str, Any]:
    """Build a detached packet; stale mandatory inputs block, optional ones omit.

    The byte bound applies to the complete canonical JSON including its digest.
    No token estimate is reported. A token bound requires the selected model's
    tokenizer supplied by the caller; its count includes the entire packet.
    ``ready`` is a context-readiness observation, never an execution permission.
    """
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_PACKET_BYTES:
        raise ValueError("max_bytes must be a positive integer at most 16 MiB")
    if max_tokens is not None and (type(max_tokens) is not int or max_tokens < 1 or token_counter is None):
        raise ValueError("a positive max_tokens requires the actual model token_counter")
    if not isinstance(current_sources, dict):
        raise ValueError("current_sources must be a trusted source snapshot")
    if not isinstance(current_work, (dict, str)) or not current_work:
        raise ValueError("current_work must be a nonempty object or string")
    if isinstance(current_work, str):
        _text(current_work, "current_work")
    if not isinstance(orientation, str):
        raise ValueError("orientation must be text")
    if orientation:
        _text(orientation, "orientation")
    for values in (required_sources, memories, worker_outputs):
        if not isinstance(values, (list, tuple)) or len(values) > 256:
            raise ValueError("a context section supports at most 256 entries")
    selected_scope = _scope(scope)
    sections = {name: {"kind": name, "items": []} for name in _SECTIONS}
    sections["instructions"]["items"] = [{"id": "instructions", "content": _text(instructions, "instructions")}]
    sections["current_work"]["items"] = [{"id": "current_work", "content": _copy(current_work)}]
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "scope": selected_scope,
        "status": "ready",
        "authorizes_effects": False,
        "budget": {"max_bytes": max_bytes, "max_tokens": max_tokens,
                   "token_measurement": "caller-tokenizer" if max_tokens is not None else "not-measured"},
        "sections": list(sections.values()),
        "blockers": [],
        "omissions": [],
        "source_refs": [],
    }
    optional: list[tuple[str, dict[str, Any]]] = []
    for name, values in (("required_sources", required_sources), ("memories", memories),
                         ("worker_outputs", worker_outputs)):
        ids: set[str] = set()
        for value in values:
            entry = _entry(value)
            if entry["id"] in ids:
                raise ValueError(f"duplicate entry id in {name}")
            ids.add(entry["id"])
            issue = _entry_issue(entry, scope=selected_scope, current_sources=current_sources,
                                 scoped=name != "required_sources")
            if issue:
                target = "blockers" if name == "required_sources" else "omissions"
                payload[target].append({"section": name, "id": entry["id"], "reason": issue})
            elif name == "required_sources":
                sections[name]["items"].append(entry)
            else:
                optional.append((name, entry))
    if payload["blockers"]:
        payload["status"] = "blocked"
    if orientation:
        optional.insert(0, ("orientation", {"id": "orientation", "content": orientation}))

    def fits(packet: dict[str, Any]) -> bool:
        encoded = _canonical(packet)
        if len(encoded) > max_bytes:
            return False
        if max_tokens is not None:
            count = token_counter(encoded.decode("utf-8"))  # type: ignore[misc]
            if type(count) is not int or count < 0:
                raise ValueError("token_counter must return a nonnegative integer")
            return count <= max_tokens
        return True

    if not fits(_seal(payload)):
        raise ContextBudgetError("mandatory context and diagnostics exceed the serialized-packet budget")
    included: list[tuple[str, dict[str, Any]]] = []
    for name, entry in optional:
        sections[name]["items"].append(entry)
        if fits(_seal(payload)):
            included.append((name, entry))
        else:
            sections[name]["items"].pop()
            payload["omissions"].append({"section": name, "id": entry["id"], "reason": "budget"})
    packet = _seal(payload)
    # Omission metadata also consumes the budget. Remove lower-priority optional
    # entries if the final diagnostic envelope no longer fits; never trim a rule.
    while not fits(packet) and included:
        name, entry = included.pop()
        sections[name]["items"].remove(entry)
        payload["omissions"].append({"section": name, "id": entry["id"], "reason": "budget"})
        packet = _seal(payload)
    if not fits(packet):
        raise ContextBudgetError("mandatory context plus explicit omissions exceed the packet budget")
    return packet


def verify_context_packet(packet: dict[str, Any]) -> None:
    """Check schema, internal source basis and bytes, not just a self-digest.

    A digest establishes artifact identity, not its writer's trustworthiness.
    Protected admission still owns provenance and currentness observations.
    """
    if not isinstance(packet, dict) or packet.get("schema") != SCHEMA or packet.get("authorizes_effects") is not False:
        raise ValueError("invalid resident context packet")
    digest = packet.get("digest")
    if not isinstance(digest, str) or not _HASH.fullmatch(digest):
        raise ValueError("invalid context digest")
    payload = {key: value for key, value in packet.items() if key != "digest"}
    if hashlib.sha256(_canonical(payload)).hexdigest() != digest:
        raise ValueError("context packet digest mismatch")
    fields = {"schema", "scope", "status", "authorizes_effects", "budget", "sections",
              "blockers", "omissions", "source_refs", "digest"}
    if set(packet) != fields or packet["status"] not in ("ready", "blocked"):
        raise ValueError("invalid context fields or status")
    scope = _scope(packet["scope"])
    budget = packet["budget"]
    if not isinstance(budget, dict) or set(budget) != {"max_bytes", "max_tokens", "token_measurement"}:
        raise ValueError("invalid context budget fields")
    bound = budget["max_bytes"]
    if type(bound) is not int or not 1 <= bound <= MAX_PACKET_BYTES or len(_canonical(packet)) > bound:
        raise ContextBudgetError("stored context exceeds its serialized byte budget")
    tokens = budget["max_tokens"]
    if ((tokens is not None and (type(tokens) is not int or tokens < 1))
            or budget["token_measurement"] != ("not-measured" if tokens is None else "caller-tokenizer")):
        raise ValueError("invalid context token measurement")
    sections = packet["sections"]
    if not isinstance(sections, list) or len(sections) != len(_SECTIONS):
        raise ValueError("all ordered context sections are required")
    ids: dict[str, set[str]] = {name: set() for name in _SECTIONS}
    basis = {}
    for expected, section in zip(_SECTIONS, sections):
        if (not isinstance(section, dict) or set(section) != {"kind", "items"}
                or section["kind"] != expected or not isinstance(section["items"], list)
                or len(section["items"]) > 256):
            raise ValueError("invalid or reordered context section")
        if expected in {"instructions", "current_work"}:
            if len(section["items"]) != 1:
                raise ValueError("instructions and current work must each occur exactly once")
        if expected == "orientation" and len(section["items"]) > 1:
            raise ValueError("orientation may occur only once")
        for value in section["items"]:
            if expected in {"instructions", "current_work", "orientation"}:
                if not isinstance(value, dict) or set(value) != {"id", "content"} or value["id"] != expected:
                    raise ValueError("invalid trusted context section item")
                if expected == "current_work" and isinstance(value["content"], dict) and value["content"]:
                    continue
                _text(value["content"], expected)
                continue
            entry = _entry(value)
            if entry != value or entry["id"] in ids[expected]:
                raise ValueError("invalid or duplicate source-bound context item")
            ids[expected].add(entry["id"])
            if (entry["status"] not in _CURRENT_STATES or not entry["source_refs"]
                    or ("scope" in entry and entry["scope"] != scope)
                    or (expected != "required_sources" and "scope" not in entry)):
                raise ValueError("invalid status, scope or basis for included context item")
            for ref in entry["source_refs"]:
                basis[(ref["source_id"], ref["revision"], ref["sha256"])] = ref
    if packet["source_refs"] != [basis[key] for key in sorted(basis)]:
        raise ValueError("context source_refs differ from the included section basis")
    reasons = {"scope-unavailable", "scope-mismatch", "inactive-or-unsupported-status",
               "source-basis-unavailable", "source-unavailable", "source-changed"}
    for name in ("blockers", "omissions"):
        diagnostics = packet[name]
        if not isinstance(diagnostics, list) or len(diagnostics) > (256 if name == "blockers" else 513):
            raise ValueError("invalid context diagnostics")
        allowed_sections = {"required_sources"} if name == "blockers" else {"orientation", "memories", "worker_outputs"}
        for value in diagnostics:
            if not isinstance(value, dict) or set(value) != {"section", "id", "reason"}:
                raise ValueError("invalid context diagnostic fields")
            section = _text(value["section"], "diagnostic.section")
            ident = _text(value["id"], "diagnostic.id", limit=256)
            reason = _text(value["reason"], "diagnostic.reason")
            if (section not in allowed_sections or ident in ids[section]
                    or reason not in reasons | ({"budget"} if name == "omissions" else set())):
                raise ValueError("invalid or contradictory context diagnostic")
            if section == "orientation" and (ident != "orientation" or reason != "budget"
                                              or sections[3]["items"]):
                raise ValueError("invalid orientation diagnostic")
            ids[section].add(ident)
            if len(ids[section]) > 256:
                raise ValueError("context section item and diagnostic count exceeds its bound")
    if (packet["status"] == "blocked") != bool(packet["blockers"]):
        raise ValueError("context status contradicts its required-source blockers")


def recheck_context(packet: dict[str, Any], current_sources: dict[str, Any]) -> dict[str, Any]:
    """Compare supplied basis with a new trusted observation; never edit history."""
    verify_context_packet(packet)
    changes = []
    for value in packet["source_refs"]:
        ref = _reference(value)
        issue = _source_issue(ref, current_sources)
        if issue:
            changes.append({"source_id": ref["source_id"], "reason": issue})
    return {"schema": "resident-context-recheck/v1", "context_digest": packet["digest"],
            "status": "review-required" if changes or packet["status"] != "ready" else "unchanged",
            "changes": changes, "authorizes_effects": False}


def save_context_packet(directory: Path, packet: dict[str, Any]) -> Path:
    """Persist exact canonical packet bytes by digest, without replacing history."""
    frozen = _copy(packet)
    verify_context_packet(frozen)
    data = _canonical(frozen)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    folder = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    name = f"{frozen['digest']}.json"
    temporary = f".staging-{uuid.uuid4()}"
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=folder)
        with os.fdopen(descriptor, "wb") as target:
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
        try:
            os.link(temporary, name, src_dir_fd=folder, dst_dir_fd=folder, follow_symlinks=False)
        except FileExistsError:
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder)
            with os.fdopen(descriptor, "rb") as source:
                if not stat.S_ISREG(os.fstat(source.fileno()).st_mode) or source.read(len(data) + 1) != data:
                    raise ValueError("context digest path already contains different bytes")
        os.fsync(folder)
    finally:
        try:
            os.unlink(temporary, dir_fd=folder)
        except FileNotFoundError:
            pass
        os.close(folder)
    return directory / name


def load_context_packet(path: Path) -> dict[str, Any]:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise ValueError("context packet must be a regular file")
        raw = source.read(MAX_PACKET_BYTES + 1)
    if len(raw) > MAX_PACKET_BYTES:
        raise ContextBudgetError("context file exceeds maximum packet size")
    packet = json.loads(raw)
    verify_context_packet(packet)
    if path.name != f"{packet['digest']}.json" or raw != _canonical(packet):
        raise ValueError("context filename or canonical bytes do not match its identity")
    return packet
