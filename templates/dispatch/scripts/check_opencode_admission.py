#!/usr/bin/env python3
"""Lightweight OpenCode admission check: routable, cost-sane, contained.

Answers two questions, cheaply and repeatably: is this provider/model
actually routable right now, and does a real call produce a reasonable
output for its cost? Nothing is signed, nothing is one-shot, nothing is
promoted or committed by this check, and no independent review gates it --
"qualification" here is not a five-stage hiring process, it is a sanity
check you can rerun immediately if it fails.

Ongoing trust in a provider/model for a role is a separate, rolling
mechanism (agentops#2143 -- role-scoped continuous fitness/routing
evidence over hundreds of real runs), explicitly not this one-shot check.

Run directly as the operator:

    python check_opencode_admission.py --provider opencode-go \\
        --model deepseek-v4-flash --agent ao-mechanical-bulk

Credential provisioning/scrub discipline is the one thing here that still
needs real protection and is unchanged from the prior design. Everything
else -- Ed25519 signing, the permanent one-shot ledger, dual independent
review, and ~400 lines of pinned-executable/parent-chain/Nix-store-mount
fingerprinting -- was attestation ceremony that never affected routability
or cost, and is gone.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys
import threading
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "templates/dispatch/provider-qualification/opencode-go-deepseek-v4-flash.json"
CONFIG = ROOT / "templates/dispatch/hybrid/opencode.hybrid.json"
RUN_REPORT_ROOT = ROOT / "docs/dispatch/admission-runs"

AUTH_SOURCE = Path("/var/lib/agentops/opencode-qualification/provider-auth.json")
WORKSPACE_PARENT = Path("/var/lib/agentops/opencode-qualification/workspaces")
OPENCODE = Path("/run/current-system/sw/bin/opencode")
RUNUSER = Path("/run/current-system/sw/bin/runuser")
TOUCH = Path("/run/current-system/sw/bin/touch")
MKDIR = Path("/run/current-system/sw/bin/mkdir")
WORKER_USER = "agentworker"

SOFT_TOKENS = 500_000
HARD_TOKENS = 1_000_000
MAX_COST_USD = 3.0
HARD_WALL_SECONDS = 120
COOLDOWN_SECONDS = 60
EXPECTED_CLI_VERSION = "1.18.4"

SAFE_PROVIDER_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
AUTH_PROVIDER = "opencode-go"
AUTH_TYPE = "api"
EXPECTED_WORKER_UID: int | None = None
ACTIVE_WORKSPACE_ROOT: Path | None = None


class CheckError(RuntimeError):
    """The admission check could not establish routability, cost-sanity, or containment."""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _check_path(path: Path, mode: int, label: str, *, directory: bool = False, owner_uid: int | None = None) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise CheckError(f"{label} is unavailable: {exc}") from exc
    if owner_uid is not None and info.st_uid != owner_uid:
        raise CheckError(f"{label} has an unexpected owner")
    if stat.S_IMODE(info.st_mode) != mode:
        raise CheckError(f"{label} must have mode {mode:04o}")
    if directory and not stat.S_ISDIR(info.st_mode):
        raise CheckError(f"{label} must be a directory")
    if not directory and not stat.S_ISREG(info.st_mode):
        raise CheckError(f"{label} must be a regular file")


def _check_parents(path: Path, label: str, *, allowed_owner_uids: set[int] | None = None) -> None:
    allowed_owner_uids = {0, os.geteuid()} if allowed_owner_uids is None else set(allowed_owner_uids)
    current = path.parent
    while True:
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode) or info.st_uid not in allowed_owner_uids:
            raise CheckError(f"{label} has an unsafe parent")
        mode = stat.S_IMODE(info.st_mode)
        if mode & 0o022 and not (mode & stat.S_ISVTX):
            raise CheckError(f"{label} has a writable parent")
        if current.parent == current:
            return
        current = current.parent


def _read_provider_auth() -> bytes:
    """Validate the fixed, protected auth input without exposing its value."""
    _check_path(AUTH_SOURCE, 0o400, "provider auth source")
    _check_parents(AUTH_SOURCE, "provider auth source")
    try:
        payload = json.loads(AUTH_SOURCE.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CheckError(f"provider auth source is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict) or set(payload) != {AUTH_PROVIDER} or not isinstance(payload[AUTH_PROVIDER], dict) or set(payload[AUTH_PROVIDER]) != {"type", "key"}:
        raise CheckError("provider auth source is not the native OpenCode auth object")
    if payload[AUTH_PROVIDER]["type"] != AUTH_TYPE or not isinstance(payload[AUTH_PROVIDER]["key"], str) or not 1 <= len(payload[AUTH_PROVIDER]["key"]) <= 4096:
        raise CheckError("provider auth source is not the exact native API credential")
    return AUTH_SOURCE.read_bytes()


def _remove_provider_auth_material(target: Path, directories: list[Path]) -> None:
    """Remove a partially-created native auth tree without touching its HOME."""
    failures: list[str] = []
    try:
        target.unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        failures.append(f"credential: {exc}")
    for directory in reversed(directories):
        try:
            directory.rmdir()
        except FileNotFoundError:
            pass
        except OSError as exc:
            failures.append(f"directory {directory}: {exc}")
    if failures:
        raise CheckError("could not completely scrub disposable provider auth material: " + "; ".join(failures))


def _provision_provider_auth(auth_bytes: bytes) -> Path:
    """Copy the approved credential into a worker-owned, transactional XDG tree."""
    assert ACTIVE_WORKSPACE_ROOT is not None
    auth_root = ACTIVE_WORKSPACE_ROOT / ".local"
    data_root = auth_root / "share"
    auth_dir = data_root / "opencode"
    target = auth_dir / "auth.json"
    directories: list[Path] = []
    worker_uid = EXPECTED_WORKER_UID if EXPECTED_WORKER_UID is not None else pwd.getpwnam(WORKER_USER).pw_uid
    try:
        for directory, label in ((auth_root, "fresh worker data root"), (data_root, "fresh worker data directory"), (auth_dir, "fresh worker OpenCode auth directory")):
            directory.mkdir(mode=0o700)
            directories.append(directory)
            os.chown(directory, worker_uid, -1)
            os.chmod(directory, 0o700)
            _check_path(directory, 0o700, label, directory=True, owner_uid=worker_uid)
            _check_parents(directory, label, allowed_owner_uids={0, worker_uid})
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
        with os.fdopen(fd, "wb") as stream:
            stream.write(auth_bytes)
        os.chown(target, worker_uid, -1)
        os.chmod(target, 0o400)
        _check_path(target, 0o400, "fresh worker provider auth", owner_uid=worker_uid)
        _check_parents(target, "fresh worker provider auth", allowed_owner_uids={0, worker_uid})
        return target
    except BaseException as exc:
        try:
            _remove_provider_auth_material(target, directories)
        except CheckError as cleanup_exc:
            raise cleanup_exc from exc
        if isinstance(exc, CheckError):
            raise
        raise CheckError(f"could not provision the fresh provider auth file: {exc}") from exc


def _scrub_provider_auth(path: Path, auth_bytes: bytes) -> None:
    """Remove credentials while tolerating legitimate disposable runtime state."""
    assert ACTIVE_WORKSPACE_ROOT is not None
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise CheckError(f"could not scrub disposable provider auth file: {exc}") from exc
    if path.exists() or path.is_symlink():
        raise CheckError("disposable provider auth file remains after scrub")
    try:
        payload = json.loads(auth_bytes.decode("utf-8"))
        credential = payload[AUTH_PROVIDER]["key"].encode("utf-8")
    except (UnicodeError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise CheckError("provisioned provider auth bytes cannot be checked for cleanup") from exc
    for root, _directories, files in os.walk(ACTIVE_WORKSPACE_ROOT, followlinks=False):
        for name in files:
            candidate = Path(root) / name
            try:
                info = candidate.lstat()
                if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                    continue
                content = candidate.read_bytes()
            except OSError as exc:
                raise CheckError(f"could not verify disposable provider cleanup: {exc}") from exc
            if auth_bytes in content or credential in content:
                raise CheckError("provider credential bytes remain in disposable workspace")


def _create_fresh_workspace(run_id: str) -> Path:
    """Create a disposable per-run workspace; directory hygiene, not a security gate."""
    global ACTIVE_WORKSPACE_ROOT
    target = WORKSPACE_PARENT / run_id
    try:
        target.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise CheckError("fresh workspace already exists") from exc
    try:
        worker_uid = EXPECTED_WORKER_UID if EXPECTED_WORKER_UID is not None else pwd.getpwnam(WORKER_USER).pw_uid
        os.chown(target, worker_uid, -1)
        os.chmod(target, 0o700)
        _check_path(target, 0o700, "fresh run workspace", directory=True, owner_uid=worker_uid)
        _check_parents(target, "fresh run workspace")
    except Exception:
        try:
            target.rmdir()
        except OSError:
            pass
        raise
    ACTIVE_WORKSPACE_ROOT = target
    return target


def _run_worker(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(RUNUSER), "--user", WORKER_USER, "--", *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False, timeout=10)


def _contained_probe() -> dict[str, Any]:
    """Prove the worker boundary before spending on OpenCode: cheap, mechanical,
    answers a distinct question ("not obviously dangerous to assign this")."""
    assert ACTIVE_WORKSPACE_ROOT is not None
    accessible = _run_worker(["/run/current-system/sw/bin/test", "-d", str(ACTIVE_WORKSPACE_ROOT)])
    writable = _run_worker(["/run/current-system/sw/bin/test", "-w", str(ACTIVE_WORKSPACE_ROOT)])
    groups = _run_worker(["/run/current-system/sw/bin/id", "-Gn"])
    version = _run_worker([str(OPENCODE), "--version"])
    if accessible.returncode != 0 or writable.returncode != 0 or version.returncode != 0 or version.stdout.strip() != EXPECTED_CLI_VERSION:
        raise CheckError("contained worker boundary probe failed")
    if set(groups.stdout.split()) != {"agentworker", "agentdispatch"}:
        raise CheckError("contained worker groups are not the exact reviewed set")
    config_dirs = _run_worker([str(MKDIR), "-p", str(ACTIVE_WORKSPACE_ROOT / ".config"), str(ACTIVE_WORKSPACE_ROOT / ".cache")])
    if config_dirs.returncode != 0:
        raise CheckError("contained worker could not create its disposable config/cache directories")
    marker = ACTIVE_WORKSPACE_ROOT / ".agentops-roundtrip"
    try:
        created = _run_worker([str(TOUCH), str(marker)])
        if created.returncode != 0 or not marker.is_file():
            raise CheckError("contained workspace round-trip failed")
    finally:
        try:
            marker.unlink()
        except FileNotFoundError:
            pass
    return {"probe_id": "contained-identity", "status": "pass", "worker_identity": WORKER_USER, "exact_groups": ["agentworker", "agentdispatch"], "opencode_version": version.stdout.strip()}


def _load_config(provider: str, model: str, agent: str) -> dict[str, Any]:
    """Read route/budgets/containment defaults from the checked-in corpus.

    No digest pinning, no root-owned install tree, no lockstep schema
    freeze: this is a plain config file the operator can edit and rerun
    against, not an attestation input.
    """
    try:
        corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CheckError(f"cannot load the admission-check config: {exc}") from exc
    if not isinstance(corpus, dict) or corpus.get("schema_version") != "opencode-admission-check/v1":
        raise CheckError("admission-check config schema is not opencode-admission-check/v1")
    route = corpus.get("route")
    budgets = corpus.get("budgets")
    containment = corpus.get("containment")
    if not isinstance(route, dict) or not isinstance(budgets, dict) or not isinstance(containment, dict):
        raise CheckError("admission-check config is missing route, budgets, or containment")
    if route.get("provider") != provider or route.get("model") != model or route.get("agent") != agent:
        raise CheckError(f"config has no reviewed route for {provider}/{model} agent {agent}")
    return {"route": route, "budgets": budgets, "containment": containment}


def _event_tokens(event: dict[str, Any]) -> int:
    """Extract one provider step-finish total; missing usage fails closed."""
    usage = event.get("usage")
    if usage is None and isinstance(event.get("part"), dict):
        usage = event["part"].get("usage")
        if usage is None and isinstance(event["part"].get("tokens"), dict):
            tokens = event["part"]["tokens"]
            components = [tokens.get(key, 0) for key in ("input", "output", "reasoning")]
            if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in components):
                raise CheckError("OpenCode step-finish tokens are not bounded integers")
            return sum(components)
    if not isinstance(usage, dict):
        raise CheckError("provider event has no usage object")
    total = usage.get("total_tokens", usage.get("totalTokens"))
    if not isinstance(total, int) or isinstance(total, bool) or total < 0:
        raise CheckError("provider event has no bounded integer total token count")
    return total


def _provider_event(event: dict[str, Any]) -> bool:
    return event.get("type") == "step_finish" and isinstance(event.get("sessionID"), str) and SAFE_PROVIDER_ID.fullmatch(event["sessionID"]) is not None


def _provider_usage(event: dict[str, Any]) -> tuple[float, float, float]:
    part = event.get("part") if isinstance(event.get("part"), dict) else {}
    usage = event.get("usage") or part.get("usage")
    if usage is None and isinstance(part.get("tokens"), dict):
        tokens = part["tokens"]
        baseline = tokens.get("input")
        observed = sum(tokens.get(key, 0) for key in ("input", "output", "reasoning"))
        cost = part.get("cost")
    elif isinstance(usage, dict):
        baseline = usage.get("baseline_units")
        observed = usage.get("observed_units")
        cost = usage.get("cost_usd")
    else:
        raise CheckError("OpenCode step-finish has no provider usage structure")
    if any(not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) for value in (baseline, observed, cost)):
        raise CheckError("OpenCode provider usage is not finite numeric evidence")
    return float(baseline), float(observed), float(cost)


def _run_opencode_once(*, command: list[str], environment: dict[str, str], popen: Callable[..., Any] = subprocess.Popen) -> dict[str, Any]:
    """Run one contained command and terminate on either ceiling.

    At least one clean completion event is required; sanity-bound every
    one observed. This is deliberately not "exactly one, hard-fail
    otherwise" -- that exact-count strictness is the same over-fit
    pattern that produced a false diagnosis earlier in this corpus's
    history (a genuine multi-step tool-use response legitimately emits
    more than one step-finish).
    """
    expected_prefix = [str(RUNUSER), "--user", WORKER_USER, "--", str(OPENCODE), "run"]
    if command[:len(expected_prefix)] != expected_prefix:
        raise CheckError("checker command is not the exact contained OpenCode run")
    process = popen(command, cwd=str(ACTIVE_WORKSPACE_ROOT), env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
    events: list[dict[str, Any]] = []
    observed = 0
    baseline = None
    observed_cost = 0.0
    timed_out = False

    def stop_for_wall_timeout() -> None:
        nonlocal timed_out
        timed_out = True
        process.kill()

    wall_timer = threading.Timer(HARD_WALL_SECONDS, stop_for_wall_timeout)
    wall_timer.daemon = True
    wall_timer.start()
    try:
        assert process.stdout is not None
        for line in process.stdout:
            try:
                event = json.loads(line)
            except (UnicodeError, json.JSONDecodeError) as exc:
                process.kill()
                raise CheckError("OpenCode emitted a non-JSON event") from exc
            if not isinstance(event, dict):
                process.kill()
                raise CheckError("OpenCode emitted a non-object event")
            if _provider_event(event):
                event_baseline, event_observed_units, event_cost = _provider_usage(event)
                if event_baseline <= 0:
                    process.kill()
                    raise CheckError("provider event has no positive bounded usage baseline")
                if not isinstance(event_observed_units, (int, float)) or isinstance(event_observed_units, bool) or event_observed_units < 0 or event_observed_units > 2 * event_baseline:
                    process.kill()
                    raise CheckError("provider event usage exceeds the two-times constraint")
                baseline = event_baseline if baseline is None else baseline
                if event_cost < 0:
                    process.kill()
                    raise CheckError("provider event has no bounded cost input")
                observed_cost = max(observed_cost, float(event_cost))
                if observed_cost > MAX_COST_USD:
                    process.kill()
                    raise CheckError("provider cost ceiling exceeded during execution")
                observed = max(observed, _event_tokens(event))
                if observed > HARD_TOKENS:
                    process.kill()
                    raise CheckError("hard token ceiling exceeded during execution")
                if observed > SOFT_TOKENS:
                    process.kill()
                    raise CheckError("soft token ceiling exceeded during execution")
                events.append({"session_id": event["sessionID"], "usage_total_tokens": observed, "usage_baseline_units": event_baseline, "usage_observed_units": event_observed_units})
        process.stdout.close()
    finally:
        wall_timer.cancel()
        return_code = process.wait(timeout=30)
    if timed_out:
        raise CheckError("contained OpenCode run exceeded the hard wall timeout")
    if return_code != 0:
        raise CheckError(f"contained OpenCode run failed with exit {return_code}")
    if not events:
        raise CheckError("no clean completion event observed")
    last = events[-1]
    return {
        "observed_tokens": observed,
        "usage_baseline": baseline,
        "usage_observed": last["usage_observed_units"],
        "usage_multiplier": last["usage_observed_units"] / baseline if baseline else None,
        "cost_usd": observed_cost,
        "session_id": last["session_id"],
        "completion_events": len(events),
    }


def _parse_sanitized_export(stdout: str, session_id: str, *, provider: str, model: str) -> dict[str, Any]:
    """Independently cross-check routability from a separately fetched export,
    not the live event stream. Loosened from an exact two-part grammar match
    (over-fit to one harness snapshot) to: session identity matches, at least
    one assistant message exists, provider/model/finish are exact, and both a
    real text part and a completion ("step-finish") part occurred somewhere
    in it -- not merely a bare step-finish with no generated content, which
    would satisfy "routable" and "cost-sane" without ever answering the
    check's second question (does it produce a reasonable output)."""
    try:
        exported = json.loads(stdout)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CheckError(f"sanitized OpenCode export is not JSON: {exc}") from exc
    if not isinstance(exported, dict) or not isinstance(exported.get("info"), dict) or exported["info"].get("id") != session_id:
        raise CheckError("sanitized OpenCode export changed session identity")
    messages = exported.get("messages")
    if not isinstance(messages, list) or not messages:
        raise CheckError("sanitized OpenCode export has no messages")
    assistants = [message for message in messages if isinstance(message, dict) and isinstance(message.get("info"), dict) and message["info"].get("role") == "assistant"]
    if not assistants:
        raise CheckError("sanitized OpenCode export has no assistant evidence")
    info = assistants[-1]["info"]
    if info.get("providerID") != provider or info.get("modelID") != model or info.get("finish") != "stop":
        raise CheckError("sanitized OpenCode export provider/model/finish is not exact")
    parts = assistants[-1].get("parts")
    part_types = {part.get("type") for part in parts if isinstance(part, dict)} if isinstance(parts, list) else set()
    if "step-finish" not in part_types:
        raise CheckError("sanitized OpenCode export has no completion evidence")
    if "text" not in part_types:
        raise CheckError("sanitized OpenCode export has no generated text content")
    return {"providerID": info["providerID"], "modelID": info["modelID"], "finish": info["finish"]}


def _sanitized_export(session_id: str, environment: dict[str, str], *, provider: str, model: str) -> dict[str, Any]:
    completed = subprocess.run([str(RUNUSER), "--user", WORKER_USER, "--", str(OPENCODE), "export", session_id, "--sanitize"], cwd=str(ACTIVE_WORKSPACE_ROOT), env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=False, timeout=30)
    if completed.returncode != 0:
        raise CheckError("contained sanitized OpenCode export failed")
    return _parse_sanitized_export(completed.stdout, session_id, provider=provider, model=model)


def _cooldown_check(provider: str, model: str, *, force: bool) -> None:
    """Optional, overridable guard against accidental loop-spend. Not a
    security gate -- --force always bypasses it."""
    if force or not RUN_REPORT_ROOT.is_dir():
        return
    prefix = f"opencode-{provider}-{model}-"
    candidates = sorted(RUN_REPORT_ROOT.glob(f"{prefix}*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not candidates:
        return
    age = datetime.now(timezone.utc).timestamp() - candidates[0].stat().st_mtime
    if age < COOLDOWN_SECONDS:
        raise CheckError(f"last check for {provider}/{model} was {age:.0f}s ago (cooldown {COOLDOWN_SECONDS}s) -- pass --force to bypass")


def check_admission(*, provider: str, model: str, agent: str, prompt: str, force: bool = False) -> dict[str, Any]:
    _cooldown_check(provider, model, force=force)
    config = _load_config(provider, model, agent)
    if EXPECTED_WORKER_UID is None:
        try:
            pwd.getpwnam(WORKER_USER)
        except KeyError as exc:
            raise CheckError(f"contained worker identity is unavailable: {WORKER_USER}") from exc
    run_id = "run-" + hashlib.sha256(f"{provider}{model}{agent}{_now()}{os.getpid()}".encode()).hexdigest()[:32]
    _create_fresh_workspace(run_id)
    started = _now()
    containment = _contained_probe()
    auth_path: Path | None = None
    auth_bytes = b""
    try:
        auth_bytes = _read_provider_auth()
        auth_path = _provision_provider_auth(auth_bytes)
        environment = {
            "PATH": "/run/current-system/sw/bin",
            "HOME": str(ACTIVE_WORKSPACE_ROOT), "TMPDIR": str(ACTIVE_WORKSPACE_ROOT),
            "XDG_CONFIG_HOME": str(ACTIVE_WORKSPACE_ROOT / ".config"), "XDG_CACHE_HOME": str(ACTIVE_WORKSPACE_ROOT / ".cache"), "XDG_DATA_HOME": str(ACTIVE_WORKSPACE_ROOT / ".local" / "share"),
            "NO_COLOR": "1", "OPENCODE_AUTH_CONTENT": auth_bytes.decode("utf-8"), "OPENCODE_CONFIG_CONTENT": CONFIG.read_text(encoding="utf-8"),
        }
        command = [str(RUNUSER), "--user", WORKER_USER, "--", str(OPENCODE), "run", prompt, "--agent", agent, "--format", "json", "--title", f"admission-check-{run_id}"]
        execution = _run_opencode_once(command=command, environment=environment)
        export = _sanitized_export(execution["session_id"], environment, provider=provider, model=model)
    finally:
        if auth_path is not None:
            _scrub_provider_auth(auth_path, auth_bytes)
    finished = _now()
    budgets = config["budgets"]
    cost_sane = execution["cost_usd"] <= budgets.get("max_cost_usd", MAX_COST_USD) and (execution["usage_multiplier"] is None or execution["usage_multiplier"] <= budgets.get("usage_multiplier_ceiling", 2))
    result = {
        "schema_version": "opencode-admission-check-result/v1",
        "started_at": started, "finished_at": finished,
        "provider": provider, "model": model, "agent": agent,
        "routable": True, "export_cross_check": export,
        "cost_sane": cost_sane, "usage_baseline": execution["usage_baseline"], "usage_observed": execution["usage_observed"], "usage_multiplier": execution["usage_multiplier"], "cost_usd": execution["cost_usd"], "tokens": execution["observed_tokens"], "completion_events": execution["completion_events"],
        "containment": containment,
        "pass": cost_sane,
    }
    RUN_REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    report_path = RUN_REPORT_ROOT / f"opencode-{provider}-{model}-{started[:10]}.json"
    report_path.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    result["run_report"] = str(report_path)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--agent", required=True)
    parser.add_argument("--prompt", default="Reply with the bounded admission-check acknowledgement.")
    parser.add_argument("--force", action="store_true", help="bypass the accidental-loop-spend cooldown")
    args = parser.parse_args(argv)
    try:
        result = check_admission(provider=args.provider, model=args.model, agent=args.agent, prompt=args.prompt, force=args.force)
    except (OSError, CheckError, subprocess.SubprocessError) as exc:
        print(json.dumps({"pass": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
