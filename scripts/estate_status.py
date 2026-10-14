#!/usr/bin/env python3
"""Read-only estate status report: `agentops estate status [--env X] [--json]`.

For every environment of the estate (the vuoro-shared appservice deployment, the
vuoro-cloud Hetzner PoC, and the agent hosts) this answers five questions with
facts, never with assumptions:

* desired  -- what Git (and the release tags Flux selects) declares;
* running  -- what the cluster or host is actually running;
* usable   -- what a live handshake/catalog/doctor says a client can use;
* held     -- what is deliberately or accidentally paused;
* gate     -- the next blocking gate and which recovery class applies now
              (``cancel`` / ``image-revert`` / ``forward-fix-or-restore``),
              derived from the facts above.

Every fact is ``{status, value, source, observed_at, evidence}``; a fact that could
not be observed is ``status: unknown`` with a ``reason`` and is a valid answer, not
an error. ``source`` is one of ``artifact`` (a file in Git or a recorded receipt),
``live-api`` (an HTTP/Git-remote call), ``cluster`` (kubectl get), ``document``
(a runbook statement) or ``derived`` (computed from named facts).

The report is strictly read-only: kubectl is only ever called with ``get``, HTTP
only with GET, and the host probes run diagnostics. ``--fetch`` updates
remote-tracking refs in the local clones (no working-tree change) so desired state
is read at the deploying ref rather than at a stale local one.

Every probe goes through one ``Probe`` object, so a live run can be recorded with
``--record DIR`` (secrets redacted before anything is written) and replayed with
``--replay DIR``; the tests use recorded fixtures and never touch the network.

The JSON shape is ``environment-record/estate-status-v1.schema.json``; ``--markdown``
(the default human output) renders the same document, and ``--from FILE`` renders
a previously saved JSON report.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

try:  # PyYAML is a scripts/ dependency already (render_disposition_fragment).
    import yaml
except ImportError:  # pragma: no cover - exercised only on a bare interpreter
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "environment-record/estate-status-v1.schema.json"
SCHEMA_VERSION = "estate-status/v1"
DEV_ROOT = Path(os.environ.get("AGENTOPS_DEV_ROOT", "/projects/dev"))

SOURCES = ("artifact", "live-api", "cluster", "document", "derived")
RECOVERY_CLASSES = ("cancel", "image-revert", "forward-fix-or-restore")
CLIENT_PROTOCOL = 1  # vuoro_client.client.PROTOCOL_VERSION
PROTOCOL_HEADER = "X-Vuoro-Client-Protocol"  # without it the service answers 426
USER_AGENT = "agentops-estate-status/1 (read-only)"

ENVIRONMENTS = ("vuoro-shared", "vuoro-cloud", "workstation", "devbox")

VUORO_SHARED = {
    "repo": DEV_ROOT / "appservice",
    "remote_url": "https://github.com/bayleafwalker/appservice.git",
    "kubeconfig": DEV_ROOT / "appservice/clusters/.kube/config",
    "namespace": "vuoro-shared",
    "app_dirs": (
        "clusters/main/kubernetes/apps/vuoro-shared",
        "clusters/main/kubernetes/apps/vuoro-shared-db",
    ),
    "deployment": "vuoro-shared",
    "endpoint": "https://vuoro-shared.apps.kotona.app",
    "service_repo": DEV_ROOT / "vuoro",
    "service_remote_url": "https://github.com/bayleafwalker/vuoro.git",
    "service_tag_prefix": "vuoro-service-v",
}

VUORO_CLOUD = {
    "repo": DEV_ROOT / "vuoro-cloud",
    "flux_source_file": "clusters/bootstrap/poc/resources.yaml",
    "kubeconfig": Path.home() / ".config/vuoro/kube/poc.yaml",
    "tunnel_interface": "vuoro-cloud-wg",
    "namespace": "vuoro-system",
    "apps_dir": "apps",
    "kustomizations": ("vuoro-cloud-operators", "vuoro-cloud-platform", "vuoro-cloud-apps"),
    "api": "https://api.vuoro.cloud",
    "operator_token_file": Path.home() / ".config/vuoro/credentials/vuoro-cloud.token",
}

HOSTS = {
    "workstation": {
        "environment_record": "environment-record/workstation-linux.vuoro-shared.json",
        "profile": "environment-record/profiles/workstation-vuoro-shared.json",
        "ssh": None,
        "envrc": DEV_ROOT / "agentops/.envrc",
        "doctor_cwd": DEV_ROOT / "agentops",
    },
    "devbox": {
        "environment_record": "environment-record/devbox-vm.vuoro-shared.json",
        "profile": "environment-record/profiles/devbox-agent-vuoro-shared.json",
        "ssh": "devbox-agent",
        "installed_profile": "~/.config/vuoro/profiles/devbox-agent-vuoro-shared.json",
        "repo_id": "agentops",
    },
}

# ---------------------------------------------------------------- redaction

_REDACTIONS = (
    (re.compile(r"(?i)(authorization:\s*bearer\s+)\S+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"), "Bearer [REDACTED]"),
    (re.compile(r"\bvuo_[A-Za-z0-9_]{6,}"), "vuo_[REDACTED]"),
    (re.compile(r"(?i)\b(postgres(?:ql)?|mysql|redis)://[^\s\"']+"), r"\1://[REDACTED]"),
    (re.compile(r"(?i)(password|passwd|secret|token)=([^\s&\"']+)"), r"\1=[REDACTED]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), "gh_[REDACTED]"),
    (re.compile(r"AGE-SECRET-KEY-[A-Z0-9]+"), "AGE-SECRET-KEY-[REDACTED]"),
)


def redact(text: str) -> str:
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------- probes


def _apply(transform: Callable[[str], str] | None, text: str) -> str:
    """Minimize raw output before it is kept (smaller fixtures, nothing unread retained)."""
    if transform is None:
        return text
    try:
        return transform(text)
    except Exception:  # noqa: BLE001 - unparseable output is kept verbatim and fails at parse
        return text


def _minimize_k8s(text: str) -> str:
    """Drop managedFields, annotations and pod/container env from kubectl JSON."""
    doc = json.loads(text)

    def strip(item: dict[str, Any]) -> None:
        meta = item.get("metadata") or {}
        meta.pop("managedFields", None)
        meta.pop("annotations", None)
        spec = item.get("spec") or {}
        for holder in (spec, (spec.get("template") or {}).get("spec") or {},
                       (((spec.get("jobTemplate") or {}).get("spec") or {}).get("template") or {}).get("spec") or {}):
            for container in holder.get("containers", []) + holder.get("initContainers", []):
                for noisy in ("env", "envFrom", "command", "args", "volumeMounts"):
                    container.pop(noisy, None)
            holder.pop("volumes", None)
        status = item.get("status") or {}
        status.pop("inventory", None)

    for item in doc.get("items", [doc]):
        strip(item)
    return json.dumps(doc, sort_keys=True)


def _minimize_catalog(text: str) -> str:
    doc = json.loads(text)
    doc["operations"] = [{"name": o.get("name"), "owning_domain": o.get("owning_domain")}
                         for o in doc.get("operations", [])]
    return json.dumps(doc, sort_keys=True)


class Probe:
    """Single choke point for every observation: live, recording, or replay."""

    def __init__(self, *, record: Path | None = None, replay: Path | None = None) -> None:
        self.record = record
        self.replay = replay
        if record:
            record.mkdir(parents=True, exist_ok=True)

    @property
    def mode(self) -> str:
        return "replay" if self.replay else "live"

    def _fixture(self, key: str) -> Path:
        return (self.replay or self.record) / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', key)}.json"

    def _replayed(self, key: str) -> dict[str, Any]:
        path = self._fixture(key)
        if not path.exists():
            return {"ok": False, "error": f"no recorded fixture for probe {key!r}",
                    "observed_at": None, "evidence": key}
        return json.loads(path.read_text(encoding="utf-8"))

    def _store(self, key: str, result: dict[str, Any]) -> dict[str, Any]:
        if self.record:
            self._fixture(key).write_text(json.dumps(result, indent=1, sort_keys=True) + "\n",
                                          encoding="utf-8")
        return result

    def run(self, key: str, argv: list[str], *, evidence: str | None = None,
            cwd: Path | None = None, env: dict[str, str] | None = None,
            unset: tuple[str, ...] = (), stdin: str | None = None,
            timeout: int = 30, transform: Callable[[str], str] | None = None) -> dict[str, Any]:
        if argv and argv[0] == "kubectl" and not set(argv[1:2]) <= {"get", "version"}:
            raise ValueError(f"estate status is read-only; refusing kubectl {argv[1:2]}")
        if self.replay:
            return self._replayed(key)
        full_env = {**os.environ, **(env or {})}
        for name in unset:
            full_env.pop(name, None)
        observed = _now()
        try:
            # Never inherit our stdin: under `agentops estate mcp` it is the JSON-RPC
            # channel, and a child (ssh, kubectl) reading it would eat protocol messages.
            stdin_kw = {"input": stdin} if stdin is not None else {"stdin": subprocess.DEVNULL}
            done = subprocess.run(argv, cwd=cwd, env=full_env, text=True,
                                  capture_output=True, timeout=timeout, **stdin_kw)
            stdout = _apply(transform, done.stdout) if done.returncode == 0 else done.stdout
            result = {"ok": done.returncode == 0, "rc": done.returncode,
                      "stdout": redact(stdout), "stderr": redact(done.stderr[-2000:])}
        except subprocess.TimeoutExpired:
            result = {"ok": False, "rc": None, "stdout": "", "stderr": "",
                      "error": f"timed out after {timeout}s"}
        except OSError as error:
            result = {"ok": False, "rc": None, "stdout": "", "stderr": "",
                      "error": f"cannot execute {argv[0]}: {error.strerror or error}"}
        result.update(observed_at=observed, evidence=evidence or " ".join(argv))
        if not result["ok"] and "error" not in result:
            tail = result["stderr"].strip().splitlines()[-1:] or [f"exit {result['rc']}"]
            result["error"] = tail[0][:300]
        return self._store(key, result)

    def http(self, key: str, url: str, *, headers: dict[str, str] | None = None,
             secret_headers: dict[str, str] | None = None, timeout: int = 15,
             transform: Callable[[str], str] | None = None) -> dict[str, Any]:
        """GET only. ``secret_headers`` are sent but never recorded or echoed."""
        if self.replay:
            return self._replayed(key)
        # Cloudflare (api.vuoro.cloud) challenges urllib's default User-Agent with a 403.
        request = urllib.request.Request(url, method="GET", headers={
            "User-Agent": USER_AGENT, **(headers or {}), **(secret_headers or {})})
        observed = _now()
        shown = " ".join(f"-H '{k}: {v}'" for k, v in (headers or {}).items())
        if secret_headers:
            shown += " " + " ".join(f"-H '{k}: [REDACTED]'" for k in secret_headers)
        evidence = f"GET {url} {shown}".strip()
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status, body, hdrs = response.status, response.read(), dict(response.headers)
        except urllib.error.HTTPError as error:
            status, body, hdrs = error.code, error.read(), dict(error.headers or {})
        except (urllib.error.URLError, OSError, TimeoutError) as error:
            return self._store(key, {"ok": False, "status": None, "body": "",
                                     "error": f"unreachable: {getattr(error, 'reason', error)}",
                                     "observed_at": observed, "evidence": evidence})
        keep = {k.lower(): v for k, v in hdrs.items() if k.lower() in {"etag", "content-type"}}
        result = {"ok": 200 <= status < 300, "status": status,
                  "body": redact(_apply(transform if 200 <= status < 300 else None,
                                        body.decode("utf-8", "replace"))[:400_000]),
                  "headers": keep, "observed_at": observed, "evidence": evidence}
        if not result["ok"]:
            result["error"] = f"HTTP {status}"
        return self._store(key, result)


# ---------------------------------------------------------------- facts


def known(value: Any, source: str, evidence: str, observed_at: str | None) -> dict[str, Any]:
    assert source in SOURCES, source
    return {"status": "known", "value": value, "source": source,
            "observed_at": observed_at, "evidence": evidence}


def unknown(reason: str, source: str, evidence: str,
            observed_at: str | None = None) -> dict[str, Any]:
    assert source in SOURCES, source
    return {"status": "unknown", "value": None, "source": source,
            "observed_at": observed_at, "evidence": evidence, "reason": reason}


def is_known(fact: dict[str, Any] | None) -> bool:
    return bool(fact) and fact["status"] == "known"


def from_probe(result: dict[str, Any], source: str,
               parse: Callable[[dict[str, Any]], Any]) -> dict[str, Any]:
    """Known(parse(result)) when the probe succeeded and parsing did; else unknown."""
    if not result.get("ok"):
        return unknown(result.get("error") or "probe failed", source, result.get("evidence", "?"),
                       result.get("observed_at"))
    try:
        value = parse(result)
    except Exception as error:  # noqa: BLE001 - any parse failure is an unknown, by design
        return unknown(f"unparseable probe output: {type(error).__name__}: {error}"[:300],
                       source, result["evidence"], result.get("observed_at"))
    return known(value, source, result["evidence"], result.get("observed_at"))


def _json_out(result: dict[str, Any]) -> Any:
    return json.loads(result["stdout"] if "stdout" in result else result["body"])


DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


def digest_of(ref: str | None) -> str | None:
    match = DIGEST.search(ref or "")
    return match.group(0) if match else None


# ---------------------------------------------------------------- git helpers


def git(probe: Probe, key: str, repo: Path, *args: str, timeout: int = 30,
        transform: Callable[[str], str] | None = None) -> dict[str, Any]:
    return probe.run(key, ["git", "-C", str(repo), *args], timeout=timeout, transform=transform,
                     evidence=f"git -C {repo} {' '.join(args)}")


def ls_remote_head(probe: Probe, key: str, url: str, branch: str = "main") -> dict[str, Any]:
    result = probe.run(key, ["git", "ls-remote", url, f"refs/heads/{branch}"], timeout=30)
    return from_probe(result, "live-api", lambda r: r["stdout"].split()[0])


def ls_remote_tags(probe: Probe, key: str, url: str) -> dict[str, Any]:
    result = probe.run(key, ["git", "ls-remote", "--tags", url], timeout=30)

    def parse(r: dict[str, Any]) -> dict[str, str]:
        tags: dict[str, str] = {}
        for line in r["stdout"].splitlines():
            sha, _, ref = line.partition("\t")
            if not ref.startswith("refs/tags/"):
                continue
            name = ref[len("refs/tags/"):]
            if name.endswith("^{}"):
                tags[name[:-3]] = sha  # peeled commit wins over the tag object
            else:
                tags.setdefault(name, sha)
        return tags

    return from_probe(result, "live-api", parse)


def yaml_docs(text: str) -> list[dict[str, Any]]:
    if yaml is None:
        raise RuntimeError("PyYAML is not installed")
    return [doc for doc in yaml.safe_load_all(text) if isinstance(doc, dict)]


def manifest_files(probe: Probe, key: str, repo: Path, ref: str,
                   dirs: tuple[str, ...]) -> dict[str, Any]:
    """{path: text} for every YAML file under ``dirs`` at ``ref`` (SOPS secrets skipped)."""
    listing = git(probe, f"{key}.ls-tree", repo, "ls-tree", "-r", "--name-only", ref, *dirs)
    if not listing.get("ok"):
        return unknown(listing.get("error", "ls-tree failed"), "artifact", listing["evidence"],
                       listing.get("observed_at"))
    files: dict[str, str] = {}
    for index, path in enumerate(sorted(listing["stdout"].split())):
        if not path.endswith((".yaml", ".yml")) or ".secret." in path or path.endswith(".sops.yaml"):
            continue
        shown = git(probe, f"{key}.show.{index}", repo, "show", f"{ref}:{path}")
        if not shown.get("ok"):
            return unknown(f"cannot read {path} at {ref}: {shown.get('error')}", "artifact",
                           shown["evidence"], shown.get("observed_at"))
        files[path] = shown["stdout"]
    return known(files, "artifact", f"git:{repo.name}@{ref}:{','.join(dirs)}",
                 listing.get("observed_at"))


def declared_workloads(files: dict[str, str]) -> dict[str, Any]:
    """Deployments, CronJobs, Jobs and Flux Kustomizations declared in ``files``."""
    out: dict[str, Any] = {"deployments": {}, "cronjobs": {}, "jobs": {}, "kustomizations": {}}
    for path, text in sorted(files.items()):
        try:
            docs = yaml_docs(text)
        except Exception:  # noqa: BLE001 - a non-YAML-ish file is not a workload
            continue
        for doc in docs:
            kind, meta, spec = doc.get("kind"), doc.get("metadata") or {}, doc.get("spec") or {}
            name = meta.get("name")
            if kind == "Deployment":
                containers = spec.get("template", {}).get("spec", {}).get("containers", [])
                out["deployments"][name] = {
                    "namespace": meta.get("namespace"), "replicas": spec.get("replicas", 1),
                    "images": {c["name"]: c.get("image") for c in containers}, "path": path}
            elif kind == "CronJob":
                out["cronjobs"][name] = {"suspend": bool(spec.get("suspend", False)), "path": path}
            elif kind == "Job":
                containers = spec.get("template", {}).get("spec", {}).get("containers", [])
                out["jobs"][name] = {"images": {c["name"]: c.get("image") for c in containers},
                                     "path": path}
            elif kind == "Kustomization" and "kustomize.toolkit.fluxcd.io" in str(doc.get("apiVersion")):
                out["kustomizations"][name] = {"suspend": bool(spec.get("suspend", False)),
                                               "path": path}
    return out


# ---------------------------------------------------------------- kubectl


def kget(probe: Probe, key: str, kubeconfig: Path, *args: str) -> dict[str, Any]:
    argv = ["kubectl", "get", *args, "-o", "json", "--request-timeout=15s"]
    return probe.run(key, argv, env={"KUBECONFIG": str(kubeconfig)}, timeout=40, transform=_minimize_k8s,
                     evidence=f"KUBECONFIG={kubeconfig} {' '.join(argv)}")


def running_workloads(probe: Probe, prefix: str, kubeconfig: Path, namespace: str,
                      kustomizations: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    facts: dict[str, dict[str, Any]] = {}
    deploys = kget(probe, f"{prefix}.deploy", kubeconfig, "deploy", "-n", namespace)
    facts["deployments"] = from_probe(deploys, "cluster", lambda r: {
        d["metadata"]["name"]: {
            "replicas": d["spec"].get("replicas", 1),
            "ready": d.get("status", {}).get("readyReplicas", 0),
            "updated": d.get("status", {}).get("updatedReplicas", 0),
            "available": d.get("status", {}).get("availableReplicas", 0),
            "images": {c["name"]: c["image"] for c in d["spec"]["template"]["spec"]["containers"]},
        } for d in _json_out(r)["items"]})
    pods = kget(probe, f"{prefix}.pods", kubeconfig, "pods", "-n", namespace)

    def parse_pods(r: dict[str, Any]) -> list[dict[str, Any]]:
        rows = []
        for pod in _json_out(r)["items"]:
            owner = (pod["metadata"].get("ownerReferences") or [{}])[0].get("kind")
            if owner == "Job":
                continue  # completed migration/backup pods are not the serving runtime
            for status in pod.get("status", {}).get("containerStatuses", []):
                rows.append({"pod": pod["metadata"]["name"], "container": status["name"],
                             "image_id": digest_of(status.get("imageID")) or status.get("imageID"),
                             "ready": bool(status.get("ready")),
                             "phase": pod.get("status", {}).get("phase")})
        return rows

    facts["pod_images"] = from_probe(pods, "cluster", parse_pods)
    cron = kget(probe, f"{prefix}.cronjobs", kubeconfig, "cronjobs", "-n", namespace)
    facts["cronjobs"] = from_probe(cron, "cluster", lambda r: {
        c["metadata"]["name"]: {"suspend": bool(c["spec"].get("suspend", False)),
                                "last_schedule": c.get("status", {}).get("lastScheduleTime")}
        for c in _json_out(r)["items"]})
    jobs = kget(probe, f"{prefix}.jobs", kubeconfig, "jobs", "-n", namespace)

    def parse_jobs(r: dict[str, Any]) -> dict[str, Any]:
        out = {}
        for job in _json_out(r)["items"]:
            conds = {c["type"]: c["status"] for c in job.get("status", {}).get("conditions", [])}
            containers = job["spec"]["template"]["spec"]["containers"]
            out[job["metadata"]["name"]] = {
                "complete": conds.get("Complete") == "True", "failed": conds.get("Failed") == "True",
                "images": {c["name"]: c["image"] for c in containers}}
        return out

    facts["jobs"] = from_probe(jobs, "cluster", parse_jobs)
    # Named, so neither unrelated apps nor their (large) inventories are fetched.
    ks = kget(probe, f"{prefix}.kustomizations", kubeconfig,
              "kustomizations.kustomize.toolkit.fluxcd.io", "-n", "flux-system", *kustomizations)

    def parse_ks(r: dict[str, Any]) -> dict[str, Any]:
        out = {}
        doc = _json_out(r)
        for item in doc.get("items", [doc] if doc.get("kind") == "Kustomization" else []):
            name = item["metadata"]["name"]
            conds = {c["type"]: c for c in item.get("status", {}).get("conditions", [])}
            ready = conds.get("Ready", {})
            out[name] = {"suspend": bool(item["spec"].get("suspend", False)),
                         "ready": ready.get("status"), "reason": ready.get("reason"),
                         "last_applied_revision": item.get("status", {}).get("lastAppliedRevision")}
        return out

    facts["kustomizations"] = from_probe(ks, "cluster", parse_ks)
    return facts


def held_from_running(running: dict[str, dict[str, Any]],
                      declared: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Suspended Kustomizations/CronJobs and scaled-down Deployments, with declared intent."""
    held: dict[str, dict[str, Any]] = {}
    ks = running.get("kustomizations")
    if is_known(ks):
        held["suspended_kustomizations"] = known(
            sorted(n for n, v in ks["value"].items() if v["suspend"]), "cluster", ks["evidence"],
            ks["observed_at"])
    else:
        held["suspended_kustomizations"] = _carry(ks, "cluster")
    cron = running.get("cronjobs")
    if is_known(cron):
        declared_cron = (declared or {}).get("cronjobs", {})
        held["suspended_cronjobs"] = known(
            [{"name": n, "declared_suspend": declared_cron.get(n, {}).get("suspend")}
             for n, v in sorted(cron["value"].items()) if v["suspend"]],
            "cluster", cron["evidence"], cron["observed_at"])
    else:
        held["suspended_cronjobs"] = _carry(cron, "cluster")
    deploys = running.get("deployments")
    if is_known(deploys) and declared is not None:
        declared_deploys = declared.get("deployments", {})
        held["scaled_below_declared"] = known(
            [{"name": n, "replicas": v["replicas"],
              "declared": declared_deploys.get(n, {}).get("replicas")}
             for n, v in sorted(deploys["value"].items())
             if n in declared_deploys and v["replicas"] < declared_deploys[n]["replicas"]],
            "cluster", deploys["evidence"], deploys["observed_at"])
    else:
        held["scaled_below_declared"] = _carry(deploys, "cluster",
                                               "declared replicas unknown" if declared is None else None)
    return held


def _carry(fact: dict[str, Any] | None, source: str, extra: str | None = None) -> dict[str, Any]:
    if fact is None:
        return unknown(extra or "input not observed", source, "n/a")
    reason = fact.get("reason") or extra or "input unknown"
    return unknown(reason, source, fact["evidence"], fact.get("observed_at"))


# ---------------------------------------------------------------- receipts


def _minimize_receipt(text: str) -> str:
    doc = json.loads(text)
    keep = {k: doc.get(k) for k in ("schema_version", "context_id", "depth", "implementation_sha")}
    keep["claims"] = [{"result": c.get("result")} for c in doc.get("claims", [])]
    return json.dumps(keep, sort_keys=True)


def receipts_at(probe: Probe, key: str, repo: Path, ref: str, directory: str,
                match: Callable[[dict[str, Any]], bool] = lambda _: True) -> dict[str, Any]:
    listing = git(probe, f"{key}.ls-tree", repo, "ls-tree", "--name-only", ref, f"{directory}/")
    if not listing.get("ok"):
        return unknown(listing.get("error", "ls-tree failed"), "artifact", listing["evidence"],
                       listing.get("observed_at"))
    rows = []
    for index, path in enumerate(sorted(p for p in listing["stdout"].split() if p.endswith(".json"))):
        shown = git(probe, f"{key}.show.{index}", repo, "show", f"{ref}:{path}",
                    transform=_minimize_receipt)
        try:
            doc = json.loads(shown["stdout"])
        except (KeyError, ValueError):
            continue
        if doc.get("schema_version") != "verification-result/v1" or not match(doc):
            continue
        results = Counter(str(c.get("result")) for c in doc.get("claims", []))
        rows.append({"path": f"{repo.name}:{path}", "context_id": doc.get("context_id"),
                     "depth": doc.get("depth"), "implementation_sha": doc.get("implementation_sha"),
                     "claims": dict(sorted(results.items()))})
    return known(rows, "artifact", f"git:{repo.name}@{ref}:{directory}/*.json",
                 listing.get("observed_at"))


# ---------------------------------------------------------------- vuoro-shared


def _ref_sha(probe: Probe, key: str, repo: Path, ref: str) -> dict[str, Any]:
    result = git(probe, key, repo, "rev-parse", "--verify", f"{ref}^{{commit}}")
    return from_probe(result, "artifact", lambda r: r["stdout"].strip())


def _semver_key(version: str) -> tuple:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?", version)
    if not match:
        raise ValueError(version)
    core = tuple(int(match.group(i)) for i in (1, 2, 3))
    pre = match.group(4)
    if pre is None:
        return core + (1, ())
    parts = tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre.split("."))
    return core + (0, parts)


def semver_in_range(version: str, constraint: str) -> bool:
    """Supports the ``>=A <B`` form Flux GitRepository refs use here."""
    try:
        key = _semver_key(version)
    except ValueError:
        return False
    for op, bound in re.findall(r"(>=|<=|<|>|=)\s*(\S+)", constraint):
        other = _semver_key(bound)
        ok = {">=": key >= other, "<=": key <= other, "<": key < other,
              ">": key > other, "=": key == other}[op]
        if not ok:
            return False
    return True


def _forward_only_runbook(probe: Probe, repo: Path, ref: str, schema: int) -> dict[str, Any]:
    path = f"docs/runbooks/sprintctl-work-schema-v{schema}-cutover.md"
    shown = git(probe, "vuoro-shared.runbook", repo, "show", f"{ref}:{path}")
    if not shown.get("ok"):
        return unknown(f"no schema-{schema} cutover runbook at {ref}: {shown.get('error')}",
                       "document", f"git:{repo.name}@{ref}:{path}", shown.get("observed_at"))
    for number, line in enumerate(shown["stdout"].splitlines(), 1):
        if re.search(r"(?i)forward[ -]only", line):
            return known(True, "document", f"git:{repo.name}@{ref}:{path}:{number}: {line.strip()}",
                         shown.get("observed_at"))
    return known(False, "document", f"git:{repo.name}@{ref}:{path} (no forward-only statement)",
                 shown.get("observed_at"))


def collect_vuoro_shared(probe: Probe, *, fetch: bool) -> dict[str, Any]:
    cfg = VUORO_SHARED
    repo = cfg["repo"]
    if fetch:
        git(probe, "vuoro-shared.fetch", repo, "fetch", "--quiet", "origin", "main", timeout=60)
        git(probe, "vuoro-shared.fetch-service", cfg["service_repo"], "fetch", "--quiet", "origin",
            "main", timeout=60)
    desired: dict[str, Any] = {}
    desired["deploying_repo_main_sha"] = ls_remote_head(probe, "vuoro-shared.ls-remote",
                                                        cfg["remote_url"])
    desired["manifest_ref_sha"] = _ref_sha(probe, "vuoro-shared.manifest-ref", repo, "origin/main")
    if is_known(desired["deploying_repo_main_sha"]) and is_known(desired["manifest_ref_sha"]):
        same = desired["deploying_repo_main_sha"]["value"] == desired["manifest_ref_sha"]["value"]
        desired["manifest_ref_is_remote_main"] = known(
            same, "derived", "desired.deploying_repo_main_sha == desired.manifest_ref_sha", None)
    files = manifest_files(probe, "vuoro-shared.manifests", repo, "origin/main", cfg["app_dirs"])
    declared = None
    if is_known(files):
        declared = declared_workloads(files["value"])
        ev, at = files["evidence"], files["observed_at"]
        deploy = declared["deployments"].get(cfg["deployment"])
        if deploy:
            image = next(iter(deploy["images"].values()))
            desired["image"] = known(image, "artifact", f"git:{repo.name}@origin/main:{deploy['path']}", at)
            desired["image_digest"] = known(digest_of(image), "artifact", desired["image"]["evidence"], at)
            desired["replicas"] = known(deploy["replicas"], "artifact", desired["image"]["evidence"], at)
        else:
            desired["image"] = unknown(f"Deployment {cfg['deployment']} not declared", "artifact", ev, at)
        desired["kustomizations"] = known(declared["kustomizations"], "artifact", ev, at)
        migrations = sorted(
            ((int(m.group(1)), name) for name in declared["jobs"]
             if (m := re.fullmatch(r"vuoro-work-migrate-v(\d+)", name))), reverse=True)
        if migrations:
            schema, job = migrations[0]
            job_path = declared["jobs"][job]["path"]
            text = files["value"][job_path]
            asserted = re.search(r"CURRENT_SCHEMA_VERSION\s*==\s*(\d+)", text)
            evidence = f"git:{repo.name}@origin/main:{job_path}"
            desired["migration_job"] = known(job, "artifact", evidence, at)
            desired["migration_job_image_digest"] = known(
                digest_of(next(iter(declared["jobs"][job]["images"].values()))), "artifact", evidence, at)
            desired["work_schema_pin"] = known(
                int(asserted.group(1)) if asserted else schema, "artifact",
                evidence + (" (CURRENT_SCHEMA_VERSION assertion)" if asserted else " (job name)"), at)
        else:
            desired["work_schema_pin"] = unknown("no vuoro-work-migrate-vN Job declared", "artifact", ev, at)
    else:
        for name in ("image", "image_digest", "work_schema_pin", "kustomizations"):
            desired[name] = _carry(files, "artifact")
    tags = ls_remote_tags(probe, "vuoro-shared.service-tags", cfg["service_remote_url"])
    if is_known(tags):
        versions = [t for t in tags["value"] if t.startswith(cfg["service_tag_prefix"])]
        newest = max(versions, key=lambda t: _semver_key(t[len(cfg["service_tag_prefix"]):]),
                     default=None)
        desired["newest_service_release_tag"] = (
            known(newest, "live-api", tags["evidence"], tags["observed_at"]) if newest
            else unknown("no vuoro-service-v* tags", "live-api", tags["evidence"], tags["observed_at"]))
    else:
        desired["newest_service_release_tag"] = _carry(tags, "live-api")

    running = running_workloads(probe, "vuoro-shared", cfg["kubeconfig"], cfg["namespace"],
                                tuple(declared["kustomizations"]) if declared else ("vuoro-shared", "vuoro-shared-db"))
    pods = running["pod_images"]
    if is_known(pods):
        serving = [p for p in pods["value"] if p["pod"].startswith(cfg["deployment"] + "-")]
        running["image_digests"] = known(sorted({p["image_id"] for p in serving}), "cluster",
                                         pods["evidence"], pods["observed_at"])
    else:
        running["image_digests"] = _carry(pods, "cluster")

    usable: dict[str, Any] = {}
    hs = probe.http("vuoro-shared.handshake", cfg["endpoint"] + "/api/meta/v1/handshake",
                    headers={PROTOCOL_HEADER: str(CLIENT_PROTOCOL)})
    usable["handshake"] = from_probe(hs, "live-api", lambda r: _handshake_summary(_json_out(r)))
    cat = probe.http("vuoro-shared.catalog", cfg["endpoint"] + "/api/catalog/v1",
                     headers={PROTOCOL_HEADER: str(CLIENT_PROTOCOL)}, transform=_minimize_catalog)
    usable["catalog"] = from_probe(cat, "live-api", lambda r: _catalog_summary(_json_out(r), r))
    usable["work_schema_version"] = unknown(
        "the handshake reports work compatibility state, not the numeric schema version; the "
        "number is observable only through a database role (sprintctl remote-schema check), "
        "which this read-only report does not hold", "live-api", hs.get("evidence", "n/a"),
        hs.get("observed_at"))

    held = held_from_running(running, declared)
    document = {}
    if is_known(desired.get("work_schema_pin")):
        document["schema_forward_only"] = _forward_only_runbook(
            probe, repo, "origin/main", desired["work_schema_pin"]["value"])
    else:
        document["schema_forward_only"] = _carry(desired.get("work_schema_pin"), "document")
    receipts = {
        "appservice": receipts_at(probe, "vuoro-shared.receipts.appservice", repo, "origin/main",
                                  "verification/results",
                                  lambda d: "vuoro" in str(d.get("context_id", "")) or
                                  "shared" in str(d.get("context_id", ""))),
        "vuoro": receipts_at(probe, "vuoro-shared.receipts.vuoro", cfg["service_repo"], "origin/main",
                             "verification/results"),
    }
    env = {"id": "vuoro-shared", "kind": "cluster", "desired": desired, "running": running,
           "usable": usable, "held": held, "document": document, "receipts": receipts}
    env["gate"] = derive_vuoro_shared_gate(env)
    return env


def _handshake_summary(doc: dict[str, Any]) -> dict[str, Any]:
    compat = doc.get("compatibility") or {}
    return {
        "environment": (doc.get("environment") or {}).get("name"),
        "service_version": doc.get("service_version"),
        "service_release": (doc.get("service_release") or {}).get("version"),
        "schema_versions": doc.get("schema_versions"),
        "client_protocol": doc.get("client_protocol"),
        "catalog_revision": doc.get("catalog_revision"),
        "compatibility": compat.get("state"),
        "domains": {k: {"state": v.get("state"), "schema_version": v.get("schema_version"),
                        "reason": v.get("reason")} for k, v in (compat.get("domains") or {}).items()},
    }


def _catalog_summary(doc: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    ops = doc["operations"]
    return {"schema_version": doc.get("schema_version"), "revision": doc.get("revision"),
            "etag": (result.get("headers") or {}).get("etag"), "operation_count": len(ops),
            "by_domain": dict(sorted(Counter(o.get("owning_domain") for o in ops).items()))}


def _short(sha: str | None) -> str:
    return (sha or "?")[:12]


def _gate(checks: list[tuple[str, Callable[[], tuple[bool | None, str]]]],
          inputs: list[str]) -> dict[str, Any]:
    """Walk ordered checks; the first blocking (or unevaluable) one is the next gate."""
    evidence = "derived from " + ", ".join(inputs)
    for name, check in checks:
        try:
            passed, detail = check()
        except (KeyError, TypeError) as error:
            passed, detail = None, f"input missing: {error}"
        if passed is None:
            return unknown(f"cannot evaluate gate {name!r}: {detail}", "derived", evidence)
        if not passed:
            return known({"gate": name, "detail": detail}, "derived", evidence, None)
    return known({"gate": "none", "detail": "desired == running and usable; nothing blocks"},
                 "derived", evidence, None)


def _need(*facts: dict[str, Any] | None) -> str | None:
    for fact in facts:
        if not is_known(fact):
            return (fact or {}).get("reason") or "input not observed"
    return None


def derive_vuoro_shared_gate(env: dict[str, Any]) -> dict[str, Any]:
    d, r, u, h, doc = (env[k] for k in ("desired", "running", "usable", "held", "document"))

    def held_ks():
        if (why := _need(h.get("suspended_kustomizations"))):
            return None, why
        names = h["suspended_kustomizations"]["value"]
        return not names, f"suspended Kustomization(s): {', '.join(names)}"

    def flux_applied():
        if (why := _need(r.get("kustomizations"), d.get("deploying_repo_main_sha"))):
            return None, why
        want = d["deploying_repo_main_sha"]["value"]
        stale = {n: v["last_applied_revision"] for n, v in r["kustomizations"]["value"].items()
                 if want not in str(v["last_applied_revision"])}
        return not stale, f"Flux has not applied main {_short(want)}: {stale}"

    def ks_ready():
        if (why := _need(r.get("kustomizations"))):
            return None, why
        bad = {n: v["reason"] for n, v in r["kustomizations"]["value"].items() if v["ready"] != "True"}
        return not bad, f"Kustomization(s) not Ready: {bad}"

    def migration():
        if (why := _need(d.get("migration_job"), r.get("jobs"))):
            return None, why
        job = d["migration_job"]["value"]
        state = r["jobs"]["value"].get(job)
        return bool(state and state["complete"]), f"migration Job {job} not Complete ({state})"

    def rollout():
        if (why := _need(d.get("image_digest"), r.get("image_digests"), r.get("deployments"))):
            return None, why
        want, have = d["image_digest"]["value"], r["image_digests"]["value"]
        dep = r["deployments"]["value"].get(env.get("deployment", VUORO_SHARED["deployment"]), {})
        ok = have == [want] and dep.get("ready") == dep.get("replicas") and dep.get("replicas", 0) > 0
        return ok, f"rollout incomplete: want {want}, pods run {have}, ready {dep.get('ready')}/{dep.get('replicas')}"

    def served():
        if (why := _need(u.get("handshake"), u.get("catalog"))):
            return None, why
        hs, cat = u["handshake"]["value"], u["catalog"]["value"]
        ok = hs["compatibility"] == "compatible" and hs["catalog_revision"] == cat["revision"]
        return ok, f"service not usable: compatibility={hs['compatibility']}, catalog revision match={hs['catalog_revision'] == cat['revision']}"

    gate = _gate([("held", held_ks), ("flux-applied", flux_applied), ("flux-ready", ks_ready),
                  ("schema-migration", migration), ("image-rollout", rollout),
                  ("served-compatibility", served)],
                 ["held.suspended_kustomizations", "running.kustomizations",
                  "desired.deploying_repo_main_sha", "desired.migration_job", "running.jobs",
                  "desired.image_digest", "running.image_digests", "usable.handshake",
                  "usable.catalog"])
    return {"next_blocking_gate": gate, "recovery_class": derive_vuoro_shared_recovery(env)}


def derive_vuoro_shared_recovery(env: dict[str, Any]) -> dict[str, Any]:
    d, r, doc = env["desired"], env["running"], env["document"]
    inputs = ["desired.migration_job", "running.jobs", "desired.image_digest",
              "running.image_digests", "document.schema_forward_only",
              "desired.migration_job_image_digest"]
    evidence = "derived from " + ", ".join(inputs)
    why = _need(d.get("migration_job"), r.get("jobs"), d.get("image_digest"),
                r.get("image_digests"))
    if why:
        return unknown(why, "derived", evidence)
    job = d["migration_job"]["value"]
    state = r["jobs"]["value"].get(job)
    if not (state and state["complete"]):
        return known({"class": "cancel", "basis": f"declared migration Job {job} has not completed: "
                      "revert the Git change and resume the previous Kustomizations before it commits"},
                     "derived", evidence, None)
    running = r["image_digests"]["value"]
    if running != [d["image_digest"]["value"]]:
        return known({"class": "cancel", "basis": "desired image is not yet running; revert the "
                      "Git change before the rollout completes"}, "derived", evidence, None)
    if (why := _need(doc.get("schema_forward_only"), d.get("migration_job_image_digest"))):
        return unknown(why, "derived", evidence)
    if doc["schema_forward_only"]["value"] and running == [d["migration_job_image_digest"]["value"]]:
        return known({"class": "forward-fix-or-restore",
                      "basis": f"{job} completed and its runbook is forward-only; the running image "
                      "introduced that schema, so every earlier image is incompatible: ship a "
                      "compatible forward image or perform a coordinated stopped-service restore"},
                     "derived", evidence, None)
    return known({"class": "image-revert",
                  "basis": "running image differs from the migration image or the schema change is "
                  "reversible; reverting to the migration image is a compatible deployment"},
                 "derived", evidence, None)


# ---------------------------------------------------------------- vuoro-cloud


_REPORT_CARD = (
    "import json, sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "from vuoro_cloud.release import build_report_card\n"
    "args = json.load(sys.stdin)\n"
    "card = build_report_card(args['previous'], args['current'])\n"
    "card.pop('generated_at', None)\n"
    "print(json.dumps(card, sort_keys=True))\n"
)


def _run_report_card(probe: Probe, previous: dict[str, Any] | None, current: dict[str, Any],
                     label: str) -> dict[str, Any]:
    """vuoro-cloud's own release report card (the builder behind scripts/release-report-card.py),
    run as a probe so the result is recorded and replayable."""
    src = VUORO_CLOUD["repo"] / "src"
    result = probe.run("vuoro-cloud.report-card", [sys.executable, "-I", "-c", _REPORT_CARD, str(src)],
                       stdin=json.dumps({"previous": previous, "current": current}), timeout=30,
                       evidence=f"vuoro_cloud.release.build_report_card({label}) from {src}")
    return from_probe(result, "artifact", _json_out)


_PIN_PATHS = ("scripts/verify-runtime-pin.py", "config/compatibility.json",
              "apps/runtime-config/compatibility.json",
              "platform/runtime-secrets/controller-runtime.secret.yaml", ".sops.yaml")


def _verify_runtime_pin(probe: Probe, repo: Path, tag: dict[str, Any] | None) -> dict[str, Any]:
    """Run vuoro-cloud's own verify-runtime-pin.py against the release tag's tree.

    The script checks the tree it lives in, and the shared checkout's HEAD is rarely the
    deployed tag, so the tag's files are exported (git archive) into a temporary tree
    and the tag's own copy of the script runs there. It prints digests only.
    """
    if (why := _need(tag)):
        return unknown(why, "artifact", "verify-runtime-pin.py")
    name = tag["value"]
    with tempfile.TemporaryDirectory(prefix="estate-pin-") as tmp:
        export = probe.run(
            "vuoro-cloud.pin-export",
            ["bash", "-c", 'git -C "$1" archive "refs/tags/$2" -- "${@:4}" | tar -x -C "$3"',
             "export", str(repo), name, tmp, *_PIN_PATHS],
            timeout=60, evidence=f"git -C {repo} archive refs/tags/{name} -- {' '.join(_PIN_PATHS)}")
        if not export.get("ok"):
            return unknown(f"cannot export {name}: {export.get('error')}", "artifact", export["evidence"],
                           export.get("observed_at"))
        pin = probe.run("vuoro-cloud.verify-runtime-pin",
                        [sys.executable, "scripts/verify-runtime-pin.py"], cwd=Path(tmp), timeout=60,
                        evidence=f"vuoro-cloud@{name}:scripts/verify-runtime-pin.py (run on the tag's tree)")
    if pin.get("rc") == 0:
        return known(True, "artifact", pin["evidence"], pin["observed_at"])
    if pin.get("rc") == 1:
        return known(False, "artifact", pin["evidence"] + ": " + pin["stderr"].strip()[:400],
                     pin["observed_at"])
    detail = (pin.get("stderr") or pin.get("error") or "no output").strip().splitlines()
    return unknown("verify-runtime-pin could not establish the deployed pin: " + (detail[0] if detail else "")[:240],
                   "artifact", pin.get("evidence", "verify-runtime-pin.py"), pin.get("observed_at"))


def collect_vuoro_cloud(probe: Probe, *, fetch: bool) -> dict[str, Any]:
    cfg = VUORO_CLOUD
    repo = cfg["repo"]
    desired: dict[str, Any] = {}
    flux_src = git(probe, "vuoro-cloud.flux-source", repo, "show", f"origin/main:{cfg['flux_source_file']}")

    def parse_source(r: dict[str, Any]) -> dict[str, Any]:
        for doc in yaml_docs(r["stdout"]):
            if doc.get("kind") == "GitRepository":
                return {"url": doc["spec"]["url"], "ref": doc["spec"]["ref"]}
        raise ValueError("no GitRepository")

    desired["flux_source"] = from_probe(flux_src, "artifact", parse_source)
    remote_name = "origin"
    if is_known(desired["flux_source"]):
        url = desired["flux_source"]["value"]["url"]
        remotes = git(probe, "vuoro-cloud.remotes", repo, "remote", "-v")
        for line in remotes.get("stdout", "").splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[1].rstrip("/") in {url, url.removesuffix(".git")}:
                remote_name = parts[0]
        if fetch:
            git(probe, "vuoro-cloud.fetch", repo, "fetch", "--quiet", "--tags", remote_name, timeout=90)
        desired["deploying_repo_main_sha"] = ls_remote_head(probe, "vuoro-cloud.ls-remote", url)
        tags = ls_remote_tags(probe, "vuoro-cloud.tags", url)
        semver = desired["flux_source"]["value"]["ref"].get("semver")
        if is_known(tags) and semver:
            eligible = sorted((t for t in tags["value"] if semver_in_range(t, semver)),
                              key=_semver_key)
            if eligible:
                desired["release_tag"] = known(eligible[-1], "live-api",
                                               f"{tags['evidence']} | semver {semver!r}", tags["observed_at"])
                desired["release_tag_sha"] = known(tags["value"][eligible[-1]], "live-api",
                                                   tags["evidence"], tags["observed_at"])
                if len(eligible) > 1:
                    desired["previous_release_tag"] = known(eligible[-2], "live-api",
                                                            tags["evidence"], tags["observed_at"])
            else:
                desired["release_tag"] = unknown(f"no tag matches {semver!r}", "live-api",
                                                 tags["evidence"], tags["observed_at"])
        else:
            desired["release_tag"] = _carry(tags, "live-api",
                                            None if semver else "flux source is not a semver ref")
    else:
        desired["release_tag"] = _carry(desired["flux_source"], "artifact")

    declared = None
    if is_known(desired.get("release_tag")):
        tag = desired["release_tag"]["value"]
        ref = f"refs/tags/{tag}"
        files = manifest_files(probe, "vuoro-cloud.manifests", repo, ref, (cfg["apps_dir"],))
        if is_known(files):
            declared = declared_workloads(files["value"])
            desired["deployments"] = known(
                {n: {"replicas": v["replicas"], "images": v["images"]}
                 for n, v in declared["deployments"].items()},
                "artifact", files["evidence"], files["observed_at"])
        else:
            desired["deployments"] = _carry(files, "artifact",
                                            f"tag {tag} not in the local clone; rerun with --fetch")
        compat = git(probe, "vuoro-cloud.compat", repo, "show", f"{ref}:config/compatibility.json")
        desired["compatibility"] = from_probe(compat, "artifact", lambda r: json.loads(r["stdout"]))
        if is_known(desired["compatibility"]):
            previous = None
            if is_known(desired.get("previous_release_tag")):
                prev = git(probe, "vuoro-cloud.compat-previous", repo, "show",
                           f"refs/tags/{desired['previous_release_tag']['value']}:config/compatibility.json")
                previous = json.loads(prev["stdout"]) if prev.get("ok") else None
            label = f"{desired.get('previous_release_tag', {}).get('value')} -> {tag}"
            desired["release_report_card"] = _run_report_card(probe, previous,
                                                              desired["compatibility"]["value"], label)
    desired["runtime_pin_agrees"] = _verify_runtime_pin(probe, repo, desired.get("release_tag"))

    # running: cluster (tunnel-gated) + what the control plane serves publicly
    tunnel = probe.run("vuoro-cloud.tunnel", ["ip", "-br", "link", "show", cfg["tunnel_interface"]], timeout=10)
    if tunnel.get("ok"):
        running = running_workloads(probe, "vuoro-cloud", cfg["kubeconfig"], cfg["namespace"],
                                    cfg["kustomizations"])
    else:
        reason = (f"operator tunnel {cfg['tunnel_interface']} is down; the PoC API is reachable only "
                  "through it (nmcli connection up vuoro-cloud-operator), and a read-only report "
                  "does not bring tunnels up")
        running = {name: unknown(reason, "cluster", tunnel.get("evidence", "ip link"), tunnel.get("observed_at"))
                   for name in ("deployments", "pod_images", "cronjobs", "jobs", "kustomizations")}
    manifest = probe.http("vuoro-cloud.bootstrap-manifest", cfg["api"] + "/api/control/v1/bootstrap/manifest")
    running["served_compatibility"] = from_probe(manifest, "live-api", _json_out)

    usable: dict[str, Any] = {}
    disco = probe.http("vuoro-cloud.discovery", cfg["api"] + "/.well-known/vuoro")
    usable["discovery"] = from_probe(disco, "live-api", lambda r: {
        k: _json_out(r).get(k) for k in ("environment_id", "api_endpoint", "client_protocol")})
    usable["handshake"] = unknown(
        "the cloud gateway handshake requires a workspace bearer token (401 identity-required); "
        "no workspace-scoped read credential is designated for this report", "live-api",
        f"GET {cfg['api']}/api/meta/v1/handshake")
    token_file = cfg["operator_token_file"]
    token = None
    if not probe.replay and token_file.exists():
        token = token_file.read_text(encoding="utf-8").strip()
    if probe.replay or token:
        rollout = probe.http("vuoro-cloud.rollout-status", cfg["api"] + "/api/control/v1/operator/rollout/status",
                             secret_headers={"Authorization": f"Bearer {token}"} if token else None)
        usable["fleet_rollout"] = from_probe(rollout, "live-api", _json_out)
    else:
        usable["fleet_rollout"] = unknown(f"operator token file {token_file} absent", "live-api",
                                          f"GET {cfg['api']}/api/control/v1/operator/rollout/status")
    token = None

    held = held_from_running(running, declared)
    held["tenants_in_maintenance"] = unknown(
        "no read-only operator endpoint enumerates workspace maintenance_mode; the operator API "
        "exposes rollout/status (serving generations) only, per-workspace routes require workspace "
        "membership, and the workspaces table is reachable only through an audited database path",
        "live-api", "vuoro-cloud src/vuoro_cloud/control.py operator GET routes")
    compat = desired.get("compatibility")
    if is_known(compat):
        held["release_ready"] = known(compat["value"].get("release_ready"), "artifact", compat["evidence"],
                                      compat["observed_at"])
    env = {"id": "vuoro-cloud", "kind": "cluster", "desired": desired, "running": running,
           "usable": usable, "held": held, "document": {}, "receipts": {}}
    env["gate"] = derive_vuoro_cloud_gate(env)
    return env


_COMPAT_KEYS = ("packages", "runtime", "tenant_schema", "client_protocol")


def derive_vuoro_cloud_gate(env: dict[str, Any]) -> dict[str, Any]:
    d, r, u, h = env["desired"], env["running"], env["usable"], env["held"]

    def served_matches():
        if (why := _need(d.get("compatibility"), r.get("served_compatibility"))):
            return None, why
        diff = [k for k in _COMPAT_KEYS
                if d["compatibility"]["value"].get(k) != r["served_compatibility"]["value"].get(k)]
        return not diff, f"served compatibility differs from {d['release_tag']['value']} in {diff}"

    def pin():
        if (why := _need(d.get("runtime_pin_agrees"))):
            return None, why
        return d["runtime_pin_agrees"]["value"], "tenant runtime pin disagrees with the compatibility set"

    def held_ks():
        if (why := _need(h.get("suspended_kustomizations"))):
            return None, why
        names = h["suspended_kustomizations"]["value"]
        return not names, f"suspended Kustomization(s): {', '.join(names)}"

    def flux_applied():
        if (why := _need(r.get("kustomizations"), d.get("release_tag"))):
            return None, why
        tag = d["release_tag"]["value"]
        stale = {n: v["last_applied_revision"] for n, v in r["kustomizations"]["value"].items()
                 if tag not in str(v["last_applied_revision"])}
        return not stale, f"Flux has not applied {tag}: {stale}"

    def rollout():
        if (why := _need(d.get("deployments"), r.get("deployments"), r.get("pod_images"))):
            return None, why
        want = {n: digest_of(next(iter(v["images"].values()))) for n, v in d["deployments"]["value"].items()}
        have: dict[str, set] = {}
        for pod in r["pod_images"]["value"]:
            for name in want:
                if pod["pod"].startswith(name + "-"):
                    have.setdefault(name, set()).add(pod["image_id"])
        off = {n: sorted(have.get(n, set())) for n, w in want.items() if have.get(n) != {w}}
        return not off, f"pods not on declared digests: {off}"

    def fleet():
        if (why := _need(u.get("fleet_rollout"))):
            return None, why
        return bool(u["fleet_rollout"]["value"].get("converged")), "tenant fleet not converged"

    gate = _gate([("served-compatibility", served_matches), ("runtime-pin", pin), ("held", held_ks),
                  ("flux-applied", flux_applied), ("image-rollout", rollout), ("fleet-converged", fleet)],
                 ["desired.compatibility", "running.served_compatibility", "desired.runtime_pin_agrees",
                  "held.suspended_kustomizations", "running.kustomizations", "desired.deployments",
                  "running.pod_images", "usable.fleet_rollout"])
    evidence = "derived from desired.compatibility, running.served_compatibility, desired.release_report_card"
    why = _need(d.get("compatibility"), r.get("served_compatibility"))
    if why:
        recovery = unknown(why, "derived", evidence)
    elif any(d["compatibility"]["value"].get(k) != r["served_compatibility"]["value"].get(k)
             for k in _COMPAT_KEYS):
        recovery = known({"class": "cancel", "basis": "the newest eligible release tag is not yet "
                          "served; withdrawing it before Flux applies it cancels the change"},
                         "derived", evidence, None)
    elif (why := _need(d.get("release_report_card"))):
        recovery = unknown(why, "derived", evidence)
    elif d["release_report_card"]["value"].get("maintenance_required"):
        recovery = known({"class": "forward-fix-or-restore", "basis": "release report card: tenant "
                          "schema floor raised (rollback_boundary=tenant-schema-floor-raised)"},
                         "derived", evidence, None)
    else:
        recovery = known({"class": "image-revert", "basis": "release report card: rollback_boundary="
                          f"{d['release_report_card']['value'].get('rollback_boundary')}; a new "
                          "signed tag pinning the previous digests is a compatible deployment"},
                         "derived", evidence, None)
    return {"next_blocking_gate": gate, "recovery_class": recovery}


# ---------------------------------------------------------------- hosts

_DEVBOX_SCRIPT = r"""
set -u
printf '{"hostname":"%s",' "$(hostname)"
printf '"sprintctl_version":"%s",' "$(sprintctl --version 2>/dev/null | awk '{print $NF}')"
printf '"profile":'; cat {profile} 2>/dev/null || printf 'null'; printf ','
d=$(mktemp -d); trap 'rm -rf "$d"' EXIT
mkdir "$d/.sprintctl"
printf '{"backend":"served","repo_id":"{repo_id}"}' > "$d/.sprintctl/backend.json"
printf '"doctor":'
out=$(cd "$d" && unset SPRINTCTL_URL && SPRINTCTL_BACKEND=served SPRINTCTL_VUORO_PROFILE={profile} timeout 60 sprintctl doctor --json 2>/dev/null)
if [ -n "$out" ]; then printf '%s' "$out"; else printf 'null'; fi
printf '}\n'
"""


def _doctor_summary(doc: dict[str, Any]) -> dict[str, Any]:
    schema = doc.get("schema") or {}
    ops = schema.get("actual_version")
    return {
        "status": doc.get("status"),
        "backend": schema.get("backend"),
        "schema_status": schema.get("status"),
        "compatible": schema.get("compatible"),
        "credential_resolved": schema.get("credential_resolved"),
        "authenticated_actor": schema.get("authenticated_actor"),
        "endpoint": (schema.get("profile") or {}).get("endpoint"),
        "operation_count": len(ops) if isinstance(ops, list) else ops,
        "findings": [f.get("code") for f in doc.get("findings", [])],
        "sprintctl_version": ((doc.get("provenance") or {}).get("invocation") or {}).get("code_version"),
    }


def _envrc_profile(text: str) -> str:
    match = re.search(r"^\s*export\s+SPRINTCTL_VUORO_PROFILE=(\S+)", text, re.M)
    if not match:
        raise ValueError("no SPRINTCTL_VUORO_PROFILE export")
    return match.group(1).strip("\"'")


def collect_host(probe: Probe, host: str, *, agentops_main: dict[str, Any]) -> dict[str, Any]:
    cfg = HOSTS[host]
    head = _ref_sha(probe, f"{host}.agentops-head", ROOT, "HEAD")
    where = f"git:agentops@{_short(head.get('value'))}"
    desired: dict[str, Any] = {"agentops_main_sha": agentops_main}
    for name, rel in (("environment_record", cfg["environment_record"]), ("client_profile", cfg["profile"])):
        try:
            doc = json.loads((ROOT / rel).read_text(encoding="utf-8"))
            keep = ("id", "revision", "environment_class", "roles", "constraints") if name == "environment_record" \
                else ("id", "revision", "source_environment_id", "target", "required_authorities")
            desired[name] = known({k: doc.get(k) for k in keep}, "artifact", f"{where}:{rel}", None)
        except (OSError, ValueError) as error:
            desired[name] = unknown(f"cannot read {rel}: {error}", "artifact", f"{where}:{rel}")
    running: dict[str, Any] = {}
    usable: dict[str, Any] = {}
    if cfg["ssh"] is None:
        version = probe.run(f"{host}.sprintctl-version", ["sprintctl", "--version"], timeout=20)
        running["sprintctl_version"] = from_probe(version, "artifact", lambda r: r["stdout"].split()[-1])
        envrc = probe.run(f"{host}.envrc", ["grep", "-E", r"^\s*export\s+SPRINTCTL_VUORO_PROFILE=",
                                            str(cfg["envrc"])], timeout=10)
        running["served_profile_path"] = from_probe(envrc, "artifact", lambda r: _envrc_profile(r["stdout"]))
        profile_path = running["served_profile_path"]["value"] or str(DEV_ROOT / "agentops" / cfg["profile"])
        doctor = probe.run(f"{host}.doctor", ["sprintctl", "doctor", "--json"], cwd=cfg["doctor_cwd"],
                           env={"SPRINTCTL_BACKEND": "served", "SPRINTCTL_VUORO_PROFILE": profile_path},
                           unset=("SPRINTCTL_URL",), timeout=90,
                           evidence=f"cd {cfg['doctor_cwd']} && SPRINTCTL_BACKEND=served "
                                    f"SPRINTCTL_VUORO_PROFILE={profile_path} sprintctl doctor --json")
        # doctor exits non-zero on findings yet still emits JSON; parse whenever it did
        if doctor.get("stdout", "").strip().startswith("{"):
            doctor = {**doctor, "ok": True}
        usable["served_doctor"] = from_probe(doctor, "live-api", lambda r: _doctor_summary(_json_out(r)))
        running["reachable"] = known(True, "artifact", "local host", version.get("observed_at"))
    else:
        script = _DEVBOX_SCRIPT.replace("{profile}", cfg["installed_profile"]).replace("{repo_id}", cfg["repo_id"])
        remote = probe.run(f"{host}.ssh", ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                                           cfg["ssh"], "bash", "-s"], stdin=script, timeout=120,
                           evidence=f"ssh {cfg['ssh']} bash -s <read-only probe: sprintctl --version, "
                                    f"cat {cfg['installed_profile']}, sprintctl doctor --json (served)>")
        envelope = from_probe(remote, "artifact", _json_out)
        running["reachable"] = (
            known(True, "artifact", remote["evidence"], remote.get("observed_at")) if remote.get("ok")
            else unknown(remote.get("error", "ssh failed"), "artifact", remote.get("evidence", "ssh"),
                         remote.get("observed_at")))
        if is_known(envelope):
            value, ev, at = envelope["value"], envelope["evidence"], envelope["observed_at"]
            running["hostname"] = known(value.get("hostname"), "artifact", ev, at)
            running["sprintctl_version"] = known(value.get("sprintctl_version"), "artifact", ev, at)
            prof = value.get("profile")
            running["installed_profile"] = (
                known({"id": prof.get("id"), "revision": prof.get("revision"), "target": prof.get("target")},
                      "artifact", f"{cfg['ssh']}:{cfg['installed_profile']}", at) if prof
                else unknown(f"{cfg['installed_profile']} absent on {host}", "artifact", ev, at))
            usable["served_doctor"] = (
                known(_doctor_summary(value["doctor"]), "live-api", ev + " (via profile on host)", at)
                if value.get("doctor") else unknown("sprintctl doctor produced no JSON", "live-api", ev, at))
        else:
            for name in ("sprintctl_version", "installed_profile"):
                running[name] = _carry(envelope, "artifact")
            usable["served_doctor"] = _carry(envelope, "live-api")
    held = {"host_holds": unknown(
        "environment-record/v1 declares no hold surface for agent hosts (no suspend/pause field), "
        "so a host hold cannot be observed, only absent from the model", "artifact",
        f"{where}:{cfg['environment_record']}")}
    env = {"id": host, "kind": "host", "desired": desired, "running": running, "usable": usable,
           "held": held, "document": {}, "receipts": {}}
    env["gate"] = derive_host_gate(env)
    return env


def derive_host_gate(env: dict[str, Any]) -> dict[str, Any]:
    d, r, u = env["desired"], env["running"], env["usable"]

    def reachable():
        if (why := _need(r.get("reachable"))):
            return None, why
        return bool(r["reachable"]["value"]), "host unreachable"

    def profile():
        if "installed_profile" not in r:
            return True, ""
        if (why := _need(r.get("installed_profile"), d.get("client_profile"))):
            return None, why
        have, want = r["installed_profile"]["value"]["revision"], d["client_profile"]["value"]["revision"]
        return have == want, f"installed client profile revision {have} != declared {want}"

    def doctor():
        if (why := _need(u.get("served_doctor"))):
            return None, why
        doc = u["served_doctor"]["value"]
        return doc["status"] == "ok" and doc["compatible"] is True, \
            f"served doctor status={doc['status']} compatible={doc['compatible']} findings={doc['findings']}"

    gate = _gate([("reachable", reachable), ("client-profile", profile), ("served-doctor", doctor)],
                 ["running.reachable", "running.installed_profile", "desired.client_profile",
                  "usable.served_doctor"])
    evidence = "derived from usable.served_doctor (compatible, schema_status)"
    why = _need(u.get("served_doctor"))
    if why:
        recovery = unknown(why, "derived", evidence)
    elif u["served_doctor"]["value"]["compatible"] is True:
        recovery = known({"class": "image-revert", "basis": "the installed client is compatible with "
                          "the served catalog; reinstalling the previous pinned client within the same "
                          "protocol range is a compatible deployment"}, "derived", evidence, None)
    elif u["served_doctor"]["value"]["compatible"] is False:
        recovery = known({"class": "forward-fix-or-restore", "basis": "the installed client is "
                          "incompatible with the served catalog; upgrade the client forward"},
                         "derived", evidence, None)
    else:
        recovery = unknown("served doctor did not report compatibility (" +
                           ", ".join(u["served_doctor"]["value"]["findings"] or ["no findings"]) + ")",
                           "derived", evidence)
    return {"next_blocking_gate": gate, "recovery_class": recovery}


# ---------------------------------------------------------------- report


def _walk_facts(env: dict[str, Any]):
    for section in ("desired", "running", "usable", "held", "document", "gate"):
        for name, fact in env.get(section, {}).items():
            yield f"{section}.{name}", fact
    for name, fact in env.get("receipts", {}).items():
        yield f"receipts.{name}", fact


def stamp_derived(env: dict[str, Any]) -> None:
    """Facts not tied to one probe (derived ones, static unknowns) take the environment's
    newest probe time, so a replayed report is byte-for-byte reproducible."""
    stamps = [f["observed_at"] for _, f in _walk_facts(env) if f.get("observed_at")]
    latest = max(stamps) if stamps else _now()
    for _, fact in _walk_facts(env):
        if not fact.get("observed_at"):
            fact["observed_at"] = latest


def summarize(env: dict[str, Any]) -> dict[str, Any]:
    facts = list(_walk_facts(env))
    unknowns = [{"fact": path, "reason": fact["reason"]} for path, fact in facts if fact["status"] == "unknown"]
    return {"facts": len(facts), "known": len(facts) - len(unknowns), "unknown": unknowns}


def build_report(probe: Probe, envs: list[str], *, fetch: bool) -> dict[str, Any]:
    agentops_url = probe.run("agentops.remote-url", ["git", "-C", str(ROOT), "remote", "get-url", "origin"],
                             timeout=10)
    if agentops_url.get("ok"):
        agentops_main = ls_remote_head(probe, "agentops.ls-remote", agentops_url["stdout"].strip())
    else:
        agentops_main = unknown(agentops_url.get("error", "no origin remote"), "live-api",
                                agentops_url.get("evidence", "git remote get-url origin"))
    head = _ref_sha(probe, "agentops.head", ROOT, "HEAD")
    out = []
    for env_id in envs:
        if env_id == "vuoro-shared":
            env = collect_vuoro_shared(probe, fetch=fetch)
        elif env_id == "vuoro-cloud":
            env = collect_vuoro_cloud(probe, fetch=fetch)
        else:
            env = collect_host(probe, env_id, agentops_main=agentops_main)
        stamp_derived(env)
        env["summary"] = summarize(env)
        out.append(env)
    stamps = [f["observed_at"] for env in out for _, f in _walk_facts(env)]
    generated = max(stamps) if probe.replay and stamps else _now()
    return {"schema_version": SCHEMA_VERSION, "generated_at": generated, "mode": probe.mode,
            "generator": {"tool": "agentops estate status", "agentops_sha": head.get("value")},
            "environments": out}


# ---------------------------------------------------------------- markdown


def _cell(value: Any, limit: int = 160) -> str:
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    text = text.replace("|", "\\|").replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def render_markdown(report: dict[str, Any]) -> str:
    lines = [f"# Estate status ({report['generated_at']})", "",
             f"Generated by `{report['generator']['tool']}` at agentops "
             f"`{_short(report['generator'].get('agentops_sha'))}`, mode `{report['mode']}`. "
             "`unknown` is a result, not an error: each one carries its reason.", "",
             "| Environment | Next blocking gate | Recovery class | Known / facts |",
             "|---|---|---|---|"]
    for env in report["environments"]:
        gate, rec = env["gate"]["next_blocking_gate"], env["gate"]["recovery_class"]
        gate_txt = gate["value"]["gate"] if is_known(gate) else "unknown"
        rec_txt = rec["value"]["class"] if is_known(rec) else "unknown"
        lines.append(f"| {env['id']} | {gate_txt} | {rec_txt} | "
                     f"{env['summary']['known']} / {env['summary']['facts']} |")
    for env in report["environments"]:
        lines += ["", f"## {env['id']} ({env['kind']})", ""]
        gate, rec = env["gate"]["next_blocking_gate"], env["gate"]["recovery_class"]
        lines.append(f"- **Next blocking gate:** " + (
            f"`{gate['value']['gate']}` — {gate['value']['detail']}" if is_known(gate)
            else f"unknown — {gate['reason']}"))
        lines.append(f"- **Recovery class:** " + (
            f"`{rec['value']['class']}` — {rec['value']['basis']}" if is_known(rec)
            else f"unknown — {rec['reason']}"))
        for section in ("desired", "running", "usable", "held", "document"):
            facts = env.get(section) or {}
            if not facts:
                continue
            lines += ["", f"### {section.capitalize()}", "",
                      "| Fact | Value | Source | Observed | Evidence |", "|---|---|---|---|---|"]
            for name, fact in facts.items():
                value = fact["value"] if is_known(fact) else f"**unknown**: {fact['reason']}"
                lines.append(f"| {name} | {_cell(value, 220 if not is_known(fact) else 160)} | "
                             f"{fact['source']} | {fact['observed_at']} | {_cell(fact['evidence'], 120)} |")
        rows = [(name, fact) for name, fact in (env.get("receipts") or {}).items()]
        if rows:
            lines += ["", "### Qualification receipts", ""]
            for name, fact in rows:
                if not is_known(fact):
                    lines.append(f"- {name}: **unknown** — {fact['reason']}")
                    continue
                lines.append(f"- {name} ({len(fact['value'])}, `{_cell(fact['evidence'], 100)}`):")
                for row in fact["value"]:
                    lines.append(f"  - `{row['context_id']}` depth {row['depth']} @ "
                                 f"`{_short(row['implementation_sha'])}` claims {_cell(row['claims'], 100)}")
        if env["summary"]["unknown"]:
            lines += ["", "### Unknown facts", ""]
            lines += [f"- `{u['fact']}`: {u['reason']}" for u in env["summary"]["unknown"]]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["status"]:  # `agentops estate status ...` arrives as `status ...`
        args = args[1:]
    parser = argparse.ArgumentParser(
        prog="agentops estate status",
        description="Read-only per-environment desired/running/usable/held status with evidence.")
    parser.add_argument("--env", action="append", choices=ENVIRONMENTS,
                        help="environment to report (repeatable; default: all)")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="emit estate-status/v1 JSON")
    output.add_argument("--markdown", action="store_true", help="emit Markdown (the default)")
    parser.add_argument("--from", dest="from_file", type=Path,
                        help="render a saved estate-status/v1 JSON report instead of probing")
    parser.add_argument("--fetch", action="store_true",
                        help="git fetch the deploying repos' remote-tracking refs first")
    parser.add_argument("--record", type=Path, help="write every probe result (redacted) to DIR")
    parser.add_argument("--replay", type=Path, help="answer every probe from fixtures in DIR")
    ns = parser.parse_args(args)
    if ns.from_file:
        report = json.loads(ns.from_file.read_text(encoding="utf-8"))
        if ns.env:
            report["environments"] = [e for e in report["environments"] if e["id"] in ns.env]
    else:
        if ns.record and ns.replay:
            parser.error("--record and --replay are exclusive")
        probe = Probe(record=ns.record, replay=ns.replay)
        report = build_report(probe, ns.env or list(ENVIRONMENTS), fetch=ns.fetch and not ns.replay)
    if ns.json:
        sys.stdout.write(json.dumps(report, indent=2, sort_keys=False) + "\n")
    else:
        sys.stdout.write(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
