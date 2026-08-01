#!/usr/bin/env python3
"""Compile immutable dispatch plans and realize ActionQ execution groups."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit, urlunsplit


SOURCE_CONTRACT = "dispatch-plan-source/v1"
PLAN_CONTRACT = "dispatch-plan/v1"
BINDINGS_CONTRACT = "action-bindings/v1"
GROUP_CONTRACT = "execution-group/v1"
ENVELOPE_CONTRACT = "execution-envelope/v1"

TOPOLOGIES = {"independent", "stacked", "wave-integrated"}
FAILURE_POLICY = "continue-independent"
OID_RE = re.compile(r"[0-9a-f]{40,64}\Z")
SSH_SCP_RE = re.compile(r"git@([A-Za-z0-9.-]+):([A-Za-z0-9._~/-]+)\Z")
FORBIDDEN_KEY_RE = re.compile(
    r"(?:claim(?:_|-)?(?:token|receipt)|credential|secret|password|token|"
    r"local(?:_|-)?path|worktree|prompt|transcript|raw(?:_|-)?log)", re.I
)
FORBIDDEN_VALUE_RE = re.compile(
    r"(?:claim[_-]?token|claim[_-]?receipt|(?:password|secret|credential|"
    r"access[_-]?token|api[_-]?key)\s*[:=]|^file://|^/(?:tmp|home|root)/)", re.I
)
ARTIFACT_RE = re.compile(r"artifact:sha256:([0-9a-f]{64})\Z")


class PlanError(ValueError):
    """Invalid compiler input or provenance."""


class JsonArgumentParser(argparse.ArgumentParser):
    """Turn malformed CLI input into the command's JSON error envelope."""

    def error(self, message: str) -> None:
        raise PlanError(message)


def _object(value: Any, field: str, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PlanError(f"{field} must be an object")
    unknown = set(value) - keys
    if unknown:
        raise PlanError(f"{field} has unknown fields: {sorted(unknown)}")
    return value


def _required(value: dict[str, Any], field: str, names: set[str]) -> None:
    missing = names - set(value)
    if missing:
        raise PlanError(f"{field} is missing fields: {sorted(missing)}")


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise PlanError(f"{field} must be a non-empty string")
    return value


def _integer(value: Any, field: str, minimum: int = 1, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise PlanError(f"{field} must be an integer >= {minimum}")
    if maximum is not None and value > maximum:
        raise PlanError(f"{field} must be <= {maximum}")
    return value


def _array(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise PlanError(f"{field} must be an array")
    return value


def _deny_leakage(value: Any, field: str = "input") -> None:
    if isinstance(value, float):
        raise PlanError(f"{field} contains a float; floats are not canonical")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise PlanError(f"{field} keys must be strings")
            if FORBIDDEN_KEY_RE.search(key):
                raise PlanError(f"{field}.{key} is a forbidden authority or local field")
            _deny_leakage(child, f"{field}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _deny_leakage(child, f"{field}[{index}]")
    elif isinstance(value, str) and FORBIDDEN_VALUE_RE.search(value):
        raise PlanError(f"{field} contains forbidden credential, claim, or local-path material")


def canonical_bytes(value: Any) -> bytes:
    _deny_leakage(value)
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def artifact_ref(data: bytes) -> str:
    return "artifact:sha256:" + hashlib.sha256(data).hexdigest()


def _repository_url(value: Any, field: str) -> str:
    url = _text(value, field)
    if SSH_SCP_RE.fullmatch(url):
        return url.rstrip("/")
    try:
        parsed = urlsplit(url)
    except ValueError as error:
        raise PlanError(f"{field} is a malformed repository URL") from error
    if parsed.scheme not in {"https", "ssh"} or not parsed.hostname:
        raise PlanError(f"{field} must be a credential-free https or ssh Git URL")
    userinfo = parsed.netloc.rsplit("@", 1)[0] if "@" in parsed.netloc else None
    allowed_ssh_user = parsed.scheme == "ssh" and userinfo == "git"
    if (parsed.username and not allowed_ssh_user) or parsed.password or parsed.query or parsed.fragment:
        raise PlanError(f"{field} must not contain credentials, query, or fragment")
    if userinfo is not None and not allowed_ssh_user:
        raise PlanError(f"{field} must not contain credentials, query, or fragment")
    if not parsed.path or parsed.path == "/":
        raise PlanError(f"{field} must identify a repository path")
    if ":" in parsed.hostname:
        raise PlanError(f"{field} IPv6 hosts are not supported")
    host = parsed.hostname.lower()
    try:
        port = parsed.port
    except ValueError as error:
        raise PlanError(f"{field} has an invalid port") from error
    if port:
        host += f":{port}"
    if allowed_ssh_user:
        host = "git@" + host
    return urlunsplit((parsed.scheme, host, parsed.path.rstrip("/"), "", ""))


def _url_identity(value: str) -> tuple[str, str, int, str]:
    match = SSH_SCP_RE.fullmatch(value)
    if match:
        host, path = match.groups()
        scheme, port = "ssh", 22
    else:
        parsed = urlsplit(value)
        host, path = parsed.hostname or "", parsed.path
        scheme = parsed.scheme
        try:
            port = parsed.port or (443 if scheme == "https" else 22)
        except ValueError as error:
            raise PlanError("repository URL has an invalid port") from error
    path = path.lstrip("/").removesuffix(".git").rstrip("/")
    return scheme, host.lower(), port, path


def _path(value: Any, field: str) -> str:
    path = _text(value, field)
    parsed = PurePosixPath(path)
    segments = path.split("/")
    if path.startswith("/") or any(segment in {"", ".", ".."} for segment in segments) or ".." in parsed.parts:
        raise PlanError(f"{field} must be normalized, relative, and traversal-free")
    return path


def _ordered_unique_texts(value: Any, field: str, *, sorted_unique: bool) -> list[str]:
    values = [_text(item, f"{field}[]") for item in _array(value, field)]
    if len(values) != len(set(values)):
        raise PlanError(f"{field} must contain unique values")
    if sorted_unique and values != sorted(values):
        raise PlanError(f"{field} must be sorted and unique")
    return values


def validate_source(value: Any) -> dict[str, Any]:
    _deny_leakage(value)
    source = _object(
        value, "source", {"contract_id", "plan_id", "repositories", "entries", "integrations", "execution"}
    )
    _required(source, "source", {"contract_id", "plan_id", "repositories", "entries", "integrations", "execution"})
    if source["contract_id"] != SOURCE_CONTRACT:
        raise PlanError(f"contract_id must be {SOURCE_CONTRACT}")
    plan_id = _text(source["plan_id"], "plan_id")

    repositories: list[dict[str, str]] = []
    repository_by_id: dict[str, dict[str, str]] = {}
    for index, raw in enumerate(_array(source["repositories"], "repositories")):
        field = f"repositories[{index}]"
        repo = _object(raw, field, {"repository_id", "repository_url", "commit"})
        _required(repo, field, {"repository_id", "repository_url", "commit"})
        repository_id = _text(repo["repository_id"], f"{field}.repository_id")
        if repository_id in repository_by_id:
            raise PlanError(f"duplicate repository_id: {repository_id}")
        commit = _text(repo["commit"], f"{field}.commit")
        if not OID_RE.fullmatch(commit):
            raise PlanError(f"{field}.commit must be a full lowercase Git object id")
        normalized = {"repository_id": repository_id, "repository_url": _repository_url(repo["repository_url"], f"{field}.repository_url"), "commit": commit}
        repositories.append(normalized)
        repository_by_id[repository_id] = normalized
    if not repositories:
        raise PlanError("repositories must not be empty")

    entries: list[dict[str, Any]] = []
    entry_by_id: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(_array(source["entries"], "entries")):
        field = f"entries[{index}]"
        keys = {"id", "repository_id", "work", "topology", "base_entry_id", "integration_lane", "command_id", "allowed_paths", "required_capabilities", "worker_profile", "acceptance_gates"}
        entry = _object(raw, field, keys)
        _required(entry, field, keys - {"base_entry_id"})
        entry_id = _text(entry["id"], f"{field}.id")
        if entry_id in entry_by_id:
            raise PlanError(f"duplicate entry id: {entry_id}")
        repository_id = _text(entry["repository_id"], f"{field}.repository_id")
        if repository_id not in repository_by_id:
            raise PlanError(f"{field}.repository_id references an unknown repository")
        work = _object(entry["work"], f"{field}.work", {"item_id", "selected_revision", "observed_revision"})
        _required(work, f"{field}.work", {"item_id", "selected_revision", "observed_revision"})
        selected_revision = _text(work["selected_revision"], f"{field}.work.selected_revision")
        observed_revision = _text(work["observed_revision"], f"{field}.work.observed_revision")
        if selected_revision != observed_revision:
            raise PlanError(f"{field}.work revision drift: selected_revision does not equal observed_revision")
        topology = entry["topology"]
        if topology not in TOPOLOGIES:
            raise PlanError(f"{field}.topology is invalid")
        base = entry.get("base_entry_id")
        if topology == "stacked":
            base = _text(base, f"{field}.base_entry_id")
            previous = entry_by_id.get(base)
            if previous is None or previous["repository_id"] != repository_id:
                raise PlanError(f"{field}.base_entry_id must name an earlier same-repository entry")
        elif base is not None:
            raise PlanError(f"{field}.base_entry_id is allowed only for stacked entries")
        lane = entry["integration_lane"]
        if lane is not None:
            lane = _text(lane, f"{field}.integration_lane")
        normalized_entry: dict[str, Any] = {
            "id": entry_id,
            "repository_id": repository_id,
            "work": {"item_id": _integer(work["item_id"], f"{field}.work.item_id"), "revision": selected_revision},
            "topology": topology,
            "integration_lane": lane,
            "command_id": _text(entry["command_id"], f"{field}.command_id"),
            "allowed_paths": [_path(item, f"{field}.allowed_paths[]") for item in _array(entry["allowed_paths"], f"{field}.allowed_paths")],
            "required_capabilities": _ordered_unique_texts(entry["required_capabilities"], f"{field}.required_capabilities", sorted_unique=True),
            "worker_profile": _text(entry["worker_profile"], f"{field}.worker_profile"),
            "acceptance_gates": _ordered_unique_texts(entry["acceptance_gates"], f"{field}.acceptance_gates", sorted_unique=True),
        }
        if len(normalized_entry["allowed_paths"]) != len(set(normalized_entry["allowed_paths"])):
            raise PlanError(f"{field}.allowed_paths must contain unique values")
        if base is not None:
            normalized_entry["base_entry_id"] = base
        entries.append(normalized_entry)
        entry_by_id[entry_id] = normalized_entry
    if not entries:
        raise PlanError("entries must not be empty")

    integrations: list[dict[str, Any]] = []
    integration_ids: set[str] = set()
    used_members: set[str] = set()
    for index, raw in enumerate(_array(source["integrations"], "integrations")):
        field = f"integrations[{index}]"
        keys = {"id", "repository_id", "member_ids", "base_commit", "verification_profile", "review_required"}
        integration = _object(raw, field, keys)
        _required(integration, field, keys)
        integration_id = _text(integration["id"], f"{field}.id")
        if integration_id in integration_ids or integration_id in entry_by_id:
            raise PlanError(f"duplicate integration id: {integration_id}")
        integration_ids.add(integration_id)
        repository_id = _text(integration["repository_id"], f"{field}.repository_id")
        repo = repository_by_id.get(repository_id)
        if repo is None:
            raise PlanError(f"{field}.repository_id references an unknown repository")
        members = _ordered_unique_texts(integration["member_ids"], f"{field}.member_ids", sorted_unique=False)
        if not members:
            raise PlanError(f"{field}.member_ids must not be empty")
        for member in members:
            candidate = entry_by_id.get(member)
            if candidate is None or candidate["repository_id"] != repository_id:
                raise PlanError(f"{field}.member_ids must name same-repository entries")
            if candidate["topology"] != "wave-integrated":
                raise PlanError(f"{field}.member_ids may contain only wave-integrated entries")
            if member in used_members:
                raise PlanError(f"entry {member!r} belongs to more than one integration")
            used_members.add(member)
        if integration["base_commit"] != repo["commit"]:
            raise PlanError(f"{field}.base_commit must equal the repository source commit")
        if not isinstance(integration["review_required"], bool):
            raise PlanError(f"{field}.review_required must be boolean")
        integrations.append({"id": integration_id, "repository_id": repository_id, "member_ids": members, "base_commit": repo["commit"], "verification_profile": _text(integration["verification_profile"], f"{field}.verification_profile"), "review_required": integration["review_required"]})
    expected_wave = {entry["id"] for entry in entries if entry["topology"] == "wave-integrated"}
    if used_members != expected_wave:
        raise PlanError(f"wave-integrated entries must appear exactly once in integrations: missing={sorted(expected_wave - used_members)}")

    execution = _object(source["execution"], "execution", {"max_parallel", "failure_policy"})
    _required(execution, "execution", {"max_parallel", "failure_policy"})
    if execution["failure_policy"] != FAILURE_POLICY:
        raise PlanError(f"execution.failure_policy must be {FAILURE_POLICY}")
    return {"contract_id": PLAN_CONTRACT, "plan_id": plan_id, "repositories": repositories, "entries": entries, "integrations": integrations, "execution": {"max_parallel": _integer(execution["max_parallel"], "execution.max_parallel", maximum=32), "failure_policy": FAILURE_POLICY}}


def compile_plan(value: Any) -> bytes:
    return canonical_bytes(validate_source(value))


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PlanError(f"cannot read JSON from {path}: {error}") from error


def load_plan(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise PlanError(f"cannot read compiled plan {path}: {error}") from error
    if not isinstance(value, dict) or value.get("contract_id") != PLAN_CONTRACT:
        raise PlanError(f"compiled plan must be {PLAN_CONTRACT}")
    try:
        source_form = {**value, "contract_id": SOURCE_CONTRACT}
        source_form["entries"] = [
            {**entry, "work": {"item_id": entry["work"]["item_id"], "selected_revision": entry["work"]["revision"], "observed_revision": entry["work"]["revision"]}}
            for entry in value.get("entries", [])
        ]
    except (KeyError, TypeError, IndexError) as error:
        raise PlanError(f"compiled plan has malformed structure: {error}") from error
    validated = validate_source(source_form)
    if validated != value:
        raise PlanError("compiled plan is not the normalized compiler output")
    canonical = canonical_bytes(value)
    if raw not in {canonical, canonical + b"\n"}:
        raise PlanError("compiled plan bytes are not canonical")
    return value, canonical


def validate_bindings(value: Any, entry_ids: list[str]) -> dict[str, tuple[int, str]]:
    _deny_leakage(value)
    bindings = _object(value, "bindings", {"contract_id", "bindings"})
    _required(bindings, "bindings", {"contract_id", "bindings"})
    if bindings["contract_id"] != BINDINGS_CONTRACT:
        raise PlanError(f"bindings.contract_id must be {BINDINGS_CONTRACT}")
    result: dict[str, tuple[int, str]] = {}
    action_ids: set[int] = set()
    for index, raw in enumerate(_array(bindings["bindings"], "bindings.bindings")):
        field = f"bindings.bindings[{index}]"
        binding = _object(raw, field, {"entry_id", "action_id", "attempt_id"})
        _required(binding, field, {"entry_id", "action_id", "attempt_id"})
        entry_id = _text(binding["entry_id"], f"{field}.entry_id")
        action_id = _integer(binding["action_id"], f"{field}.action_id")
        attempt_id = _text(binding["attempt_id"], f"{field}.attempt_id")
        if entry_id in result or action_id in action_ids:
            raise PlanError("bindings require unique entry_id and action_id values")
        result[entry_id] = (action_id, attempt_id)
        action_ids.add(action_id)
    if list(result) != entry_ids:
        raise PlanError("bindings must be complete and in exact compiled plan entry order")
    return result


def realize_group(plan: dict[str, Any], plan_bytes: bytes, bindings_value: Any) -> dict[str, Any]:
    entries = plan.get("entries")
    if not isinstance(entries, list):
        raise PlanError("compiled plan entries are invalid")
    if any(entry.get("topology") == "stacked" for entry in entries):
        raise PlanError("stacked topology requires staged downstream realization that binds the predecessor candidate commit")
    entry_ids = [entry["id"] for entry in entries]
    bindings = validate_bindings(bindings_value, entry_ids)
    repo_commits = {repo["repository_id"]: repo["commit"] for repo in plan["repositories"]}
    members = []
    for entry in entries:
        action_id, attempt_id = bindings[entry["id"]]
        envelope = {"contract_id": ENVELOPE_CONTRACT, "action_id": action_id, "attempt_id": attempt_id, "source_commit": repo_commits[entry["repository_id"]], "command_id": entry["command_id"], "allowed_paths": entry["allowed_paths"]}
        if set(envelope) != {"contract_id", "action_id", "attempt_id", "source_commit", "command_id", "allowed_paths"}:
            raise AssertionError("execution envelope field drift")
        members.append({"action_id": action_id, "envelope": envelope})
    return {"contract_id": GROUP_CONTRACT, "plan_ref": artifact_ref(plan_bytes), "max_parallel": plan["execution"]["max_parallel"], "failure_policy": plan["execution"]["failure_policy"], "members": members}


def _artifact(value: Any, field: str) -> str:
    text = _text(value, field)
    if not ARTIFACT_RE.fullmatch(text):
        raise PlanError(f"{field} must be artifact:sha256:<hex>")
    return text


def _digest_ref(reference: str) -> str:
    match = ARTIFACT_RE.fullmatch(reference)
    assert match
    return "sha256:" + match.group(1)


def realize_integration(plan: dict[str, Any], plan_bytes: bytes, results_value: Any) -> dict[str, Any]:
    results = _object(results_value, "results", {"contract_id", "integration_id", "member_results"})
    _required(results, "results", {"contract_id", "integration_id", "member_results"})
    if results["contract_id"] != "integration-results/v1":
        raise PlanError("results.contract_id must be integration-results/v1")
    integration_id = _text(results["integration_id"], "results.integration_id")
    integrations = [item for item in plan.get("integrations", []) if item.get("id") == integration_id]
    if len(integrations) != 1:
        raise PlanError("integration_id must select exactly one compiled integration")
    integration = integrations[0]
    members = _array(results["member_results"], "results.member_results")
    expected_ids = integration["member_ids"]
    if len(members) != len(expected_ids):
        raise PlanError("member results must match exact compiled integration count and order")
    refs: list[str] = []
    for index, (raw, expected_id) in enumerate(zip(members, expected_ids, strict=True)):
        field = f"results.member_results[{index}]"
        member = _object(raw, field, {"entry_id", "result_ref"})
        _required(member, field, {"entry_id", "result_ref"})
        if member["entry_id"] != expected_id:
            raise PlanError("member results must match exact compiled integration count and order")
        refs.append(_artifact(member["result_ref"], f"{field}.result_ref"))
    if len(refs) != len(set(refs)):
        raise PlanError("member result references must be unique")
    input_set = {"contract_id": "immutable-input-set/v1", "inputs": refs}
    input_set_digest = "sha256:" + hashlib.sha256(canonical_bytes(input_set)).hexdigest()
    spec = {"contract_id": "candidate-integration-spec/v1", "topology": "wave-integrated", "base_commit": integration["base_commit"], "member_result_refs": refs, "input_set_digest": input_set_digest}
    spec_bytes = canonical_bytes(spec)
    spec_ref = artifact_ref(spec_bytes)
    request = {"contract_id": "action-creation-request/v1", "plan_ref": artifact_ref(plan_bytes), "topology": "wave-integrated", "role": "candidate-integration", "subject": integration_id, "spec_ref": spec_ref, "spec_digest": _digest_ref(spec_ref), "input_set_digest": input_set_digest}
    return {"contract_id": "integration-realization/v1", "input_refs": refs, "integration_spec": spec, "action_creation_request": request}


def _git(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(["git", "-C", str(root), *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PlanError(f"Git source check failed for {root}: {error}") from error
    if result.returncode:
        raise PlanError(f"Git source check failed for {root}: {result.stderr.strip()}")
    return result.stdout.strip()


def check_repositories(plan: dict[str, Any], roots: dict[str, Path]) -> None:
    expected = {repo["repository_id"] for repo in plan["repositories"]}
    if set(roots) != expected:
        raise PlanError(f"repo roots must cover exact repository set: {sorted(expected)}")
    for repo in plan["repositories"]:
        root = roots[repo["repository_id"]]
        head = _git(root, "rev-parse", "HEAD")
        if head != repo["commit"]:
            raise PlanError(f"{repo['repository_id']} HEAD mismatch: expected {repo['commit']}, got {head}")
        _git(root, "cat-file", "-e", f"{repo['commit']}^{{commit}}")
        origin = _repository_url(_git(root, "remote", "get-url", "origin"), f"{repo['repository_id']} origin")
        if _url_identity(origin) != _url_identity(repo["repository_url"]):
            raise PlanError(f"{repo['repository_id']} origin does not match frozen repository_url")


def _parse_roots(values: list[str], repository_ids: list[str]) -> dict[str, Path]:
    roots: dict[str, Path] = {}
    for value in values:
        if "=" in value:
            repository_id, path = value.split("=", 1)
        elif len(repository_ids) == 1:
            repository_id, path = repository_ids[0], value
        else:
            raise PlanError("multiple repositories require --repo-root REPOSITORY_ID=PATH")
        if not repository_id or not path or repository_id in roots:
            raise PlanError("invalid or duplicate --repo-root")
        roots[repository_id] = Path(path)
    return roots


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _status(command: str, status: str, **values: Any) -> None:
    print(json.dumps({"command": command, "status": status, **values}, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    command_name = raw_argv[0] if raw_argv else "unknown"
    parser = JsonArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("compile", "check"):
        command = commands.add_parser(name)
        command.add_argument("--source", required=True, type=Path)
        command.add_argument("--output", required=True, type=Path)
        command.add_argument("--repo-root", action="append", default=[])
    realize = commands.add_parser("realize")
    realize.add_argument("--plan", required=True, type=Path)
    realize.add_argument("--bindings", required=True, type=Path)
    realize.add_argument("--output", required=True, type=Path)
    realize_integration_parser = commands.add_parser("realize-integration")
    realize_integration_parser.add_argument("--plan", required=True, type=Path)
    realize_integration_parser.add_argument("--results", required=True, type=Path)
    realize_integration_parser.add_argument("--output", required=True, type=Path)
    try:
        args = parser.parse_args(raw_argv)
        command_name = args.command
        if args.command in {"compile", "check"}:
            source = load_json(args.source)
            compiled = compile_plan(source)
            plan = json.loads(compiled)
            if args.repo_root:
                check_repositories(plan, _parse_roots(args.repo_root, [repo["repository_id"] for repo in plan["repositories"]]))
            reference = artifact_ref(compiled)
            if args.command == "compile":
                _atomic_write(args.output, compiled)
                _status("compile", "written", output=str(args.output), plan_ref=reference)
                return 0
            if not args.output.exists():
                _status("check", "missing", output=str(args.output), plan_ref=reference)
                return 1
            actual = args.output.read_bytes()
            if actual == compiled:
                _status("check", "exact", output=str(args.output), plan_ref=reference)
                return 0
            diff = "".join(difflib.unified_diff(actual.decode("utf-8", "replace").splitlines(True), compiled.decode("utf-8").splitlines(True), fromfile=str(args.output), tofile="expected"))
            _status("check", "drift", output=str(args.output), plan_ref=reference, diff=diff)
            return 1
        plan, plan_bytes = load_plan(args.plan)
        if args.command == "realize":
            product = realize_group(plan, plan_bytes, load_json(args.bindings))
        else:
            product = realize_integration(plan, plan_bytes, load_json(args.results))
        rendered = canonical_bytes(product)
        _atomic_write(args.output, rendered)
        plan_reference = product.get("plan_ref", product.get("action_creation_request", {}).get("plan_ref"))
        _status(args.command, "written", output=str(args.output), plan_ref=plan_reference)
        return 0
    except (PlanError, OSError, KeyError, IndexError, TypeError) as error:
        _status(command_name, "invalid", error=str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
