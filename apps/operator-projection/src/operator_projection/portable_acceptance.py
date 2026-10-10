"""Fixed, redacted presentation of P1; no owner reads or acceptance decisions."""

from __future__ import annotations

import json
import re
from datetime import datetime

from . import reconstruction as p1

SCHEMA = "operator-acceptance-presentation/v1"
ID = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
UTC_TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|\+00:00)\Z")
STATES = frozenset({"proposed", "accepted", "rejected", "applied"})
SOURCE_MODES = frozenset({"live-owner-reads", "supplied-capture"})
LINK_STATES = frozenset({"observed", "missing", "conflict"})
OWNER_INT_MAX = 2**31 - 1  # work_effect_intent.revision: PostgreSQL integer
OWNER_BIGINT_MAX = 2**63 - 1  # work_effect_intent.work_item_id: PostgreSQL bigint


def _refuse() -> None:
    raise p1.ReconstructionError("unsupported acceptance presentation input")


def _id(value: object) -> str:
    if type(value) is not str or not ID.fullmatch(value):
        _refuse()
    return value


def _positive(value: object, ceiling: int) -> int:
    if type(value) is not int or not 1 <= value <= ceiling:
        _refuse()
    return value


def _hex(value: object, pattern: re.Pattern[str]) -> str:
    if type(value) is not str or not pattern.fullmatch(value):
        _refuse()
    return value


def _time(value: object) -> str | None:
    if value is None:
        return None
    if type(value) is not str or not UTC_TIME.fullmatch(value):
        _refuse()
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _refuse()
    return value.replace("+00:00", "Z")


def _facts(key: str, value: object, intent_id: str) -> dict:
    if type(value) is not dict:
        _refuse()
    if key == "intent":
        if (value.get("intent_id") != intent_id or type(value.get("state")) is not str
                or value["state"] not in STATES):
            _refuse()
        return {"intent_id": intent_id, "revision": _positive(value.get("revision"), OWNER_INT_MAX),
                "item_id": _positive(value.get("item_id"), OWNER_BIGINT_MAX), "state": value["state"]}
    if key == "work_release":
        return {"release_digest": _hex(value.get("release_digest"), p1.HEX)}
    if key == "release_intent_binding":
        if value.get("intent_id") != intent_id:
            _refuse()
        _positive(value.get("intent_revision"), OWNER_INT_MAX)
        return {"release_digest": _hex(value.get("release_digest"), p1.HEX)}
    if key == "attempts_and_claims":
        return {"scope": "owner item history; exact intent attempt join not established"}
    if key == "artifact":
        if value.get("domain") != "sprintctl-effect-intent/v1":
            _refuse()
        return {"canonical_intent_digest": _hex(value.get("digest"), p1.HEX),
                "base_commit": _hex(value.get("base_commit"), p1.COMMIT)}
    if key == "verification_evidence":
        return {"evidence_digest": _hex(value.get("evidence_digest"), p1.SHA),
                "assurance": "owner-frozen assertion; execution not independently attested"}
    if key == "acceptance":
        if value.get("intent_id") != intent_id:
            _refuse()
        return {"intent_revision": _positive(value.get("intent_revision"), OWNER_INT_MAX),
                "canonical_intent_digest": _hex(value.get("canonical_intent_digest"), p1.HEX),
                "accepting_identity": "unknown", "acceptor_policy_revision": "unknown"}
    if key == "effect_receipt":
        return {"commit_sha": _hex(value.get("commit_sha"), p1.COMMIT)}
    _refuse()


def present(report: dict) -> dict:
    """Copy only safe P1 facts; a report itself cannot authenticate its origin."""
    if (type(report) is not dict or report.get("schema") != p1.SCHEMA
            or report.get("derived") is not True or report.get("authorizes_effects") is not False
            or type(report.get("source_mode")) is not str or report["source_mode"] not in SOURCE_MODES
            or type(report.get("status")) is not str or report["status"] not in {"complete", "incomplete", "conflict"}
            or type(report.get("links")) is not dict or set(report["links"]) != set(p1.LINKS)
            or type(report.get("sources")) is not list or len(report["sources"]) > len(p1.READ_OPS)):
        _refuse()
    repo_id, intent_id = _id(report.get("repo_id")), _id(report.get("intent_id"))
    links = {}
    for key in p1.LINKS:
        row = report["links"][key]
        if (type(row) is not dict or type(row.get("status")) is not str
                or row["status"] not in LINK_STATES):
            _refuse()
        links[key] = {"status": row["status"]}
        if row["status"] == "observed":
            links[key]["facts"] = _facts(key, row.get("value"), intent_id)
    missing = [key for key in p1.LINKS if links[key]["status"] == "missing"]
    conflict = any(row["status"] == "conflict" for row in links.values())
    status = "conflict" if conflict else "incomplete" if missing else "complete"
    if report.get("missing") != missing or report["status"] != status:
        _refuse()
    intent = links["intent"].get("facts")
    acceptance = links["acceptance"].get("facts")
    artifact = links["artifact"].get("facts")
    release = links["work_release"].get("facts")
    binding = links["release_intent_binding"].get("facts")
    if (intent and acceptance and intent["revision"] != acceptance["intent_revision"]
            or artifact and acceptance and artifact["canonical_intent_digest"] != acceptance["canonical_intent_digest"]
            or release and binding and release["release_digest"] != binding["release_digest"]
            or intent and binding and
            report["links"]["release_intent_binding"]["value"]["intent_revision"] != intent["revision"]):
        _refuse()
    sources, seen = [], set()
    for row in report["sources"]:
        if (type(row) is not dict or type(row.get("operation")) is not str
                or row["operation"] not in p1.READ_OPS or row["operation"] in seen
                or type(row.get("status")) is not str
                or row["status"] not in {"observed", "unavailable"}):
            _refuse()
        seen.add(row["operation"])
        sources.append({"operation": row["operation"], "status": row["status"],
                        "observed_at": _time(row.get("observed_at"))})
    return {"schema": SCHEMA, "source_schema": p1.SCHEMA, "derived": True,
            "authorizes_effects": False, "repo_id": repo_id, "intent_id": intent_id,
            "status": status, "status_scope": "p1-link-consistency",
            "provenance": {"reported_source_mode": report["source_mode"],
            "owner_authentication": "unknown", "owner_currentness": "unknown",
            "current_authorization": "unknown"},
            "links": links, "missing": missing, "sources": sources}


def render_text(report: dict) -> str:
    """Render only the freshly redacted DTO, never P1's raw link values."""
    dto = present(report)
    lines = [f"P1 LINK EXPLANATION {dto['intent_id']} · {dto['status']}",
             f"Repository: {dto['repo_id']}",
             "Status covers P1 link consistency, not a terminal acceptance outcome.",
             "Owner authentication, currentness and caller authorization: unknown"]
    for key in p1.LINKS:
        row = dto["links"][key]
        facts = " · " + json.dumps(row["facts"], sort_keys=True) if row["status"] == "observed" else ""
        lines.append(f"{key}: {row['status']}{facts}")
    lines.append("Missing links: " + (", ".join(dto["missing"]) if dto["missing"] else "none"))
    lines.append("Derived reading only; authorizes no effect.")
    return "\n".join(lines) + "\n"
