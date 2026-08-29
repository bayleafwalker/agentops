#!/usr/bin/env python3
"""Normative semantic validator for capability-receipt JSON files (v1 and v2).

v2 (2026-08-29) removes `ratified` from the document lifecycle and removes
ratification as a workflow stage.  A receipt is `draft`, `current`, or
`superseded`.  Who established it, and on what authority, is recorded in
`established_by` as *provenance* -- an `actor_type` of `human` says a person did
it, not that a person approved it.  Validity is its own interval, so kind, state,
provenance/authority and validity stay orthogonal.

v1 files still validate: they are migrated in memory (`migrate_v1`) rather than
rejected.  `ratified` maps to `current`.  The v1 `ratification` block recorded
that a person acted, which is now `actor_type: human`; it never recorded a basis,
and no basis is owner-reserved, so it migrates as `delegated`.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


SCHEMA_VERSION = "capability-receipt/v2"
LEGACY_SCHEMA_VERSION = "capability-receipt/v1"
SCHEMA_VERSIONS = {LEGACY_SCHEMA_VERSION, SCHEMA_VERSION}
STATUSES = {"draft", "current", "superseded"}
LEGACY_STATUSES = {"draft", "ratified", "superseded"}
ACTOR_TYPES = {"human", "agent", "automation"}
AUTHORITY_BASES = {"delegated", "standing-policy"}
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
    "established_by",
    "validity",
    "basis_for",
    "supersedes",
}
BOUNDARY_REQUIRED_FIELDS = {"kind", "ref"}
IMMUTABLE_REF_REQUIRED_FIELDS = {"kind", "source", "revision"}
EVIDENCE_REQUIRED_FIELDS = {"ref", "observation"}
UNKNOWN_REQUIRED_FIELDS = {"field", "reason"}
ESTABLISHED_BY_REQUIRED_FIELDS = {
    "actor",
    "actor_type",
    "at",
    "authority_basis",
    "decision_ref",
}
VALIDITY_REQUIRED_FIELDS = {"effective_from"}
VALIDITY_OPTIONAL_FIELDS = {"effective_to"}
RECEIPT_REF_REQUIRED_FIELDS = {"id", "sha256"}
# `current` and `superseded` both describe an established claim; only the validity
# interval distinguishes them.
ESTABLISHED_STATUSES = {"current", "superseded"}
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


def _validate_established_by(value: Any, path: Path) -> None:
    established = _object(value, "established_by", path)
    _keys(
        established,
        "established_by",
        path,
        required=ESTABLISHED_BY_REQUIRED_FIELDS,
    )
    _non_blank(established["actor"], "established_by.actor", path)
    # actor_type is provenance and nothing else: no value of it grants or withholds
    # authority, and none of them is a workflow stage.
    _enum(
        established["actor_type"],
        "established_by.actor_type",
        ACTOR_TYPES,
        path,
    )
    _validate_datetime(established["at"], "established_by.at", path)
    _enum(
        established["authority_basis"],
        "established_by.authority_basis",
        AUTHORITY_BASES,
        path,
    )
    _validate_immutable_ref(
        established["decision_ref"],
        "established_by.decision_ref",
        path,
    )


def _validate_validity(value: Any, path: Path, *, status: str) -> None:
    validity = _object(value, "validity", path)
    _keys(
        validity,
        "validity",
        path,
        required=VALIDITY_REQUIRED_FIELDS,
        optional=VALIDITY_OPTIONAL_FIELDS,
    )
    _validate_datetime(validity["effective_from"], "validity.effective_from", path)
    effective_to = validity.get("effective_to")
    if status == "superseded" and effective_to is None:
        raise _error(
            path,
            "validity.effective_to",
            "is required while status is superseded",
        )
    if effective_to is not None:
        _validate_datetime(effective_to, "validity.effective_to", path)
        if effective_to < validity["effective_from"]:
            raise _error(
                path,
                "validity.effective_to",
                "must not precede validity.effective_from",
            )


def migrate_v1(value: dict[str, Any]) -> dict[str, Any]:
    """Return a v2-shaped copy of a v1 receipt.

    v1 encoded a human attestation as a lifecycle state. The same facts survive as
    provenance: the ratifier becomes the actor and `human` becomes the actor_type.
    The literal `authority: human` assertion carried no authority basis -- it
    asserted only that a person acted -- so it migrates as `delegated`, the basis
    every ordinary act of establishment has.
    """

    migrated = dict(value)
    migrated["schema_version"] = SCHEMA_VERSION
    if migrated.get("status") == "ratified":
        migrated["status"] = "current"
    ratification = migrated.pop("ratification", None)
    if isinstance(ratification, dict):
        at = ratification.get("at")
        migrated["established_by"] = {
            "actor": ratification.get("ratifier"),
            "actor_type": "human",
            "at": at,
            "authority_basis": "delegated",
            "decision_ref": ratification.get("decision_ref"),
        }
        validity: dict[str, Any] = {"effective_from": at}
        if migrated["status"] == "superseded":
            validity["effective_to"] = at
        migrated["validity"] = validity
    return migrated


def validate_receipt(value: dict[str, Any], path: Path) -> None:
    """Validate one decoded capability receipt."""

    declared = value.get("schema_version")
    if declared not in SCHEMA_VERSIONS:
        raise _error(
            path,
            "schema_version",
            f"must be one of {', '.join(sorted(SCHEMA_VERSIONS))}",
        )
    if declared == LEGACY_SCHEMA_VERSION:
        legacy_status = value.get("status")
        if legacy_status is not None and legacy_status not in LEGACY_STATUSES:
            raise _error(path, "status", f"must be one of {', '.join(sorted(LEGACY_STATUSES))}")
        value = migrate_v1(value)
    _keys(value, "receipt", path, required=REQUIRED_FIELDS, optional=OPTIONAL_FIELDS)

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

    has_established_by = "established_by" in value
    has_validity = "validity" in value
    if status == "draft":
        if has_established_by:
            raise _error(path, "established_by", "is not allowed while status is draft")
        if has_validity:
            raise _error(path, "validity", "is not allowed while status is draft")
    if status in ESTABLISHED_STATUSES:
        if not has_established_by:
            raise _error(path, "established_by", f"is required while status is {status}")
        if not has_validity:
            raise _error(path, "validity", f"is required while status is {status}")
    if has_established_by:
        _validate_established_by(value["established_by"], path)
    if has_validity:
        _validate_validity(value["validity"], path, status=status)

    if "basis_for" in value:
        # Canonicality is a dependency relation: what this receipt is the basis for,
        # and therefore the blast radius of changing it. Not approval or maturity.
        for entry in _string_array(value["basis_for"], "basis_for", path):
            _identifier(entry, "basis_for[]", path)

    if status in ESTABLISHED_STATUSES and "supersedes" not in value:
        raise _error(path, "supersedes", f"is required while status is {status}")
    if "supersedes" in value:
        _validate_receipt_ref(value["supersedes"], "supersedes", path, receipt_id)

    if publication in PUBLICATION_SUCCESSOR_STATES and status not in ESTABLISHED_STATUSES:
        raise _error(
            path,
            "publication",
            f"{publication} requires a current or superseded established successor",
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
