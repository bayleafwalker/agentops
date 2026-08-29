#!/usr/bin/env python3
"""L-1 hand-off driver: one packet, prepare -> run -> gate -> receipt -> PR, stop.

The driver chains the ``hybrid_dispatch.py`` stages for exactly one frozen task
packet and then, when the gate disposition is ``candidate``, opens a pull
request whose body is the receipt. It never merges. It never runs ``git``
against the coordinator checkout: every ``git`` invocation is pinned to the
packet's disposable worktree, and the PR step happens here in the driver —
outside the worker sandbox, whose ``network_policy: disabled`` and
``allowed_command_ids`` make ``gh pr create`` impossible from inside.

Step order is fixed in ``STEPS`` and is not configurable at the call site.
Any step that exits non-zero stops the sequence, writes an auditctl
``workflow.escalation`` event, and makes the driver exit non-zero.

One deliberate exception to "non-zero stops": ``gate`` exits 2 when it reached a
verdict of ``coordinator_review_required`` (a complete, parseable receipt with a
disposition). That is a *verdict*, not a failure — the packet contract says the
PR step is skipped with a recorded reason when the disposition is not
``candidate``, which requires ``receipt`` to run after such a gate. A gate exit
without a parseable disposition is a failure like any other.
"""
from __future__ import annotations

import argparse
import copy
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
HYBRID_DISPATCH = HERE / "hybrid_dispatch.py"

#: Fixed stage order. The PR step is not a hybrid_dispatch stage; it is the
#: driver's own and runs only after ``receipt`` has been written to disk.
STEPS: tuple[str, ...] = ("prepare", "run", "gate", "receipt")

#: L-4: one cheap retry after a red gate, and no more. Named so a reader can
#: tell a bounded retry from a loop that happened to stop.
MAX_GATE_ATTEMPTS = 2

#: What a retry re-runs. ``prepare`` is what makes a dispatch expensive and the
#: worktree already exists with its cold gates no longer red, so re-running it
#: would buy nothing -- that is what makes the retry cheap.
RETRY_STEPS: tuple[str, ...] = ("run", "gate", "receipt")

#: Gate exit codes that carry a verdict rather than a failure. hybrid_dispatch
#: returns 2 from ``gate`` for ``coordinator_review_required``.
GATE_VERDICT_EXITS = frozenset({0, 2})

#: The L-2 stop-condition vocabulary, in the order the M-1 spec row lists them.
#: A fired condition exits non-zero, escalates once with ``stop_condition`` in
#: the metadata, and never reaches the PR step.
STOP_CONDITIONS: tuple[str, ...] = (
    "release-boundary",
    "command-not-allowed",
    "path-outside-writable",
    "gate-red-twice",
)

#: The five parts of the PR step, in the only order that works. M-10 adds the
#: receipt capture and puts it *first*: the captured files have to be inside
#: the commit that follows, and a push before it would put starting_commit on
#: the remote and gh would open an empty PR. A failed part names itself in
#: report["pr"]["failed_step"] so a reader of a failed report can tell "the
#: capture would not write" from "the commit would not be made" from "the remote
#: would not add" from "the push was rejected" from "gh refused".
PR_STEP_NAMES: tuple[str, ...] = ("receipt-capture", "commit", "remote-add", "push", "pr-create")

#: Where the capture lands, repo-relative to the worktree. The directory
#: already carries an ``.ignore`` (coordinator work), so the files reach the
#: commit but never a repo-wide grep inside a worker's clone.
CAPTURE_ROOT = "docs/evidence/receipts"

#: The sidecar that carries the worker's transcript as text, never inside JSON:
#: embedding it produced a 288 KB single line and tripped ripgrep's 64 KB
#: record limit in every worker clone.
SIDECAR_NAME = "worker-stdout.txt"

ESCALATION_TYPE = "workflow.escalation"
DRIVER_ACTOR = "dispatch-release"

#: The secret shapes the module-level scan detects, keyed by the stable name a
#: finding carries. A finding never carries the matched text, so a report that
#: embeds the names cannot echo a credential. The groups are what the M-10
#: spec row enumerates, hardened by M-12: matching is case-insensitive where
#: case carries no meaning, the general assignment pattern accepts ':' beside
#: '=', a quoted or bare and prefixed key name, and the vendor formats the
#: shipped scan did not know. Each name tells one kind from another, and every
#: pattern is bounded so a transcript full of unbroken tokens cannot hang it.
SCAN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("github_token", re.compile(r"gh[opsu]_[A-Za-z0-9]{8,}|github_pat_[A-Za-z0-9]{8,}")),
    ("aws_access_key_id", re.compile(r"AKIA[A-Z0-9]{16}")),
    ("pem_private_key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("slack_token", re.compile(r"xox[abprs]-[A-Za-z0-9-]{8,}")),
    ("authorization_bearer", re.compile(r"authorization:\s*bearer\s+\S{20,}", re.IGNORECASE)),
    (
        "secret_assignment",
        re.compile(
            r"\b\"?(?:[\w.-]+[_-])?(?:api_?key|token|secret|password|access_key)\"?\s*[:=]\s*"
            r"(?:\"[^\"\n]{20,}\"|'[^'\n]{20,}'|\S{20,})",
            re.IGNORECASE,
        ),
    ),
    ("openai_api_key", re.compile(r"(?<![A-Za-z0-9_])sk-[A-Za-z0-9_]{20,}")),
    ("anthropic_api_key", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("google_api_key", re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    ("stripe_secret_key", re.compile(r"sk_(?:live|test)_[0-9A-Za-z]{20,}")),
    ("npm_token", re.compile(r"npm_[0-9A-Za-z]{20,}")),
    ("pypi_token", re.compile(r"pypi-[0-9A-Za-z_]{20,}")),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    (
        "url_basic_auth",
        re.compile(r"\b[A-Za-z][A-Za-z0-9+.-]{0,31}://[^/\s:@]+:[^/\s:@]{20,}@"),
    ),
)


#: The two patterns whose value side is bounded only by "twenty non-space
#: characters". A worker transcript is a stream of JSON, so its text arrives
#: with the escapes still in it: a newline is the two characters ``\`` and
#: ``n``, not a line break. Both of these patterns stop at a real newline and
#: neither stops at an escaped one, so on raw transcript text their value run
#: crosses line boundaries and reaches twenty characters out of source code
#: that contains no secret at all. They are matched against decoded text only.
ESCAPE_SENSITIVE_PATTERNS = frozenset({"secret_assignment", "authorization_bearer"})

#: What a JSON string escape decodes to. Anything else keeps its backslash,
#: because this is a scanner's best effort at reading the text a human would
#: see, not a JSON parser.
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "'": "'", "\\": "\\", "/": "/"}
_ESCAPE_RE = re.compile(r"\\(.)", re.DOTALL)


#: How many decode passes to attempt. A worker transcript is escaped at least
#: twice by the time it reaches the receipt text -- once at source, because the
#: worker's stdout is JSON lines whose string values are themselves escaped,
#: and again when the receipt payload is serialised. One pass leaves ``\n``
#: still standing as two characters and the false positive intact. Decoding is
#: contracting, so the loop settles; the bound only stops a pathological input
#: from spinning.
_MAX_DECODE_PASSES = 6


def decode_transcript_escapes(text: str) -> str:
    """The text a human would see, from text that is still JSON-escaped.

    Applied repeatedly until it stops changing, because the escaping is nested:
    the first pass turns ``\\n`` into ``\n`` and only the second turns that
    into a newline.

    Decoding before scanning is better in both directions for the anchored
    patterns, which are matched against the raw text as well. For the two loose
    patterns it is a deliberate trade: their value side is bounded by "twenty
    non-space characters", so on escaped text the run crosses line boundaries
    and matches source code containing no secret at all -- which withheld every
    receipt of a session. The cost is that a value whose own characters include
    a literal backslash-n could be split below twenty and missed. Real
    credentials in known formats are caught by the anchored patterns on the raw
    text regardless, so the residue is a heuristic pattern on an unusual value,
    weighed against a false positive that silently empties the evidence corpus.
    """
    for _ in range(_MAX_DECODE_PASSES):
        decoded = _ESCAPE_RE.sub(lambda m: _ESCAPES.get(m.group(1), m.group(0)), text)
        if decoded == text:
            return text
        text = decoded
    return text


def scan_for_secrets(text: str) -> list[str]:
    """Names of the secret patterns that match ``text``; never the text itself.

    The names are stable and distinct, so a report that embeds them can tell
    one kind from another without ever echoing the credential. Ordinary prose
    returns an empty list: a scan that fires on prose withholds every
    transcript, which is the same as never capturing one -- and a withheld
    receipt is worse than a missing one, because ``worker_totals`` cannot count
    it while the run still reports ``cost_reported: true``.

    The vendor patterns are anchored on their own prefixes and cannot be
    lengthened by an escape, so they are matched against both the raw and the
    decoded text: whichever form the credential arrived in, it is found.
    """
    decoded = decode_transcript_escapes(text)
    found = []
    for name, pattern in SCAN_PATTERNS:
        if name in ESCAPE_SENSITIVE_PATTERNS:
            hit = pattern.search(decoded) is not None
        else:
            hit = pattern.search(text) is not None or pattern.search(decoded) is not None
        if hit:
            found.append(name)
    return found


def _worker_stdout(payload: dict[str, Any]) -> str:
    """The run stage's transcript, where the receipt nested it under
    ``driver_steps``. Empty when the run stage reported none."""
    for entry in payload.get("driver_steps") or []:
        if isinstance(entry, dict) and entry.get("step") == "run":
            receipt = entry.get("receipt")
            if isinstance(receipt, dict):
                worker = receipt.get("worker")
                if isinstance(worker, dict) and isinstance(worker.get("stdout"), str):
                    return worker["stdout"]
    return ""


def _transcript_marker(transcript: str) -> str:
    """The short marker left where the transcript was, naming the sidecar that
    now holds it and the transcript's own byte count. It carries neither the
    transcript nor any part of it, so a scan of the report stays clean."""
    return (
        f"<transcript removed; sidecar {SIDECAR_NAME} holds "
        f"{len(transcript.encode('utf-8'))} bytes>"
    )


def _strip_transcript(payload: dict[str, Any], transcript: str) -> dict[str, Any]:
    """A deep copy of ``payload`` with the transcript removed from every value
    that carried it, the marker left in each place. An empty transcript removes
    nothing: there is nothing to take out of the JSON."""
    if not transcript:
        return copy.deepcopy(payload)
    marker = _transcript_marker(transcript)

    def _walk(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: _walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_walk(v) for v in node]
        return marker if node == transcript else node

    return _walk(payload)


def capture_receipt(
    worktree: Path, task_id: str, payload: dict[str, Any], transcript: str,
) -> dict[str, Any]:
    """Put the receipt and the worker's transcript onto the packet branch, or
    withhold both.

    The scan runs over the receipt and the transcript together and returns the
    *names* of the patterns that matched, never the matched text: the finding
    goes into a report that may be read anywhere. A finding writes neither file
    and returns a withholding record -- a secret in a transcript must not turn
    a green packet into a failed one. A clean scan writes ``receipt.json`` with
    the transcript removed (the marker names the sidecar and its byte count)
    and the transcript beside it as ``worker-stdout.txt`` with its own
    newlines intact.

    Returns the ``report["pr"]["receipt"]`` record. Raises ``OSError`` when the
    write cannot happen, which the caller treats as a failed ``receipt-capture``
    step that stops before the commit.
    """
    capture_dir = worktree / CAPTURE_ROOT / task_id
    receipt_text = json.dumps(payload, indent=2) + "\n"
    findings = sorted(set(scan_for_secrets(receipt_text) + scan_for_secrets(transcript)))
    if findings:
        # A withheld transcript must still leave a receipt behind. Writing
        # nothing made the gap invisible: `worker_totals` reads receipts and
        # cannot count one that was never written, so a tract with a withheld
        # receipt was silently short while every receipt it *did* find reported
        # its cost, leaving `cost_reported: true` over an incomplete corpus.
        # The stub carries numbers and names only -- never transcript text --
        # and is re-scanned before it is written.
        stub = _withheld_receipt_stub(payload, findings)
        stub_text = json.dumps(stub, indent=2) + "\n"
        if scan_for_secrets(stub_text):
            # Unreachable by construction; if the stub itself ever scans dirty,
            # record the gap and nothing else rather than write a secret.
            stub = {
                "task_id": task_id,
                "transcript_withheld": {"captured": False, "findings": findings},
            }
            stub_text = json.dumps(stub, indent=2) + "\n"
        capture_dir.mkdir(parents=True, exist_ok=True)
        (capture_dir / "receipt.json").write_text(stub_text, encoding="utf-8")
        return {
            "captured": False,
            "findings": findings,
            "path": f"{CAPTURE_ROOT}/{task_id}/receipt.json",
            "stub": True,
        }
    capture_dir.mkdir(parents=True, exist_ok=True)
    (capture_dir / "receipt.json").write_text(
        json.dumps(_strip_transcript(payload, transcript), indent=2) + "\n",
        encoding="utf-8",
    )
    (capture_dir / SIDECAR_NAME).write_text(transcript, encoding="utf-8")
    return {"captured": True, "path": f"{CAPTURE_ROOT}/{task_id}/receipt.json"}


def _withheld_receipt_stub(
    payload: dict[str, Any], findings: list[str]
) -> dict[str, Any]:
    """A receipt that records its own gap, safe to write when the scan fires.

    Structured numbers and stable pattern names only: the worker's spend, the
    gate verdict, and which shapes matched. No transcript, no diff, no command
    output -- nothing that carried the text the scan objected to.

    It exists so the corpus is short *visibly*. A scorecard can count a run it
    can see, and `cost_reported` over a corpus with a hole in it is a number
    nobody should trust.
    """
    spend: dict[str, Any] = {}
    passed = None
    for entry in payload.get("driver_steps") or []:
        if not isinstance(entry, dict):
            continue
        nested = entry.get("receipt")
        if not isinstance(nested, dict):
            continue
        if entry.get("step") == "run" and isinstance(nested.get("spend"), dict):
            candidate = nested["spend"]
            spend = {
                "cost_usd": candidate.get("cost_usd", 0.0),
                "tokens": candidate.get("tokens", 0),
                "cost_reported": bool(candidate.get("cost_reported", False)),
            }
        if entry.get("step") == "gate":
            evidence = nested.get("evidence")
            if isinstance(evidence, dict):
                passed = evidence.get("passed")
    return {
        "schema_version": payload.get("schema_version"),
        "task_id": payload.get("task_id"),
        "attempt": payload.get("attempt"),
        "starting_commit": payload.get("starting_commit"),
        "disposition": payload.get("disposition"),
        # Shaped so worker_totals reads it exactly as it reads a full receipt.
        # It takes spend from driver_steps and the first-pass verdict from the
        # top-level gate, so the stub has to carry both.
        "driver_steps": [
            {"step": "run", "receipt": {"spend": spend}},
            {"step": "gate", "receipt": {"evidence": {"passed": passed}}},
        ],
        "gate": {"evidence": {"passed": passed}},
        "transcript_withheld": {"captured": False, "findings": list(findings)},
    }


def _gate_table(final: dict[str, Any]) -> dict[str, Any]:
    """The gate table, as the gate receipt reports it under ``evidence.gates``."""
    gate = final.get("gate")
    if isinstance(gate, dict):
        evidence = gate.get("evidence")
        if isinstance(evidence, dict):
            gates = evidence.get("gates")
            if isinstance(gates, dict):
                return gates
    return {}


def _run_spend(final: dict[str, Any]) -> dict[str, Any]:
    """The run stage's spend record, where the receipt nested it under
    ``driver_steps``. Empty when the run stage reported none."""
    for entry in final.get("driver_steps") or []:
        if isinstance(entry, dict) and entry.get("step") == "run":
            receipt = entry.get("receipt")
            if isinstance(receipt, dict):
                spend = receipt.get("spend")
                if isinstance(spend, dict):
                    return spend
    return {}


def _disposition(final: dict[str, Any]) -> str | None:
    gate = final.get("gate")
    if isinstance(gate, dict):
        return gate.get("disposition")
    return None


def build_pr_body(
    packet: dict[str, Any], final: dict[str, Any], capture: dict[str, Any],
    commit_sha: str | None = None,
) -> str:
    """The bounded PR body: task, commit, disposition, gate table, spend, and
    the captured receipt's path -- or a note that the transcript was withheld.

    It carries no part of the worker's transcript, so it stays small no matter
    how large the receipt is, and it never becomes the place a withheld secret
    leaks. Cost is rendered rounded to two decimal places; each gate's boolean
    is rendered with a word that does not depend on the gate's own name.
    """
    lines = [
        f"# Hybrid dispatch {packet['task_id']}",
        "",
        f"- task: {packet['task_id']}",
        f"- starting_commit: {packet['starting_commit']}",
        f"- disposition: {_disposition(final)}",
    ]
    spend = _run_spend(final)
    cost = spend.get("cost_usd")
    tokens = spend.get("tokens")
    if isinstance(cost, (int, float)):
        lines.append(f"- cost_usd: {cost:.2f}")
    else:
        lines.append("- cost_usd: n/a")
    if tokens is not None:
        lines.append(f"- tokens: {tokens}")
    else:
        lines.append("- tokens: n/a")
    if capture.get("captured"):
        lines.append(f"- receipt: {capture['path']}")
    else:
        lines.append("- receipt: withheld (the transcript was not captured)")
    if commit_sha:
        lines.append(f"- worker_commit: {commit_sha}")
    lines.append("")
    lines.append("## Gates")
    for name, value in _gate_table(final).items():
        lines.append(f"- {name}: {'true' if value else 'false'}")
    if commit_sha:
        # The gate ran over the worker's commit. Acceptance happens over the
        # merged pull request, and the coordinator routinely adds commits to
        # this branch afterwards -- oracle reconciliations, evidence, and on one
        # occasion a change to a protected path, while the table above still
        # read protected-paths-untouched: true. Widening the gate to the whole
        # branch is the wrong fix, because those commits are legitimately
        # outside the packet's writable paths. Saying what the table covers is
        # the right one.
        lines.append("")
        lines.append(
            f"The gate table above was computed over `{commit_sha[:12]}` only. "
            "Commits added to this branch afterwards were not gated."
        )
    return "\n".join(lines) + "\n"


class DriverError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _parse_receipt(stdout: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


Runner = Callable[[list[str], Path | None], subprocess.CompletedProcess]


def _default_runner(cmd: list[str], cwd: Path | None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=cwd, text=True, capture_output=True, check=False, stdin=subprocess.DEVNULL,
    )


def worktree_path(packet: dict[str, Any]) -> Path:
    return Path(packet["worktree"]["root"]) / packet["repo_id"] / packet["task_id"]


def write_escalation(
    packet: dict[str, Any],
    step: str,
    exit_code: int,
    detail: str,
    runner: Runner,
    auditctl_bin: str,
    stop_condition: str | None = None,
) -> dict[str, Any]:
    """Record a workflow.escalation event. Degrades quietly without auditctl."""
    metadata = {
        "task_id": packet["task_id"],
        "repo_id": packet["repo_id"],
        "step": step,
        "exit_code": exit_code,
        "starting_commit": packet["starting_commit"],
        "driver": DRIVER_ACTOR,
    }
    if stop_condition is not None:
        metadata["stop_condition"] = stop_condition
    record = {
        "type": ESCALATION_TYPE,
        "actor": DRIVER_ACTOR,
        "summary": f"{packet['task_id']}: step {step} exited {exit_code}; sequence stopped",
        "detail": detail[-4000:],
        "metadata": metadata,
        "recorded_at": _now(),
    }
    if shutil.which(auditctl_bin) is None and not Path(auditctl_bin).exists():
        record["sink"] = "unavailable"
        return record
    cmd = [
        auditctl_bin, "add",
        "--type", ESCALATION_TYPE,
        "--source", DRIVER_ACTOR,
        "--actor", DRIVER_ACTOR,
        "--summary", record["summary"],
        "--detail", record["detail"],
        "--ref", f"sha:{packet['starting_commit']}",
        "--metadata", json.dumps(metadata, sort_keys=True),
    ]
    # The root is deliberately not set here. auditctl <= 0.1.3 required it, and the
    # default this driver supplied named one repository -- for a driver that runs in
    # whichever repo the packet targets, which is how shards and indexes came to
    # disagree. Since 0.1.4 the publisher defaults the root to the repository it
    # resolves itself, so a caller that sets it can only redirect a correct answer to
    # a wrong one.
    completed = runner(cmd, None)
    record["sink"] = "auditctl" if completed.returncode == 0 else "auditctl_failed"
    if completed.returncode != 0:
        record["sink_error"] = (completed.stderr or completed.stdout).strip()[-1000:]
    return record


#: The agentops checkout this driver belongs to. ``hybrid_dispatch`` otherwise
#: falls back to its own hardcoded default, so a stage could resolve its policy
#: from a different checkout than the one the coordinator validated the packet
#: against -- and did: validate accepted a retry packet that the run stage then
#: refused, because the two policies disagreed about max_attempts.
DEFAULT_AGENTOPS_ROOT = HERE.parents[2]


def hybrid_cmd(
    step: str,
    packet_path: Path,
    repo_root: Path,
    python_bin: str,
    passthrough: list[str],
    agentops_root: Path | None = None,
) -> list[str]:
    return [
        python_bin, str(HYBRID_DISPATCH),
        "--repo-root", str(repo_root),
        "--agentops-root", str(agentops_root or DEFAULT_AGENTOPS_ROOT),
        "--packet", str(packet_path),
        *passthrough,
        step,
    ]


def packet_branch(packet: dict[str, Any]) -> str:
    """The remote branch an attempt pushes to.

    The packet declares a fixed branch in ``worktree.branch``, and a first
    attempt pushes that name, unchanged: every packet merged to date used it,
    and renaming them retroactively would orphan their history. A retry -- any
    attempt above 1 -- pushes a distinct name that still carries the packet's
    branch and names the attempt, so two retries can never collide with each
    other and the earlier attempt's branch stays exactly as it was. A missing
    or non-integer attempt is a first attempt.
    """
    branch = packet["worktree"]["branch"]
    attempt = packet.get("attempt")
    if not isinstance(attempt, int) or attempt <= 1:
        return branch
    return f"{branch}.attempt-{attempt}"


def pr_command(
    packet: dict[str, Any], body: Path, base: str, title: str, gh_bin: str,
) -> list[str]:
    """The single ``gh pr create`` invocation. Body is the generated body file."""
    return [
        gh_bin, "pr", "create",
        "--head", packet_branch(packet),
        "--base", base,
        "--title", title,
        "--body-file", str(body),
    ]


def _resolve_push_remote(
    repo_root: Path, push_remote: str | None, runner: Runner,
) -> str | None:
    """The URL the PR step pushes to. An explicit argument wins; otherwise the
    coordinator's origin is asked, read-only. None means no URL could be
    resolved, and the PR step skips rather than failing."""
    if push_remote is not None:
        return push_remote
    completed = runner(["git", "remote", "get-url", "origin"], repo_root)
    if completed.returncode != 0:
        return None
    return (completed.stdout or "").strip() or None


def _commit_worktree(
    packet: dict[str, Any], worktree: Path, runner: Runner,
) -> tuple[dict[str, Any] | None, int, str]:
    """Stage and commit the worker's worktree onto the packet branch.

    Returns (record, exit_code, stderr): record carries the resulting sha and
    is None when any git command failed, in which case exit_code and stderr
    describe the first failure. The commit supplies its own identity because
    the worktree is a clone and user.name/user.email may be configured nowhere
    on the host.
    """
    completed = runner(["git", "add", "-A"], worktree)
    if completed.returncode != 0:
        return None, completed.returncode, (completed.stderr or "").strip()[-2000:]
    message = f"[hybrid] {packet['task_id']} @ {packet['starting_commit'][:12]}"
    completed = runner(
        [
            "git",
            "-c", f"user.name={DRIVER_ACTOR}",
            "-c", f"user.email={DRIVER_ACTOR}@agentops.invalid",
            "commit", "-m", message,
        ],
        worktree,
    )
    if completed.returncode != 0:
        return None, completed.returncode, (completed.stderr or "").strip()[-2000:]
    completed = runner(["git", "rev-parse", "HEAD"], worktree)
    if completed.returncode != 0:
        return None, completed.returncode, (completed.stderr or "").strip()[-2000:]
    return {"sha": (completed.stdout or "").strip(), "message": message}, 0, ""


def _packet_command_ids(packet: dict[str, Any]) -> list[str]:
    """Every command id a packet references, from the oracle and acceptance rows."""
    ids: list[str] = []
    oracle = packet.get("oracle")
    if isinstance(oracle, dict):
        starts_red = oracle.get("starts_red")
        if isinstance(starts_red, str):
            ids.append(starts_red)
        elif isinstance(starts_red, list):
            ids.extend(cid for cid in starts_red if isinstance(cid, str))
    for prop in packet.get("acceptance_properties") or []:
        if isinstance(prop, dict):
            cid = prop.get("command_id")
            if isinstance(cid, str):
                ids.append(cid)
    return ids


def _preflight_stop(packet: dict[str, Any]) -> tuple[str, str] | None:
    """Stop conditions checked before any stage runs. Returns (condition, detail)."""
    if packet.get("release_boundary") is True:
        return ("release-boundary", "release_boundary is true in the packet")
    allowed = packet.get("allowed_command_ids")
    if allowed is not None:
        offending = [cid for cid in _packet_command_ids(packet) if cid not in allowed]
        if offending:
            return (
                "command-not-allowed",
                f"command ids outside allowed_command_ids: {', '.join(offending)}",
            )
    return None


def _gate_evidence(receipt: dict[str, Any] | None) -> dict[str, Any]:
    """The gate's evidence: nested under ``evidence`` in a real receipt, flat in a stub."""
    if isinstance(receipt, dict) and isinstance(receipt.get("evidence"), dict):
        return receipt["evidence"]
    return receipt if isinstance(receipt, dict) else {}


def _path_allowed(path: str, patterns: list[str]) -> bool:
    """True when ``path`` is covered by any glob or directory-prefix pattern.

    Agrees with ``hybrid_dispatch._matches_any`` so the driver's L-2
    path-outside-writable stop asks the same question the validator asks at
    validate time. Manifest scope roots are written as directory prefixes
    (``docs/``) while packets use globs (``docs/**``); both forms must resolve
    here. Reproduced deliberately instead of importing the packet engine, so
    the driver does not depend on it at runtime.
    """
    for pattern in patterns:
        if pattern.endswith("/"):
            if path == pattern.rstrip("/") or path.startswith(pattern):
                return True
            continue
        if fnmatch.fnmatch(path, pattern):
            return True
        prefix = pattern[: -len("/**")] if pattern.endswith("/**") else None
        if prefix is not None and (path == prefix or path.startswith(prefix + "/")):
            return True
        if path == pattern:
            return True
    return False


def _post_gate_stop(packet: dict[str, Any], evidence: dict[str, Any]) -> tuple[str, str] | None:
    """Stop conditions checked after the gate and before the PR step."""
    allowed = packet.get("allowed_command_ids")
    if allowed is not None:
        results = evidence.get("command_results") or []
        offending = [
            r.get("command_id") for r in results
            if isinstance(r, dict) and r.get("command_id") not in allowed
        ]
        if offending:
            return (
                "command-not-allowed",
                f"command ids outside allowed_command_ids: {', '.join(offending)}",
            )
    writable = packet.get("writable_patch_paths")
    if writable is not None:
        touched = evidence.get("touched_paths") or []
        offending = [p for p in touched if not _path_allowed(p, writable)]
        if offending:
            return (
                "path-outside-writable",
                f"touched paths outside writable_patch_paths: {', '.join(offending)}",
            )
    return None


def _gate_is_red(completed: subprocess.CompletedProcess, parsed: dict[str, Any] | None) -> bool:
    """A gate is red on a non-zero exit, a non-candidate disposition, or passed=false."""
    if completed.returncode != 0:
        return True
    if not isinstance(parsed, dict):
        return True
    if parsed.get("disposition") != "candidate":
        return True
    return _gate_evidence(parsed).get("passed") is False


def _record_red_gate(attempts_path: Path, starting_commit: str) -> int:
    """Increment the red-gate count for a starting_commit; returns the new count."""
    ledger: dict[str, Any] = {}
    if attempts_path.exists():
        ledger = _load_json(attempts_path)
    count = int(ledger.get(starting_commit, 0)) + 1
    ledger[starting_commit] = count
    attempts_path.parent.mkdir(parents=True, exist_ok=True)
    attempts_path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    return count


def build_retry_packet(
    packet: dict[str, Any], attempt: int, stdout_tail: str, stderr_tail: str,
) -> dict[str, Any]:
    """The frozen packet plus the red gate's own output, and nothing else.

    The tails go into ``purpose`` as well as into ``retry_context``: the purpose
    is what the worker's prompt actually renders, so a retry that only sets a
    sibling key re-runs the same dispatch and calls it a retry. Nothing else
    moves -- a retry that quietly widened the sandbox would not be one.
    """
    retried = copy.deepcopy(packet)
    retried["attempt"] = attempt
    retried["retry_context"] = {
        "attempt": attempt,
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
    }
    retried["purpose"] = (
        str(packet.get("purpose", ""))
        + f"\n\nretry_context: attempt {attempt}. The previous attempt's gate was red. "
        "The gate's own output follows; it says what is still failing. Fix that, "
        "inside the same writable paths.\n"
        f"stdout_tail:\n{stdout_tail}\n"
        f"stderr_tail:\n{stderr_tail}"
    )
    return retried


def drive(
    packet_path: Path,
    repo_root: Path,
    *,
    dry_run: bool,
    base_branch: str,
    python_bin: str = sys.executable,
    gh_bin: str = "gh",
    auditctl_bin: str = "auditctl",
    passthrough: list[str] | None = None,
    runner: Runner = _default_runner,
    report_path: Path | None = None,
    attempts_path: Path | None = None,
    push_remote: str | None = None,
    agentops_root: Path | None = None,
) -> tuple[int, dict[str, Any]]:
    """Run the fixed sequence. Returns (exit_code, report)."""
    packet = _load_json(packet_path)
    worktree = worktree_path(packet)
    passthrough = list(passthrough or [])
    if attempts_path is None:
        attempts_path = worktree.parent / f"{packet['task_id']}.attempts.json"
    report: dict[str, Any] = {
        "schema_version": "agentops-dispatch-release/v1",
        "task_id": packet["task_id"],
        "starting_commit": packet["starting_commit"],
        "coordinator_repo_root": str(repo_root),
        "worktree": str(worktree),
        "dry_run": dry_run,
        "started_at": _now(),
        "steps": [],
        "disposition": None,
        "receipt_path": None,
        "pr": None,
        "escalation": None,
        "stop": None,
        "retry": None,
    }

    def finish(code: int) -> tuple[int, dict[str, Any]]:
        report["finished_at"] = _now()
        report["exit_code"] = code
        if report_path is not None:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return code, report

    def stop(condition: str, detail: str) -> tuple[int, dict[str, Any]]:
        report["stop"] = {"condition": condition, "detail": detail}
        report["escalation"] = write_escalation(
            packet, "stop", 1, detail, runner, auditctl_bin, stop_condition=condition,
        )
        return finish(1)

    receipt_path = worktree.parent / f"{packet['task_id']}.receipt.json"
    report["receipt_path"] = str(receipt_path)
    gate_receipt: dict[str, Any] | None = None
    final: dict[str, Any] | None = None
    preflight = _preflight_stop(packet)
    if preflight is not None:
        return stop(*preflight)

    attempt = int(packet.get("attempt", 1))
    current_packet_path = packet_path
    current_packet = packet
    steps: tuple[str, ...] = STEPS

    while True:
      gate_red = False
      red_stdout = ""
      red_stderr = ""
      for step in steps:
        cmd = hybrid_cmd(
            step, current_packet_path, repo_root, python_bin, passthrough, agentops_root,
        )
        started = _now()
        completed = runner(cmd, None)
        parsed = _parse_receipt(completed.stdout)
        entry: dict[str, Any] = {
            "step": step,
            "attempt": attempt,
            "command": cmd,
            "started_at": started,
            "finished_at": _now(),
            "exit_code": completed.returncode,
            "stderr": (completed.stderr or "").strip()[-2000:],
        }
        # Each stage emits its receipt on stdout, and that receipt is the only
        # record of what the stage actually observed -- the worker's exit code,
        # its spend, the gate's per-command results. Keeping only stderr made a
        # run that finished cleanly and changed nothing indistinguishable from a
        # run that never reached the model: diagnosing it cost a second dispatch.
        if parsed is not None:
            entry["receipt"] = parsed
        elif completed.stdout:
            entry["stdout_tail"] = completed.stdout.strip()[-4000:]
        if step == "gate":
            disposition = parsed.get("disposition") if parsed else None
            entry["disposition"] = disposition
            verdict = completed.returncode in GATE_VERDICT_EXITS and disposition is not None
            failed = not verdict
            if not failed:
                gate_receipt = parsed
                report["disposition"] = disposition
        else:
            failed = completed.returncode != 0
        entry["failed"] = failed
        report["steps"].append(entry)
        if failed:
            detail = (completed.stderr or "").strip() or (completed.stdout or "").strip()
            report["escalation"] = write_escalation(
                packet, step, completed.returncode, detail, runner, auditctl_bin,
            )
            return finish(completed.returncode or 1)
        if step == "gate":
            evidence = _gate_evidence(parsed)
            post_gate = _post_gate_stop(packet, evidence)
            if post_gate is not None:
                return stop(*post_gate)
            if _gate_is_red(completed, parsed):
                count = _record_red_gate(attempts_path, packet["starting_commit"])
                if count >= MAX_GATE_ATTEMPTS:
                    return stop(
                        "gate-red-twice",
                        f"second red gate on starting_commit {packet['starting_commit']}",
                    )
                gate_red = True
                # The retry has to carry what the gate actually said, not a
                # summary of it: the raw stdout is the gate's receipt and the
                # stderr is the command output the receipt points at.
                red_stdout = (completed.stdout or "").strip()[-4000:]
                red_stderr = (completed.stderr or "").strip()[-4000:]
        if step == "receipt":
            # Written before the PR step, and it IS the PR body.
            final = parsed if parsed is not None else {"raw_stdout": completed.stdout}
            final = dict(final)
            final["attempt"] = attempt
            final["gate"] = gate_receipt
            final["driver_steps"] = [
                {k: v for k, v in s.items() if k != "command"} for s in report["steps"]
            ]
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text(json.dumps(final, indent=2) + "\n", encoding="utf-8")

      # L-4: exactly one cheap retry, and only for a red gate. A stage that
      # exited non-zero never produced a verdict to feed back, and a post-gate
      # stop means the packet is wrong rather than the worker -- neither is
      # answerable by running the worker again.
      if not gate_red or attempt >= MAX_GATE_ATTEMPTS:
          break
      attempt += 1
      current_packet = build_retry_packet(current_packet, attempt, red_stdout, red_stderr)
      current_packet_path = worktree.parent / f"{packet['task_id']}.attempt-{attempt}.json"
      current_packet_path.parent.mkdir(parents=True, exist_ok=True)
      current_packet_path.write_text(
          json.dumps(current_packet, indent=2) + "\n", encoding="utf-8",
      )
      report["retry"] = {
          "attempt": attempt,
          "packet_path": str(current_packet_path),
          "reason": "gate was red on the previous attempt; retried with its output",
      }
      steps = RETRY_STEPS

    if not receipt_path.exists():
        report["escalation"] = write_escalation(
            packet, "receipt", 1, "receipt file was not written", runner, auditctl_bin,
        )
        return finish(1)

    title = f"[hybrid] {packet['task_id']} @ {packet['starting_commit'][:12]}"
    cmd = pr_command(packet, receipt_path, base_branch, title, gh_bin)
    pr: dict[str, Any] = {"command": cmd, "body_file": str(receipt_path), "opened": False}
    def pr_failed(step_name: str, exit_code: int, stderr: str) -> tuple[int, dict[str, Any]]:
        pr["failed_step"] = step_name
        pr["exit_code"] = exit_code
        pr["stderr"] = stderr
        report["pr"] = pr
        report["escalation"] = write_escalation(
            packet, "pr", exit_code, stderr, runner, auditctl_bin,
        )
        return finish(exit_code)

    if report["disposition"] != "candidate":
        pr["skipped"] = True
        pr["reason"] = (
            f"gate disposition is {report['disposition']!r}, not 'candidate'; "
            "the coordinator must review before any PR is opened"
        )
    elif gate_red:
        pr["skipped"] = True
        pr["reason"] = (
            "gate is red (first red gate recorded); "
            "the coordinator must review before any PR is opened"
        )
    elif dry_run:
        pr["skipped"] = True
        pr["reason"] = "dry-run: would open this PR with the receipt as body"
    else:
        # M-10c: the receipt capture is the first thing the PR step hands
        # onward, and it precedes the commit because the captured files have to
        # be inside it. A withheld transcript is a capture that did not happen,
        # recorded under report["pr"]["receipt"]; a capture that cannot be
        # written is a failed step that names itself and stops here, before the
        # commit and everything after it.
        assert final is not None
        transcript = _worker_stdout(final)
        try:
            pr["receipt"] = capture_receipt(
                worktree, packet["task_id"], final, transcript,
            )
        except OSError as exc:
            return pr_failed(
                "receipt-capture", 1,
                f"receipt-capture could not write into the worktree: {exc}",
            )
        # M-10b: the PR body is generated to its own file, never the receipt and
        # never the captured copy. It is bounded no matter how large the receipt
        # is, and it carries no part of the worker's transcript. gh pr create
        # points --body-file at it.
        # M-9: the commit is the next thing the PR step hands onward, and it
        # precedes remote resolution so an unresolvable remote still leaves the
        # work committed on the packet branch.
        commit, commit_code, commit_stderr = _commit_worktree(packet, worktree, runner)
        if commit is None:
            return pr_failed("commit", commit_code, commit_stderr)
        pr["commit"] = commit
        # M-10b: the PR body is generated to its own file, never the receipt and
        # never the captured copy. It is bounded no matter how large the receipt
        # is, and it carries no part of the worker's transcript. gh pr create
        # points --body-file at it.
        #
        # It is written AFTER the commit so it can name the sha the gate ran
        # over. The body lives in worktree.parent, outside the tree being
        # committed, so writing it later changes nothing about what the commit
        # contains -- and the captured receipt still has to precede the commit.
        body_path = worktree.parent / f"{packet['task_id']}.pr-body.md"
        body_path.write_text(
            build_pr_body(packet, final, pr["receipt"], commit.get("sha")),
            encoding="utf-8",
        )
        pr["body_file"] = str(body_path)
        cmd = pr_command(packet, body_path, base_branch, title, gh_bin)
        pr["command"] = cmd
        # The remote comes back here, in the driver, after the worker is done:
        # prepare_workspace deliberately removes origin from the worker's clone,
        # so the PR step has to re-add it. Resolution is read-only against the
        # coordinator checkout; every mutating git command below is pinned to
        # the packet's worktree.
        remote = _resolve_push_remote(repo_root, push_remote, runner)
        if remote is None:
            pr["skipped"] = True
            pr["reason"] = (
                "could not resolve a push remote from the coordinator's origin; "
                "no PR was opened"
            )
        else:
            branch = packet["worktree"]["branch"]
            remote_branch = packet_branch(packet)
            add_cmd = ["git", "remote", "add", "origin", remote]
            completed = runner(add_cmd, worktree)
            if completed.returncode != 0:
                return pr_failed(
                    "remote-add", completed.returncode,
                    (completed.stderr or "").strip()[-2000:],
                )
            push_cmd = ["git", "push", "origin", f"{branch}:{remote_branch}"]
            completed = runner(push_cmd, worktree)
            if completed.returncode != 0:
                return pr_failed(
                    "push", completed.returncode,
                    (completed.stderr or "").strip()[-2000:],
                )
            pr["push"] = {"remote": remote, "branch": remote_branch}
            # Runs in the worktree so gh resolves the repository from there,
            # never from the coordinator checkout. It is the only network step
            # and the only step that is not a hybrid_dispatch stage.
            completed = runner(cmd, worktree)
            pr["exit_code"] = completed.returncode
            pr["stdout"] = (completed.stdout or "").strip()
            pr["stderr"] = (completed.stderr or "").strip()[-2000:]
            pr["opened"] = completed.returncode == 0
            if completed.returncode != 0:
                return pr_failed("pr-create", completed.returncode, pr["stderr"])
            pr["url"] = pr["stdout"].splitlines()[-1] if pr["stdout"] else None
    report["pr"] = pr
    return finish(0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--base", default="main", help="PR base branch (never pushed to).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run every step except gh pr create; report what it would open.")
    parser.add_argument("--gh-bin", default=os.environ.get("GH_BIN", "gh"))
    parser.add_argument("--auditctl-bin", default=os.environ.get("AUDITCTL_BIN", "auditctl"))
    parser.add_argument("--report", type=Path, help="Write the driver report JSON here too.")
    parser.add_argument(
        "--agentops-root", type=Path, default=None,
        help="Agentops checkout every stage resolves its policy from. Defaults to "
             "this driver's own checkout, so one run is judged by one policy.",
    )
    args, passthrough = parser.parse_known_args(argv)
    if passthrough and passthrough[0] == "--":
        passthrough = passthrough[1:]
    code, report = drive(
        args.packet.resolve(),
        args.repo_root.resolve(),
        dry_run=args.dry_run,
        base_branch=args.base,
        gh_bin=args.gh_bin,
        auditctl_bin=args.auditctl_bin,
        passthrough=passthrough,
        report_path=args.report,
        agentops_root=args.agentops_root,
    )
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
