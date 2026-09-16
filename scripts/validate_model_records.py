#!/usr/bin/env python3
"""Normative semantic validator for the metanarrative model records.

Four record kinds, and the rules that keep them orthogonal:

* `claim/v1` -- a tenet, direction, practice or decision. `kind`, `state`,
  provenance/authority and validity are independent axes. There is no Practice
  object: current practice is a projection over establishing and superseding
  events (`current_claims`), and observations test it.
* `observation/v1` -- evidence bearing on a claim. It never changes the claim's
  state, so `state: current` with `observational_status: contradicted` is a
  legal and useful position: the discrepancy is reconciliation work.
* `commitment/v1` -- a provider->consumer dependency on a contract revision under
  stated compatibility terms. Commitment is this relation, never a boolean.
* `realignment-session/v1` -- opened by a divergence finding against a
  `review`-mode tenet. Two substantive resolutions; an attention request is
  routing and leaves the session open.

No record kind has an approval field, and none has a state that only a human can
enter. `actor_type` is provenance.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable

CLAIM_VERSION = "claim/v1"
OBSERVATION_VERSION = "observation/v1"
COMMITMENT_VERSION = "commitment/v1"
SESSION_VERSION = "realignment-session/v1"

CLAIM_KINDS = {"tenet", "direction", "practice", "decision"}
STATES = {"draft", "current", "superseded"}
ACTOR_TYPES = {"human", "agent", "automation"}
AUTHORITY_BASES = {"delegated", "standing-policy"}
ENFORCEMENT_MODES = {"review", "block"}
STANCES = {"corroborates", "contradicts"}
COMPATIBILITY_TERMS = {
    "backward-compatible",
    "forward-compatible",
    "exact-revision",
    "breaking",
}
ALIGNMENTS = {"aligned", "extension", "tension", "divergent"}
RESOLUTIONS = {"realign-work", "supersede-tenet"}
# Three grounds, all of them about the limits of authority or an unsettled value.
# There is no "an owner must decide" ground: by its nature no authority basis is
# owner-reserved, and a human-in-the-loop is a perpendicular plane (meta-sessions
# realigning intent, architecture and the workflow itself), never a stage the
# regular workstream stops at.
ATTENTION_REASONS = {
    "missing-delegated-authority",
    "unresolved-value-choice",
    "conflict-without-precedence",
}
ESTABLISHED_STATES = {"current", "superseded"}

IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ISO_DATETIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)

# Vocabulary that encoded approval as a lifecycle state or a workflow stage. It is
# rejected outright rather than aliased: an alias keeps the idea alive in the data.
FORBIDDEN_KEYS = {"ratified", "ratification", "approved", "approval", "committed"}
FORBIDDEN_STATES = {"ratified", "approved", "pending-approval", "awaiting-review"}


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
    optional: set[str] = frozenset(),
) -> None:
    missing = sorted(required - set(value))
    if missing:
        raise _error(path, field, f"is missing fields: {', '.join(missing)}")
    unknown = sorted(set(value) - required - set(optional))
    if unknown:
        raise _error(path, field, f"has unknown fields: {', '.join(unknown)}")


def _non_blank(value: Any, field: str, path: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error(path, field, "must be a non-blank string")
    return value


def _identifier(value: Any, field: str, path: Path) -> str:
    text = _non_blank(value, field, path)
    if not IDENTIFIER.fullmatch(text):
        raise _error(path, field, "must be a bare identifier")
    return text


def _enum(value: Any, field: str, allowed: set[str], path: Path) -> str:
    text = _non_blank(value, field, path)
    if text not in allowed:
        raise _error(path, field, f"must be one of {', '.join(sorted(allowed))}")
    return text


def _datetime(value: Any, field: str, path: Path) -> str:
    text = _non_blank(value, field, path)
    if not ISO_DATETIME.fullmatch(text):
        raise _error(path, field, "must be an RFC 3339 timestamp")
    return text


def _reject_approval_vocabulary(value: dict[str, Any], path: Path) -> None:
    present = sorted(FORBIDDEN_KEYS & set(value))
    if present:
        raise _error(
            path,
            ", ".join(present),
            "encodes approval as data; use established_by (provenance), "
            "commitment records (dependency), or basis_for (canonicality)",
        )


def _validate_established_by(value: Any, path: Path) -> None:
    established = _object(value, "established_by", path)
    _keys(
        established,
        "established_by",
        path,
        required={"actor", "actor_type", "at", "authority_basis"},
        optional={"decision_ref"},
    )
    _non_blank(established["actor"], "established_by.actor", path)
    _enum(established["actor_type"], "established_by.actor_type", ACTOR_TYPES, path)
    _datetime(established["at"], "established_by.at", path)
    _enum(
        established["authority_basis"],
        "established_by.authority_basis",
        AUTHORITY_BASES,
        path,
    )


def _validate_validity(value: Any, path: Path, *, state: str) -> None:
    validity = _object(value, "validity", path)
    _keys(
        validity,
        "validity",
        path,
        required={"effective_from"},
        optional={"effective_to"},
    )
    _datetime(validity["effective_from"], "validity.effective_from", path)
    effective_to = validity.get("effective_to")
    if state == "superseded" and effective_to is None:
        raise _error(path, "validity.effective_to", "is required while state is superseded")
    if effective_to is not None:
        _datetime(effective_to, "validity.effective_to", path)
        if effective_to < validity["effective_from"]:
            raise _error(
                path, "validity.effective_to", "must not precede validity.effective_from"
            )


def validate_claim(value: dict[str, Any], path: Path) -> None:
    _reject_approval_vocabulary(value, path)
    _keys(
        value,
        "claim",
        path,
        required={"schema_version", "id", "kind", "scope", "statement", "state"},
        optional={
            "established_by",
            "validity",
            "supersedes",
            "basis_for",
            "enforcement_mode",
            "review_trigger",
        },
    )
    _identifier(value["id"], "id", path)
    kind = _enum(value["kind"], "kind", CLAIM_KINDS, path)
    _identifier(value["scope"], "scope", path)
    _non_blank(value["statement"], "statement", path)
    raw_state = value["state"]
    if isinstance(raw_state, str) and raw_state in FORBIDDEN_STATES:
        raise _error(
            path,
            "state",
            f"{raw_state!r} is not a lifecycle state; a claim is draft, current or superseded",
        )
    state = _enum(raw_state, "state", STATES, path)

    if state == "draft":
        for field in ("established_by", "validity"):
            if field in value:
                raise _error(path, field, "is not allowed while state is draft")
    else:
        for field in ("established_by", "validity"):
            if field not in value:
                raise _error(path, field, f"is required while state is {state}")
    if "established_by" in value:
        _validate_established_by(value["established_by"], path)
    if "validity" in value:
        _validate_validity(value["validity"], path, state=state)
    if "supersedes" in value:
        superseded = _identifier(value["supersedes"], "supersedes", path)
        if superseded == value["id"]:
            raise _error(path, "supersedes", "must not reference the claim itself")
    if "basis_for" in value:
        if not isinstance(value["basis_for"], list):
            raise _error(path, "basis_for", "must be an array")
        for index, entry in enumerate(value["basis_for"]):
            _identifier(entry, f"basis_for[{index}]", path)
    # A tenet without an enforcement mode is indistinguishable from an invariant,
    # and the difference is the whole point: review opens a session, block stops work.
    if kind == "tenet" and "enforcement_mode" not in value:
        raise _error(path, "enforcement_mode", "is required for a tenet")
    if "enforcement_mode" in value:
        _enum(value["enforcement_mode"], "enforcement_mode", ENFORCEMENT_MODES, path)


def validate_observation(value: dict[str, Any], path: Path) -> None:
    _reject_approval_vocabulary(value, path)
    _keys(
        value,
        "observation",
        path,
        required={"schema_version", "id", "subject", "stance", "observed_at", "evidence_ref"},
        optional={"note"},
    )
    _identifier(value["id"], "id", path)
    _identifier(value["subject"], "subject", path)
    _enum(value["stance"], "stance", STANCES, path)
    _datetime(value["observed_at"], "observed_at", path)
    _non_blank(value["evidence_ref"], "evidence_ref", path)


def validate_commitment(value: dict[str, Any], path: Path) -> None:
    _reject_approval_vocabulary(value, path)
    _keys(
        value,
        "commitment",
        path,
        required={"schema_version", "provider", "consumer", "effective_from", "compatibility"},
        optional={"scope", "supersedes"},
    )
    provider = _non_blank(value["provider"], "provider", path)
    consumer = _non_blank(value["consumer"], "consumer", path)
    if provider == consumer:
        raise _error(path, "consumer", "must differ from provider")
    date_text = _non_blank(value["effective_from"], "effective_from", path)
    if not ISO_DATE.fullmatch(date_text):
        raise _error(path, "effective_from", "must use YYYY-MM-DD")
    _enum(value["compatibility"], "compatibility", COMPATIBILITY_TERMS, path)


def validate_session(value: dict[str, Any], path: Path) -> None:
    _reject_approval_vocabulary(value, path)
    _keys(
        value,
        "realignment-session",
        path,
        required={
            "schema_version",
            "id",
            "tenet",
            "work_ref",
            "alignment",
            "state",
            "resolution_options",
        },
        optional={"resolution", "attention_request"},
    )
    _identifier(value["id"], "id", path)
    _identifier(value["tenet"], "tenet", path)
    _non_blank(value["work_ref"], "work_ref", path)
    alignment = _enum(value["alignment"], "alignment", ALIGNMENTS, path)
    state = _enum(value["state"], "state", {"open", "resolved"}, path)

    options = value["resolution_options"]
    if not isinstance(options, list) or set(options) != RESOLUTIONS:
        raise _error(
            path,
            "resolution_options",
            f"must offer exactly {', '.join(sorted(RESOLUTIONS))}",
        )
    # Only divergence opens a session. Tension is recorded and watched, and calling
    # it divergence would make every difference of emphasis a process event.
    if alignment != "divergent" and state == "open":
        raise _error(
            path,
            "alignment",
            "must be divergent for an open realignment session",
        )
    if state == "resolved":
        if "resolution" not in value:
            raise _error(path, "resolution", "is required while state is resolved")
        _enum(value["resolution"], "resolution", RESOLUTIONS, path)
        if "attention_request" in value:
            raise _error(
                path,
                "attention_request",
                "must not accompany a resolution; attention is routing, not an outcome",
            )
    else:
        if "resolution" in value:
            raise _error(path, "resolution", "is not allowed while state is open")
    if "attention_request" in value:
        request = _object(value["attention_request"], "attention_request", path)
        _keys(
            request,
            "attention_request",
            path,
            required={"reason", "raised_at"},
            optional={"detail"},
        )
        _enum(request["reason"], "attention_request.reason", ATTENTION_REASONS, path)
        _datetime(request["raised_at"], "attention_request.raised_at", path)


VALIDATORS = {
    CLAIM_VERSION: validate_claim,
    OBSERVATION_VERSION: validate_observation,
    COMMITMENT_VERSION: validate_commitment,
    SESSION_VERSION: validate_session,
}


def validate_record(value: Any, path: Path) -> str:
    """Validate one decoded record and return its schema version."""

    record = _object(value, "record", path)
    version = record.get("schema_version")
    if version not in VALIDATORS:
        raise _error(
            path,
            "schema_version",
            f"must be one of {', '.join(sorted(VALIDATORS))}",
        )
    VALIDATORS[version](record, path)
    return version


def current_claims(claims: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Project the operative claims: current state, and not superseded by another.

    This projection is why no Practice object is needed. "What do we do now" is
    answered by reading establishing and superseding events, not by a separate
    mutable record that has to be kept true.
    """

    claims = list(claims)
    superseded = {c["supersedes"] for c in claims if c.get("supersedes")}
    return [c for c in claims if c.get("state") == "current" and c.get("id") not in superseded]


def observational_status(
    claim_id: str, observations: Iterable[dict[str, Any]]
) -> str:
    """`contradicted`, `corroborated`, or `untested` for one claim.

    Deliberately independent of the claim's lifecycle state: a claim can be current
    and contradicted at once. That pairing is the useful one -- it names
    reconciliation work instead of silently rewriting history or policy.
    """

    stances = {o["stance"] for o in observations if o.get("subject") == claim_id}
    if "contradicts" in stances:
        return "contradicted"
    if "corroborates" in stances:
        return "corroborated"
    return "untested"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args(argv)

    files: list[Path] = []
    for path in args.paths:
        files.extend(sorted(path.rglob("*.json")) if path.is_dir() else [path])

    counts: dict[str, int] = {}
    for file in files:
        try:
            decoded = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"{file}: not readable JSON: {exc}", file=sys.stderr)
            return 1
        try:
            version = validate_record(decoded, file)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        counts[version] = counts.get(version, 0) + 1

    for version in sorted(counts):
        print(f"{version}: {counts[version]} valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
