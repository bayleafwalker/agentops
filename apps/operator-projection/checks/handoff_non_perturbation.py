#!/usr/bin/env python3
"""One-time check (P1 checklist 12, run at 14): reading a handoff does not perturb the ledger it reads.

Run it once, with the generator identity only (work:read, work:project-read), never a write-capable profile:

    OPERATOR_PROJECTION_PROFILE=/etc/operator-projection/profile.yaml \
        python checks/handoff_non_perturbation.py --sprint-id <id>

It lists the sprint's events, invokes work.read.handoff once, and lists the events again. Every call passes the
read allowlist, checked against the catalog fetched in the same run. Exit 0: the event list is unchanged. Exit 1:
events were appended; they are printed so a concurrent writer can be told apart from the read. Exit 2: not runnable.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from operator_projection.sources import READ_OPS, Authority, ReadRefused, SourceUnavailable, open_authority  # noqa: E402

ALLOW = READ_OPS | {"work.read.events"}
PAGE = 500


def events(authority: Authority, sprint_id: int) -> list[dict]:
    listed: list[dict] = []
    while True:
        page = authority.read("work.read.events", {"sprint_id": sprint_id, "after_offset": len(listed), "limit": PAGE})["events"]
        listed += page
        if len(page) < PAGE:
            return listed


def check(authority: Authority, sprint_id: int) -> dict:
    authority.handshake()
    catalog = authority.catalog()
    before = events(authority, sprint_id)
    authority.read("work.read.handoff", {"sprint_id": sprint_id, "events_limit": 1})
    after = events(authority, sprint_id)
    return {
        "check": "handoff-non-perturbation",
        "sprint_id": sprint_id,
        "catalog_revision": catalog["revision"],
        "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "events_before": len(before),
        "events_after": len(after),
        "unchanged": before == after,
        "appended": after[len(before):] if after[:len(before)] == before else after,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sprint-id", type=int, required=True)
    parser.add_argument("--profile", default=os.environ.get("OPERATOR_PROJECTION_PROFILE"))
    args = parser.parse_args(argv)
    if not args.profile or not Path(args.profile).is_file():
        print("not runnable: set OPERATOR_PROJECTION_PROFILE to the generator profile", file=sys.stderr)
        return 2
    authority = open_authority(yaml.safe_load(Path(args.profile).read_text()), allow=ALLOW)
    if not authority.has_credential():
        print("not runnable: the generator credential is absent (needs work:read, work:project-read)", file=sys.stderr)
        return 2
    try:
        result = check(authority, args.sprint_id)
    except (ReadRefused, SourceUnavailable) as error:
        print(f"not runnable: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=1))
    return 0 if result["unchanged"] else 1


if __name__ == "__main__":
    sys.exit(main())
