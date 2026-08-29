#!/usr/bin/env python3
"""Recover one repository's dispatch cycle from the substrate's own record.

Plan §10.5 asks for the consumer proof, and is explicit that the way to get it is not
to ask a consumer what worked. So this reads what the substrate durably recorded --
the repository's audit stream, and the receipts its accepted attempts cite -- and emits
an acceptance-lab candidate output for the `dispatch-cycle` scenario to score.

A cycle is one unit of work across all of its attempts. Attempts are numbered `-rN` on
the task id, so `ERM-005-redaction-idempotency-r2` and `-r3` are two attempts at one
cycle; grouping by the stem is what makes a refusal and the acceptance that followed it
parts of the same story rather than two unrelated events.

Reusable means: nothing here knows what the consumer builds. Gate names, file paths,
languages and toolchains travel as data inside the candidate, never as conditions. If
this file ever needs a branch per consumer, the seam did not generalise -- which is the
question the scenario exists to answer, so the answer must be allowed to be no.

Usage:
    dispatch_cycle_probe.py --repo bindery-core --out candidate.json
    dispatch_cycle_probe.py --repo bindery-core --list
    dispatch_cycle_probe.py --repo bindery-core --cycle ERM-005-redaction-idempotency
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

ARTIFACTS_ROOT = Path("/projects/dev/_artifacts")
REPO_ROOT = Path("/projects/dev")
ATTEMPT_SUFFIX = re.compile(r"-r\d+$")

REFUSAL_TYPES = ("dispatch.packet.rejected", "dispatch.preflight_rejected")
REVIEW_TYPES = ("dispatch.packet.reviewed", "dispatch.candidate.review", "dispatch.reviewed")
ACCEPT_TYPES = ("dispatch.packet.accepted", "coordinator.work.completed")

# The trajectory names the ARM, not the event type. Two spellings of a refusal --
# refused at preflight, refused after a contained attempt but before it mutated
# anything -- are the same arm of the same cycle, and a scenario that had to enumerate
# every spelling would be pinned to one substrate's vocabulary. Naming the arm is what
# lets the same scenario read a consumer whose events are spelled differently; the
# concrete type travels in the step's action and in the metadata, where it is evidence
# rather than a condition.
ARMS = (("cycle.refused", REFUSAL_TYPES), ("cycle.reviewed", REVIEW_TYPES),
        ("cycle.accepted", ACCEPT_TYPES))


def arm_of(event_type: str) -> str | None:
    for arm, types in ARMS:
        if event_type in types:
            return arm
    return None


def load_events(repo: str, artifacts_root: Path) -> list[dict[str, Any]]:
    directory = artifacts_root / repo / "audit"
    if not directory.is_dir():
        raise SystemExit(f"no audit stream for {repo}: {directory} does not exist")
    events: list[dict[str, Any]] = []
    for shard in sorted(directory.glob("events-*.ndjson")):
        for line in shard.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    events.sort(key=lambda event: (event.get("created_at") or "", event.get("origin_seq") or 0))
    return events


def cycle_key(task_id: str) -> str:
    return ATTEMPT_SUFFIX.sub("", task_id)


def group_cycles(events: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    cycles: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        task_id = (event.get("metadata") or {}).get("task_id")
        if isinstance(task_id, str) and task_id:
            cycles.setdefault(cycle_key(task_id), []).append(event)
    return cycles


def is_complete(events: list[dict[str, Any]]) -> bool:
    """A cycle is complete when it shows all three arms.

    Acceptance alone is not a cycle. A loop that has never refused anything has not
    shown it can, and the refusal is the arm that says the gate is load-bearing.
    """
    types = {event["type"] for event in events}
    return bool(
        types & set(REFUSAL_TYPES) and types & set(REVIEW_TYPES) and types & set(ACCEPT_TYPES)
    )


def smallest_complete(cycles: dict[str, list[dict[str, Any]]]) -> str | None:
    """The smallest complete cycle: fewest events that still show every arm.

    "Smallest" is the point of the extraction. A large cycle proves the same thing with
    more noise, and the noise is where consumer-specific detail hides.
    """
    complete = {key: value for key, value in cycles.items() if is_complete(value)}
    if not complete:
        return None
    return min(complete, key=lambda key: (len(complete[key]), key))


def _receipt_path(events: list[dict[str, Any]], repo: str, repo_root: Path) -> Path | None:
    for event in events:
        reference = (event.get("metadata") or {}).get("receipt")
        if isinstance(reference, str) and reference:
            candidate = repo_root / repo / reference
            if candidate.is_file():
                return candidate
    return None


def build_candidate(repo: str, key: str, events: list[dict[str, Any]], repo_root: Path) -> dict[str, Any]:
    facts: list[str] = []
    supports: dict[str, list[str]] = {}
    trajectory: list[dict[str, Any]] = []

    def claim(fact: str, source: str) -> None:
        facts.append(fact)
        supports.setdefault(source, []).append(fact)

    refusals = [event for event in events if event["type"] in REFUSAL_TYPES]
    reviews = [event for event in events if event["type"] in REVIEW_TYPES]
    accepts = [event for event in events if event["type"] in ACCEPT_TYPES]

    for seq, event in enumerate(events, start=1):
        metadata = event.get("metadata") or {}
        arm = arm_of(event["type"])
        if arm is None:
            continue
        step: dict[str, Any] = {
            "seq": len(trajectory) + 1,
            "tool": arm,
            "action": f"{event['type']} — {metadata.get('task_id', key)}: "
                      f"{event.get('summary', '')}"[:300],
        }
        # The merge is the effect this cycle had on the world, and the commit it landed
        # as is its receipt. Nothing else here changes anything outside the record.
        commit = metadata.get("implementation_commit") or metadata.get("commit")
        if event["type"] in ACCEPT_TYPES and commit:
            step.update(effect=True, effect_id=f"merge-{metadata.get('task_id', key)}",
                        receipt=f"commit:{commit}")
        trajectory.append(step)

    if refusals:
        first = refusals[0]
        claim("cycle: an attempt was refused", first["id"])
        metadata = first.get("metadata") or {}
        # Two different spellings for the same substantive fact: a packet refused before
        # the worker ran at all, and a contained attempt refused before it mutated
        # anything. Both mean the refusal was free.
        if metadata.get("no_mutation") is True or metadata.get("worker_started") is False:
            claim("refusal: no mutation was made", first["id"])
        refused_attempt = metadata.get("task_id", "")
        later = [
            event for event in reviews + accepts
            if (event.get("metadata") or {}).get("task_id", "") != refused_attempt
        ]
        if metadata.get("retry_required") is True or later:
            claim("refusal: a revised packet followed it", first["id"])

    if reviews:
        claim("cycle: a revised attempt was independently reviewed", reviews[-1]["id"])
        if (reviews[-1].get("metadata") or {}).get("reference_patch_semantic_match") is True:
            claim("review: the candidate matched the coordinator reference", reviews[-1]["id"])

    if accepts:
        last = accepts[-1]
        claim("cycle: an attempt was accepted and merged", last["id"])
        metadata = last.get("metadata") or {}
        if metadata.get("reservation_id") is not None:
            claim("cycle: the reservation it held was released", last["id"])

    # Containment is asserted by the receipt the acceptance cites, not by this probe
    # looking at a working tree. A probe that inspected the tree would be answering from
    # the present about a claim made in the past.
    metrics: dict[str, float] = {"attempts": float(len({
        (event.get("metadata") or {}).get("task_id") for event in events})),
        "cycle_events": float(len(events))}
    receipt_file = _receipt_path(events, repo, repo_root)
    receipt_facts: dict[str, Any] = {}
    if receipt_file is not None:
        receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
        source = f"receipt:{receipt_file.relative_to(repo_root / repo)}"
        worker = receipt.get("worker") or {}
        containment = receipt.get("containment") or {}
        if worker.get("protected_paths_untouched") is True:
            claim("containment: protected paths were untouched", source)
        if worker.get("coordinator_tree_untouched") is True or \
                containment.get("coordinator_tree_untouched") is True:
            claim("containment: the coordinator tree was untouched", source)
        spend = receipt.get("spend") or {}
        if spend.get("cost_reported") is True:
            metrics["cost_usd"] = float(spend.get("reported_cost_usd") or 0.0)
        if spend.get("reported_final_cumulative_tokens") is not None:
            metrics["tokens"] = float(spend["reported_final_cumulative_tokens"])
        receipt_facts = {
            "receipt": str(receipt_file.relative_to(repo_root / repo)),
            "gates": receipt.get("gates"),
            "harness": (receipt.get("harness") or {}).get("name"),
            "qualification": (receipt.get("qualification") or {}).get("state"),
        }

    citations = [
        {"id": source, "supports": sorted(set(claims))}
        for source, claims in sorted(supports.items())
    ]
    return {
        "schema_version": "acceptance-lab/candidate-output/v1",
        "answer": (
            f"{repo} cycle {key}: {len(refusals)} refusal(s), {len(reviews)} review(s), "
            f"{len(accepts)} acceptance(s) across "
            f"{int(metrics['attempts'])} attempt(s), recovered from the audit stream."
        ),
        "facts": facts,
        "citations": citations,
        "abstained": False,
        "trajectory": trajectory,
        "metrics": metrics,
        "metadata": {
            "repo": repo,
            "cycle": key,
            "attempts": sorted({
                (event.get("metadata") or {}).get("task_id") for event in events
            }),
            # Everything consumer-specific lives here, as data. The scenario never
            # reads it -- which is the whole claim about reusability.
            "consumer_specific": receipt_facts,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--artifacts-root", default=str(ARTIFACTS_ROOT))
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--cycle", help="cycle key; defaults to the smallest complete one")
    parser.add_argument("--list", action="store_true", help="list cycles and their arms")
    parser.add_argument("--out")
    args = parser.parse_args()

    events = load_events(args.repo, Path(args.artifacts_root))
    cycles = group_cycles(events)
    if not cycles:
        raise SystemExit(f"no dispatch cycles found for {args.repo}")

    if args.list:
        print(f"{'cycle':44} {'events':>6}  {'arms':22} complete")
        for key in sorted(cycles):
            types = {event["type"] for event in cycles[key]}
            arms = "".join(
                letter if types & set(group) else "-"
                for letter, group in (("R", REFUSAL_TYPES), ("V", REVIEW_TYPES), ("A", ACCEPT_TYPES))
            )
            print(f"{key:44} {len(cycles[key]):>6}  {arms:22} {is_complete(cycles[key])}")
        return 0

    key = args.cycle or smallest_complete(cycles)
    if key is None:
        raise SystemExit(
            f"{args.repo} has no complete dispatch cycle: no unit of work shows a refusal, "
            "a review and an acceptance. That is a finding about the consumer, not an error."
        )
    if key not in cycles:
        raise SystemExit(f"unknown cycle: {key}")

    candidate = build_candidate(args.repo, key, cycles[key], Path(args.repo_root))
    text = json.dumps(candidate, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"{args.repo} {key}: {len(candidate['facts'])} facts -> {args.out}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
