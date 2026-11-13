#!/usr/bin/env python3
"""Read-only observations of obligations when the operator is absent.

Inventory and receipts are private inputs. This command neither renews credentials
nor repairs services, and a successful command is not a healthy-estate verdict.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
from typing import Any, Callable


SCENARIO = "operator_absent_automation_continues"
KINDS = {"expiry", "renewal", "retention", "drill", "manual_action", "prerequisite"}
STATES = {"available", "blocked", "unknown"}
RECEIPT_FIELDS = {
    "subject_id", "observed_at", "evidence_ref", "basis", "state", "reason",
    "due_at", "last_success_at", "latest_recovery_point_at", "timer_state",
}
ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
MAX_JSON_BYTES = 1_000_000


class InvalidInput(ValueError):
    """Invalid inputs cannot establish an observation."""


def timestamp(value: str) -> datetime:
    if not isinstance(value, str):
        raise InvalidInput("timestamp must be an RFC3339 string with an offset")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise InvalidInput("invalid timestamp") from error
    if result.tzinfo is None or result.utcoffset() is None:
        raise InvalidInput("timestamp needs an explicit offset")
    return result.astimezone(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def read_json(path: Path) -> Any:
    if path.stat().st_size > MAX_JSON_BYTES:
        raise InvalidInput("JSON input exceeds the size limit")
    return json.loads(path.read_text(encoding="utf-8"))


def text_field(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 2048:
        raise InvalidInput(f"{name} must be a nonempty bounded string")
    return value


def fields(value: Any, allowed: set[str], name: str) -> None:
    if not isinstance(value, dict) or set(value) - allowed:
        raise InvalidInput(f"unexpected fields in {name}")


def validate_inventory(inventory: Any) -> dict:
    fields(inventory, {"schema_version", "inventory_id", "scenario", "source_revisions", "obligations"}, "inventory")
    if inventory.get("schema_version") != 1 or inventory.get("scenario") != SCENARIO:
        raise InvalidInput("unsupported inventory schema or scenario")
    text_field(inventory.get("inventory_id"), "inventory_id")
    revisions = inventory.get("source_revisions")
    if not isinstance(revisions, dict) or not revisions:
        raise InvalidInput("source_revisions must identify the inspected source revisions")
    for repo, revision in revisions.items():
        text_field(repo, "repository")
        if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", revision):
            raise InvalidInput("source revision must be an immutable digest")
    obligations = inventory.get("obligations")
    if not isinstance(obligations, list) or not 1 <= len(obligations) <= 1000:
        raise InvalidInput("inventory needs 1 to 1000 obligations")
    identifiers: set[str] = set()
    for item in obligations:
        fields(item, {"id", "kind", "source_ref", "max_age_seconds", "probe", "due", "renewer_id", "prerequisites", "recovery_path", "retention_seconds"}, "obligation")
        identifier = item.get("id")
        if not isinstance(identifier, str) or not ID_PATTERN.fullmatch(identifier) or identifier in identifiers:
            raise InvalidInput("obligation IDs must be unique, bounded identifiers")
        identifiers.add(identifier)
        if item.get("kind") not in KINDS:
            raise InvalidInput("unsupported obligation kind")
        text_field(item.get("source_ref"), "source_ref")
        age = item.get("max_age_seconds")
        if type(age) is not int or not 1 <= age <= 366 * 86400:
            raise InvalidInput("max_age_seconds must be explicit and within one year")
        probe = item.get("probe")
        if not isinstance(probe, dict):
            raise InvalidInput("probe is required, including for unknown observations")
        kind = probe.get("kind")
        if kind == "none":
            fields(probe, {"kind"}, "none probe")
        elif kind in {"receipt", "certificate"}:
            allowed = {"kind", "path"} | ({"collect_on"} if kind == "certificate" else set())
            fields(probe, allowed, "file probe")
            text_field(probe.get("path"), "probe path")
        elif kind == "systemd_timer":
            fields(probe, {"kind", "unit", "service", "scope", "collect_on"}, "timer probe")
            for key, suffix in (("unit", "timer"), ("service", "service")):
                if key == "service" and key not in probe:
                    continue
                if not isinstance(probe.get(key), str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.@:-]*\." + suffix, probe[key]):
                    raise InvalidInput("timer and service must be literal systemd unit names")
            if probe.get("scope") not in {"user", "system"}:
                raise InvalidInput("systemd scope must be user or system")
        else:
            raise InvalidInput("unsupported probe; arbitrary commands are not accepted")
        if kind in {"certificate", "systemd_timer"}:
            text_field(probe.get("collect_on"), "collect_on hostname")
        if "due" in item:
            due = item["due"]
            fields(due, {"at", "basis", "evidence_ref"}, "declared deadline")
            timestamp(due.get("at"))
            if due.get("basis") != "configured":
                raise InvalidInput("inventory dates are configured, not runtime observations")
            text_field(due.get("evidence_ref"), "deadline evidence_ref")
        if "retention_seconds" in item:
            if item["kind"] != "retention" or type(item["retention_seconds"]) is not int or item["retention_seconds"] <= 0:
                raise InvalidInput("retention_seconds requires a positive retention policy")
        for key in ("prerequisites", "recovery_path"):
            edges = item.get(key, [])
            if not isinstance(edges, list) or len(edges) > 1000:
                raise InvalidInput("dependency edges must be a bounded list")
            for edge in edges:
                fields(edge, {"id", "basis", "evidence_ref"}, "dependency edge")
                text_field(edge.get("id"), "dependency ID")
                if edge.get("basis") not in {"source", "observed", "unknown"}:
                    raise InvalidInput("dependency basis must be source, observed or unknown")
                if edge.get("evidence_ref") is not None:
                    text_field(edge["evidence_ref"], "dependency evidence_ref")
    for item in obligations:
        references = [edge["id"] for key in ("prerequisites", "recovery_path") for edge in item.get(key, [])]
        if item.get("renewer_id"):
            references.append(item["renewer_id"])
        if any(reference not in identifiers for reference in references):
            raise InvalidInput("every dependency needs an inventory entry, including unknown prerequisites")
    return inventory


def validate_receipt(receipt: Any, subject_id: str) -> dict:
    fields(receipt, RECEIPT_FIELDS, "receipt")
    if receipt.get("subject_id") != subject_id:
        raise InvalidInput("receipt subject does not match its inventory entry")
    if receipt.get("state") not in STATES or receipt.get("basis") not in {"runtime", "source"}:
        raise InvalidInput("invalid receipt state or basis")
    for field in ("observed_at", "due_at", "last_success_at", "latest_recovery_point_at"):
        value = receipt.get(field)
        if value is not None:
            timestamp(value)
    if receipt.get("state") != "unknown" and receipt.get("observed_at") is None:
        raise InvalidInput("an available or blocked observation needs a date")
    text_field(receipt.get("evidence_ref"), "receipt evidence_ref")
    for key in ("reason", "timer_state"):
        if receipt.get(key) is not None:
            text_field(receipt[key], key)
    return dict(receipt)


def resolve_input(path: str, base: Path) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate
    resolved = (base / candidate).resolve()
    if not resolved.is_relative_to(base.resolve()):
        raise InvalidInput("relative input path escapes the inventory directory")
    return resolved


def unknown(item: dict, now: datetime, reason: str) -> dict:
    return {
        "subject_id": item["id"], "observed_at": iso(now), "basis": "runtime",
        "evidence_ref": item["source_ref"], "state": "unknown", "reason": reason,
    }


def run_read_only(argv: list[str], runner: Callable = subprocess.run) -> subprocess.CompletedProcess:
    environment = dict(os.environ)
    environment.update(LC_ALL="C", TZ="UTC")
    environment.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    environment.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={environment['XDG_RUNTIME_DIR']}/bus")
    return runner(argv, capture_output=True, text=True, timeout=15, check=False, env=environment)


def parse_systemd_date(value: str) -> str | None:
    for form in ("%a %Y-%m-%d %H:%M:%S UTC", "%a %Y-%m-%d %H:%M:%S.%f UTC"):
        try:
            return iso(datetime.strptime(value, form).replace(tzinfo=timezone.utc))
        except ValueError:
            pass
    return None


def collect_one(item: dict, base: Path, now: datetime, host: str, runner: Callable) -> dict:
    probe = item["probe"]
    kind = probe["kind"]
    if kind == "none":
        result = unknown(item, now, "no_runtime_observation")
        result.update(observed_at=None, basis="source")
        return result
    if kind in {"certificate", "systemd_timer"} and probe["collect_on"] != host:
        return unknown(item, now, "wrong_collection_host")
    try:
        if kind == "receipt":
            receipt = validate_receipt(read_json(resolve_input(probe["path"], base)), item["id"])
            return receipt
        if kind == "certificate":
            path = resolve_input(probe["path"], base)
            response = run_read_only(["openssl", "x509", "-in", str(path), "-noout", "-enddate"], runner)
            if response.returncode != 0 or not response.stdout.strip().startswith("notAfter="):
                return unknown(item, now, "certificate_probe_failed")
            # Only the selected public field is retained. No PEM, subject, key,
            # stderr, or arbitrary receipt fields are copied to the snapshot.
            expiry = datetime.strptime(response.stdout.strip()[9:], "%b %d %H:%M:%S %Y GMT").replace(tzinfo=timezone.utc)
            return {
                "subject_id": item["id"], "observed_at": iso(now), "basis": "runtime",
                "evidence_ref": f"local-certificate:{host}:{item['id']}",
                "state": "available" if expiry > now else "blocked",
                "reason": "certificate_not_expired" if expiry > now else "certificate_expired",
                "due_at": iso(expiry),
            }
        prefix = ["systemctl"] + (["--user"] if probe["scope"] == "user" else [])
        response = run_read_only(prefix + ["show", probe["unit"], "-p", "LoadState", "-p", "ActiveState", "-p", "UnitFileState"], runner)
        properties = dict(line.split("=", 1) for line in response.stdout.splitlines() if "=" in line)
        if response.returncode != 0 or not properties.get("LoadState"):
            return unknown(item, now, "timer_probe_failed")
        state = "available" if properties.get("LoadState") == "loaded" and properties.get("ActiveState") == "active" else "blocked"
        reason = "timer_active" if state == "available" else "timer_inactive"
        if properties["LoadState"] == "not-found":
            roots = [Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "systemd/user"] if probe["scope"] == "user" else [Path("/etc/systemd/system"), Path("/usr/lib/systemd/system")]
            present = any((root / probe["unit"]).exists() or (root / probe["unit"]).is_symlink() for root in roots)
            reason = "timer_present_not_loaded" if present else "timer_not_installed"
        receipt = {
            "subject_id": item["id"], "observed_at": iso(now), "basis": "runtime",
            "evidence_ref": f"local-systemd:{host}:{item['id']}", "state": state,
            "reason": reason, "timer_state": properties.get("ActiveState", "unknown"),
        }
        if "service" in probe:
            service = run_read_only(prefix + ["show", probe["service"], "-p", "Result", "-p", "ExecMainStatus", "-p", "ExecMainExitTimestamp"], runner)
            values = dict(line.split("=", 1) for line in service.stdout.splitlines() if "=" in line)
            if service.returncode == 0 and values.get("Result") == "success" and values.get("ExecMainStatus") == "0":
                success = parse_systemd_date(values.get("ExecMainExitTimestamp", ""))
                if success is not None:
                    receipt["last_success_at"] = success
        return receipt
    except (OSError, ValueError, subprocess.SubprocessError):
        return unknown(item, now, "probe_failed")


def collect(inventory: dict, base: Path, now: datetime, host: str | None = None, runner: Callable = subprocess.run) -> dict:
    validate_inventory(inventory)
    actual_host = host if host is not None else socket.gethostname()
    return {
        "schema_version": 1, "inventory_id": inventory["inventory_id"],
        "inventory_digest": digest(inventory), "collected_at": iso(now),
        "collector_host": actual_host, "collector_digest": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "observations": [collect_one(item, base, now, actual_host, runner) for item in inventory["obligations"]],
    }


def normalise(item: dict, receipt: dict | None, at: datetime) -> dict:
    result = {"state": "unknown", "reason": "missing_receipt", "observed_at": None, "evidence_ref": None, "basis": "unknown"}
    if receipt is None:
        return result
    result.update(receipt)
    result["reason"] = receipt.get("reason", f"observed_{receipt['state']}")
    observed = timestamp(receipt["observed_at"]) if receipt.get("observed_at") else None
    if observed is None:
        result.update(state="unknown", reason="undated_receipt")
    elif observed > at:
        result.update(state="unknown", reason="future_receipt")
    elif (at - observed).total_seconds() > item["max_age_seconds"]:
        result.update(state="unknown", reason="stale_receipt")
    elif receipt["basis"] != "runtime":
        result.update(state="unknown", reason="source_only_evidence")
    elif receipt["state"] == "available" and item["kind"] == "renewal":
        success = timestamp(receipt["last_success_at"]) if receipt.get("last_success_at") else None
        if success is None:
            result.update(state="unknown", reason="renewal_success_unknown")
        elif success > observed:
            result.update(state="unknown", reason="future_renewal_success")
        elif (at - success).total_seconds() > item["max_age_seconds"]:
            result.update(state="unknown", reason="renewal_success_stale")
    for field in ("last_success_at", "latest_recovery_point_at"):
        if observed and receipt.get(field) and timestamp(receipt[field]) > observed:
            result.update(state="unknown", reason="future_receipt_fact")
    if result["state"] == "available" and item["kind"] == "expiry" and receipt.get("due_at") and timestamp(receipt["due_at"]) <= at:
        result.update(state="blocked", reason="expiry_reached_at_cutoff")
    return result


def evaluate(inventory: dict, snapshot: dict, at: datetime) -> dict:
    validate_inventory(inventory)
    fields(snapshot, {"schema_version", "inventory_id", "inventory_digest", "collected_at", "collector_host", "collector_digest", "observations"}, "observation snapshot")
    if snapshot.get("schema_version") != 1 or snapshot.get("inventory_id") != inventory["inventory_id"] or snapshot.get("inventory_digest") != digest(inventory):
        raise InvalidInput("snapshot is not bound to this inventory revision")
    timestamp(snapshot.get("collected_at"))
    items = {item["id"]: item for item in inventory["obligations"]}
    receipts = snapshot.get("observations")
    if not isinstance(receipts, list):
        raise InvalidInput("snapshot observations must be a list")
    indexed: dict[str, dict] = {}
    for receipt in receipts:
        if not isinstance(receipt, dict) or receipt.get("subject_id") not in items or receipt["subject_id"] in indexed:
            raise InvalidInput("receipt subjects must be unique inventory members")
        identifier = receipt["subject_id"]
        indexed[identifier] = validate_receipt(receipt, identifier)
    evidence = {identifier: normalise(item, indexed.get(identifier), at) for identifier, item in items.items()}

    def walk_edges(edges: list[dict], trail: list[str], edge_trace: list[dict] | None = None) -> dict:
        edge_trace = list(edge_trace or [])
        if len(trail) > 64:
            return {"status": "unknown", "path": trail, "edges": edge_trace, "first_unresolved_prerequisite": trail[-1], "reason": "dependency_depth_limit"}
        checked: list[str] = []
        for edge in edges:
            identifier = edge["id"]
            path = trail + [identifier]
            trace = edge_trace + [{"from": trail[-1], "to": identifier, "basis": edge["basis"], "evidence_ref": edge.get("evidence_ref")}]
            if edge.get("basis") == "unknown" or not edge.get("evidence_ref"):
                return {"status": "unknown", "path": path, "edges": trace, "first_unresolved_prerequisite": identifier, "reason": "dependency_evidence_missing"}
            if identifier in trail:
                return {"status": "cycle", "path": path, "edges": trace, "first_unresolved_prerequisite": identifier, "reason": "cycle_in_evidenced_dependency_declarations", "runtime_deadlock_proven": False}
            observation = evidence[identifier]
            if observation["state"] != "available":
                return {"status": observation["state"], "path": path, "edges": trace, "first_unresolved_prerequisite": identifier, "reason": observation["reason"]}
            nested = walk_edges(items[identifier].get("prerequisites", []), path, trace)
            if nested["status"] != "available":
                return nested
            checked.extend([identifier] + nested.get("checked", []))
            edge_trace.extend(nested.get("edges", [])[len(edge_trace):])
        return {"status": "available", "checked": checked, "edges": edge_trace, "first_unresolved_prerequisite": None}

    rows: list[dict] = []
    conditional_limits: list[dict] = []
    for identifier, item in items.items():
        observation = evidence[identifier]
        due_at = None
        due_basis = "unknown"
        due_evidence = None
        if observation["state"] != "unknown" and observation.get("due_at"):
            due_at, due_basis, due_evidence = iso(timestamp(observation["due_at"])), "observed", observation["evidence_ref"]
        elif observation["state"] != "unknown" and item["kind"] == "retention" and observation.get("latest_recovery_point_at") and item.get("retention_seconds"):
            due_at = iso(timestamp(observation["latest_recovery_point_at"]) + timedelta(seconds=item["retention_seconds"]))
            due_basis, due_evidence = "derived", observation["evidence_ref"]
        elif item.get("due"):
            due_at, due_basis, due_evidence = iso(timestamp(item["due"]["at"])), "configured", item["due"]["evidence_ref"]
        recovery = walk_edges(item["recovery_path"], [identifier]) if item.get("recovery_path") else {"status": "not_declared", "first_unresolved_prerequisite": None}
        prerequisites = walk_edges(item.get("prerequisites", []), [identifier])
        renewal = {"status": "not_declared", "first_unresolved_prerequisite": None}
        if item.get("renewer_id"):
            renewal = walk_edges([{"id": item["renewer_id"], "basis": "source", "evidence_ref": item["source_ref"]}], [identifier])
        deadline_type = {"drill": "proof_obligation", "manual_action": "policy_deadline", "expiry": "expiry_boundary", "retention": "retention_boundary"}.get(item["kind"], "none")
        if deadline_type in {"expiry_boundary", "retention_boundary"} and due_basis in {"observed", "derived"} and renewal["status"] != "available":
            conditional_limits.append({
                "subject_id": identifier, "at": due_at, "kind": item["kind"],
                "condition": "no newer usable recovery point before this boundary and configured retention remains in effect" if item["kind"] == "retention" else "no successful renewal or replacement before this boundary",
                "renewal_evidence": renewal["status"], "outage_prediction": False,
            })
        rows.append({
            "id": identifier, "kind": item["kind"], "source_ref": item["source_ref"],
            "observation": observation, "due_at": due_at, "due_basis": due_basis,
            "due_evidence_ref": due_evidence, "deadline_type": deadline_type,
            "overdue": timestamp(due_at) <= at if due_at else None,
            "prerequisites": prerequisites, "renewal": renewal, "recovery": recovery,
        })
    unknown_ids = [identifier for identifier, value in evidence.items() if value["state"] == "unknown"]
    conditional_limits.sort(key=lambda limit: (timestamp(limit["at"]), limit["subject_id"]))
    return {
        "schema_version": 1, "inventory_id": inventory["inventory_id"], "scenario": SCENARIO,
        "evaluated_at": iso(at), "inventory_digest": digest(inventory), "observations_digest": digest(snapshot),
        "source_revisions": inventory["source_revisions"],
        "coverage": {"expected": len(items), "observed": len(items) - len(unknown_ids), "unknown": len(unknown_ids), "unknown_ids": unknown_ids},
        "status": "incomplete" if unknown_ids else "observed",
        "first_failure": {"status": "unknown", "at": None, "reason": "incomplete_observation_coverage" if unknown_ids else "future_automation_outcomes_are_not_predictions"},
        "earliest_known_conditional_limit": conditional_limits[0] if conditional_limits else None,
        "conditional_limits": conditional_limits, "obligations": rows,
    }


def markdown(report: dict) -> str:
    def cell(value: Any) -> str:
        return str(value if value is not None else "unknown").replace("|", "\\|").replace("\n", " ")
    coverage = report["coverage"]
    lines = [
        "# Neglect ledger", "", f"Evaluated: {report['evaluated_at']}", "",
        "Scenario: operator absent; existing automation continues.", "",
        f"Coverage: {coverage['observed']}/{coverage['expected']} observed; {coverage['unknown']} unknown.", "",
        "First failure: unknown. Expiry boundaries and overdue proofs are not outage predictions.", "",
        "| Obligation | Evidence state | Deadline | Deadline meaning | Renewal | First unresolved recovery prerequisite |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in report["obligations"]:
        lines.append("| " + " | ".join(cell(value) for value in [row["id"], row["observation"]["state"] + ": " + row["observation"]["reason"], row["due_at"], row["deadline_type"] + " / " + row["due_basis"], row["renewal"]["status"], row["recovery"].get("first_unresolved_prerequisite")]) + " |")
    lines.extend(["", "## Earliest known conditional limit", ""])
    limit = report["earliest_known_conditional_limit"]
    if limit:
        lines.append(f"{limit['subject_id']} at {limit['at']}, conditional on {limit['condition']}.")
    else:
        lines.append("No conditional limit is established by this snapshot.")
    lines.extend(["", "The canonical JSON retains observation dates, evidence references, missing coverage, dependency paths, and source revisions.", ""])
    return "\n".join(lines)


def write_private(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=".neglect-ledger-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("collect", "evaluate"):
        child = commands.add_parser(command)
        child.add_argument("--inventory", type=Path, required=True)
        child.add_argument("--output", type=Path, required=True)
        if command == "evaluate":
            child.add_argument("--observations", type=Path, required=True)
            child.add_argument("--at", help="RFC3339 evaluation cutoff; defaults to now")
            child.add_argument("--markdown", type=Path)
            child.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    try:
        inventory = validate_inventory(read_json(args.inventory))
        inputs = {args.inventory.resolve()}
        for item in inventory["obligations"]:
            if "path" in item["probe"]:
                inputs.add(resolve_input(item["probe"]["path"], args.inventory.resolve().parent).resolve())
        if args.command == "evaluate":
            inputs.add(args.observations.resolve())
        outputs = [args.output] + ([args.markdown] if getattr(args, "markdown", None) else [])
        if any(path.resolve() in inputs for path in outputs) or len({path.resolve() for path in outputs}) != len(outputs):
            raise InvalidInput("outputs must not replace inputs or each other")
        now = datetime.now(timezone.utc)
        if args.command == "collect":
            result = collect(inventory, args.inventory.resolve().parent, now)
        else:
            result = evaluate(inventory, read_json(args.observations), timestamp(args.at) if args.at else now)
        write_private(args.output, json.dumps(result, indent=2, sort_keys=True) + "\n")
        if args.command == "evaluate" and args.markdown:
            write_private(args.markdown, markdown(result))
        if args.command == "evaluate" and args.require_complete and result["coverage"]["unknown"]:
            return 2
        return 0
    except (OSError, ValueError) as error:
        parser.exit(1, f"neglect-ledger: {type(error).__name__}: invalid input or inaccessible output\n")


if __name__ == "__main__":
    raise SystemExit(main())
