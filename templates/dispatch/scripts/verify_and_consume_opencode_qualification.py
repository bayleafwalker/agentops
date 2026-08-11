#!/usr/bin/env python3
"""Fixed-path privileged admission boundary.

Install this file as a root-owned executable under ``/usr/local/libexec`` and
permit only this executable through the workstation's sudoers/service policy.
It has no private-key path and cannot select a corpus, validator, trust root,
or ledger root.  Its only caller inputs are the three output paths.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import sys


INSTALL_ROOT = Path("/etc/agentops/opencode-qualification")
CORPUS = INSTALL_ROOT / "corpus.json"
PROFILE = INSTALL_ROOT / "profile.json"
CONFIG = INSTALL_ROOT / "opencode.hybrid.json"
POLICY = INSTALL_ROOT / "hybrid-dispatch.v1.json"
MANIFEST = INSTALL_ROOT / "agentops.dispatch.json"
PREFLIGHT_ROOT = INSTALL_ROOT / "preflight-evidence"
PUBLIC_KEY = Path("/var/lib/agentops/opencode-qualification/runner.pub")
ALLOWED_SIGNERS = Path("/var/lib/agentops/opencode-qualification/allowed_signers")
RECORD_ROOT = Path("/var/lib/agentops/opencode-qualification/records")
LEDGER_ROOT = Path("/var/lib/agentops/opencode-qualification/ledger")
EVIDENCE_ROOT = Path("/var/lib/agentops/opencode-qualification/evidence")
HELPER_PATH = Path("/usr/local/libexec/agentops-opencode-qualification-verify-consume")
HELPER_DIGEST_FILE = INSTALL_ROOT / "verify-consume.sha256"
VALIDATOR_PATH = Path("/usr/local/libexec/agentops-opencode-qualification-validator.py")
PROFILE_VALIDATOR_PATH = Path("/usr/local/libexec/agentops-opencode-qualification-profile-validator.py")
HYBRID_VALIDATOR_PATH = Path("/usr/local/libexec/agentops-opencode-qualification-hybrid-validator.py")
HYBRID_DISPATCH_PATH = Path("/usr/local/libexec/agentops-opencode-qualification-hybrid-dispatch.py")

EXPECTED_OWNER_UID = 0
EXPECTED_CORPUS_DIGEST = "sha256:d62334d581e17a34bc286f42a45fd27bf85043486a2529a4851430eafaa345b7"
EXPECTED_CONFIG_DIGEST = "sha256:dc8e846c1cf22e536a35b3d842b518e194c2fde355b87e1b677ca82570ae566c"
EXPECTED_PROFILE_DIGEST = "sha256:38d17f648ffc6831752fd6250638648580fbfc478cb4789b732c8ae95e25b84a"
EXPECTED_POLICY_DIGEST = "sha256:dc9fcb92f1c4dfceecc5372f84cadeb1b58aad026a45ea0379a5f7ab196555a6"
EXPECTED_MANIFEST_DIGEST = "sha256:6bfa1a88618a8246b20a2b30af565bb5b828bfb6608611c062d017ba79958ab6"
EXPECTED_VALIDATOR_DIGEST = "sha256:d08022a0b3451a8e0acf298f5650dafaf75564b59c97ceb535db64ea999b4aa8"
EXPECTED_PROFILE_VALIDATOR_DIGEST = "sha256:0aacdd187121dede9ebb2738d187f7dd2370fbaeeb7159a406cf2b0bd36a0192"
EXPECTED_HYBRID_VALIDATOR_DIGEST = "sha256:4e4ef7a785c1d6cca3a6f49010f6275dd7ef27864ad037b9e8db7bf7a6e8fb6d"
EXPECTED_HYBRID_DISPATCH_DIGEST = "sha256:f0592949c151bf5c0a0797c0d666ce85e075a3ff70e4b805ebc6ec2e3c66c640"


class BoundaryError(RuntimeError):
    """The narrow privileged boundary is unavailable or unsafe."""


def _digest(path: Path) -> str:
    try:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise BoundaryError(f"cannot hash fixed installed file {path}: {exc}") from exc


def _check(path: Path, mode: int, label: str, *, directory: bool = False) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise BoundaryError(f"{label} is unavailable: {exc}") from exc
    if info.st_uid != EXPECTED_OWNER_UID:
        raise BoundaryError(f"{label} has an unexpected owner")
    if stat.S_IMODE(info.st_mode) != mode:
        raise BoundaryError(f"{label} must have mode {mode:04o}")
    if directory and not stat.S_ISDIR(info.st_mode):
        raise BoundaryError(f"{label} must be a directory")
    if not directory and not stat.S_ISREG(info.st_mode):
        raise BoundaryError(f"{label} must be a regular file")


def _parents(path: Path, label: str) -> None:
    current = path.parent
    while True:
        try:
            info = current.lstat()
        except OSError as exc:
            raise BoundaryError(f"{label} has an unavailable parent: {exc}") from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode) or info.st_uid != EXPECTED_OWNER_UID:
            raise BoundaryError(f"{label} has an unsafe parent")
        if stat.S_IMODE(info.st_mode) & 0o022 and not (stat.S_IMODE(info.st_mode) & stat.S_ISVTX):
            raise BoundaryError(f"{label} has a writable parent")
        if current.parent == current:
            return
        current = current.parent


def _verify_installed_material() -> None:
    """Verify the fixed root-owned admission package, without private-key access."""
    _check(INSTALL_ROOT, 0o700, "installed qualification root", directory=True)
    _parents(INSTALL_ROOT, "installed qualification root")
    _check(PREFLIGHT_ROOT, 0o700, "installed preflight root", directory=True)
    for path, mode, label in (
        (CORPUS, 0o400, "installed corpus"),
        (PROFILE, 0o400, "installed profile"),
        (CONFIG, 0o400, "installed config"),
        (POLICY, 0o400, "installed policy"),
        (MANIFEST, 0o400, "installed manifest"),
        (PUBLIC_KEY, 0o444, "pinned public key"),
        (ALLOWED_SIGNERS, 0o444, "pinned allowed signers"),
    ):
        _check(path, mode, label)
        _parents(path, label)
    for path, label in ((RECORD_ROOT, "record root"), (LEDGER_ROOT, "ledger root"), (EVIDENCE_ROOT, "evidence root")):
        _check(path, 0o700, label, directory=True)
        _parents(path, label)
    for name in ("capability.json", "lifecycle.json", "overlay.json", "workspace.json"):
        path = PREFLIGHT_ROOT / name
        _check(path, 0o400, f"preflight {name}")
        _parents(path, f"preflight {name}")
    if _digest(CORPUS) != EXPECTED_CORPUS_DIGEST:
        raise BoundaryError("installed corpus bytes are not pinned")
    for path, expected, label in ((CONFIG, EXPECTED_CONFIG_DIGEST, "config"), (PROFILE, EXPECTED_PROFILE_DIGEST, "profile"), (POLICY, EXPECTED_POLICY_DIGEST, "policy"), (MANIFEST, EXPECTED_MANIFEST_DIGEST, "manifest")):
        if _digest(path) != expected:
            raise BoundaryError(f"installed {label} bytes are not pinned")
    _check(HELPER_PATH, 0o755, "installed admission helper")
    _parents(HELPER_PATH, "installed admission helper")
    _check(HELPER_DIGEST_FILE, 0o400, "helper digest pin")
    _parents(HELPER_DIGEST_FILE, "helper digest pin")
    if _digest(VALIDATOR_PATH) != EXPECTED_VALIDATOR_DIGEST or HELPER_DIGEST_FILE.read_text(encoding="ascii").strip() != _digest(HELPER_PATH):
        raise BoundaryError("installed admission helper or validator bytes are not pinned")
    for path, expected, label in (
        (PROFILE_VALIDATOR_PATH, EXPECTED_PROFILE_VALIDATOR_DIGEST, "profile validator"),
        (HYBRID_VALIDATOR_PATH, EXPECTED_HYBRID_VALIDATOR_DIGEST, "hybrid validator"),
        (HYBRID_DISPATCH_PATH, EXPECTED_HYBRID_DISPATCH_DIGEST, "hybrid dispatch builder"),
    ):
        if not expected.startswith("sha256:"):
            raise BoundaryError(f"{label} pin is not provisioned")
        _check(path, 0o755, label)
        _parents(path, label)
        if _digest(path) != expected:
            raise BoundaryError(f"installed {label} bytes are not pinned")


def _validator():
    spec = importlib.util.spec_from_file_location("opencode_qualification_installed_validator", VALIDATOR_PATH)
    if spec is None or spec.loader is None:
        raise BoundaryError("cannot load the fixed installed validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.DEFAULT_PROFILE = PROFILE
    module.DEFAULT_CONFIG = CONFIG
    module.DEFAULT_MANIFEST = MANIFEST
    module.DEFAULT_PREFLIGHT_ROOT = PREFLIGHT_ROOT
    module.PROFILE_VALIDATOR_SCRIPT = PROFILE_VALIDATOR_PATH
    module.HYBRID_VALIDATOR_SCRIPT = HYBRID_VALIDATOR_PATH
    module.HYBRID_DISPATCH_SCRIPT = HYBRID_DISPATCH_PATH
    module.POLICY_PATH = POLICY
    module.HISTORY_ROOT = INSTALL_ROOT
    module.VERIFY_HISTORY_FILES = False
    module.EXPECTED_RUNNER_PUBLIC_KEY_PATH = str(PUBLIC_KEY)
    module.EXPECTED_RUNNER_ALLOWED_SIGNERS_PATH = str(ALLOWED_SIGNERS)
    module.EXPECTED_RECORD_ROOT = str(RECORD_ROOT)
    module.EXPECTED_LEDGER_ROOT = str(LEDGER_ROOT)
    module.EXPECTED_EVIDENCE_ROOT = str(EVIDENCE_ROOT)
    return module


def verify_and_consume(receipt: Path, evidence_root: Path, runner_record: Path) -> dict[str, object]:
    _verify_installed_material()
    gate = _validator()
    result = gate.evaluate(
        CORPUS,
        receipt_path=receipt,
        evidence_root=evidence_root,
        runner_record_path=runner_record,
        runner_public_key_path=PUBLIC_KEY,
        runner_allowed_signers_path=ALLOWED_SIGNERS,
        consume=True,
    )
    return {"status": result["status"], "candidate_ready": bool(result.get("candidate_ready")), "qualification_state": result["qualification_state"], "qualification_eligible": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("evidence_root", type=Path)
    parser.add_argument("runner_record", type=Path)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(verify_and_consume(args.receipt, args.evidence_root, args.runner_record), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"status": "failed", "candidate_ready": False, "qualification_state": "preflight_observed", "qualification_eligible": False, "error": str(exc)}, sort_keys=True))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
