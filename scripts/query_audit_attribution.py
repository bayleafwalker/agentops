#!/usr/bin/env python3
"""Read-only, digest-bound attribution over explicitly supplied audit snapshots.

Attribution is a derived observation, never producer identity or authorization.
An overlay cannot edit an event or follow aliases. Paths are supplied locally;
reviewed public overlays need not reveal paths or protected provenance witnesses.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import sys


class AttributionError(ValueError):
    pass


_HEX = re.compile(r"^[0-9a-f]{64}$")
_TOKEN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AttributionError("duplicate JSON field")
        result[key] = value
    return result


def _finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise AttributionError("non-finite JSON number")
    return number


def _json(raw: bytes):
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_object, parse_float=_finite_float,
                          parse_constant=lambda _: (_ for _ in ()).throw(AttributionError("non-JSON number")))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise AttributionError("invalid JSON input") from error


def _fields(value, required, optional=()):
    if type(value) is not dict or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        raise AttributionError("invalid or unknown manifest fields")


def _token(value):
    if type(value) is not str or not _TOKEN.fullmatch(value):
        raise AttributionError("invalid manifest token")


def _positive(value):
    if type(value) is not int or value < 1:
        raise AttributionError("manifest counts must be positive integers")


def overlay_digest(value: dict) -> str:
    body = {key: item for key, item in value.items() if key != "digest"}
    try:
        encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                             allow_nan=False).encode("utf-8")
    except (ValueError, UnicodeError, RecursionError) as error:
        raise AttributionError("overlay is outside the supported JSON domain") from error
    return hashlib.sha256(encoded).hexdigest()


def load_overlay(path: Path) -> dict:
    try:
        overlay = _json(path.read_bytes())
    except OSError as error:
        raise AttributionError("overlay cannot be read") from error
    _fields(overlay, {"schema_version", "scope", "digest", "sources", "entries"})
    if overlay["schema_version"] != "audit-attribution-overlay/v1" or type(overlay["scope"]) is not str or overlay["scope"] not in {"committed-only", "protected-tail"}:
        raise AttributionError("unsupported attribution overlay")
    if type(overlay["digest"]) is not str or overlay["digest"] != "sha256:" + overlay_digest(overlay):
        raise AttributionError("overlay digest mismatch")
    if type(overlay["sources"]) is not list or not overlay["sources"] or type(overlay["entries"]) is not list:
        raise AttributionError("overlay collections must be arrays")
    sources = {}
    for source in overlay["sources"]:
        if type(source) is not dict:
            raise AttributionError("source must be an object")
        for field in ("byte_count", "line_count", "start_line"):
            _positive(source.get(field))
        common = {"source_id", "source_repo_id", "kind", "byte_count", "line_count", "sha256", "start_line"}
        if source.get("kind") == "committed-shard":
            _fields(source, common | {"commit", "blob_id"})
            if overlay["scope"] != "committed-only" or source["start_line"] != 1:
                raise AttributionError("committed overlay cannot select a tail")
            if any(type(source[field]) is not str or not re.fullmatch(r"[0-9a-f]{40}", source[field]) for field in ("commit", "blob_id")):
                raise AttributionError("invalid recorded git provenance")
        elif source.get("kind") == "uncommitted-tail":
            _fields(source, common | {"prefix_source_id"})
            _token(source["prefix_source_id"])
            if overlay["scope"] != "protected-tail" or source["start_line"] <= 1:
                raise AttributionError("tail requires an explicit committed prefix")
        else:
            raise AttributionError("unsupported source kind")
        for field in ("source_id", "source_repo_id"):
            _token(source[field])
        for field in ("byte_count", "line_count", "start_line"):
            _positive(source[field])
        if source["start_line"] > source["line_count"] or type(source["sha256"]) is not str or not _HEX.fullmatch(source["sha256"]):
            raise AttributionError("invalid source byte binding")
        if source["source_id"] in sources:
            raise AttributionError("duplicate source identity")
        sources[source["source_id"]] = source
    seen = set()
    for entry in overlay["entries"]:
        _fields(entry, {"event_id", "source_id", "line", "raw_line_sha256", "attributed_repo_id"})
        for field in ("source_id", "attributed_repo_id"):
            _token(entry[field])
        _positive(entry["line"])
        if type(entry["event_id"]) is not str or not entry["event_id"] or len(entry["event_id"]) > 256:
            raise AttributionError("invalid event identity")
        if type(entry["raw_line_sha256"]) is not str or not _HEX.fullmatch(entry["raw_line_sha256"]):
            raise AttributionError("invalid event byte binding")
        source = sources.get(entry["source_id"])
        if source is None or not source["start_line"] <= entry["line"] <= source["line_count"]:
            raise AttributionError("mapping lies outside its bound source")
        if entry["event_id"] in seen:
            raise AttributionError("duplicate attribution identity")
        seen.add(entry["event_id"])
    return overlay


def query(overlays: list[dict], supplied: dict[str, list[Path]], *, include_events=False) -> dict:
    sources = {}; mappings = {}; scopes = []
    for overlay in overlays:
        scopes.append({"scope": overlay["scope"], "digest": overlay["digest"], "mapped_events": len(overlay["entries"])})
        for source in overlay["sources"]:
            if source["source_id"] in sources:
                raise AttributionError("source identity appears in multiple overlays")
            sources[source["source_id"]] = source
        for entry in overlay["entries"]:
            if entry["event_id"] in mappings:
                raise AttributionError("attribution identity appears in multiple overlays")
            mappings[entry["event_id"]] = entry
    if supplied.keys() != sources.keys():
        raise AttributionError("supply exactly the source identities declared by the overlays")
    snapshots = {}; extras = {}
    for identity, source in sources.items():
        paths = supplied[identity]
        if not paths:
            raise AttributionError("source has no supplied copy")
        for path in paths:
            try:
                with path.open("rb") as stream:
                    raw = stream.read(source["byte_count"])
                    extra = stream.read(1)
            except OSError as error:
                raise AttributionError("source copy cannot be read") from error
            if len(raw) != source["byte_count"] or hashlib.sha256(raw).hexdigest() != source["sha256"]:
                raise AttributionError("source copy differs from its frozen byte binding")
            if not raw.endswith(b"\n") or len(raw.splitlines()) != source["line_count"]:
                raise AttributionError("source line framing differs from its binding")
            snapshots[identity] = raw
            extras[identity] = extras.get(identity, False) or bool(extra)
    for identity, source in sources.items():
        if source["kind"] == "uncommitted-tail":
            prefix = sources.get(source["prefix_source_id"])
            if (prefix is None or prefix["kind"] != "committed-shard"
                    or prefix["source_repo_id"] != source["source_repo_id"]
                    or prefix["line_count"] + 1 != source["start_line"]
                    or not snapshots[identity].startswith(snapshots[source["prefix_source_id"]])):
                raise AttributionError("tail does not extend the supplied committed prefix")
    records = {}; found = set()
    copies = sum((len(supplied[identity]) - 1) * (source["line_count"] - source["start_line"] + 1)
                 for identity, source in sources.items())
    for identity, source in sources.items():
        for number, line in enumerate(snapshots[identity].splitlines(keepends=True), 1):
            if number < source["start_line"]:
                continue
            event = _json(line)
            if type(event) is not dict or type(event.get("id")) is not str or not event["id"]:
                raise AttributionError("source record has no stable identity")
            event_id = event["id"]
            raw_hash = hashlib.sha256(line).hexdigest()
            prior = records.get(event_id)
            if prior is not None and (prior["raw_line_sha256"] != raw_hash or prior["source_repo_id"] != source["source_repo_id"]):
                raise AttributionError("conflicting physical copies of one event identity")
            entry = mappings.get(event_id)
            if entry is not None:
                if entry["source_id"] == identity and entry["line"] == number:
                    if entry["raw_line_sha256"] != raw_hash:
                        raise AttributionError("mapped event bytes changed")
                    found.add(event_id)
                elif entry["source_id"] == identity:
                    raise AttributionError("mapped event moved within its source")
            if prior is not None:
                copies += 1
                continue
            records[event_id] = {"event_id": event_id, "source_repo_id": source["source_repo_id"],
                                 "attributed_repo_id": entry["attributed_repo_id"] if entry else source["source_repo_id"],
                                 "mapped": entry is not None, "raw_line_sha256": raw_hash,
                                 "original_event": event}
    if found != mappings.keys():
        raise AttributionError("one or more mapped identities are absent from their exact source positions")
    selected = [record for record in records.values() if record["mapped"]]
    result = {"schema_version": "audit-attribution-query/v1", "overlays": scopes,
              "coverage": "committed-and-explicit-protected-tail" if any(scope["scope"] == "protected-tail" for scope in scopes) else "committed-only",
              "verified_source_count": len(sources), "verified_copy_count": sum(map(len, supplied.values())), "unparsed_bytes_beyond_snapshots": extras,
              "unique_events": len(records), "duplicate_records": copies,
              "mapped_events": len(selected), "unmapped_events": len(records) - len(selected),
              "attributed_counts": dict(sorted(Counter(record["attributed_repo_id"] for record in selected).items()))}
    if include_events:
        result["events"] = sorted(records.values(), key=lambda record: record["event_id"])
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overlay", type=Path, action="append", required=True)
    parser.add_argument("--source", action="append", required=True, metavar="SOURCE_ID=PATH",
                        help="explicit local copy; repeat an identity to verify additional identical copies")
    parser.add_argument("--events", action="store_true", help="include unchanged original events; output may be sensitive")
    args = parser.parse_args(argv)
    try:
        supplied = {}
        for item in args.source:
            identity, separator, path = item.partition("=")
            if not separator or not path:
                raise AttributionError("source argument must be SOURCE_ID=PATH")
            _token(identity)
            supplied.setdefault(identity, []).append(Path(path))
        result = query([load_overlay(path) for path in args.overlay], supplied, include_events=args.events)
    except (AttributionError, ValueError) as error:
        print(json.dumps({"schema_version": "audit-attribution-query/v1", "status": "cannot-determine", "error": str(error)}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
