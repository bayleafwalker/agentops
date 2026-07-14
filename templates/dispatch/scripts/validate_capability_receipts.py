#!/usr/bin/env python3
"""Normative semantic validator for capability-receipt/v1 JSON files."""

from __future__ import annotations

import argparse
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


SCHEMA_VERSION = "capability-receipt/v1"
STATUSES = {"draft", "ratified", "superseded"}
BOUNDARY_KINDS = {
    "release",
    "sprint-close",
    "experiment-killed",
    "operating-change",
}
LOCI = {"embodied", "delegated", "governed", "institutionalised"}
PUBLICATIONS = {"private", "candidate", "published"}
REFERENCE_KINDS = {
    "git-commit",
    "sprint-event",
    "document",
    "verification-result",
    "release",
    "artifact",
}
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ISO_DATETIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
GIT_REVISION = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
SPRINT_EVENT_REVISION = re.compile(r"^event:[1-9][0-9]*$")
CONTENT_SHA256_REVISION = re.compile(r"^sha256:[0-9a-f]{64}$")
DOCUMENT_RELEASE_REVISION = re.compile(
    r"^(?:(?:[0-9a-f]{40}|[0-9a-f]{64})|sha256:[0-9a-f]{64})$"
)
SHA256 = re.compile(r"^[0-9a-f]{64}$")

REQUIRED_FIELDS = {
    "schema_version",
    "id",
    "project",
    "as_of",
    "boundary",
    "status",
    "before",
    "after",
    "locus",
    "evidence",
    "counterfactual",
    "transfer",
    "dependency",
    "belief_changed",
    "displaced_alternative",
    "would_disconfirm",
    "unknowns",
    "publication",
}
OPTIONAL_FIELDS = {
    "expectation_ref",
    "ratification",
    "supersedes",
}
BOUNDARY_REQUIRED_FIELDS = {"kind", "ref"}
IMMUTABLE_REF_REQUIRED_FIELDS = {"kind", "source", "revision"}
EVIDENCE_REQUIRED_FIELDS = {"ref", "observation"}
UNKNOWN_REQUIRED_FIELDS = {"field", "reason"}
RATIFICATION_REQUIRED_FIELDS = {"authority", "ratifier", "at", "decision_ref"}
RECEIPT_REF_REQUIRED_FIELDS = {"id", "sha256"}
SUCCESSOR_STATUSES = {"ratified", "superseded"}
PUBLICATION_SUCCESSOR_STATES = {"candidate", "published"}


def _error(path: Path, field: str, message: str) -> ValueError:
    return ValueError(f"{path}: {field} {message}")


def _object(value: Any, field: str, path: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _error(path, field, "must be an object")
    return value


def _keys(
    value: dict[str, Any],
    field: str,
    path: Path,
    *,
    required: set[str],
    optional: set[str] | None = None,
) -> None:
    missing = sorted(required - value.keys())
    if missing:
        raise _error(path, field, f"is missing fields: {', '.join(missing)}")
    unexpected = sorted(value.keys() - required - (optional or set()))
    if unexpected:
        raise _error(path, field, f"has unexpected fields: {', '.join(unexpected)}")


def _non_blank(value: Any, field: str, path: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error(path, field, "must be a non-blank string")
    return value


def _identifier(value: Any, field: str, path: Path) -> str:
    text = _non_blank(value, field, path)
    if not IDENTIFIER.fullmatch(text):
        raise _error(path, field, "must contain only letters, digits, dot, underscore, or hyphen")
    return text


def _enum(value: Any, field: str, allowed: set[str], path: Path) -> str:
    if not isinstance(value, str) or value not in allowed:
        choices = ", ".join(sorted(allowed))
        raise _error(path, field, f"must be one of: {choices}")
    return value


def _string_array(
    value: Any,
    field: str,
    path: Path,
    *,
    non_empty: bool = False,
) -> list[str]:
    if not isinstance(value, list) or (non_empty and not value):
        qualifier = "a non-empty array" if non_empty else "an array"
        raise _error(path, field, f"must be {qualifier}")
    result = [_non_blank(item, f"{field}[{index}]", path) for index, item in enumerate(value)]
    if len(result) != len(set(result)):
        raise _error(path, field, "must not contain duplicates")
    return result


def _validate_date(value: Any, field: str, path: Path) -> None:
    text = _non_blank(value, field, path)
    if not ISO_DATE.fullmatch(text):
        raise _error(path, field, "must use YYYY-MM-DD")
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise _error(path, field, "must be a real calendar date") from exc


def _validate_datetime(value: Any, field: str, path: Path) -> None:
    text = _non_blank(value, field, path)
    if not ISO_DATETIME.fullmatch(text):
        raise _error(path, field, "must be an RFC 3339 date-time with an explicit offset")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _error(path, field, "must be a real date-time") from exc
    if parsed.tzinfo is None:
        raise _error(path, field, "must include a timezone offset")


def _validate_revision(value: Any, kind: str, field: str, path: Path) -> None:
    revision = _non_blank(value, field, path)
    if kind == "git-commit":
        if not GIT_REVISION.fullmatch(revision):
            raise _error(
                path,
                field,
                "must be a lowercase full 40- or 64-character Git object ID",
            )
        return
    if kind == "sprint-event":
        if not SPRINT_EVENT_REVISION.fullmatch(revision):
            raise _error(path, field, "must be event:<positive integer>")
        return
    if kind in {"artifact", "verification-result"}:
        if not CONTENT_SHA256_REVISION.fullmatch(revision):
            raise _error(path, field, "must be sha256:<lowercase content SHA-256>")
        return
    if kind in {"document", "release"}:
        if not DOCUMENT_RELEASE_REVISION.fullmatch(revision):
            raise _error(
                path,
                field,
                "must be a lowercase full Git object ID or sha256:<lowercase content SHA-256>",
            )
        return
    raise _error(path, field, f"has unsupported reference kind {kind!r}")


def _validate_immutable_ref(value: Any, field: str, path: Path) -> None:
    ref = _object(value, field, path)
    _keys(ref, field, path, required=IMMUTABLE_REF_REQUIRED_FIELDS)
    kind = _enum(ref["kind"], f"{field}.kind", REFERENCE_KINDS, path)
    _non_blank(ref["source"], f"{field}.source", path)
    _validate_revision(ref["revision"], kind, f"{field}.revision", path)


def _validate_receipt_ref(value: Any, field: str, path: Path, receipt_id: str) -> None:
    ref = _object(value, field, path)
    _keys(ref, field, path, required=RECEIPT_REF_REQUIRED_FIELDS)
    referenced_id = _identifier(ref["id"], f"{field}.id", path)
    if referenced_id == receipt_id:
        raise _error(path, f"{field}.id", "must not refer to the receipt itself")
    digest = _non_blank(ref["sha256"], f"{field}.sha256", path)
    if not SHA256.fullmatch(digest):
        raise _error(path, f"{field}.sha256", "must be a lowercase SHA-256 digest")


def _validate_boundary(value: Any, path: Path, project: str) -> None:
    boundary = _object(value, "boundary", path)
    _keys(boundary, "boundary", path, required=BOUNDARY_REQUIRED_FIELDS)
    boundary_kind = _enum(boundary["kind"], "boundary.kind", BOUNDARY_KINDS, path)
    _validate_immutable_ref(boundary["ref"], "boundary.ref", path)
    if boundary_kind == "sprint-close":
        ref = boundary["ref"]
        if ref["kind"] != "sprint-event":
            raise _error(path, "boundary.ref.kind", "must be sprint-event for sprint-close")
        expected_source = re.compile(
            rf"^sprintctl:{re.escape(project)}:sprint:[A-Za-z0-9][A-Za-z0-9._-]*$"
        )
        if not expected_source.fullmatch(ref["source"]):
            raise _error(
                path,
                "boundary.ref.source",
                f"must be sprintctl:{project}:sprint:<id> for sprint-close",
            )


def _validate_evidence(value: Any, path: Path) -> None:
    if not isinstance(value, list) or not value:
        raise _error(path, "evidence", "must be a non-empty array")
    for index, item in enumerate(value):
        field = f"evidence[{index}]"
        evidence = _object(item, field, path)
        _keys(evidence, field, path, required=EVIDENCE_REQUIRED_FIELDS)
        _validate_immutable_ref(evidence["ref"], f"{field}.ref", path)
        _non_blank(evidence["observation"], f"{field}.observation", path)


def _validate_unknowns(value: Any, path: Path) -> None:
    if not isinstance(value, list):
        raise _error(path, "unknowns", "must be an array")
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(value):
        field = f"unknowns[{index}]"
        unknown = _object(item, field, path)
        _keys(unknown, field, path, required=UNKNOWN_REQUIRED_FIELDS)
        pair = (
            _non_blank(unknown["field"], f"{field}.field", path),
            _non_blank(unknown["reason"], f"{field}.reason", path),
        )
        if pair in seen:
            raise _error(path, "unknowns", "must not contain duplicates")
        seen.add(pair)


def _validate_ratification(value: Any, path: Path) -> None:
    ratification = _object(value, "ratification", path)
    _keys(
        ratification,
        "ratification",
        path,
        required=RATIFICATION_REQUIRED_FIELDS,
    )
    if ratification["authority"] != "human":
        raise _error(
            path,
            "ratification.authority",
            "must contain the literal procedural assertion human",
        )
    _non_blank(ratification["ratifier"], "ratification.ratifier", path)
    _validate_datetime(ratification["at"], "ratification.at", path)
    _validate_immutable_ref(
        ratification["decision_ref"],
        "ratification.decision_ref",
        path,
    )


def validate_receipt(value: dict[str, Any], path: Path) -> None:
    """Validate one decoded capability receipt."""

    _keys(value, "receipt", path, required=REQUIRED_FIELDS, optional=OPTIONAL_FIELDS)
    if value["schema_version"] != SCHEMA_VERSION:
        raise _error(path, "schema_version", f"must be {SCHEMA_VERSION}")

    project = _identifier(value["project"], "project", path)
    receipt_id = _identifier(value["id"], "id", path)
    project_prefix = f"{project}."
    if not receipt_id.startswith(project_prefix) or receipt_id == project_prefix:
        raise _error(path, "id", f"must start with {project_prefix!r} and include a suffix")
    _validate_date(value["as_of"], "as_of", path)
    _validate_boundary(value["boundary"], path, project)
    status = _enum(value["status"], "status", STATUSES, path)

    before = _non_blank(value["before"], "before", path)
    after = _non_blank(value["after"], "after", path)
    if before.strip() == after.strip():
        raise _error(path, "before/after", "must describe different capability states")
    _enum(value["locus"], "locus", LOCI, path)
    _validate_evidence(value["evidence"], path)
    if "expectation_ref" in value:
        _validate_immutable_ref(value["expectation_ref"], "expectation_ref", path)

    _non_blank(value["counterfactual"], "counterfactual", path)
    _string_array(value["transfer"], "transfer", path)
    _string_array(value["dependency"], "dependency", path, non_empty=True)
    _non_blank(value["belief_changed"], "belief_changed", path)
    _non_blank(value["displaced_alternative"], "displaced_alternative", path)
    _non_blank(value["would_disconfirm"], "would_disconfirm", path)
    _validate_unknowns(value["unknowns"], path)
    publication = _enum(value["publication"], "publication", PUBLICATIONS, path)

    has_ratification = "ratification" in value
    if status == "draft" and has_ratification:
        raise _error(path, "ratification", "is not allowed while status is draft")
    if status in SUCCESSOR_STATUSES and not has_ratification:
        raise _error(path, "ratification", f"is required while status is {status}")
    if has_ratification:
        _validate_ratification(value["ratification"], path)

    if status in SUCCESSOR_STATUSES and "supersedes" not in value:
        raise _error(path, "supersedes", f"is required while status is {status}")
    if "supersedes" in value:
        _validate_receipt_ref(value["supersedes"], "supersedes", path, receipt_id)

    if publication in PUBLICATION_SUCCESSOR_STATES and status not in SUCCESSOR_STATUSES:
        raise _error(
            path,
            "publication",
            f"{publication} requires a ratified or superseded procedurally attested successor",
        )


def load_receipt(path: Path) -> dict[str, Any]:
    """Load and validate the top-level JSON shape for one file."""

    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"{path}: cannot read JSON: {exc}") from exc
    return _decode_receipt(raw, path)


def _decode_receipt(raw: bytes, path: Path) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: cannot read JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path}: top-level value must be an object")
    return value


class ReceiptDocument:
    """A locally validated receipt together with the digest of its exact bytes."""

    __slots__ = ("path", "value", "digest")

    def __init__(self, path: Path, value: dict[str, Any], digest: str) -> None:
        self.path = path
        self.value = value
        self.digest = digest


def _load_document(
    path: Path,
    *,
    expected_project: str | None = None,
) -> ReceiptDocument:
    """Load and locally validate one receipt without resolving its predecessor."""

    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"{path}: cannot read JSON: {exc}") from exc
    value = _decode_receipt(raw, path)
    validate_receipt(value, path)
    if expected_project is not None and value["project"] != expected_project:
        raise _error(path, "project", f"must be {expected_project!r}")
    return ReceiptDocument(path, value, hashlib.sha256(raw).hexdigest())


def validate_documents(
    paths: list[Path],
    *,
    expected_project: str | None = None,
) -> list[ReceiptDocument]:
    """Validate receipts and resolve every backward lineage link in this set."""

    documents = [
        _load_document(path, expected_project=expected_project)
        for path in paths
    ]
    by_id: dict[str, ReceiptDocument] = {}
    for document in documents:
        receipt_id = document.value["id"]
        prior = by_id.get(receipt_id)
        if prior is not None:
            raise _error(
                document.path,
                "id",
                f"duplicates {receipt_id!r} already loaded from {prior.path}",
            )
        by_id[receipt_id] = document

    predecessor_by_id: dict[str, str] = {}
    for document in documents:
        supersedes = document.value.get("supersedes")
        if supersedes is None:
            continue
        predecessor_id = supersedes["id"]
        predecessor = by_id.get(predecessor_id)
        if predecessor is None:
            raise _error(
                document.path,
                "supersedes.id",
                f"does not resolve {predecessor_id!r} in the validation set",
            )
        if supersedes["sha256"] != predecessor.digest:
            raise _error(
                document.path,
                "supersedes.sha256",
                f"does not match the exact bytes of {predecessor.path}",
            )
        if document.value["project"] != predecessor.value["project"]:
            raise _error(
                document.path,
                "supersedes",
                "must reference a predecessor from the same project",
            )
        predecessor_by_id[document.value["id"]] = predecessor_id

    for receipt_id in predecessor_by_id:
        seen: set[str] = set()
        current = receipt_id
        while current in predecessor_by_id:
            if current in seen:
                raise _error(
                    by_id[receipt_id].path,
                    "supersedes",
                    "must not form a lineage cycle",
                )
            seen.add(current)
            current = predecessor_by_id[current]

    return documents


def validate_file(path: Path, *, expected_project: str | None = None) -> str:
    """Validate one receipt, including any lineage possible in a one-file set."""

    return validate_documents([path], expected_project=expected_project)[0].digest


def discover_paths(inputs: list[Path]) -> list[Path]:
    """Expand explicit files and directories into a stable, unique file list."""

    discovered: list[Path] = []
    for input_path in inputs:
        if input_path.is_file():
            discovered.append(input_path)
        elif input_path.is_dir():
            discovered.extend(sorted(path for path in input_path.rglob("*.json") if path.is_file()))
        else:
            raise ValueError(f"{input_path}: path is neither a file nor a directory")

    unique: list[Path] = []
    seen: set[Path] = set()
    for path in discovered:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    if not unique:
        raise ValueError("no JSON receipt files found")
    return unique


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate capability-receipt/v1 JSON files and print their exact digests."
    )
    parser.add_argument("paths", nargs="+", type=Path, help="receipt file or directory")
    parser.add_argument(
        "--expected-project",
        help="require every receipt to use this project identifier",
    )
    args = parser.parse_args(argv)

    try:
        if args.expected_project is not None:
            _identifier(args.expected_project, "--expected-project", Path("command line"))
        paths = discover_paths(args.paths)
        documents = validate_documents(paths, expected_project=args.expected_project)
        for document in documents:
            print(f"ok {document.path} receipt_sha256={document.digest}")
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
