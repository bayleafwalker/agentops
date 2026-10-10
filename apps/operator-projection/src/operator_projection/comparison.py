"""Derived cross-attempt comparison over P1 captures; Sprintctl alone settles.

Capture ordering supplies no currentness authority. Different shared owner reads
are exposed as changed sources, never resolved by timestamp, winner or status.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

from . import reconstruction as p1

SCHEMA = "operator-attempt-comparison/v1"


def _digest(value):
    return hashlib.sha256(p1.canonical(value)).hexdigest()


def _candidate(capture):
    report = p1.reconstruct(capture)
    links = report["links"]
    intent = links["intent"].get("value", {})
    release = links["work_release"].get("value", {})
    binding = {"repo_id": report["repo_id"], "repository": intent.get("repository"),
               "item_id": intent.get("item_id"), "release_digest": release.get("release_digest")}
    sources = []
    for source in report["sources"]:
        entry = capture["results"][source["operation"]]
        value = entry.get("value", {})
        # Preserve explicit owner revisions independently of derived result hashes.
        revisions = {key: value[key] for key in ("revision", "source_revision", "evaluated_at") if key in value}
        if source["operation"] == p1.RELEASE and isinstance(value.get("release"), dict):
            revisions.update({key: value["release"][key] for key in ("item_revision", "release_digest") if key in value["release"]})
        if source["operation"] == p1.EFFECT and isinstance(value.get("intent"), dict):
            revisions["intent_revision"] = value["intent"].get("revision")
        sources.append({**source, "owner_revisions": deepcopy(revisions),
                        "owner_revision_known": bool(revisions)})
    stale = [{"link": key, "reason": links[key]["reason"],
              "scope": "binding inconsistent within this supplied capture; no terminal inference"}
             for key in ("artifact", "release_intent_binding", "acceptance", "verification_evidence")
             if links[key]["status"] == "conflict"]
    return {"capture_sha256": _digest(capture), "binding": binding,
            "intent_id": report["intent_id"], "run_id": intent.get("run_id"),
            "catalog_revision": report["catalog_revision"], "sources": sources,
            "links": deepcopy(links), "missing": list(report["missing"]),
            "conflicts": deepcopy(report["conflicts"]), "stale_markers": stale,
            "reconstruction_status": report["status"],
            "freshness": {"status": "unknown", "reason": "supplied captures establish no authenticated current owner read"}}


def compare(left_capture, right_capture):
    """Compare two exact-scope captures without network access or input mutation.

Missing scope links remain unknown; known mismatches refuse the whole report.
Shared source differences remain unordered, even with different observed times.
"""
    left, right = _candidate(left_capture), _candidate(right_capture)
    missing = []
    for key in ("repo_id", "repository", "item_id", "release_digest"):
        a, b = left["binding"][key], right["binding"][key]
        if a is None or b is None:
            missing.append(key)
        elif a != b:
            raise p1.ReconstructionError("comparison " + key + " binding mismatch")
    a_sources = {s["operation"]: s for s in left["sources"]}
    b_sources = {s["operation"]: s for s in right["sources"]}
    changed = []
    # EFFECT is deliberately attempt-specific. Compare shared owner item reads.
    for operation in sorted(p1.READ_OPS - {p1.EFFECT}):
        a, b = a_sources.get(operation), b_sources.get(operation)
        if a is None or b is None or a["status"] != "observed" or b["status"] != "observed":
            changed.append({"operation": operation, "status": "unknown", "reason": "shared owner source missing or unavailable"})
        elif a["result_digest"] != b["result_digest"]:
            changed.append({"operation": operation, "status": "changed",
                            "left_result_digest": a["result_digest"], "right_result_digest": b["result_digest"],
                            "reason": "shared owner snapshots differ; neither is established as current"})
    return {"schema": SCHEMA, "derived": True, "authorizes_effects": False,
            "settlement_owner": "Sprintctl", "settlement_inferred": False,
            "binding_status": "partial" if missing else "exact", "missing_bindings": missing,
            "binding": {k: left["binding"][k] if k not in missing else None for k in left["binding"]},
            "same_recorded_attempt": left["intent_id"] == right["intent_id"] and left["run_id"] == right["run_id"],
            "candidates": {"left": left, "right": right}, "changed_sources": changed,
            "assurance": "supplied P1 captures; provenance and current authorization not authenticated"}


def render_text(report):
    lines = ["ATTEMPT COMPARISON · " + report["binding_status"], report["assurance"]]
    for side in ("left", "right"):
        c = report["candidates"][side]
        lines.append(f"{side}: {c['intent_id']} · run {c['run_id']} · capture {c['capture_sha256']}")
        lines.append(f"  freshness: unknown · missing: {', '.join(c['missing']) or 'none'}")
        for key in p1.LINKS:
            link = c['links'][key]
            detail = json.dumps(link['value'], sort_keys=True, ensure_ascii=False) if link['status'] == 'observed' else link['reason']
            lines.append(f"  {key}: {link['status']} · {detail}")
        for marker in c["stale_markers"]:
            lines.append(f"  stale/conflict {marker['link']}: {marker['reason']}")
        for source in c["sources"]:
            lines.append(f"  source {source['operation']}: {source['status']} · result {source['result_digest']} · owner revisions {source['owner_revisions']}")
    for source in report["changed_sources"]:
        lines.append(f"shared source {source['operation']}: {source['status']} · {source['reason']}")
    lines.append("Derived read; Sprintctl alone settles. Authorizes no effect.")
    return "\n".join(lines) + "\n"
