"""Read-only, partial reconstruction over the published Sprintctl owner reads.

This is a reading surface, never an acceptance evaluator. Missing owner links
remain missing even when an intent has an acceptance and an application row.
Offline captures are supplied observations, not authenticated owner responses.
"""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime, timezone

SCHEMA = "operator-reconstruction/v1"
CAPTURE_SCHEMA = "operator-reconstruction-capture/v1"
EFFECT = "work.effect.get-v1"
RELEASE = "work.read.release"
DECISIONS = "work.read.item-decisions"
LEASES = "work.lease.read-v1"
READ_OPS = frozenset({EFFECT, RELEASE, DECISIONS, LEASES})
LINKS = ("intent", "work_release", "release_intent_binding", "attempts_and_claims",
         "artifact", "verification_evidence", "acceptance", "effect_receipt")
CONTENT = ("item_id", "repository", "base_commit", "title", "rationale", "unified_diff")
HEX = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")


class ReconstructionError(ValueError):
    pass


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise ReconstructionError("capture is outside the JSON domain") from error


def intent_digest(intent):
    """The frozen sprintctl-effect-intent/v1 digest domain; not a Git commit hash."""
    body = {"schema": "sprintctl-effect-intent/v1", **{k: intent[k] for k in CONTENT}}
    return hashlib.sha256(canonical(body)).hexdigest()


def _text(value):
    return type(value) is str and bool(value.strip())


def _positive(value):
    return type(value) is int and value > 0


def collect(authority, repo_id, intent_id):
    """Only the four explicit read operations can cross the authority boundary."""
    capture = {"schema": CAPTURE_SCHEMA, "repo_id": repo_id, "intent_id": intent_id,
               "source_mode": "live-owner-reads", "catalog_revision": None, "results": {}}
    try:
        catalog = authority.catalog()
        capture["catalog_revision"] = catalog.get("catalog_revision", catalog.get("revision"))
    except Exception:
        capture["results"][EFFECT] = {"status": "unavailable", "reason": "catalog read unavailable"}
        return capture

    def read(operation, arguments):
        observed_at = datetime.now(timezone.utc).isoformat()
        try:
            value = authority.read(operation, arguments, repo_id)
        except Exception:
            # Transport exceptions can contain credential-bearing URLs or bodies.
            result = {"status": "unavailable", "reason": "owner read refused or unavailable"}
        else:
            result = {"status": "observed", "value": value}
        capture["results"][operation] = {**result, "arguments": arguments, "observed_at": observed_at}
        return result.get("value")

    value = read(EFFECT, {"intent_id": intent_id})
    intent = value.get("intent") if type(value) is dict else None
    if type(intent) is dict and _positive(intent.get("item_id")):
        for operation in (RELEASE, DECISIONS, LEASES):
            read(operation, {"item_id": intent["item_id"]})
    return capture


def reconstruct(capture, *, live=False):
    """Derive a bounded report; never infer a missing release, verifier or receipt."""
    if (type(capture) is not dict or capture.get("schema") != CAPTURE_SCHEMA
            or not _text(capture.get("repo_id")) or not _text(capture.get("intent_id"))
            or type(capture.get("results")) is not dict
            or set(capture["results"]) - READ_OPS):
        raise ReconstructionError("unsupported reconstruction capture")
    canonical(capture)
    report = {"schema": SCHEMA, "derived": True, "authorizes_effects": False,
              "repo_id": capture["repo_id"], "intent_id": capture["intent_id"],
              "source_mode": "live-owner-reads" if live else "supplied-capture",
              "catalog_revision": capture.get("catalog_revision"),
              "links": {key: {"status": "missing", "reason": "owner link not supplied"} for key in LINKS},
              "sources": [], "conflicts": []}
    links = report["links"]

    def observed(key, value, operation):
        links[key] = {"status": "observed", "value": deepcopy(value), "operation": operation}

    def conflict(key, reason):
        links[key] = {"status": "conflict", "reason": reason}
        report["conflicts"].append({"link": key, "reason": reason})

    def result(operation, item_id=None):
        entry = capture["results"].get(operation)
        if entry is None:
            return None
        if type(entry) is not dict or entry.get("status") not in {"observed", "unavailable"}:
            raise ReconstructionError("malformed capture result")
        report["sources"].append({"operation": operation, "status": entry["status"],
                                  "observed_at": entry.get("observed_at"),
                                  "result_digest": hashlib.sha256(canonical(entry.get("value"))).hexdigest()
                                  if entry["status"] == "observed" else None})
        if entry["status"] == "unavailable":
            return None
        value = entry.get("value")
        if type(value) is not dict or value.get("repo_id") != capture["repo_id"]:
            raise ReconstructionError("owner response repository mismatch")
        args = entry.get("arguments", {})
        expected = {"intent_id": capture["intent_id"]} if operation == EFFECT else {"item_id": item_id}
        if args != expected:
            raise ReconstructionError("capture arguments do not match the requested result")
        return value

    effect = result(EFFECT)
    intent = effect.get("intent") if effect else None
    if effect is not None and type(intent) is not dict:
        raise ReconstructionError("malformed owner intent")
    if intent is not None:
        if (type(intent) is not dict or intent.get("intent_id") != capture["intent_id"]
                or not _positive(intent.get("item_id")) or not _positive(intent.get("revision"))
                or intent.get("state") not in {"proposed", "accepted", "rejected", "applied"}
                or not _text(intent.get("run_id"))
                or any(not _text(intent.get(k)) for k in CONTENT if k != "item_id")
                or not COMMIT.fullmatch(str(intent.get("base_commit", "")))
                or not HEX.fullmatch(str(intent.get("canonical_intent_digest", "")))):
            raise ReconstructionError("malformed owner intent")
        digest = intent_digest(intent)
        observed("intent", {k: intent[k] for k in ("intent_id", "revision", "item_id", "run_id", "repository", "state")}, EFFECT)
        if digest != intent["canonical_intent_digest"]:
            conflict("artifact", "intent content differs from its recorded canonical digest")
        else:
            observed("artifact", {"digest": digest, "domain": "sprintctl-effect-intent/v1",
                                  "unified_diff_sha256": hashlib.sha256(intent["unified_diff"].encode()).hexdigest(),
                                  "base_commit": intent["base_commit"],
                                  "scope": "proposed intent content; resulting repository bytes not verified"}, EFFECT)
        acceptance = intent.get("acceptance")
        if acceptance is not None:
            if (type(acceptance) is not dict or acceptance.get("intent_id") != intent["intent_id"]
                    or acceptance.get("intent_revision") != intent["revision"]
                    or not _positive(acceptance.get("intent_revision"))
                    or acceptance.get("canonical_intent_digest") != digest
                    or digest != intent["canonical_intent_digest"]
                    or not _text(acceptance.get("acceptor_principal"))
                    or not _text(acceptance.get("accepted_at"))
                    or intent["state"] not in {"accepted", "applied"}):
                conflict("acceptance", "acceptance does not bind this exact intent revision and content")
            else:
                observed("acceptance", {k: acceptance.get(k) for k in
                                        ("intent_id", "intent_revision", "canonical_intent_digest", "acceptor_principal", "acceptor_policy_version", "accepted_at")}, EFFECT)
        receipt = intent.get("application")
        if receipt is not None:
            if (type(receipt) is not dict or intent["state"] != "applied"
                    or links["acceptance"]["status"] != "observed"
                    or not _text(receipt.get("applier_principal"))
                    or not _text(receipt.get("applied_at"))
                    or not COMMIT.fullmatch(str(receipt.get("commit_sha", "")))):
                conflict("effect_receipt", "application receipt lacks a matching accepted intent")
            else:
                observed("effect_receipt", {k: receipt.get(k) for k in
                                            ("applier_principal", "commit_sha", "pr_url", "applied_at")}, EFFECT)
        item_id = intent["item_id"]
        release_result = result(RELEASE, item_id)
        if release_result is not None:
            release = release_result.get("release")
            if (type(release) is not dict or release.get("work_item_id") != item_id
                    or not HEX.fullmatch(str(release.get("release_digest", "")))
                    or not _text(release.get("item_revision"))):
                raise ReconstructionError("release response item or revision mismatch")
            observed("work_release", {k: release.get(k) for k in
                                      ("release_digest", "item_revision", "acceptance_contract", "created_at")}, RELEASE)
        links["release_intent_binding"]["reason"] = "effect owner does not record a work-release digest; association by item ID is insufficient"
        decisions = result(DECISIONS, item_id)
        if decisions is not None:
            if decisions.get("item_id") != item_id or type(decisions.get("decisions")) is not list:
                raise ReconstructionError("decision response item mismatch")
            links["verification_evidence"] = {"status": "missing",
                "reason": "work Decision references do not establish verification of this effect artifact",
                "work_decision_ids": [d.get("id") for d in decisions["decisions"] if type(d) is dict]}
        leases = result(LEASES, item_id)
        if leases is not None:
            if leases.get("item_id") != item_id or type(leases.get("leases")) is not list or type(leases.get("outcome_reports")) is not list:
                raise ReconstructionError("lease response item or histories mismatch")
            observed("attempts_and_claims", {"scope": "owner item history; not every attempt is this intent's run",
                "intent_run_id": intent["run_id"], **{k: leases.get(k) for k in
                ("current_lease", "leases", "outcome_reports", "verification", "evaluated_at")}}, LEASES)
    report["missing"] = [key for key in LINKS if links[key]["status"] == "missing"]
    report["status"] = "conflict" if report["conflicts"] else "incomplete" if report["missing"] else "complete"
    report["assurance"] = ("observed owner responses" if any(s["status"] == "observed" for s in report["sources"])
                           else "live read attempted; owner responses unavailable") if live else "supplied capture; owner provenance not authenticated"
    return report


def render_text(report):
    lines = [f"RECONSTRUCTION {report['intent_id']} · {report['status']}", report["assurance"]]
    for key in LINKS:
        link = report["links"][key]
        value = json.dumps(link.get("value"), sort_keys=True, ensure_ascii=False) if link["status"] == "observed" else link["reason"]
        lines.append(f"{key}: {link['status']} · {value}")
    lines.append("Derived read; authorizes no effect.")
    return "\n".join(lines) + "\n"
