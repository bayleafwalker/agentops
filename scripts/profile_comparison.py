#!/usr/bin/env python3
"""Compare observed profiles using a derived, read-only query (TS-3/TS-7).

Digest definition: SHA-256 of canonical JSON (sorted keys, no whitespace) of
{root, sources: [{path, sha256}] in recorded order, skills: [{name, path,
sha256}] sorted by name}. Unresolved skills retain null path and sha256.
Timing (loaded_at) and resolution labels are excluded. No profile is compiled.

Reuse cost_per_release's done-tick -> lane-note -> item join. Each item/tick
uses its latest lane.review inside that tick's window: first-pass requires
both first-pass and verdict:accepted; other reviewed attempts are reworked.
Missing reviews are counted as no_review, not inferred to be reworked.
first_pass_rate divides by reviewed attempts (items minus no_review).
Counts are item attempts, not globally deduplicated items; sessions are unique
within each profile. Missing bindings are counted separately, never invented.
No cache, settlement record, schema change or write is involved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

# Importing the existing join must not create a local bytecode artifact.
if __name__ == "__main__":
    sys.dont_write_bytecode = True
from cost_per_release import (  # noqa: E402
    DEFAULT_BINDINGS_DIR, DEFAULT_LEDGER,
    apportion_tick, lane_notes, lane_note_records, load_done_ticks, load_events, tick_window,
)

DIGEST_DEFINITION = ("SHA-256 of canonical JSON (sorted keys, no whitespace) of "
    "{root, sources: [{path, sha256}] in recorded order, skills: [{name, path, sha256}] "
    "sorted by name (ties by path then sha256)}; unresolved entries keep null path/sha256; "
    "loaded_at and resolution are excluded")


def observed_profile(binding: dict) -> dict:
    instructions = binding["instructions"]
    return {
        "root": instructions["root"],
        "sources": [
            {"path": source["path"], "sha256": source["sha256"]}
            for source in instructions["sources"]
        ],
        "skills": sorted(
            [{"name": skill["name"], "path": skill["path"], "sha256": skill["sha256"]}
             for skill in instructions["skills"]],
            key=lambda skill: (skill["name"], skill["path"] or "", skill["sha256"] or ""),
        ),
    }


def observed_profile_digest(binding: dict) -> str:
    encoded = json.dumps(observed_profile(binding), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def build_report(ticks: list[dict], events: list[dict], bindings_dir: Path) -> dict:
    notes = lane_notes(events)
    reviews = []
    for index, note in enumerate(lane_note_records(events)):
        if note["event_type"] == "lane.review":
            order = note["event_id"] if isinstance(note["event_id"], int) else index
            reviews.append((note["ts"], order, note["item_id"], note["tags"]))

    groups = {}
    missing = set()
    bindings = {}
    for tick in ticks:
        session = tick["session_id"]
        if not isinstance(session, str) or not session or Path(session).name != session or "\\" in session:
            raise ValueError("session_id must be a binding filename, not a path")
        if session not in bindings:
            path = bindings_dir / (session + ".json")
            bindings[session] = json.loads(path.read_text()) if path.is_file() else None
        binding = bindings[session]
        if binding is None:
            missing.add(session)
            continue
        if binding.get("runtime_session_id") != session:
            raise ValueError("binding runtime_session_id does not match its ledger session")
        profile = observed_profile(binding)
        digest = observed_profile_digest(binding)
        group = groups.setdefault(digest, {
            "digest": digest[:12], "root": profile["root"],
            "n_sources": len(profile["sources"]), "n_skills": len(profile["skills"]),
            "sessions": set(), "items": 0, "first_pass": 0, "accepted": 0, "no_review": 0,
        })
        group["sessions"].add(session)
        window = tick_window(tick)
        if window is None:
            raise ValueError("done tick has no valid timestamp")
        start, end = window
        for item in apportion_tick(tick, notes):
            eligible = [review for review in reviews
                        if review[2] == item["item_id"] and start <= review[0] <= end]
            tags = max(eligible, key=lambda review: review[:2])[3] if eligible else []
            group["items"] += 1
            group["no_review"] += not bool(eligible)
            group["first_pass"] += "first-pass" in tags and "verdict:accepted" in tags
            group["accepted"] += "verdict:accepted" in tags
    rows = []
    for digest, group in sorted(groups.items()):
        group["sessions"] = len(group["sessions"])
        reviewed = group["items"] - group["no_review"]
        group["reworked"] = reviewed - group["accepted"]
        group["first_pass_rate"] = group["first_pass"] / reviewed if reviewed else None
        rows.append(group)
    return {"rows": rows, "no_binding": len(missing), "done_ticks": len(ticks),
            "digest_definition": DIGEST_DEFINITION}


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare observed profiles using a read-only derived query.")
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--bindings-dir", type=Path, default=DEFAULT_BINDINGS_DIR)
    parser.add_argument("--events-json", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        if not args.ledger.is_file():
            raise ValueError("ledger does not exist: " + str(args.ledger))
        report = build_report(load_done_ticks(args.ledger), load_events(args.events_json), args.bindings_dir)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print("profile comparison failed: " + str(error), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        columns = ("digest", "root", "n_sources", "n_skills", "sessions", "items",
                   "first_pass", "accepted", "reworked", "no_review", "first_pass_rate")
        print("\t".join(columns))
        for row in report["rows"]:
            print("\t".join(str(row[column]) for column in columns))
        print("no_binding=" + str(report["no_binding"]))
        print("done_ticks=" + str(report["done_ticks"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
