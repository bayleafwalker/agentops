"""Bounded portable P1 bytes; offline integrity grants no owner authority."""
import hashlib
import json

from . import reconstruction as p1

SCHEMA = "operator-reconstruction-bundle/v1"
LIMIT = 4 * 1024 * 1024
CAPTURE_LIMIT = 512 * 1024
ARTIFACT_LIMIT = 256 * 1024
REPORT_LIMIT = 1024 * 1024
DOMAINS = {"capture": "utf8-p1-capture/v1", "artifact": "utf8-unified-diff/v1",
           "report": "canonical-operator-reconstruction/v1"}


class BundleError(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise BundleError(reason)


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON field")
        result[key] = value
    return result


def nonfinite(value):
    raise BundleError("nonfinite JSON number")


def utf8(blob, limit):
    require(type(blob) is bytes and len(blob) <= limit, "byte input exceeds bound")
    try:
        return blob.decode("utf-8")
    except UnicodeError as error:
        raise BundleError("input is not strict UTF-8") from error


def parse(blob, limit=LIMIT):
    text = utf8(blob, limit)
    try:
        value = json.loads(text, object_pairs_hook=unique, parse_constant=nonfinite)
        # Bound structure as well as bytes; no unbounded recursive P1 report.
        pending = [(value, 0)]
        count = 0
        while pending:
            child, depth = pending.pop()
            count += 1
            require(depth <= 64 and count <= 100_000, "JSON structure exceeds bound")
            if type(child) is dict:
                pending.extend((x, depth + 1) for x in child.values())
            elif type(child) is list:
                pending.extend((x, depth + 1) for x in child)
        p1.canonical(value)  # Also refuse escaped Unicode surrogates.
        return value
    except (ValueError, TypeError, RecursionError, UnicodeError) as error:
        raise BundleError("invalid bounded JSON") from error


def entry(name, blob):
    return {"domain": DOMAINS[name], "bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}


def parts(capture_blob, artifact_blob):
    capture = parse(capture_blob, CAPTURE_LIMIT)
    artifact = utf8(artifact_blob, ARTIFACT_LIMIT)
    report = p1.reconstruct(capture)  # Always supplied mode; no live credential/transport.
    effect = capture["results"].get(p1.EFFECT, {})
    value = effect.get("value")
    require(type(value) is dict, "P1 artifact bytes missing")
    intent = value.get("intent")
    require(type(intent) is dict and type(intent.get("unified_diff")) is str,
            "P1 artifact bytes missing")
    require(artifact_blob == intent["unified_diff"].encode("utf-8"), "artifact bytes differ from P1 capture")
    report_blob = p1.canonical(report)
    require(len(report_blob) <= REPORT_LIMIT, "derived report exceeds bound")
    manifest = {name: entry(name, blob) for name, blob in
                (("capture", capture_blob), ("artifact", artifact_blob), ("report", report_blob))}
    return artifact, report, manifest


def export(capture_blob, artifact_blob):
    artifact, report, manifest = parts(capture_blob, artifact_blob)
    envelope = {"schema": SCHEMA, "manifest": manifest,
                "capture_utf8": utf8(capture_blob, CAPTURE_LIMIT),
                "artifact_utf8": artifact, "report": report}
    blob = p1.canonical(envelope)
    require(len(blob) + 1 <= LIMIT, "bundle exceeds bound")
    return blob


def verify(blob):
    envelope = parse(blob)
    require(type(envelope) is dict and set(envelope) == {
        "schema", "manifest", "capture_utf8", "artifact_utf8", "report"}, "unsupported bundle fields")
    require(envelope["schema"] == SCHEMA, "unsupported bundle schema")
    require(type(envelope["capture_utf8"]) is str and type(envelope["artifact_utf8"]) is str,
            "missing UTF-8 byte carriers")
    manifest = envelope["manifest"]
    require(type(manifest) is dict and set(manifest) == set(DOMAINS), "unsupported manifest entries")
    for name, value in manifest.items():
        require(type(value) is dict and set(value) == {"domain", "bytes", "sha256"}, "unsupported manifest fields")
        require(value["domain"] == DOMAINS[name] and type(value["bytes"]) is int and value["bytes"] >= 0
                and type(value["sha256"]) is str and p1.HEX.fullmatch(value["sha256"]), "malformed manifest entry")
    capture_blob = envelope["capture_utf8"].encode("utf-8")
    artifact_blob = envelope["artifact_utf8"].encode("utf-8")
    report_blob = p1.canonical(envelope["report"])
    require(len(report_blob) <= REPORT_LIMIT, "report exceeds bound")
    for name, data in (("capture", capture_blob), ("artifact", artifact_blob), ("report", report_blob)):
        require(manifest[name] == entry(name, data), "manifest byte integrity failure")
    _, report, expected = parts(capture_blob, artifact_blob)
    require(manifest == expected and envelope["report"] == report, "derived P1 report differs from capture")
    return {"schema": "operator-bundle-verification/v1", "integrity": "verified-local-bytes",
            "owner_authority": "UNKNOWN", "owner_currentness": "UNKNOWN", "history_completeness": "UNKNOWN",
            "owner_provenance": "unauthenticated supplied capture", "authorizes_effects": False,
            "p1_consistency": report["status"], "missing": report["missing"], "conflicts": report["conflicts"],
            "reconstruction": report}
