#!/usr/bin/env python3
"""Privileged, one-shot OpenCode qualification runner.

This program is intentionally separate from admission.  It is installed
root-owned on a workstation, reads the private signing key only here, invokes
one contained OpenCode request, enforces both token ceilings while consuming
JSON events, and emits a sealed execution record plus a one-time nonce ledger
entry.  The admission validator only needs the public key and allowed-signers
file; it never accepts or reads the private key.

The command is deliberately not run by repository validation.  A workstation
operator runs it once, after independent review and the offline gates pass.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import pwd
import re
import secrets
import stat
import subprocess
import sys
import threading
from typing import Any, Callable


INSTALL_ROOT = Path("/etc/agentops/opencode-qualification")
CORPUS = INSTALL_ROOT / "corpus.json"
CORPUS_DIGEST_FILE = INSTALL_ROOT / "corpus.sha256"
CONFIG = INSTALL_ROOT / "opencode.hybrid.json"
PROFILE = INSTALL_ROOT / "profile.json"
POLICY = INSTALL_ROOT / "hybrid-dispatch.v1.json"
MANIFEST = INSTALL_ROOT / "agentops.dispatch.json"
STATIC_EVIDENCE_ROOT = INSTALL_ROOT / "preflight-evidence"
RUNNER_ID = "agentops-opencode-qualification-runner/v1"
SIGNATURE_NAMESPACE = "agentops-opencode-qualification"
SSH_KEYGEN = "/run/current-system/sw/bin/ssh-keygen"
PRIVATE_KEY = Path("/var/lib/agentops/opencode-qualification/runner.key")
PUBLIC_KEY = Path("/var/lib/agentops/opencode-qualification/runner.pub")
ALLOWED_SIGNERS = Path("/var/lib/agentops/opencode-qualification/allowed_signers")
RECORD_ROOT = Path("/var/lib/agentops/opencode-qualification/records")
LEDGER_ROOT = Path("/var/lib/agentops/opencode-qualification/ledger")
ATTEMPT_SENTINEL = LEDGER_ROOT / "packet.attempted"
EVIDENCE_ROOT = Path("/var/lib/agentops/opencode-qualification/evidence")
AUTH_SOURCE = Path("/var/lib/agentops/opencode-qualification/provider-auth.json")
WORKSPACE_ROOT = Path("/var/lib/agentops/opencode-qualification/workspace")
WORKSPACE_PARENT = Path("/var/lib/agentops/opencode-qualification/workspaces")
OPENCODE = Path("/run/current-system/sw/bin/opencode")
RUNNER_PATH = Path("/usr/local/sbin/agentops-opencode-qualification-runner")
RUNUSER = Path("/run/current-system/sw/bin/runuser")
TOUCH = Path("/run/current-system/sw/bin/touch")
MKDIR = Path("/run/current-system/sw/bin/mkdir")
PINNED_EXECUTABLE_NAMES = ("OPENCODE", "RUNUSER", "TOUCH", "MKDIR", "SSH_KEYGEN")
WORKER_USER = "agentworker"
SOFT_TOKENS = 500_000
HARD_TOKENS = 1_000_000
MAX_COST_USD = 3.0
FRESHNESS_SECONDS = 900
HARD_WALL_SECONDS = 120
PACKET_ACTION = "opencode-provider-qualification-v1"
SAFE_PROVIDER_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
SAFE_PROVIDER_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
EXPECTED_OWNER_UID = 0
EXPECTED_EUID = 0
EXPECTED_WORKER_UID: int | None = None
ACTIVE_WORKSPACE_ROOT = WORKSPACE_ROOT
PINNED_PREFLIGHT_EVIDENCE: dict[str, str] = {}
PINNED_RUNNER_DIGEST = ""
PINNED_OPENCODE_DIGEST = ""
PINNED_EXECUTABLE_TARGETS: dict[Path, tuple[Path, tuple[tuple[int, ...], ...]]] = {}
PINNED_EXECUTABLE_PARENT_OWNER_UID = 0
NIX_STORE = Path("/nix/store")
PINNED_CONFIG_DIGEST = "sha256:dc8e846c1cf22e536a35b3d842b518e194c2fde355b87e1b677ca82570ae566c"
PINNED_PROFILE_DIGEST = "sha256:38d17f648ffc6831752fd6250638648580fbfc478cb4789b732c8ae95e25b84a"
PINNED_POLICY_DIGEST = "sha256:dc9fcb92f1c4dfceecc5372f84cadeb1b58aad026a45ea0379a5f7ab196555a6"
PINNED_MANIFEST_DIGEST = "sha256:6bfa1a88618a8246b20a2b30af565bb5b828bfb6608611c062d017ba79958ab6"
PINNED_PUBLIC_KEY_DIGEST = "sha256:309ddaae451d99a2350bdbaff31f9e6bfbd9b1f462bb5783e00f26ca41b49a5a"
PINNED_ALLOWED_SIGNERS_DIGEST = "sha256:0192272e12634cc312f56e3b32789be3a0e99e6c4b9295e5b1588bd13cd970a0"
AUTH_PROVIDER = "opencode-go"
AUTH_TYPE = "api"
REQUIRED_PROBES = ("cli-version", "run-help", "contained-worktree-model-list", "explicit-tool-enumeration", "message-before-file", "json-events", "stable-session-identity", "session-continuation", "contained-identity", "no-tools-finalizer", "provider-qualification")


class RunnerError(RuntimeError):
    """A runner invariant failed; no candidate record may be admitted."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _digest(value: Any) -> str:
    return _digest_bytes(_canonical(value))


def _file_digest(path: Path) -> str:
    target = _executable_path(path) if path in PINNED_EXECUTABLE_TARGETS else path
    digest = "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
    if path in PINNED_EXECUTABLE_TARGETS:
        checked_target, fingerprints = PINNED_EXECUTABLE_TARGETS[path]
        label = next((label for candidate, label in _pinned_executables() if candidate == path), f"pinned executable {path}")
        _assert_pinned_executable_stable(path, checked_target, fingerprints, label)
    return digest


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _bundle_digest(artifacts: dict[str, dict[str, str]]) -> str:
    return _digest({name: {"artifact": item["artifact"], "digest": item["digest"]} for name, item in sorted(artifacts.items())})


def _receipt_binding_digest(receipt: dict[str, Any]) -> str:
    binding = dict(receipt)
    binding.pop("runner_record_digest", None)
    binding.pop("runner_signature_digest", None)
    return _digest(binding)


def _load_static_evidence(name: str) -> tuple[dict[str, Any], str]:
    path = STATIC_EVIDENCE_ROOT / name
    _check_path(path, 0o400, f"static {name} evidence")
    _check_parents(path, f"static {name} evidence")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RunnerError(f"static {name} evidence is not JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise RunnerError(f"static {name} evidence is not an object")
    digest = _file_digest(path)
    if PINNED_PREFLIGHT_EVIDENCE.get(name) != digest:
        raise RunnerError(f"static {name} evidence bytes are not the pinned preflight bytes")
    return value, digest


def _check_path(path: Path, mode: int, label: str, *, directory: bool = False, owner_uid: int | None = None) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise RunnerError(f"{label} is unavailable: {exc}") from exc
    if info.st_uid != (EXPECTED_OWNER_UID if owner_uid is None else owner_uid):
        raise RunnerError(f"{label} has an unexpected owner")
    if stat.S_IMODE(info.st_mode) != mode:
        raise RunnerError(f"{label} must have mode {mode:04o}")
    if directory and not stat.S_ISDIR(info.st_mode):
        raise RunnerError(f"{label} must be a directory")
    if not directory and not stat.S_ISREG(info.st_mode):
        raise RunnerError(f"{label} must be a regular file")


def _stat_fingerprint(info: os.stat_result) -> tuple[int, ...]:
    """Capture metadata needed to detect a target change across a check."""
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _pinned_executables() -> tuple[tuple[Path, str], ...]:
    """Return the exact executable set from ``verify_installation``."""
    labels = {
        "OPENCODE": "pinned OpenCode executable",
        "RUNUSER": "pinned runuser executable",
        "TOUCH": "pinned touch executable",
        "MKDIR": "pinned mkdir executable",
        "SSH_KEYGEN": "pinned ssh-keygen executable",
    }
    return tuple((Path(globals()[name]), labels[name]) for name in PINNED_EXECUTABLE_NAMES)


def _check_resolved_executable_parents(target: Path, label: str) -> tuple[tuple[int, ...], ...]:
    """Check every parent of a resolved executable target.

    The only writable-parent exception is the host's Nix store: its exact
    root-owned sticky ``01775`` mode is accepted only while its filesystem is
    read-only, which prevents the runner identity from replacing an entry.
    This exception is deliberately path-, owner-, mode-, and mount-specific;
    arbitrary sticky or writable directories remain rejected.
    """
    fingerprints: list[tuple[int, ...]] = []
    current = target.parent
    while True:
        try:
            info = current.lstat()
        except OSError as exc:
            raise RunnerError(f"{label} has an unavailable resolved parent: {exc}") from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise RunnerError(f"{label} has an unsafe resolved parent")
        if info.st_uid not in {0, PINNED_EXECUTABLE_PARENT_OWNER_UID}:
            raise RunnerError(f"{label} has a non-root resolved parent")
        mode = stat.S_IMODE(info.st_mode)
        if mode & 0o022:
            try:
                read_only = bool(os.statvfs(current).f_flag & os.ST_RDONLY)
            except OSError as exc:
                raise RunnerError(f"{label} cannot inspect resolved parent mount: {exc}") from exc
            nix_store_exception = current == NIX_STORE and mode == 0o1775 and read_only
            if not nix_store_exception:
                raise RunnerError(f"{label} has a writable resolved parent")
        fingerprints.append(_stat_fingerprint(info))
        if current.parent == current:
            return tuple(fingerprints)
        current = current.parent


def _check_pinned_executable(path: Path, label: str) -> tuple[Path, tuple[tuple[int, ...], ...]]:
    """Validate a configured executable's target and resolved parent chain.

    The configured path may be a symlink, but its resolved final target must be
    root-owned, regular, executable, and free of group/world write bits. Every
    parent of that resolved target is lstat-checked, and the target plus parent
    metadata is checked again before use so a changed link, target, parent, or
    Nix-store mount state is rejected.
    """
    try:
        target = path.resolve(strict=True)
        if path.resolve(strict=True) != target:
            raise RunnerError(f"{label} changed while resolving its target")
        target_info = os.stat(target, follow_symlinks=False)
        configured_info = os.stat(path, follow_symlinks=True)
    except (OSError, RuntimeError) as exc:
        raise RunnerError(f"{label} is unavailable: {exc}") from exc
    fingerprint = _stat_fingerprint(target_info)
    if fingerprint != _stat_fingerprint(configured_info):
        raise RunnerError(f"{label} changed while resolving its target")
    if target_info.st_uid != EXPECTED_OWNER_UID:
        raise RunnerError(f"{label} target has an unexpected owner")
    if not stat.S_ISREG(target_info.st_mode):
        raise RunnerError(f"{label} target must be a regular file")
    if not target_info.st_mode & 0o111:
        raise RunnerError(f"{label} target must be executable")
    if target_info.st_mode & 0o022:
        raise RunnerError(f"{label} target must not be group/world-writable")
    parent_fingerprints = _check_resolved_executable_parents(target, label)
    return target, (fingerprint, *parent_fingerprints)


def _assert_pinned_executable_stable(path: Path, target: Path, fingerprints: tuple[tuple[int, ...], ...], label: str) -> None:
    """Recheck the resolved target and every resolved parent before use."""
    try:
        if path.resolve(strict=True) != target:
            raise RunnerError(f"{label} changed its resolved target")
        target_info = os.stat(target, follow_symlinks=False)
        configured_info = os.stat(path, follow_symlinks=True)
    except (OSError, RuntimeError) as exc:
        raise RunnerError(f"{label} became unavailable: {exc}") from exc
    if _stat_fingerprint(target_info) != fingerprints[0] or _stat_fingerprint(configured_info) != fingerprints[0]:
        raise RunnerError(f"{label} changed after validation")
    try:
        current_fingerprints = _check_resolved_executable_parents(target, label)
    except OSError as exc:
        raise RunnerError(f"{label} has an unavailable resolved parent: {exc}") from exc
    if current_fingerprints != fingerprints[1:]:
        raise RunnerError(f"{label} changed a resolved parent after validation")


def _executable_path(path: Path) -> Path:
    """Return the checked target, or the configured path for unvalidated calls."""
    checked = PINNED_EXECUTABLE_TARGETS.get(path)
    if checked is None:
        return path
    target, fingerprints = checked
    label = next((label for candidate, label in _pinned_executables() if candidate == path), f"pinned executable {path}")
    _assert_pinned_executable_stable(path, target, fingerprints, label)
    return target


def _check_parents(path: Path, label: str, *, allowed_owner_uids: set[int] | None = None) -> None:
    allowed_owner_uids = {0, EXPECTED_OWNER_UID} if allowed_owner_uids is None else set(allowed_owner_uids)
    current = path.parent
    while True:
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode) or info.st_uid not in allowed_owner_uids:
            raise RunnerError(f"{label} has an unsafe parent")
        mode = stat.S_IMODE(info.st_mode)
        if mode & 0o022 and not (mode & stat.S_ISVTX):
            raise RunnerError(f"{label} has a writable parent")
        if current.parent == current:
            return
        current = current.parent


def _read_provider_auth() -> bytes:
    """Validate the fixed, root-only auth input without exposing its value."""
    _check_path(AUTH_SOURCE, 0o400, "provider auth source")
    _check_parents(AUTH_SOURCE, "provider auth source")
    try:
        payload = json.loads(AUTH_SOURCE.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RunnerError(f"provider auth source is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict) or set(payload) != {AUTH_PROVIDER} or not isinstance(payload[AUTH_PROVIDER], dict) or set(payload[AUTH_PROVIDER]) != {"type", "key"}:
        raise RunnerError("provider auth source is not the native OpenCode auth object")
    if payload[AUTH_PROVIDER]["type"] != AUTH_TYPE or not isinstance(payload[AUTH_PROVIDER]["key"], str) or not 1 <= len(payload[AUTH_PROVIDER]["key"]) <= 4096:
        raise RunnerError("provider auth source is not the exact native API credential")
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
        raise RunnerError("could not completely scrub disposable provider auth material: " + "; ".join(failures))


def _provision_provider_auth(auth_bytes: bytes) -> Path:
    """Copy the approved credential into a worker-owned, transactional XDG tree."""
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
        except RunnerError as cleanup_exc:
            raise cleanup_exc from exc
        if isinstance(exc, RunnerError):
            raise
        raise RunnerError(f"could not provision the fresh provider auth file: {exc}") from exc


def _scrub_provider_auth(path: Path, auth_bytes: bytes) -> None:
    """Remove credentials while tolerating legitimate disposable runtime state."""
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise RunnerError(f"could not scrub disposable provider auth file: {exc}") from exc
    if path.exists() or path.is_symlink():
        raise RunnerError("disposable provider auth file remains after scrub")
    try:
        payload = json.loads(auth_bytes.decode("utf-8"))
        credential = payload[AUTH_PROVIDER]["key"].encode("utf-8")
    except (UnicodeError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RunnerError("provisioned provider auth bytes cannot be checked for cleanup") from exc
    for root, directories, files in os.walk(ACTIVE_WORKSPACE_ROOT, followlinks=False):
        for name in files:
            candidate = Path(root) / name
            try:
                info = candidate.lstat()
                if stat.S_ISLNK(info.st_mode):
                    continue
                if not stat.S_ISREG(info.st_mode):
                    continue
                content = candidate.read_bytes()
            except OSError as exc:
                raise RunnerError(f"could not verify disposable provider cleanup: {exc}") from exc
            if auth_bytes in content or credential in content:
                raise RunnerError("provider credential bytes remain in disposable workspace")


def verify_installation() -> None:
    global PINNED_EXECUTABLE_TARGETS
    if os.geteuid() != EXPECTED_EUID:
        raise RunnerError("the one-shot runner must execute as root")
    PINNED_EXECUTABLE_TARGETS = {}
    _check_path(PRIVATE_KEY, 0o400, "runner private key")
    _check_path(AUTH_SOURCE, 0o400, "provider auth source")
    _check_path(PUBLIC_KEY, 0o444, "runner public key")
    _check_path(ALLOWED_SIGNERS, 0o444, "runner allowed-signers file")
    _check_path(RECORD_ROOT, 0o700, "runner record root", directory=True)
    _check_path(LEDGER_ROOT, 0o700, "runner ledger root", directory=True)
    _check_path(EVIDENCE_ROOT, 0o700, "runner evidence root", directory=True)
    try:
        worker_uid = EXPECTED_WORKER_UID if EXPECTED_WORKER_UID is not None else pwd.getpwnam(WORKER_USER).pw_uid
    except KeyError as exc:
        raise RunnerError(f"contained worker identity is unavailable: {WORKER_USER}") from exc
    # The parent is root-owned and non-listable, but must be searchable so the
    # worker can reach its unique 0700 child without gaining access to state.
    _check_path(WORKSPACE_PARENT, 0o711, "runner workspace parent", directory=True, owner_uid=EXPECTED_OWNER_UID)
    _check_path(INSTALL_ROOT, 0o700, "runner installation root", directory=True)
    for path, label in ((CORPUS, "installed corpus"), (CONFIG, "installed OpenCode config"), (PROFILE, "installed profile"), (POLICY, "installed policy"), (MANIFEST, "installed manifest")):
        _check_path(path, 0o400, label)
    _check_path(STATIC_EVIDENCE_ROOT, 0o700, "static preflight evidence root", directory=True)
    executable_targets = {path: _check_pinned_executable(path, label) for path, label in _pinned_executables()}
    _check_path(RUNNER_PATH, 0o755, "installed runner executable")
    for path, label in ((INSTALL_ROOT, "runner installation root"), (CORPUS, "installed corpus"), (CONFIG, "installed OpenCode config"), (PROFILE, "installed profile"), (POLICY, "installed policy"), (MANIFEST, "installed manifest"), (STATIC_EVIDENCE_ROOT, "static preflight evidence root"), (PRIVATE_KEY, "runner private key"), (AUTH_SOURCE, "provider auth source"), (PUBLIC_KEY, "runner public key"), (ALLOWED_SIGNERS, "runner allowed-signers file"), (RECORD_ROOT, "runner record root"), (LEDGER_ROOT, "runner ledger root"), (EVIDENCE_ROOT, "runner evidence root"), (WORKSPACE_PARENT, "runner workspace parent"), (ATTEMPT_SENTINEL, "attempt sentinel")):
        _check_parents(path, label)
    _check_path(CORPUS_DIGEST_FILE, 0o400, "installed corpus digest pin")
    _check_parents(CORPUS_DIGEST_FILE, "installed corpus digest pin")
    _read_provider_auth()
    if _file_digest(PUBLIC_KEY) != PINNED_PUBLIC_KEY_DIGEST or _file_digest(ALLOWED_SIGNERS) != PINNED_ALLOWED_SIGNERS_DIGEST:
        raise RunnerError("installed public verification material is not the pinned material")
    PINNED_EXECUTABLE_TARGETS = executable_targets
    derived = subprocess.run([str(_executable_path(Path(SSH_KEYGEN))), "-y", "-f", str(PRIVATE_KEY)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False, timeout=5)
    if derived.returncode != 0 or derived.stdout.strip().split()[:2] != PUBLIC_KEY.read_text(encoding="utf-8").strip().split()[:2]:
        raise RunnerError("runner private key does not match the pinned public key")


def _create_fresh_workspace(run_id: str) -> Path:
    """Create and prove an empty disposable workspace before reserving the packet."""
    global ACTIVE_WORKSPACE_ROOT
    target = WORKSPACE_PARENT / run_id
    try:
        target.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise RunnerError("fresh workspace already exists") from exc
    try:
        worker_uid = EXPECTED_WORKER_UID if EXPECTED_WORKER_UID is not None else pwd.getpwnam(WORKER_USER).pw_uid
        os.chown(target, worker_uid, -1)
        os.chmod(target, 0o700)
        _check_path(target, 0o700, "fresh run workspace", directory=True, owner_uid=worker_uid)
        _check_parents(target, "fresh run workspace")
        if any(os.scandir(target)):
            raise RunnerError("fresh run workspace is not empty")
    except Exception:
        try:
            target.rmdir()
        except OSError:
            pass
        raise
    ACTIVE_WORKSPACE_ROOT = target
    return target


def _contained_probe() -> dict[str, Any]:
    """Prove the worker boundary and workspace round-trip before OpenCode."""
    def run_worker(args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run([str(_executable_path(RUNUSER)), "--user", WORKER_USER, "--", *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False, timeout=10)

    accessible = run_worker(["/run/current-system/sw/bin/test", "-d", str(ACTIVE_WORKSPACE_ROOT)])
    writable = run_worker(["/run/current-system/sw/bin/test", "-w", str(ACTIVE_WORKSPACE_ROOT)])
    coordinator_writable = run_worker(["/run/current-system/sw/bin/test", "-w", str(RECORD_ROOT)])
    groups = run_worker(["/run/current-system/sw/bin/id", "-Gn"])
    version = run_worker([str(_executable_path(OPENCODE)), "--version"])
    if accessible.returncode != 0 or writable.returncode != 0 or coordinator_writable.returncode != 1 or version.returncode != 0 or version.stdout.strip() != "1.18.4":
        raise RunnerError("contained worker boundary probe failed")
    if set(groups.stdout.split()) != {"agentworker", "agentdispatch"}:
        raise RunnerError("contained worker groups are not the exact reviewed set")
    config_dirs = run_worker([str(_executable_path(MKDIR)), "-p", str(ACTIVE_WORKSPACE_ROOT / ".config"), str(ACTIVE_WORKSPACE_ROOT / ".cache")])
    if config_dirs.returncode != 0:
        raise RunnerError("contained worker could not create its disposable config/cache directories")
    marker = ACTIVE_WORKSPACE_ROOT / ".agentops-roundtrip"
    try:
        if marker.exists():
            raise RunnerError("contained workspace round-trip marker already exists")
        created = run_worker([str(_executable_path(TOUCH)), str(marker)])
        if created.returncode != 0 or not marker.is_file():
            raise RunnerError("contained workspace round-trip failed")
    finally:
        try:
            marker.unlink()
        except FileNotFoundError:
            pass
    return {"probe_id": "contained-identity", "status": "pass", "worker_identity": WORKER_USER, "coordinator_write_denied": True, "workspace_round_trip": True, "exact_groups": ["agentworker", "agentdispatch"], "reads_contained": False}


def _load_packet() -> tuple[dict[str, Any], str]:
    global PINNED_PREFLIGHT_EVIDENCE, PINNED_RUNNER_DIGEST, PINNED_OPENCODE_DIGEST
    try:
        pinned_corpus_digest = CORPUS_DIGEST_FILE.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError) as exc:
        raise RunnerError(f"installed corpus digest pin is unavailable: {exc}") from exc
    if any(_file_digest(path) != expected for path, expected in ((CORPUS, pinned_corpus_digest), (CONFIG, PINNED_CONFIG_DIGEST), (PROFILE, PINNED_PROFILE_DIGEST), (POLICY, PINNED_POLICY_DIGEST), (MANIFEST, PINNED_MANIFEST_DIGEST))):
        raise RunnerError("installed corpus, profile, policy, manifest, or OpenCode config bytes are not pinned")
    try:
        corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RunnerError(f"cannot load the checked-in qualification packet: {exc}") from exc
    if not isinstance(corpus, dict) or corpus.get("schema_version") != "opencode-provider-qualification/v2":
        raise RunnerError("qualification corpus schema is not the reviewed v2 packet")
    live = corpus.get("live_run")
    packet = live.get("packet") if isinstance(live, dict) else None
    if not isinstance(packet, dict) or packet.get("action_id") != PACKET_ACTION or packet.get("attempts") != 1:
        raise RunnerError("qualification packet is not the exact one-attempt action")
    if packet.get("soft_token_ceiling") != SOFT_TOKENS or packet.get("hard_token_ceiling") != HARD_TOKENS:
        raise RunnerError("qualification packet ceilings are not exact")
    request = packet.get("request")
    if not isinstance(request, dict) or set(request) != {"prompt", "agent", "format"} or not isinstance(request["prompt"], str) or not request["prompt"] or request["agent"] != "ao-mechanical-bulk" or request["format"] != "json":
        raise RunnerError("qualification packet request is not the exact bounded request")
    if live.get("record_root") != str(RECORD_ROOT) or live.get("consumption_ledger_root") != str(LEDGER_ROOT) or live.get("evidence_root") != str(EVIDENCE_ROOT):
        raise RunnerError("qualification packet roots are not the configured roots")
    if live.get("provider_auth_source") != str(AUTH_SOURCE) or live.get("provider_auth_discovery") != "XDG_DATA_HOME/opencode/auth.json" or live.get("provider_auth_content_env") != "OPENCODE_AUTH_CONTENT" or live.get("provider_auth_provider") != AUTH_PROVIDER or live.get("provider_auth_type") != AUTH_TYPE:
        raise RunnerError("qualification packet provider auth is not the exact bounded input")
    if live.get("runner_path") != str(RUNNER_PATH) or live.get("opencode_path") != str(OPENCODE):
        raise RunnerError("qualification packet executable paths are not the configured paths")
    if _file_digest(RUNNER_PATH) != live.get("runner_digest") or _file_digest(OPENCODE) != live.get("opencode_digest"):
        raise RunnerError("installed runner or OpenCode bytes are not the pinned bytes")
    PINNED_RUNNER_DIGEST = live["runner_digest"]
    PINNED_OPENCODE_DIGEST = live["opencode_digest"]
    preflight = live.get("preflight_evidence")
    if not isinstance(preflight, dict) or set(preflight) != {"capability.json", "lifecycle.json", "overlay.json", "workspace.json"}:
        raise RunnerError("qualification preflight evidence pins are incomplete")
    PINNED_PREFLIGHT_EVIDENCE = dict(preflight)
    return packet, _digest(packet)


def issue_nonce(packet_digest: str, *, run_id: str | None = None, nonce: str | None = None) -> tuple[str, str, Path]:
    """Issue one nonce atomically; an existing nonce marker is never reused."""
    run_id = run_id or ("run-" + secrets.token_hex(16))
    nonce = nonce or ("nonce-" + secrets.token_hex(32))
    issued = LEDGER_ROOT / f"{nonce}.issued"
    payload = {
        "schema_version": "opencode-provider-qualification-nonce/v1",
        "runner_id": RUNNER_ID,
        "run_id": run_id,
        "nonce": nonce,
        "packet_digest": packet_digest,
        "issued_at": _now(),
        "attempts": 1,
        "consumed": False,
    }
    try:
        fd = os.open(issued, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
        with os.fdopen(fd, "wb") as stream:
            stream.write(_canonical(payload))
    except (FileExistsError, OSError) as exc:
        raise RunnerError(f"could not issue a fresh one-time nonce: {exc}") from exc
    _check_path(issued, 0o400, "issued nonce record")
    return run_id, nonce, issued


def acquire_attempt_sentinel(packet_digest: str) -> Path:
    """Permanently reserve the packet before any provider-facing process."""
    payload = _canonical({"schema_version": "opencode-provider-qualification-attempt/v1", "runner_id": RUNNER_ID, "packet_digest": packet_digest, "attempts": 1, "reserved_at": _now()})
    try:
        fd = os.open(ATTEMPT_SENTINEL, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
    except FileExistsError as exc:
        raise RunnerError("the qualification packet already has a permanently reserved attempt") from exc
    except OSError as exc:
        raise RunnerError(f"could not reserve the one-shot packet attempt: {exc}") from exc
    _check_path(ATTEMPT_SENTINEL, 0o400, "packet attempt sentinel")
    return ATTEMPT_SENTINEL


def _event_tokens(event: dict[str, Any]) -> int:
    """Extract one provider step-finish total; missing usage fails closed."""
    usage = event.get("usage")
    if usage is None and isinstance(event.get("part"), dict):
        usage = event["part"].get("usage")
        if usage is None and isinstance(event["part"].get("tokens"), dict):
            tokens = event["part"]["tokens"]
            components = [tokens.get(key, 0) for key in ("input", "output", "reasoning")]
            if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in components):
                raise RunnerError("OpenCode step-finish tokens are not bounded integers")
            return sum(components)
    if not isinstance(usage, dict):
        raise RunnerError("provider event has no usage object")
    total = usage.get("total_tokens", usage.get("totalTokens"))
    if not isinstance(total, int) or isinstance(total, bool) or total < 0:
        raise RunnerError("provider event has no bounded integer total token count")
    return total


def _provider_event(event: dict[str, Any]) -> bool:
    request_id = _raw_provider_request_id(event)
    return (
        event.get("type") == "step_finish"
        and isinstance(event.get("sessionID"), str)
        and SAFE_PROVIDER_ID.fullmatch(event["sessionID"]) is not None
        and isinstance(request_id, str) and SAFE_PROVIDER_REQUEST_ID.fullmatch(request_id) is not None
    )


def _raw_provider_request_id(event: dict[str, Any]) -> Any:
    part = event.get("part")
    if isinstance(part, dict):
        for key in ("requestID", "requestId", "providerRequestID", "provider_request_id"):
            if key in part:
                return part[key]
    for key in ("requestID", "requestId", "providerRequestID", "provider_request_id"):
        if key in event:
            return event[key]
    return None


def _provider_request_id(event: dict[str, Any]) -> str:
    request_id = _raw_provider_request_id(event)
    if not isinstance(request_id, str) or SAFE_PROVIDER_REQUEST_ID.fullmatch(request_id) is None:
        raise RunnerError("provider event has no genuine bounded provider request identifier")
    return request_id


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
        raise RunnerError("OpenCode step-finish has no provider usage structure")
    if any(not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) for value in (baseline, observed, cost)):
        raise RunnerError("OpenCode provider usage is not finite numeric evidence")
    return float(baseline), float(observed), float(cost)


def execute_once(
    *,
    command: list[str],
    environment: dict[str, str],
    popen: Callable[..., Any] = subprocess.Popen,
) -> dict[str, Any]:
    """Run exactly one contained command and terminate on either ceiling.

    The subprocess receives no retry loop.  stdout is parsed line-by-line and
    never persisted; only bounded provider-origin fields and digests survive.
    """
    expected_prefix = [str(_executable_path(RUNUSER)), "--user", WORKER_USER, "--", str(_executable_path(OPENCODE)), "run"]
    if command[:len(expected_prefix)] != expected_prefix:
        raise RunnerError("runner command is not the exact one-shot OpenCode run")
    process = popen(command, cwd=str(ACTIVE_WORKSPACE_ROOT), env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
    events: list[dict[str, Any]] = []
    observed = 0
    provider_events = 0
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
                raise RunnerError("OpenCode emitted a non-JSON event") from exc
            if not isinstance(event, dict):
                process.kill()
                raise RunnerError("OpenCode emitted a non-object event")
            if _provider_event(event):
                provider_events += 1
                event_baseline, event_observed_units, event_cost = _provider_usage(event)
                if event_baseline <= 0:
                    process.kill()
                    raise RunnerError("provider event has no positive bounded usage baseline")
                if not isinstance(event_observed_units, (int, float)) or isinstance(event_observed_units, bool) or event_observed_units < 0 or event_observed_units > 2 * event_baseline:
                    process.kill()
                    raise RunnerError("provider event usage exceeds the two-times constraint")
                baseline = event_baseline if baseline is None else baseline
                if event_baseline != baseline:
                    process.kill()
                    raise RunnerError("provider usage baseline changed during the one-shot run")
                if event_cost < 0:
                    process.kill()
                    raise RunnerError("provider event has no bounded cost input")
                observed_cost = max(observed_cost, float(event_cost))
                if observed_cost > MAX_COST_USD:
                    process.kill()
                    raise RunnerError("provider cost ceiling exceeded during execution")
                observed = max(observed, _event_tokens(event))
                if observed > HARD_TOKENS:
                    process.kill()
                    raise RunnerError("hard token ceiling exceeded during execution")
                if observed > SOFT_TOKENS:
                    process.kill()
                    raise RunnerError("soft token ceiling exceeded during execution")
                events.append({
                    "phase": "worker",
                    "session_id": event["sessionID"],
                    "usage_total_tokens": observed,
                    "usage_baseline_units": event_baseline,
                    "usage_observed_units": event_observed_units,
                    "session_id_digest": _digest_bytes(event["sessionID"].encode("utf-8")),
                    "source_event_digest": _digest(event),
                    "provider_request_id_digest": _digest_bytes(_provider_request_id(event).encode("utf-8")),
                })
        process.stdout.close()
    finally:
        wall_timer.cancel()
        return_code = process.wait(timeout=30)
    if timed_out:
        raise RunnerError("contained OpenCode run exceeded the hard wall timeout")
    if return_code != 0:
        raise RunnerError(f"contained OpenCode run failed with exit {return_code}")
    if provider_events != 1 or len(events) != 1:
        raise RunnerError("one-shot run did not produce exactly one provider-origin step-finish")
    usage_payload = {
        "schema_version": "opencode-provider-usage/v1",
        "provider_request_id_digest": events[0]["provider_request_id_digest"],
        "source_event_digest": events[0]["source_event_digest"],
        "source": "provider-reported",
        "usage_baseline": baseline,
        "usage_observed": events[0]["usage_observed_units"],
        "phase_units": [{"phase": "worker", "units": events[0]["usage_observed_units"]}],
    }
    return {
        "observed_tokens": observed,
        "usage_baseline": baseline,
        "usage_observed": events[0]["usage_observed_units"],
        "cost_usd": observed_cost,
        "provider_events": events,
        "provider_payload": None,
        "usage_payload": usage_payload,
        "provider_artifact_digest": "",
        "usage_artifact_digest": _digest(usage_payload),
        "provider_request_id_digest": events[0]["provider_request_id_digest"],
        "source_event_digest": events[0]["source_event_digest"],
        "attempts": 1,
    }


def _sign(record_path: Path, signature_path: Path) -> None:
    completed = subprocess.run(
        [str(_executable_path(Path(SSH_KEYGEN))), "-q", "-Y", "sign", "-f", str(PRIVATE_KEY), "-n", SIGNATURE_NAMESPACE, str(record_path)],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=10,
    )
    generated = record_path.with_name(record_path.name + ".sig")
    if completed.returncode != 0 or not generated.is_file():
        raise RunnerError(f"could not sign the immutable runner record: {completed.stderr.decode(errors='replace')[-200:]}")
    if generated != signature_path:
        raise RunnerError("ssh-keygen returned an unexpected detached signature path")
    os.chmod(signature_path, 0o400)
    _check_path(signature_path, 0o400, "detached runner signature")


def _write_structural_artifact(root: Path, name: str, payload: dict[str, Any]) -> str:
    path = root / name
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    with os.fdopen(fd, "wb") as stream:
        stream.write(_canonical(payload))
    _check_path(path, 0o400, f"immutable {name} evidence")
    return _file_digest(path)


def _parse_sanitized_export(stdout: str, session_id: str) -> dict[str, Any]:
    """Retain only the #2118 export projection; never persist transcript text."""
    try:
        exported = json.loads(stdout)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RunnerError(f"sanitized OpenCode export is not JSON: {exc}") from exc
    if not isinstance(exported, dict) or not isinstance(exported.get("info"), dict) or exported["info"].get("id") != session_id:
        raise RunnerError("sanitized OpenCode export changed session identity")
    messages = exported.get("messages")
    if not isinstance(messages, list) or not messages:
        raise RunnerError("sanitized OpenCode export has no messages")
    assistants = [message for message in messages if isinstance(message, dict) and isinstance(message.get("info"), dict) and message["info"].get("role") == "assistant"]
    if not assistants:
        raise RunnerError("sanitized OpenCode export has no assistant evidence")
    info = assistants[-1]["info"]
    if info.get("providerID") != "opencode-go" or info.get("modelID") != "deepseek-v4-flash" or info.get("finish") != "stop":
        raise RunnerError("sanitized OpenCode export provider/model/finish is not exact")
    parts = assistants[-1].get("parts")
    if not isinstance(parts, list):
        raise RunnerError("sanitized OpenCode export assistant has no parts")
    part_types = [part.get("type") for part in parts if isinstance(part, dict) and part.get("type") in {"text", "step-finish"}]
    if part_types != ["text", "step-finish"]:
        raise RunnerError("sanitized OpenCode export part grammar is not exact")
    request_binding_digest = _digest({"providerID": info["providerID"], "modelID": info["modelID"], "finish": info["finish"], "part_types": part_types})
    return {
        "schema_version": "opencode-provider-origin/v1",
        "session_id_digest": _digest_bytes(session_id.encode("utf-8")),
        "request_binding_digest": request_binding_digest,
        "events": [{"phase": "worker", "providerID": info["providerID"], "modelID": info["modelID"], "finish": info["finish"], "part_types": part_types}],
    }


def _sanitized_export(session_id: str, environment: dict[str, str]) -> dict[str, Any]:
    completed = subprocess.run([str(_executable_path(RUNUSER)), "--user", WORKER_USER, "--", str(_executable_path(OPENCODE)), "export", session_id, "--sanitize"], cwd=str(ACTIVE_WORKSPACE_ROOT), env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=False, timeout=30)
    if completed.returncode != 0:
        raise RunnerError("contained sanitized OpenCode export failed")
    return _parse_sanitized_export(completed.stdout, session_id)


def run_one_shot() -> dict[str, Any]:
    verify_installation()
    packet, packet_digest = _load_packet()
    # Pin every installed preflight byte before reserving the irreversible attempt.
    for name in ("capability.json", "lifecycle.json", "overlay.json", "workspace.json"):
        _load_static_evidence(name)
    run_id = "run-" + secrets.token_hex(16)
    nonce = "nonce-" + secrets.token_hex(32)
    _create_fresh_workspace(run_id)
    acquire_attempt_sentinel(packet_digest)
    run_id, nonce, issued_path = issue_nonce(packet_digest, run_id=run_id, nonce=nonce)
    started = _now()
    containment_payload = _contained_probe()
    auth_path: Path | None = None
    try:
        auth_bytes = _read_provider_auth()
        auth_path = _provision_provider_auth(auth_bytes)
        config = {
            "PATH": "/run/current-system/sw/bin",
            "HOME": str(ACTIVE_WORKSPACE_ROOT),
            "TMPDIR": str(ACTIVE_WORKSPACE_ROOT),
            "XDG_CONFIG_HOME": str(ACTIVE_WORKSPACE_ROOT / ".config"),
            "XDG_CACHE_HOME": str(ACTIVE_WORKSPACE_ROOT / ".cache"),
            "XDG_DATA_HOME": str(ACTIVE_WORKSPACE_ROOT / ".local" / "share"),
            "NO_COLOR": "1",
            "OPENCODE_AUTH_CONTENT": auth_bytes.decode("utf-8"),
        }
        config["OPENCODE_CONFIG_CONTENT"] = CONFIG.read_text(encoding="utf-8")
        request = packet["request"]
        command = [str(_executable_path(RUNUSER)), "--user", WORKER_USER, "--", str(_executable_path(OPENCODE)), "run", request["prompt"], "--agent", request["agent"], "--format", request["format"]]
        execution = execute_once(command=command, environment=config)
        execution["provider_payload"] = _sanitized_export(execution["provider_events"][0]["session_id"], config)
    finally:
        if auth_path is not None:
            _scrub_provider_auth(auth_path, auth_bytes)
    execution["provider_artifact_digest"] = _digest(execution["provider_payload"])
    provider_event = execution["provider_payload"]["events"][0]
    execution["provider_events"][0].update(provider_event)
    execution["provider_events"][0]["request_binding_digest"] = execution["provider_payload"]["request_binding_digest"]
    finished = _now()
    run_evidence_root = EVIDENCE_ROOT / run_id
    run_evidence_root.mkdir(mode=0o700)
    _check_path(run_evidence_root, 0o700, "fresh run evidence root", directory=True)
    _check_parents(run_evidence_root, "fresh run evidence root")
    provider_artifact_digest = _write_structural_artifact(run_evidence_root, "provider.json", execution["provider_payload"])
    usage_artifact_digest = _write_structural_artifact(run_evidence_root, "usage.json", execution["usage_payload"])
    containment_artifact_digest = _write_structural_artifact(run_evidence_root, "containment.json", {key: containment_payload[key] for key in ("coordinator_write_denied", "workspace_round_trip", "worker_identity", "exact_groups", "reads_contained")})
    static_payloads: dict[str, dict[str, Any]] = {}
    static_digests: dict[str, str] = {}
    for name in ("capability.json", "lifecycle.json", "overlay.json", "workspace.json"):
        static_payloads[name], _ = _load_static_evidence(name)
        static_digests[name] = _write_structural_artifact(run_evidence_root, name, static_payloads[name])
    artifact_descriptors = {
        "provider_model": {"artifact": "provider.json", "digest": provider_artifact_digest},
        "usage": {"artifact": "usage.json", "digest": usage_artifact_digest},
        "containment": {"artifact": "containment.json", "digest": containment_artifact_digest},
        "capability": {"artifact": "capability.json", "digest": static_digests["capability.json"]},
        "lifecycle": {"artifact": "lifecycle.json", "digest": static_digests["lifecycle.json"]},
        "overlay": {"artifact": "overlay.json", "digest": static_digests["overlay.json"]},
        "workspace": {"artifact": "workspace.json", "digest": static_digests["workspace.json"]},
    }
    if set(static_payloads["capability.json"]) != set(REQUIRED_PROBES) or any(value != "pass" for value in static_payloads["capability.json"].values()) or set(static_payloads["lifecycle.json"]) != set(REQUIRED_PROBES) or any(value != "pass" for value in static_payloads["lifecycle.json"].values()):
        raise RunnerError("static preflight evidence is not the exact reviewed pass set")
    evidence_bundle_digest = _bundle_digest(artifact_descriptors)
    provider_event = execution["provider_payload"]["events"][0]
    usage_payload = execution["usage_payload"]
    containment_receipt = {key: containment_payload[key] for key in ("coordinator_write_denied", "workspace_round_trip", "worker_identity", "exact_groups", "reads_contained")}
    containment_receipt["evidence_digest"] = containment_artifact_digest
    receipt: dict[str, Any] = {
        "schema_version": "opencode-provider-qualification-receipt/v2",
        "profile_id": "opencode-nixpkgs-devbox-1.18.4", "semantic_adapter": "opencode-noninteractive/v1", "cli_version": "1.18.4",
        "executable_fingerprint": PINNED_OPENCODE_DIGEST, "channel_revision": "nixpkgs/nixos-unstable@47e6de6",
        "profile_digest": PINNED_PROFILE_DIGEST, "config_digest": PINNED_CONFIG_DIGEST, "overlay_digest": static_digests["overlay.json"], "policy_digest": PINNED_POLICY_DIGEST,
        "provider_model": "opencode-go/deepseek-v4-flash", "provider_id": "opencode-go", "model_id": "deepseek-v4-flash", "route_model": "opencode-go/deepseek-v4-flash", "worker_model": "opencode-go/deepseek-v4-flash", "model_override": False, "worker_identity": WORKER_USER, "provider_contacted": True,
        "request_digest": _digest(request),
        "runner_digest": PINNED_RUNNER_DIGEST, "opencode_digest": PINNED_OPENCODE_DIGEST,
        "workspace_opt_in": True, "workspace_evidence": {"manifest_digest": PINNED_MANIFEST_DIGEST, "repository_opt_in": True, "provider_workspace_opt_in": True},
        "usage_baseline": usage_payload["usage_baseline"], "usage_observed": usage_payload["usage_observed"], "usage_multiplier": usage_payload["usage_observed"] / usage_payload["usage_baseline"],
        "usage_evidence": {key: usage_payload[key] for key in ("source", "provider_request_id_digest", "source_event_digest", "phase_units")}, "usage_evidence_digest": usage_artifact_digest,
        "cost_usd": execution["cost_usd"], "cost_limit_semantics": "post-hoc-acceptance", "hard_wall_seconds": HARD_WALL_SECONDS, "tokens": execution["observed_tokens"], "attempts": 1, "containment": containment_receipt,
        "provider_model_evidence": [{**provider_event, "evidence_digest": provider_artifact_digest}],
        "capability_probe_results": static_payloads["capability.json"], "lifecycle_probe_results": static_payloads["lifecycle.json"],
        "capability_evidence_digest": static_digests["capability.json"], "lifecycle_evidence_digest": static_digests["lifecycle.json"], "evidence_artifacts": artifact_descriptors,
        "raw_transcript_captured": False, "qualification_state": "preflight_observed", "independent_review": {"status": "pending", "ref": None},
        "runner_id": RUNNER_ID, "run_id": run_id, "run_nonce": nonce, "packet_digest": packet_digest,
        "runner_record_digest": "sha256:" + "0" * 64, "runner_signature_digest": "sha256:" + "0" * 64, "evidence_bundle_digest": evidence_bundle_digest,
    }
    record = {
        "schema_version": "opencode-provider-qualification-runner-record/v1",
        "runner_id": RUNNER_ID,
        "run_id": run_id,
        "nonce": nonce,
        "packet_digest": packet_digest,
        "request_digest": _digest(request),
        "runner_digest": PINNED_RUNNER_DIGEST,
        "opencode_digest": PINNED_OPENCODE_DIGEST,
        "issued_at": json.loads(issued_path.read_text(encoding="utf-8"))["issued_at"],
        "started_at": started,
        "finished_at": finished,
        "status": "completed",
        "attempts": 1,
        "record_filename": f"{run_id}.json",
        "signature_filename": f"{run_id}.json.sig",
        "token_budget": {
            "soft_ceiling": SOFT_TOKENS, "hard_ceiling": HARD_TOKENS,
            "observed_tokens": execution["observed_tokens"], "soft_enforced": True, "hard_enforced": True,
            "soft_limit_hit": False, "hard_limit_hit": False, "attempts": 1,
            "enforcement_events": [{"phase": "worker", "observed_tokens": execution["observed_tokens"], "soft_ceiling": SOFT_TOKENS, "hard_ceiling": HARD_TOKENS, "soft_enforced": True, "hard_enforced": True}],
        },
        "provider_origin": {
            "source": "opencode-sanitized-export", "providerID": "opencode-go", "modelID": "deepseek-v4-flash",
            "artifact_digest": provider_artifact_digest, "session_count": 1,
            "session_id_digest": execution["provider_events"][0]["session_id_digest"],
            "request_binding_digest": execution["provider_events"][0]["request_binding_digest"], "event_count": 1,
        },
        "usage": {
            "source": "opencode-provider-step-finish", "baseline": execution["usage_baseline"], "observed": execution["usage_observed"],
            "artifact_digest": usage_artifact_digest, "provider_request_id_digest": execution["provider_request_id_digest"],
            "source_event_digest": execution["source_event_digest"],
        },
        "containment": {**containment_payload, "artifact_digest": containment_artifact_digest},
        "cost_usd": execution["cost_usd"], "cost_limit_semantics": "post-hoc-acceptance", "hard_wall_seconds": HARD_WALL_SECONDS,
        "evidence_bundle_digest": evidence_bundle_digest,
        "receipt_binding_digest": _receipt_binding_digest(receipt),
        "sealed": True,
    }
    record_path = RECORD_ROOT / record["record_filename"]
    fd = os.open(record_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    with os.fdopen(fd, "wb") as stream:
        stream.write(_canonical(record))
    _check_path(record_path, 0o400, "immutable runner record")
    signature_path = RECORD_ROOT / record["signature_filename"]
    try:
        signature_path.lstat()
    except FileNotFoundError:
        pass
    else:
        raise RunnerError("detached signature path already exists")
    _sign(record_path, signature_path)
    receipt["runner_record_digest"] = _file_digest(record_path)
    receipt["runner_signature_digest"] = _file_digest(signature_path)
    receipt_path = run_evidence_root / "receipt.json"
    fd = os.open(receipt_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    with os.fdopen(fd, "wb") as stream:
        stream.write(_canonical(receipt))
    _check_path(receipt_path, 0o400, "immutable qualification receipt")
    consumed = LEDGER_ROOT / f"{nonce}.completed"
    fd = os.open(consumed, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    with os.fdopen(fd, "wb") as stream:
        stream.write(_canonical({"schema_version": "opencode-provider-qualification-nonce/v1-completed", "run_id": run_id, "nonce": nonce, "packet_digest": packet_digest, "record_digest": _file_digest(record_path), "signature_digest": _file_digest(signature_path)}))
    _check_path(consumed, 0o400, "completed nonce ledger record")
    return {"record": str(record_path), "signature": str(signature_path), "receipt": str(receipt_path), "evidence_root": str(run_evidence_root), "nonce": nonce, "run_id": run_id, "attempts": 1}


def verify_installation_only() -> dict[str, Any]:
    """Check final installed bytes and trust material without any mutation."""
    verify_installation()
    packet, packet_digest = _load_packet()
    static = {name: _load_static_evidence(name)[1] for name in ("capability.json", "lifecycle.json", "overlay.json", "workspace.json")}
    _read_provider_auth()
    return {
        "status": "verified",
        "side_effects": False,
        "provider_contacted": False,
        "packet_digest": packet_digest,
        "preflight_evidence": static,
        "qualification_state": "preflight_observed",
        "qualification_eligible": False,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--verify-installation", action="store_true", help="verify installed final bytes and trust material without creating state")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(verify_installation_only() if args.verify_installation else run_one_shot(), sort_keys=True))
    except (OSError, RunnerError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "failed", "qualification_eligible": False, "error": str(exc)}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
