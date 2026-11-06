#!/usr/bin/env python3
"""Validate the source and coverage structure of the execution placement matrix.

This read-only check verifies citations, required responsibility dimensions and
qualification cases. A valid matrix remains source-mapped, not runtime-qualified.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


DEFAULT_MATRIX = Path(__file__).resolve().parents[1] / "docs" / "plans" / "agentops" / "execution-placement-matrix.json"
OFFICIAL_HOSTS = {
    "platform.claude.com", "developers.openai.com", "openai.github.io", "help.openai.com",
}
CLAIM_FIELDS = (
    "model_location", "tool_execution_location", "environment_custodian",
    "context_egress", "tool_surface", "provider_identity", "retry_and_completion",
    "cancellation_and_interruption", "usage_and_cost", "effect_authority",
)
REQUIRED_SCENARIOS = {
    "duplicate-event", "missing-child-evidence", "failed-child", "late-result-after-replacement",
}
REQUIRED_OWNER_FIELDS = {
    "work_item_ref", "attempt_id", "artifact_revision_or_digest",
    "current_owner_revision", "owner_acceptance_ref", "effect_receipt_ref_when_applicable",
}


class PlacementMatrixError(ValueError):
    """The matrix is incomplete, invalid or cites an unrecognized source."""


def _need(condition: bool, message: str) -> None:
    if not condition:
        raise PlacementMatrixError(message)


def _text(value: Any, field: str) -> str:
    _need(isinstance(value, str) and bool(value.strip()), f"{field} must be a non-empty string")
    return value


def _string_list(value: Any, field: str, *, nonempty: bool = True) -> list[str]:
    _need(isinstance(value, list), f"{field} must be an array")
    _need(not nonempty or bool(value), f"{field} must not be empty")
    _need(all(isinstance(item, str) and bool(item.strip()) for item in value),
          f"{field} must contain non-empty strings")
    return value


def _date(value: Any, field: str) -> date:
    _need(isinstance(value, str), f"{field} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise PlacementMatrixError(f"{field} must be an ISO date") from exc


def validate(document: Any, *, repository_root: Path | None = None) -> dict[str, Any]:
    """Return a structural report; never upgrades source review to qualification."""
    if repository_root is None:
        repository_root = Path(__file__).resolve().parents[1]
    _need(isinstance(document, dict), "matrix root must be an object")
    _need(document.get("schema_version") == "agentops-execution-placement-matrix/v1",
          "unsupported schema_version")
    _need(document.get("qualification_status") == "source-mapped-not-qualified",
          "qualification_status must remain source-mapped-not-qualified")
    reviewed_at = _date(document.get("reviewed_at"), "reviewed_at")

    raw_sources = document.get("sources")
    _need(isinstance(raw_sources, list) and bool(raw_sources), "sources must be a non-empty array")
    sources: dict[str, dict[str, Any]] = {}
    for index, source in enumerate(raw_sources):
        field = f"sources[{index}]"
        _need(isinstance(source, dict), f"{field} must be an object")
        source_id = _text(source.get("id"), f"{field}.id")
        _need(source_id not in sources, f"duplicate source id: {source_id}")
        _text(source.get("title"), f"{field}.title")
        source_date = _date(source.get("reviewed_at"), f"{field}.reviewed_at")
        _need(source_date <= reviewed_at, f"{field}.reviewed_at follows matrix review date")
        kind = source.get("kind")
        if kind == "official_docs":
            url = _text(source.get("url"), f"{field}.url")
            parts = urlsplit(url)
            _need(parts.scheme == "https" and parts.hostname is not None,
                  f"{field}.url must use HTTPS")
            _need(any(parts.hostname == host or parts.hostname.endswith("." + host)
                      for host in OFFICIAL_HOSTS),
                  f"{field}.url is outside the approved official documentation hosts")
        elif kind == "repository_doc":
            path = _text(source.get("path"), f"{field}.path")
            _need(not Path(path).is_absolute() and ".." not in Path(path).parts,
                  f"{field}.path must remain inside the repository")
            _need((repository_root / path).is_file(), f"{field}.path does not exist: {path}")
        else:
            raise PlacementMatrixError(f"{field}.kind must be official_docs or repository_doc")
        sources[source_id] = source

    owner_fields = set(_string_list(document.get("required_owner_identity"), "required_owner_identity"))
    _need(REQUIRED_OWNER_FIELDS <= owner_fields,
          "required_owner_identity is missing an owner/work/attempt/effect binding")

    raw_placements = document.get("placements")
    _need(isinstance(raw_placements, list) and len(raw_placements) >= 2,
          "placements must contain at least two integrations")
    placement_ids: set[str] = set()
    for index, placement in enumerate(raw_placements):
        field = f"placements[{index}]"
        _need(isinstance(placement, dict), f"{field} must be an object")
        extra = set(placement) - {"id", "product", "environment_variant", "unknowns", *CLAIM_FIELDS}
        _need(not extra, f"{field} has unrecognized fields (qualification or run claims are not allowed): "
                         f"{', '.join(sorted(extra))}")
        placement_id = _text(placement.get("id"), f"{field}.id")
        _need(placement_id not in placement_ids, f"duplicate placement id: {placement_id}")
        placement_ids.add(placement_id)
        _text(placement.get("product"), f"{field}.product")
        _text(placement.get("environment_variant"), f"{field}.environment_variant")
        unknowns = _string_list(placement.get("unknowns"), f"{field}.unknowns")
        _need(bool(unknowns), f"{field}.unknowns must state remaining qualification unknowns")
        for claim_name in CLAIM_FIELDS:
            claim = placement.get(claim_name)
            _need(isinstance(claim, dict), f"{field}.{claim_name} must be an object")
            _text(claim.get("claim"), f"{field}.{claim_name}.claim")
            refs = _string_list(claim.get("source_refs"), f"{field}.{claim_name}.source_refs")
            _need(set(refs) <= set(sources), f"{field}.{claim_name} has unknown source refs")
        provider_ids = _string_list(placement["provider_identity"].get("ids"),
                                    f"{field}.provider_identity.ids")
        _need(len(provider_ids) == len(set(provider_ids)), f"{field}.provider_identity.ids has duplicates")

    raw_scenarios = document.get("qualification_scenarios")
    _need(isinstance(raw_scenarios, list), "qualification_scenarios must be an array")
    scenario_ids: set[str] = set()
    for index, scenario in enumerate(raw_scenarios):
        field = f"qualification_scenarios[{index}]"
        _need(isinstance(scenario, dict), f"{field} must be an object")
        scenario_id = _text(scenario.get("id"), f"{field}.id")
        _need(scenario_id not in scenario_ids, f"duplicate qualification scenario: {scenario_id}")
        scenario_ids.add(scenario_id)
        _need(scenario.get("status") == "not-run", f"{field}.status must remain not-run until owner evidence exists")
        _text(scenario.get("scenario"), f"{field}.scenario")
        _text(scenario.get("required_owner_invariant"), f"{field}.required_owner_invariant")
        refs = _string_list(scenario.get("source_refs"), f"{field}.source_refs")
        _need(set(refs) <= set(sources), f"{field} has unknown source refs")
    _need(REQUIRED_SCENARIOS <= scenario_ids,
          "qualification_scenarios must include duplicate, missing evidence, failed child and late result")

    limitations = _string_list(document.get("limitations"), "limitations")
    _need(bool(limitations), "limitations must explicitly bound qualification claims")
    return {
        "schema_version": document["schema_version"],
        "valid": True,
        "qualification_status": document["qualification_status"],
        "reviewed_at": document["reviewed_at"],
        "source_count": len(sources),
        "placement_count": len(placement_ids),
        "required_scenario_count": len(REQUIRED_SCENARIOS),
        "scenarios_run": 0,
        "limitations": limitations,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("matrix", nargs="?", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--json", action="store_true", help="print the validation report as JSON")
    args = parser.parse_args(argv)
    try:
        document = json.loads(args.matrix.read_text())
        report = validate(document)
    except (OSError, json.JSONDecodeError, PlacementMatrixError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"valid source map: {report['placement_count']} placements, "
              f"{report['source_count']} refs; qualification={report['qualification_status']}; "
              f"scenarios_run={report['scenarios_run']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
