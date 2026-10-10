#!/usr/bin/env python3
"""Emit and resolve the local dispatcher's RunManifest (agentops#2479).

vuoro#122 made ``RunManifest`` a first-class object
(``packages/vuoro-evidence/src/vuoro_evidence/run.py``) and the hosted path
emits one through ``register_run``. This is the *local* residual: a
``vuoro-dispatch-build`` run emits one manifest when it starts, and every
evidence record it writes afterwards names that manifest by ``run_id`` and
``manifest_digest``. The contract is ``docs/contracts/local-run-manifest.md``.

What a manifest holds
---------------------
Exactly the vuoro-evidence ``RunManifest`` composition -- ``run_id``,
``harness_id``, ``harness_build``, ``model_id``, ``recipe_id``,
``observed_profile`` (``instruction_digest``, ``skill_digests``),
``grant_ids``, ``claim_ids`` -- plus ``composition_digest`` computed the way
``RunManifest.composition_digest`` computes it, so a reader holding
vuoro-evidence can rebuild the object and get the same comparison key.

Observed or declared, never manufactured
----------------------------------------
``recipe_id`` is the workflow name bound to the digest of the script file on
disk. ``observed_profile.instruction_digest`` is a digest over the native
root-to-CWD instruction chain, observed through ``session_binding`` (TS-3:
observed, not compiled). ``harness_build`` is what ``claude --version``
printed, or ``unobserved``. ``model_id`` is the set of models the workflow
declares it routes to. Nothing here mints work identity: a local run id is
``lrun_<ULID>``, deliberately outside sprintctl's served ``run_<ULID>``
namespace, and ``grant_ids``/``claim_ids`` stay empty at start because the
dispatcher holds no grant and has reserved nothing yet. Reservations taken
later are recorded on the evidence that cites them, not back-filled here.

Immutability
------------
A manifest file is published by exclusive link and never rewritten. The
reference digest (``manifest_digest``) covers the whole record, ``run_id``
and ``emitted_at`` included, so a reference resolves only to the exact bytes
of meaning it was issued for.

Usage::

    agentops run-manifest emit --input-json '{"workflow": "vuoro-dispatch-build", "harness_id": "claude-code", "model_ids": [...]}'
    agentops run-manifest resolve --run-id lrun_... --digest sha256:...
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import auditctl_resolve  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "run-manifest/v1"
SOURCE = "agentops-local-dispatcher"
EVENT_TYPE = "run.manifest"
DEFAULT_DIR = Path("/projects/dev/.claude/state/run-manifests")
CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

#: Local run handle: ``lrun_`` + a Crockford-base32 ULID. Not ``run_``: that
#: namespace is sprintctl's served run, which a local process cannot mint.
RUN_ID_RE = re.compile(r"lrun_[0-7][0-9A-HJKMNP-TV-Z]{25}")
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
#: Workflows that emit a manifest, by name. The script path is derived, never passed in.
WORKFLOWS = {"vuoro-dispatch-build": ROOT / ".claude" / "workflows" / "vuoro-dispatch-build.js"}
HARNESSES = ("claude-code", "codex")
UNOBSERVED = "unobserved"

#: The fields of vuoro_evidence.run.RunManifest.composition(), in its order.
COMPOSITION_FIELDS = ("run_id", "harness_id", "harness_build", "model_id", "recipe_id",
                      "observed_profile", "grant_ids", "claim_ids")


class RunManifestError(ValueError):
    """The input or the record does not satisfy the manifest contract."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def manifest_dir() -> Path:
    return Path(os.environ.get("AGENTOPS_RUN_MANIFEST_DIR") or DEFAULT_DIR)


def mint_run_id(now_ms: int | None = None, entropy: bytes | None = None) -> str:
    """``lrun_`` + ULID: 48-bit millisecond time, 80 random bits, Crockford base32."""
    ms = int(time.time() * 1000) if now_ms is None else now_ms
    rand = secrets.token_bytes(10) if entropy is None else entropy
    if not 0 <= ms < 2 ** 48 or len(rand) != 10:
        raise RunManifestError("ULID needs a 48-bit time and 10 bytes of entropy")
    value = (ms << 80) | int.from_bytes(rand, "big")
    chars = []
    for _ in range(26):
        chars.append(CROCKFORD[value & 31])
        value >>= 5
    return "lrun_" + "".join(reversed(chars))


def composition(record: dict[str, Any]) -> dict[str, Any]:
    return {field: record[field] for field in COMPOSITION_FIELDS}


def composition_digest(record: dict[str, Any]) -> str:
    """``RunManifest.composition_digest``: the composition without ``run_id``."""
    payload = composition(record)
    payload.pop("run_id")
    return _sha256(_canonical(payload))


def manifest_digest(record: dict[str, Any]) -> str:
    """The reference digest: the whole record except this digest itself."""
    return _sha256(_canonical({k: v for k, v in record.items() if k != "manifest_digest"}))


def recipe_id(workflow: str) -> str:
    path = WORKFLOWS.get(workflow)
    if path is None:
        raise RunManifestError(f"workflow must be one of {sorted(WORKFLOWS)}")
    return f"{workflow}@{_sha256(path.read_bytes())}"


def observe_profile(cwd: Path) -> dict[str, Any]:
    """Digest over the observed native instruction chain (``session_binding._instructions``)."""
    import session_binding  # local import: its environment resolution is not needed here

    sources = session_binding._instructions(cwd)["sources"]
    chain = [[source["path"], source["sha256"]] for source in sources]
    return {"instruction_digest": _sha256(_canonical(chain)), "skill_digests": []}


def observe_harness_build(harness_id: str) -> str:
    binary = {"claude-code": "claude", "codex": "codex"}[harness_id]
    try:
        result = subprocess.run([binary, "--version"], capture_output=True, text=True,
                                timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return UNOBSERVED
    line = (result.stdout or "").strip().splitlines()[:1]
    if result.returncode != 0 or not line or not line[0].strip():
        return UNOBSERVED
    return line[0].strip()[:200]


def build_manifest(document: Any, *, cwd: Path = ROOT, harness_build: str | None = None,
                   run_id: str | None = None, emitted_at: str | None = None) -> dict[str, Any]:
    """Validate the dispatcher's declaration and add what is observed."""
    if not isinstance(document, dict):
        raise RunManifestError("input must be an object")
    unknown = set(document) - {"workflow", "harness_id", "model_ids"}
    if unknown:
        raise RunManifestError(f"unknown input fields: {sorted(unknown)}")
    workflow = document.get("workflow")
    harness_id = document.get("harness_id")
    if harness_id not in HARNESSES:
        raise RunManifestError(f"harness_id must be one of {HARNESSES}")
    models = document.get("model_ids")
    if (not isinstance(models, list) or not models
            or not all(isinstance(m, str) and SAFE_NAME.fullmatch(m) for m in models)):
        raise RunManifestError("model_ids must be a non-empty list of safe model ids")
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id or mint_run_id(),
        "harness_id": harness_id,
        "harness_build": harness_build if harness_build is not None else observe_harness_build(harness_id),
        "model_id": ",".join(sorted(set(models))),
        "recipe_id": recipe_id(workflow),
        "observed_profile": observe_profile(cwd),
        "grant_ids": [],
        "claim_ids": [],
        "emitted_at": emitted_at or _now(),
        "emitter": SOURCE,
    }
    record["composition_digest"] = composition_digest(record)
    record["manifest_digest"] = manifest_digest(record)
    validate_record(record)
    return record


def validate_record(record: Any) -> None:
    """Every field present and well formed, both digests recomputing."""
    if not isinstance(record, dict) or record.get("schema_version") != SCHEMA_VERSION:
        raise RunManifestError("not a run-manifest/v1 record")
    if not isinstance(record.get("run_id"), str) or not RUN_ID_RE.fullmatch(record["run_id"]):
        raise RunManifestError("run_id must be lrun_<ULID>")
    for field in ("harness_id", "harness_build", "model_id", "recipe_id"):
        if not isinstance(record.get(field), str) or not record[field].strip():
            raise RunManifestError(f"{field} must be a non-empty string")
    profile = record.get("observed_profile")
    if (not isinstance(profile, dict) or set(profile) != {"instruction_digest", "skill_digests"}
            or not DIGEST_RE.fullmatch(str(profile.get("instruction_digest")))
            or not isinstance(profile.get("skill_digests"), list)):
        raise RunManifestError("observed_profile must hold an instruction_digest and skill_digests")
    for field in ("grant_ids", "claim_ids"):
        values = record.get(field)
        if not isinstance(values, list) or not all(isinstance(v, str) and v.strip() for v in values):
            raise RunManifestError(f"{field} must be a list of non-empty strings")
    if record.get("composition_digest") != composition_digest(record):
        raise RunManifestError("composition_digest does not recompute")
    if record.get("manifest_digest") != manifest_digest(record):
        raise RunManifestError("manifest_digest does not recompute")


def write_manifest(directory: Path, record: dict[str, Any]) -> Path:
    """Publish by exclusive link: a whole record or none, never a rewrite."""
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{record['run_id']}.json"
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                     prefix=".pending-", delete=False) as handle:
        json.dump(record, handle, sort_keys=True, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    try:
        os.link(temporary, target)
    except FileExistsError as error:
        raise RunManifestError(f"a manifest for {record['run_id']} already exists") from error
    finally:
        temporary.unlink()
    return target


def resolve_reference(run_id: Any, digest: Any, directory: Path | None = None) -> dict[str, Any]:
    """Resolve an evidence record's run reference. Never raises.

    ``status`` is ``resolved`` only when the manifest exists, validates and its
    ``manifest_digest`` equals the cited digest; otherwise ``invalid`` (the
    reference itself is malformed), ``unresolved`` (no readable manifest under
    that id) or ``digest-mismatch``.
    """
    if not (isinstance(run_id, str) and RUN_ID_RE.fullmatch(run_id)
            and isinstance(digest, str) and DIGEST_RE.fullmatch(digest)):
        return {"run_id": None, "manifest_digest": None, "status": "invalid"}
    reference = {"run_id": run_id, "manifest_digest": digest}
    path = (directory or manifest_dir()) / f"{run_id}.json"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        validate_record(record)
        if record["run_id"] != run_id:
            raise RunManifestError("run_id does not match its file")
    except (OSError, ValueError):
        return {**reference, "status": "unresolved"}
    status = "resolved" if record["manifest_digest"] == digest else "digest-mismatch"
    return {**reference, "status": status}


def publish(record: dict[str, Any]) -> bool:
    """One ``run.manifest`` auditctl event. Never fatal: telemetry is not the run."""
    binary = auditctl_resolve.resolve(quiet_when_absent=True)
    if binary is None:
        return False
    metadata = {field: record[field] for field in (
        "run_id", "manifest_digest", "composition_digest", "harness_id", "harness_build",
        "model_id", "recipe_id")}
    try:
        result = subprocess.run(
            [binary, "add", "--type", EVENT_TYPE, "--source", SOURCE, "--actor", SOURCE,
             "--summary", f"run manifest {record['run_id']} for {record['recipe_id'].split('@')[0]}",
             "--metadata", json.dumps(metadata)],
            cwd=ROOT, capture_output=True, env=auditctl_resolve.child_env(), timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def cmd_emit(args: argparse.Namespace) -> int:
    """Print the reference; on failure print why. Always exits 0: the run proceeds."""
    try:
        record = build_manifest(json.loads(args.input_json))
        path = write_manifest(manifest_dir(), record)
    except Exception as error:  # noqa: BLE001 - emission must never fail its host
        print(json.dumps({"emitted": False, "error": f"{type(error).__name__}: {str(error)[:300]}"}))
        return 0
    published = False if args.no_publish else publish(record)
    print(json.dumps({"emitted": True, "run_id": record["run_id"],
                      "manifest_digest": record["manifest_digest"],
                      "composition_digest": record["composition_digest"],
                      "path": str(path), "published": published}))
    return 0


def cmd_resolve(args: argparse.Namespace) -> int:
    result = resolve_reference(args.run_id, args.digest)
    print(json.dumps(result))
    return 0 if result["status"] == "resolved" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    emit = commands.add_parser("emit", help="emit one manifest at dispatcher run start")
    emit.add_argument("--input-json", required=True,
                      help="{workflow, harness_id, model_ids}: names and ids only")
    emit.add_argument("--no-publish", action="store_true", help="skip the auditctl event")
    emit.set_defaults(func=cmd_emit)
    resolve = commands.add_parser("resolve", help="resolve a run reference; exit 1 unless resolved")
    resolve.add_argument("--run-id", required=True)
    resolve.add_argument("--digest", required=True)
    resolve.set_defaults(func=cmd_resolve)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
