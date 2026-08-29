#!/usr/bin/env python3
"""Black-box probe for the `resume-and-settle` acceptance scenario.

The outcome under test, from docs/plans/agentops/meta-narrative-plan-2026-08-29.md §10.3:

    from a fresh process with no local cache, after interruption, through the served
    backend, recover session identity, work authority, checkpoint, and exact revision.

Resumability is unproven rather than broken, and the way to settle it is to run the
outcome. So this probe runs it, and the acceptance scenario scores what came back.

Three phases, because the interruption has to be real:

  arrange   In the repository, in a normal environment. Opens a reservation carrying a
            session id, records a handoff, and observes the revision. Writes an
            observation file that ONLY the emit phase reads.
  recover   A separate process, whose environment is deliberately impoverished: a
            scratch working directory that is not a git repository, an empty sprintctl
            database, and the repository id passed explicitly. It carries the
            principal's credential, because a resuming agent legitimately holds its own
            principal -- what it must not carry is the interrupted session's state.
            It never sees the observation file.
  emit      Joins what recover found with what arrange observed, and writes an
            acceptance-lab candidate output.

Keeping recover and emit apart is the whole discipline: a probe that compared against
the truth while recovering could pass by remembering rather than by recovering.

Usage:
    resume_probe.py run --out-dir DIR [--item-id N]
    resume_probe.py arrange --out DIR/observed.json [--item-id N]
    resume_probe.py recover --out DIR/recovered.json --repo-id agentops
    resume_probe.py emit --observed DIR/observed.json --recovered DIR/recovered.json \
        --out DIR/candidate.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
PROFILE = REPO / "templates/dispatch/environment-record/profiles/workstation-vuoro-shared.json"
DEFAULT_ITEM_ID = 2311
SHA40 = re.compile(r"^[0-9a-f]{40}$")

# Served operations, named as the scenario's tool allowlist names them. A CLI command is
# recorded under the served operation it reaches, not under its own spelling: the scenario
# is about what the platform serves, and the command names are this client's business.
COMMAND_OPERATIONS = {
    "session resume": "session.resume",
    "handoff": "work.read.handoff",
    "usage --context": "work.read.context",
    "context-candidates": "work.read.context-candidates",
    "next-work --explain": "work.read.next-work-explain",
    "reservation list": "work.read.reservations",
    "reservation reserve": "work.reservation.reserve",
    "git-context": "local:git-worktree",
}


def _served_env(*, db: Path, extra: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        SPRINTCTL_BACKEND="served",
        SPRINTCTL_VUORO_PROFILE=str(PROFILE),
        SPRINTCTL_DB=str(db),
    )
    env.pop("SPRINTCTL_URL", None)
    if extra:
        env.update(extra)
    return env


def _run(args: list[str], *, cwd: Path, env: dict[str, str]) -> tuple[int, str, str, float]:
    started = time.monotonic()
    proc = subprocess.run(
        args, cwd=str(cwd), env=env, capture_output=True, text=True, timeout=120
    )
    return proc.returncode, proc.stdout, proc.stderr, (time.monotonic() - started) * 1000.0


def _json_or_none(text: str) -> Any:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


# --- arrange ---------------------------------------------------------------------------


def cmd_arrange(args: argparse.Namespace) -> int:
    """Leave behind exactly what an interrupted session leaves behind."""
    env = _served_env(db=REPO / ".sprintctl/sprintctl.db")
    session_id = f"resume-probe-{uuid.uuid4().hex[:12]}"
    observed: dict[str, Any] = {
        "session_id": session_id,
        "item_id": args.item_id,
        "repo_id": args.repo_id,
        "effects": [],
    }

    # The revision the interrupted session was working at. Read from git because that is
    # where a working session reads it; whether it survives is the question.
    rc, out, err, _ = _run(["git", "rev-parse", "HEAD"], cwd=REPO, env=env)
    if rc != 0:
        print(f"arrange: cannot read HEAD: {err.strip()}", file=sys.stderr)
        return 1
    observed["revision"] = out.strip()
    rc, out, _, _ = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=REPO, env=env)
    observed["branch"] = out.strip() if rc == 0 else None

    # The authenticated principal owns the reservation; the session id is what distinguishes
    # this session's claim from the same principal's other claims. `--actor` must equal the
    # authenticated identity -- the backend rejects anything else -- so it is read, not chosen.
    actor = args.actor
    rc, out, err, _ = _run(
        [
            "sprintctl", "reservation", "reserve",
            "--item-id", str(args.item_id),
            "--actor", actor,
            "--session-id", session_id,
            "--role", args.role,
            "--json",
        ],
        cwd=REPO,
        env=env,
    )
    if rc != 0:
        print(f"arrange: reservation failed: {(err or out).strip()[-400:]}", file=sys.stderr)
        return 1
    reservation = _json_or_none(out) or {}
    observed["actor"] = actor
    observed["reservation_id"] = reservation.get("id")
    observed["effects"].append(
        {
            "operation": "work.reservation.reserve",
            "effect_id": f"reservation-{reservation.get('id')}",
            # The receipt is the durable identity the backend assigned to the effect. An
            # effect whose only evidence is that the command exited 0 has no receipt.
            "receipt": f"reservation#{reservation.get('id')}"
            if reservation.get("id") is not None
            else "",
        }
    )
    # Written now, not at the end: the claim exists from here on, and a later failure must
    # still leave the release phase something to read.
    Path(args.out).write_text(json.dumps(observed, indent=2) + "\n")

    # Recording a handoff is what a session does before it stops. Whether the bundle's own
    # checkpoint survives the recording is precisely what recover will find out.
    rc, out, err, _ = _run(
        ["sprintctl", "handoff", "--format", "json", "--output", "-"], cwd=REPO, env=env
    )
    observed["handoff_recorded"] = rc == 0
    if rc != 0:
        # This happens. A sprint with an active reservation is the state an interrupted
        # session leaves behind, and it is the state in which the bundle may refuse to
        # build -- so record the refusal and carry on rather than aborting the probe.
        observed["handoff_error"] = (err or out).strip()[-300:]
        print(f"arrange: handoff unavailable: {observed['handoff_error']}", file=sys.stderr)
    bundle = _json_or_none(out) or {}
    observed["handoff_generated_at"] = bundle.get("generated_at")
    observed["handoff_git_context"] = bundle.get("git_context")
    observed["sprint_id"] = (bundle.get("sprint") or {}).get("id")

    # The receipt for the recording is the event the backend assigned it. The CLI does not
    # return it, so it is looked up -- a receipt that has to be found is still a receipt,
    # and one that cannot be found is honestly absent.
    receipt = ""
    if observed["handoff_recorded"] and observed["sprint_id"] is not None:
        rc, out, _, _ = _run(
            ["sprintctl", "event", "list", "--sprint-id", str(observed["sprint_id"]),
             "--type", "handoff-generated", "--limit", "1", "--json"],
            cwd=REPO,
            env=env,
        )
        events = _json_or_none(out)
        if isinstance(events, list) and events:
            latest = events[-1]
            receipt = f"event#{latest.get('id') or latest.get('event_id')}"
    if observed["handoff_recorded"]:
        observed["effects"].append(
            {
                "operation": "work.handoff.record",
                "effect_id": "handoff-record",
                "receipt": receipt,
            }
        )

    Path(args.out).write_text(json.dumps(observed, indent=2) + "\n")
    print(f"arrange: session={session_id} item={args.item_id} revision={observed['revision'][:12]}")
    return 0


# --- recover ---------------------------------------------------------------------------


def cmd_recover(args: argparse.Namespace) -> int:
    """Recover through the served backend alone, and report only what came back."""
    scratch = Path(tempfile.mkdtemp(prefix="resume-probe-recover-"))
    workdir = scratch / "cwd"
    workdir.mkdir()
    empty_db = scratch / "empty.db"

    # `--allow-markerless-nonlocal` exists for exactly this: a served invocation from a
    # directory that carries no repository marker. The repository id is carried across the
    # interruption; nothing else about the repository is.
    base = ["sprintctl", "--repo-id", args.repo_id, "--allow-markerless-nonlocal"]
    env = _served_env(db=empty_db)

    steps: list[dict[str, Any]] = []
    total_ms = 0.0

    def step(label: str, argv: list[str]) -> Any:
        nonlocal total_ms
        rc, out, err, ms = _run(base + argv, cwd=workdir, env=env)
        total_ms += ms
        payload = _json_or_none(out)
        steps.append(
            {
                "label": label,
                "operation": COMMAND_OPERATIONS.get(label, label),
                "argv": argv,
                "exit_code": rc,
                "ms": round(ms, 1),
                "available": rc == 0,
                "error": (err or out).strip()[-300:] if rc != 0 else None,
            }
        )
        return payload if rc == 0 else None

    # The resume plan, top-down. The aggregate sits first and is not required: a resumer
    # runs the plan and skips what is unavailable, which is what lets a mixed-version
    # rollout happen without a flag day.
    step("session resume", ["session", "resume", "--json"])
    handoff = step("handoff", ["handoff", "--format", "json", "--output", "-"])
    reservations = step("reservation list", ["reservation", "list", "--all", "--json"])
    step("usage --context", ["usage", "--context", "--json"])
    step("next-work --explain", ["next-work", "--json", "--explain"])

    found: dict[str, Any] = {
        "session_id": None,
        "item_id": None,
        "actor": None,
        "checkpoint": None,
        "revision": None,
        "branch": None,
    }
    citations: dict[str, str] = {}

    # Session identity and work authority: an open reservation is a session's claim on an
    # item, and it carries both the session id that made it and the principal that owns it.
    if isinstance(reservations, list):
        active = [r for r in reservations if r.get("state") == "active"]
        # Newest first; a resumer picks up its own most recent claim.
        active.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        if active:
            claim = active[0]
            if claim.get("session_id"):
                found["session_id"] = claim["session_id"]
                citations["session-identity: recovered"] = "work.read.reservations"
            if claim.get("work_item_id") is not None and claim.get("actor"):
                found["item_id"] = claim["work_item_id"]
                found["actor"] = claim["actor"]
                citations["work-authority: recovered"] = "work.read.reservations"

    # Checkpoint and exact revision: whatever the served surfaces know about where the
    # interrupted session had got to. `git_context` is the bundle's own field for it.
    if isinstance(handoff, dict):
        git_context = handoff.get("git_context")
        if isinstance(git_context, dict) and git_context.get("sha"):
            found["checkpoint"] = git_context
            found["revision"] = git_context.get("sha")
            found["branch"] = git_context.get("branch")
            citations["checkpoint: recovered"] = "work.read.handoff"
            citations["exact-revision: recovered"] = "work.read.handoff"

    # A revision may also have been recorded as an item reference or an evidence locator.
    # Looking there before concluding it is unrecoverable keeps the finding honest.
    if found["revision"] is None and isinstance(handoff, dict):
        blob = json.dumps(handoff)
        candidates = sorted(set(re.findall(r"\b[0-9a-f]{40}\b", blob)))
        if candidates:
            found["revision"] = candidates[0]
            citations["exact-revision: recovered"] = "work.read.handoff"

    recovered = {
        "repo_id": args.repo_id,
        "found": found,
        "citations": citations,
        "steps": steps,
        "latency_ms": round(total_ms, 1),
        "workdir_was_a_git_repo": (workdir / ".git").exists(),
        "local_db_bytes": empty_db.stat().st_size if empty_db.exists() else 0,
    }
    Path(args.out).write_text(json.dumps(recovered, indent=2) + "\n")
    shutil.rmtree(scratch, ignore_errors=True)

    served = [s["operation"] for s in steps if s["available"]]
    print(f"recover: {len(served)}/{len(steps)} surfaces answered; " +
          ", ".join(k.split(':')[0] for k in citations) or "recover: nothing recovered")
    return 0


# --- emit ------------------------------------------------------------------------------


def cmd_emit(args: argparse.Namespace) -> int:
    """Join the two phases into an acceptance-lab candidate output."""
    observed = json.loads(Path(args.observed).read_text())
    recovered = json.loads(Path(args.recovered).read_text())
    found = recovered["found"]

    facts: list[str] = []
    citations: list[dict[str, Any]] = []
    by_source: dict[str, list[str]] = {}

    def claim(fact: str, source: str | None) -> None:
        facts.append(fact)
        if source:
            by_source.setdefault(source, []).append(fact)

    for fact, source in recovered["citations"].items():
        claim(fact, source)

    # The comparisons the recover phase was not allowed to make.
    if found.get("session_id") and found["session_id"] == observed["session_id"]:
        claim("session-identity: matches the session interrupted", "work.read.reservations")
    if found.get("item_id") == observed["item_id"] and found.get("actor") == observed.get("actor"):
        claim("work-authority: matches the authority held before the interruption",
              "work.read.reservations")
    revision = found.get("revision")
    if revision and revision == observed["revision"]:
        claim("exact-revision: matches the revision observed before the interruption",
              recovered["citations"].get("exact-revision: recovered", "work.read.handoff"))
    elif revision and not SHA40.match(revision):
        claim("exact-revision: recovered as a symbolic name rather than an exact revision", None)

    # Facts that would mean the recovery was not black-box after all. They are emitted from
    # measurements rather than from intent: an assertion of isolation that nothing checks is
    # the thing this scenario exists to distrust.
    if recovered.get("workdir_was_a_git_repo"):
        claim("checkpoint: read from a local working tree", "local:git-worktree")
    if recovered.get("local_db_bytes"):
        claim("work-authority: read from a local work cache", "local:sprintctl-db")

    for source, supports in sorted(by_source.items()):
        citations.append({"id": source, "supports": sorted(set(supports))})

    trajectory = []
    for seq, s in enumerate(recovered["steps"], start=1):
        if not s["available"]:
            # An unavailable surface is a skip, not a step: the resume plan is defined to
            # skip what is unserved, and a skipped step is not a tool the resumer used.
            continue
        trajectory.append({"seq": len(trajectory) + 1, "tool": s["operation"],
                           "action": " ".join(s["argv"])})
    for effect in observed.get("effects", []):
        trajectory.append(
            {
                "seq": len(trajectory) + 1,
                "tool": effect["operation"],
                "action": f"arrange: {effect['operation']}",
                "effect": True,
                "effect_id": effect["effect_id"],
                **({"receipt": effect["receipt"]} if effect["receipt"] else {}),
            }
        )

    unavailable = [s["operation"] for s in recovered["steps"] if not s["available"]]
    answer = (
        f"Recovered {len(recovered['citations'])} of 4 required elements through the served "
        f"backend for repo {recovered['repo_id']}."
    )
    if unavailable:
        answer += " Unserved and skipped: " + ", ".join(sorted(set(unavailable))) + "."

    candidate = {
        "schema_version": "acceptance-lab/candidate-output/v1",
        "answer": answer,
        "facts": facts,
        "citations": citations,
        "abstained": False,
        "trajectory": trajectory,
        "metrics": {
            "latency_ms": recovered["latency_ms"],
            "served_surfaces_used": float(len(trajectory)),
        },
        "metadata": {
            "profile": "workstation-vuoro-shared",
            "probe": "templates/dispatch/scripts/resume_probe.py",
            "observed_revision": observed["revision"],
            "recovered_revision": found.get("revision"),
            "observed_session_id": observed["session_id"],
            "recovered_session_id": found.get("session_id"),
            "unserved_operations": sorted(set(unavailable)),
        },
    }
    Path(args.out).write_text(json.dumps(candidate, indent=2) + "\n")
    print(f"emit: {len(facts)} facts, {len(trajectory)} trajectory steps -> {args.out}")
    return 0


# --- release ---------------------------------------------------------------------------


def cmd_release(args: argparse.Namespace) -> int:
    """Release the probe's reservation. A probe that leaves claims open is a leak."""
    observed = json.loads(Path(args.observed).read_text())
    reservation_id = observed.get("reservation_id")
    if reservation_id is None:
        print("release: nothing to release")
        return 0
    env = _served_env(db=REPO / ".sprintctl/sprintctl.db")
    rc, out, err, _ = _run(
        ["sprintctl", "reservation", "release", "--id", str(reservation_id)], cwd=REPO, env=env
    )
    if rc != 0:
        print(f"release: failed: {(err or out).strip()[-300:]}", file=sys.stderr)
        return 1
    print(f"release: reservation#{reservation_id} released")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    observed = out_dir / "observed.json"
    recovered = out_dir / "recovered.json"
    candidate = out_dir / "candidate.json"
    me = [sys.executable, str(Path(__file__).resolve())]

    def phase(argv: list[str]) -> int:
        # Each phase is its own process. That is the interruption.
        return subprocess.run(me + argv).returncode

    rc = phase(["arrange", "--out", str(observed), "--item-id", str(args.item_id),
                "--repo-id", args.repo_id, "--actor", args.actor, "--role", args.role])
    if rc != 0:
        return rc
    try:
        rc = phase(["recover", "--out", str(recovered), "--repo-id", args.repo_id])
        if rc != 0:
            return rc
        rc = phase(["emit", "--observed", str(observed), "--recovered", str(recovered),
                    "--out", str(candidate)])
    finally:
        phase(["release", "--observed", str(observed)])
    return rc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--repo-id", default="agentops")
        p.add_argument("--item-id", type=int, default=DEFAULT_ITEM_ID)
        p.add_argument("--actor", default="workstation-vuoro",
                       help="Must equal the authenticated identity; the backend rejects others.")
        p.add_argument("--role", default="observation",
                       choices=("execution", "verification", "observation"))

    p_run = sub.add_parser("run", help="arrange, recover, emit, release")
    p_run.add_argument("--out-dir", required=True)
    common(p_run)
    p_run.set_defaults(func=cmd_run)

    p_arrange = sub.add_parser("arrange", help="leave an interrupted session behind")
    p_arrange.add_argument("--out", required=True)
    common(p_arrange)
    p_arrange.set_defaults(func=cmd_arrange)

    p_recover = sub.add_parser("recover", help="recover through the served backend alone")
    p_recover.add_argument("--out", required=True)
    p_recover.add_argument("--repo-id", default="agentops")
    p_recover.set_defaults(func=cmd_recover)

    p_emit = sub.add_parser("emit", help="join the phases into a candidate output")
    p_emit.add_argument("--observed", required=True)
    p_emit.add_argument("--recovered", required=True)
    p_emit.add_argument("--out", required=True)
    p_emit.set_defaults(func=cmd_emit)

    p_release = sub.add_parser("release", help="release the probe's reservation")
    p_release.add_argument("--observed", required=True)
    p_release.set_defaults(func=cmd_release)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
