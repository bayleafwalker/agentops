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
only with GET, and the host probes run diagnostics. No secret is decrypted:
vuoro-cloud's tenant-runtime pin is read only from a digest-only rollout/status field, else unknown.
``--fetch`` updates remote-tracking refs in the local clones (no working-tree change)
so desired state is read at the deploying ref rather than at a stale local one.

Freshness: content read from a local ref is stamped with the ls-remote time when
the local sha equals the remote's, and otherwise with the ref's last fetch time
(reflog, or FETCH_HEAD when it records that ref at that sha). A local ref behind its
remote makes the desired-current gate check unknown. A moved tag makes the tag's
facts unknown.

Rules that keep derivations honest:

* the gate is ``none`` only when every hold is known and absent;
* a recovery class needs every input it depends on to be known;
* the Flux semver constraint is read from the remote Flux actually watches;
* the tag it selects is labelled a prediction, distinct from Flux's applied
  revision.

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
import math
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
        "agentops_checkout": DEV_ROOT / "agentops",
    },
    "devbox": {
        "environment_record": "environment-record/devbox-vm.vuoro-shared.json",
        "profile": "environment-record/profiles/devbox-agent-vuoro-shared.json",
        "ssh": "devbox-agent",
        "installed_profile": "~/.config/vuoro/profiles/devbox-agent-vuoro-shared.json",
        "repo_id": "agentops",
        "agentops_checkout": "/projects/dev/agentops",
    },
}

# ---------------------------------------------------------------- redaction

_REDACTIONS = (
    (re.compile(r"(?i)(authorization:\s*bearer\s+)\S+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"), "Bearer [REDACTED]"),
    (re.compile(r"\bvuo_[A-Za-z0-9_]{6,}"), "vuo_[REDACTED]"),
    (re.compile(r"(?i)\b(postgres(?:ql)?|mysql|redis)://[^\s\"']+"), r"\1://[REDACTED]"),
    # key=value only where it is a credential by construction, so code such as
    # `const token=readToken()` survives: URL query parameters, upper-case env-style
    # assignments (FOO_TOKEN=..., export DB_PASSWORD=...), and libpq conninfo strings.
    (re.compile(r"(?i)([?&](?:password|passwd|secret|token|access_token|api_key|apikey)=)[^&\s\"'#]+"),
     r"\1[REDACTED]"),
    (re.compile(r"(?<![\w.])((?:export\s+)?[A-Z][A-Z0-9_]*(?:PASSWORD|PASSWD|SECRET|TOKEN|API_KEY)[A-Z0-9_]*=)"
                r"(?!\[REDACTED\])[^\s\"']+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)((?:\bhost|\bdbname|\buser)=\S+\s+(?:\w+=\S+\s+)*)password=\S+"),
     r"\1password=[REDACTED]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), "gh_[REDACTED]"),
    (re.compile(r"AGE-SECRET-KEY-[A-Z0-9]+"), "AGE-SECRET-KEY-[REDACTED]"),
)


_SECRET_KEY = re.compile(
    r"(?i)(?:password|passwd|secret|token|api[_-]?key|apikey|private[_-]?key|access[_-]?key|"
    r"credentials?|authorization|dsn|connection[_-]?string|conninfo)")
# Keys that name or point at a secret rather than hold one.
_SECRET_KEY_EXEMPT = re.compile(r"(?i)(?:_?ref|_?name|_?path|_?file|_?id|_?kind|_?type|_?hint)$")
_JSON_STRING_PAIR = re.compile(r'"((?:[^"\\]|\\.){1,80})"(\s*:\s*)"((?:[^"\\]|\\.)*)"')


def _redact_json_pair(match: re.Match) -> str:
    key, sep, value = match.group(1), match.group(2), match.group(3)
    if (not value or value == "[REDACTED]" or not _SECRET_KEY.search(key)
            or _SECRET_KEY_EXEMPT.search(key)):
        return match.group(0)
    return f'"{key}"{sep}"[REDACTED]"'


def redact(text: str) -> str:
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    # JSON (and JSON-in-text) string values under credential-like keys: "password": "x".
    return _JSON_STRING_PAIR.sub(_redact_json_pair, text)


# ---------------------------------------------------------------- emit guard
#
# A second, independent line of defence: before any report leaves the process (stdout or
# MCP), every string in it is scanned with detectors that share nothing with redact(),
# and a string that trips one is replaced as a whole (fail closed).

_JWT = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")
_USERINFO = re.compile(r"\b[A-Za-z0-9_.-]+:[^@\s/:\"']{3,}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PEM = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
_PREFIXED = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|xox[abprs]-[A-Za-z0-9-]{10,}|sk-[A-Za-z0-9]{20,}|"
                       r"AKIA[0-9A-Z]{16}|vuo_[a-z]+_[A-Za-z0-9]{8,})")
_CANDIDATE = re.compile(r"[A-Za-z0-9+/_=-]{24,}")
GUARD_PLACEHOLDER = "[REDACTED: possible secret]"


def _entropy(text: str) -> float:
    counts = Counter(text)
    return -sum(c / len(text) * math.log2(c / len(text)) for c in counts.values())


def secret_findings(text: str) -> list[str]:
    """Kinds of secret-looking content in ``text`` (empty when clean)."""
    found = [kind for kind, pattern in (("jwt", _JWT), ("userinfo", _USERINFO), ("pem", _PEM),
                                        ("prefixed-token", _PREFIXED)) if pattern.search(text)]
    for match in _CANDIDATE.finditer(text):
        token = match.group(0)
        if re.fullmatch(r"[0-9a-f]+", token) or re.fullmatch(r"[a-z0-9-]+", token):
            continue  # hex shas/digests and lower-case slugs (names, uids)
        if re.fullmatch(r"[A-Za-z0-9_-]+", token) and "_" in token and not re.search(r"\d{3}", token):
            continue  # identifiers such as SPRINTCTL_VUORO_PROFILE
        if (re.search(r"[A-Z]", token) and re.search(r"[a-z]", token) and re.search(r"\d", token)
                and _entropy(token) > 4.2):
            found.append("high-entropy")
            break
    return found


_PLAIN_KEY = re.compile(r"[\w-]+")


def _key_segment(key: str) -> str:
    """Path segment for a dict key: ``.key``, or ``["key"]`` (JSON escaping) if not word chars/-."""
    return f".{key}" if _PLAIN_KEY.fullmatch(key) else f"[{json.dumps(key)}]"


def guard(value: Any, path: str = "$", hits: list[str] | None = None) -> tuple[Any, list[str]]:
    """Copy of ``value`` with every secret-looking string or key replaced whole; returns the paths.

    A secret-looking key becomes ``GUARD_PLACEHOLDER#n`` (n skips existing sibling keys) and
    its value is replaced by the placeholder."""
    hits = [] if hits is None else hits
    if isinstance(value, str):
        if secret_findings(value):
            hits.append(path)
            return GUARD_PLACEHOLDER, hits
        return value, hits
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        taken = set(value)
        n = 0
        for k, v in value.items():
            if secret_findings(k):
                n += 1
                while f"{GUARD_PLACEHOLDER}#{n}" in taken:
                    n += 1
                key = f"{GUARD_PLACEHOLDER}#{n}"
                taken.add(key)
                hits.append(path + _key_segment(key))
                out[key] = GUARD_PLACEHOLDER
            else:
                out[k] = guard(v, path + _key_segment(k), hits)[0]
        return out, hits
    if isinstance(value, list):
        return [guard(v, f"{path}[{i}]", hits)[0] for i, v in enumerate(value)], hits
    return value, hits


_QUOTED = r'\["(?:[^"\\]|\\.)*"\]'
_SEGMENT = rf"\.([\w-]+)|\[(\d+)\]|({_QUOTED})"
GUARD_PATH = re.compile(rf"\$(?:\.[\w-]+|\[\d+\]|{_QUOTED})*")


def _segments(path: str) -> list[str | int] | None:
    """Parse a guard path into keys / indexes; None if a quoted segment is not a JSON string."""
    out: list[str | int] = []
    for key, index, quoted in re.findall(_SEGMENT, path):
        if quoted:
            try:
                key = json.loads(quoted[1:-1])
            except ValueError:
                return None
            out.append(key)
        elif index:
            out.append(int(index))
        else:
            out.append(key)
    return out


def is_guard_path(value: Any) -> bool:
    return (isinstance(value, str) and GUARD_PATH.fullmatch(value) is not None
            and not secret_findings(value) and _segments(value) is not None)


def resolves_to_placeholder(report: Any, path: str) -> bool:
    """True if walking ``path`` (``.key`` / ``["key"]`` / ``[n]`` segments) through ``report``
    lands on the guard placeholder: the only proof that an earlier redaction record is genuine."""
    segments = _segments(path)
    if segments is None:
        return False
    node = report
    for seg in segments:
        if isinstance(seg, int):
            if not isinstance(node, list) or seg >= len(node):
                return False
            node = node[seg]
        else:
            if not isinstance(node, dict) or seg not in node:
                return False
            node = node[seg]
    return node == GUARD_PLACEHOLDER


def remap_guard_paths(paths: Any, kept_indexes: list[int]) -> list[str]:
    """After filtering ``environments`` (``--from --env``), point recorded paths at the
    environments' new positions and drop paths of environments that were filtered out."""
    if not isinstance(paths, list):
        return []
    new_index = {old: new for new, old in enumerate(kept_indexes)}
    out = []
    for path in paths:
        if not is_guard_path(path):
            continue
        match = re.match(r'\$(?:\.environments|\["environments"\])\[(\d+)\]', path)
        if match is None:
            out.append(path)
        elif int(match.group(1)) in new_index:
            out.append(f"$.environments[{new_index[int(match.group(1))]}]" + path[match.end():])
    return out


def guard_report(report: dict[str, Any]) -> dict[str, Any]:
    """The report as it may be emitted: guarded, with the redacted paths listed.

    Paths redacted by an earlier emission (a saved report re-emitted with --from) are
    kept: the placeholder no longer trips the detector, but the record of it must survive.
    The earlier list is untrusted input too: an entry is kept only if it is path-shaped,
    clean, and resolves in this report to the placeholder; anything else is dropped."""
    earlier = report.get("guard_redactions")
    earlier = [p for p in earlier if is_guard_path(p) and resolves_to_placeholder(report, p)] \
        if isinstance(earlier, list) else []
    clean, hits = guard({k: v for k, v in report.items() if k != "guard_redactions"})
    merged = list(dict.fromkeys(earlier + hits))
    if merged:
        clean["guard_redactions"] = merged
    return clean


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


_FETCH_TIME = (
    'gitdir=$(git -C "$1" rev-parse --absolute-git-dir) || exit 1\n'
    'printf "reflog=%s\\n" "$(git -C "$1" reflog -n1 --date=iso-strict --format=%gd "$2" 2>/dev/null)"\n'
    # FETCH_HEAD counts only if it records this very branch, from this remote, at the sha the
    # ref has now: then its mtime is when that state was last confirmed by a fetch.
    'remote=${2%%/*}; branch=${2#*/}\n'
    'url=$(git -C "$1" remote get-url "$remote" 2>/dev/null); url=${url%.git}\n'
    'want="branch '"'"'$branch'"'"' of $url"\n'
    'fsha=$(awk -F "\\t" -v w="$want" \'$3 == w {print $1; exit}\' "$gitdir/FETCH_HEAD" 2>/dev/null)\n'
    'if [ -n "$url" ] && [ -n "$fsha" ] && [ "$fsha" = "$(git -C "$1" rev-parse "$2" 2>/dev/null)" ]; then\n'
    '  printf "fetch_head_mtime=%s\\n" "$(stat -c %Y "$gitdir/FETCH_HEAD")"\n'
    'fi\n'
)


def ref_fetch_time(probe: Probe, key: str, repo: Path, ref: str) -> str | None:
    """When the local ``ref`` was last brought up to date: its reflog time, else the
    FETCH_HEAD mtime. That, not the time `git show` ran, is when its content was observed."""
    result = probe.run(key, ["bash", "-c", _FETCH_TIME, "fetch-time", str(repo), ref], timeout=15,
                       evidence=f"git -C {repo} reflog -n1 {ref}; stat FETCH_HEAD")
    if not result.get("ok"):
        return None
    fields = dict(line.partition("=")[::2] for line in result["stdout"].splitlines())
    times = []
    match = re.search(r"@\{([^}]+)\}", fields.get("reflog", ""))
    if match:
        try:
            times.append(datetime.fromisoformat(match.group(1)).astimezone(UTC))
        except ValueError:
            pass
    if fields.get("fetch_head_mtime", "").isdigit():
        times.append(datetime.fromtimestamp(int(fields["fetch_head_mtime"]), UTC))
    if not times:
        return None
    return max(times).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ref_current(probe: Probe, key: str, repo: Path, local_ref: str,
                remote_sha: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    """Compare a local ref with the remote's sha.

    Returns ``(local_sha_fact, is_current_fact, content_observed_at)``. Content read at the
    local sha was observed at the ls-remote time when the shas agree (the remote served that
    exact commit then); otherwise at the local ref's last fetch time.
    """
    local = _ref_sha(probe, f"{key}.local", repo, local_ref)
    if not is_known(local):
        return local, _carry(local, "derived"), None
    if not is_known(remote_sha):
        current = unknown(f"cannot compare local {local_ref} with the remote: {remote_sha.get('reason')}",
                          "derived", f"{local['evidence']} vs {remote_sha.get('evidence')}")
        return local, current, ref_fetch_time(probe, f"{key}.fetch-time", repo, local_ref)
    same = local["value"] == remote_sha["value"]
    current = known(same, "derived", f"{local_ref} {_short(local['value'])} vs remote "
                    f"{_short(remote_sha['value'])}", remote_sha["observed_at"])
    at = remote_sha["observed_at"] if same else ref_fetch_time(probe, f"{key}.fetch-time", repo, local_ref)
    return local, current, at


def restamp(facts: dict[str, dict[str, Any]], names: list[str], observed_at: str | None) -> None:
    """Give git-derived facts the time their content was actually current."""
    for name in names:
        fact = facts.get(name)
        if fact and observed_at:
            fact["observed_at"] = observed_at


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


DNS1123 = re.compile(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*")


def is_dns1123(name: Any) -> bool:
    return isinstance(name, str) and len(name) <= 253 and DNS1123.fullmatch(name) is not None


def kget(probe: Probe, key: str, kubeconfig: Path, resource: str, namespace: str,
         names: tuple[str, ...] = ()) -> dict[str, Any]:
    """``kubectl get RESOURCE -n NS -o json -- NAMES``; names and namespace must be DNS-1123,
    and come after ``--`` so a name can never be read as a flag."""
    bad = [n for n in (namespace, *names) if not is_dns1123(n)]
    argv = ["kubectl", "get", resource, "-n", namespace, "-o", "json", "--request-timeout=15s"]
    if names:
        argv += ["--", *names]
    evidence = f"KUBECONFIG={kubeconfig} {' '.join(argv)}"
    if bad:
        return {"ok": False, "error": f"refusing non-DNS-1123 name(s) {bad!r}", "observed_at": None,
                "evidence": evidence}
    return probe.run(key, argv, env={"KUBECONFIG": str(kubeconfig)}, timeout=40, transform=_minimize_k8s,
                     evidence=evidence)


def running_workloads(probe: Probe, prefix: str, kubeconfig: Path, namespace: str,
                      kustomizations: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    facts: dict[str, dict[str, Any]] = {}
    deploys = kget(probe, f"{prefix}.deploy", kubeconfig, "deployments", namespace)
    facts["deployments"] = from_probe(deploys, "cluster", lambda r: {
        d["metadata"]["name"]: {
            "replicas": d["spec"].get("replicas", 1),
            "ready": d.get("status", {}).get("readyReplicas", 0),
            "updated": d.get("status", {}).get("updatedReplicas", 0),
            "available": d.get("status", {}).get("availableReplicas", 0),
            "images": {c["name"]: c["image"] for c in d["spec"]["template"]["spec"]["containers"]},
        } for d in _json_out(r)["items"]})
    pods = kget(probe, f"{prefix}.pods", kubeconfig, "pods", namespace)

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
    cron = kget(probe, f"{prefix}.cronjobs", kubeconfig, "cronjobs", namespace)
    facts["cronjobs"] = from_probe(cron, "cluster", lambda r: {
        c["metadata"]["name"]: {"suspend": bool(c["spec"].get("suspend", False)),
                                "last_schedule": c.get("status", {}).get("lastScheduleTime")}
        for c in _json_out(r)["items"]})
    jobs = kget(probe, f"{prefix}.jobs", kubeconfig, "jobs", namespace)

    def parse_jobs(r: dict[str, Any]) -> dict[str, Any]:
        out = {}
        for job in _json_out(r)["items"]:
            conds = {c["type"]: c["status"] for c in job.get("status", {}).get("conditions", [])}
            containers = job["spec"]["template"]["spec"]["containers"]
            status = job.get("status", {})
            out[job["metadata"]["name"]] = {
                "complete": conds.get("Complete") == "True", "failed": conds.get("Failed") == "True",
                "active": int(status.get("active") or 0), "started": bool(status.get("startTime")),
                "images": {c["name"]: c["image"] for c in containers}}
        return out

    facts["jobs"] = from_probe(jobs, "cluster", parse_jobs)
    # Named, so neither unrelated apps nor their (large) inventories are fetched.
    ks = kget(probe, f"{prefix}.kustomizations", kubeconfig,
              "kustomizations.kustomize.toolkit.fluxcd.io", "flux-system", tuple(kustomizations))

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


_ROLLBACK_HEADING = re.compile(
    r"^#{1,6}\s+(?:failure\s+and\s+)?rollback\s*\((forward[- ]only|reversible)\)\s*$", re.I)


def parse_rollback_marker(text: str) -> tuple[bool | None, int | None, str | None]:
    """The structured rollback marker of a cutover runbook.

    Recognised, in order:

    * YAML front matter ``rollback: forward-only`` or ``rollback: reversible``;
    * a Markdown heading, outside code fences, whose whole text is ``Rollback (forward only)``,
      ``Failure and rollback (forward only)`` or the ``(reversible)`` form.

    Anything else, including prose such as "this is not forward only", is no marker, and
    the caller reports ``unknown``. Returns ``(forward_only, line_number, line)``.
    """
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for number, line in enumerate(lines[1:], 2):
            if line.strip() == "---":
                break
            match = re.fullmatch(r"\s*rollback\s*:\s*[\"']?(forward-only|reversible)[\"']?\s*", line)
            if match:
                return match.group(1) == "forward-only", number, line.strip()
    fenced = False
    for number, line in enumerate(lines, 1):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced:
            continue
        match = _ROLLBACK_HEADING.match(line.strip())
        if match:
            return match.group(1).lower().replace("-", " ") == "forward only", number, line.strip()
    return None, None, None


def _forward_only_runbook(probe: Probe, repo: Path, ref: str, schema: int) -> dict[str, Any]:
    path = f"docs/runbooks/sprintctl-work-schema-v{schema}-cutover.md"
    shown = git(probe, "vuoro-shared.runbook", repo, "show", f"{ref}:{path}")
    where = f"git:{repo.name}@{_short(ref)}:{path}"
    if not shown.get("ok"):
        return unknown(f"no schema-{schema} cutover runbook at {_short(ref)}: {shown.get('error')}",
                       "document", where, shown.get("observed_at"))
    value, number, line = parse_rollback_marker(shown["stdout"])
    if value is None:
        return unknown("the runbook carries no structured rollback marker (front matter `rollback:` or "
                       "a `Rollback (forward only|reversible)` heading)", "document", where,
                       shown.get("observed_at"))
    return known(value, "document", f"{where}:{number}: {line}", shown.get("observed_at"))


# -------------------------------------------------------------- shared gate helpers


def holds_check(h: dict[str, Any], names: tuple[str, ...]) -> tuple[bool | None, str]:
    """No hold may be unknown or present. A CronJob suspended because Git declares it
    suspended (break-glass jobs) is intent, not a hold."""
    for name in names:
        if (why := _need(h.get(name))):
            return None, f"{name}: {why}"
    present = []
    for name in names:
        value = h[name]["value"]
        if name == "suspended_cronjobs":
            value = [c["name"] for c in value if c.get("declared_suspend") is not True]
        if value:
            present.append(f"{name}={value}")
    return not present, "holds present: " + "; ".join(present)


def current_check(fact: dict[str, Any] | None, what: str) -> tuple[bool | None, str]:
    """Desired state read from a stale local ref is not desired state: unknown, not a pass."""
    if (why := _need(fact)):
        return None, f"{what}: {why}"
    if not fact["value"]:
        return None, f"{what} is behind the remote ({fact['evidence']}); rerun with --fetch"
    return True, ""


# -------------------------------------------------------------- vuoro-shared


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
    local, current, content_at = ref_current(probe, "vuoro-shared.manifest-ref", repo, "origin/main",
                                             desired["deploying_repo_main_sha"])
    desired["manifest_ref_sha"] = local
    desired["manifest_ref_is_remote_main"] = current
    ref = local["value"] if is_known(local) else "origin/main"
    files = manifest_files(probe, "vuoro-shared.manifests", repo, ref, cfg["app_dirs"])
    declared = None
    git_facts = ["manifest_ref_sha"]
    if is_known(files):
        declared = declared_workloads(files["value"])
        ev, at = files["evidence"], files["observed_at"]
        deploy = declared["deployments"].get(cfg["deployment"])
        if deploy:
            image = next(iter(deploy["images"].values()))
            evidence = f"git:{repo.name}@{_short(ref)}:{deploy['path']}"
            desired["image"] = known(image, "artifact", evidence, at)
            desired["image_digest"] = known(digest_of(image), "artifact", evidence, at)
            desired["replicas"] = known(deploy["replicas"], "artifact", evidence, at)
        else:
            desired["image"] = unknown(f"Deployment {cfg['deployment']} not declared", "artifact", ev, at)
        desired["kustomizations"] = known(declared["kustomizations"], "artifact", ev, at)
        migrations = sorted(
            ((int(m.group(1)), name) for name in declared["jobs"]
             if (m := re.fullmatch(r"vuoro-work-migrate-v(\d+)", name))), reverse=True)
        if migrations:
            schema, job = migrations[0]
            job_path = declared["jobs"][job]["path"]
            asserted = re.search(r"CURRENT_SCHEMA_VERSION\s*==\s*(\d+)", files["value"][job_path])
            evidence = f"git:{repo.name}@{_short(ref)}:{job_path}"
            desired["migration_job"] = known(job, "artifact", evidence, at)
            desired["migration_job_image_digest"] = known(
                digest_of(next(iter(declared["jobs"][job]["images"].values()))), "artifact", evidence, at)
            desired["work_schema_pin"] = known(
                int(asserted.group(1)) if asserted else schema, "artifact",
                evidence + (" (CURRENT_SCHEMA_VERSION assertion)" if asserted else " (job name)"), at)
        else:
            desired["work_schema_pin"] = unknown("no vuoro-work-migrate-vN Job declared", "artifact", ev, at)
        git_facts += ["image", "image_digest", "replicas", "kustomizations", "migration_job",
                      "migration_job_image_digest", "work_schema_pin"]
    else:
        for name in ("image", "image_digest", "work_schema_pin", "kustomizations", "migration_job"):
            desired[name] = _carry(files, "artifact")
    restamp(desired, git_facts, content_at)
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

    ks_names = tuple(declared["kustomizations"]) if declared else ("vuoro-shared", "vuoro-shared-db")
    running = running_workloads(probe, "vuoro-shared", cfg["kubeconfig"], cfg["namespace"], ks_names)
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
        document["schema_forward_only"] = _forward_only_runbook(probe, repo, ref,
                                                                desired["work_schema_pin"]["value"])
        restamp(document, ["schema_forward_only"], content_at)
    else:
        document["schema_forward_only"] = _carry(desired.get("work_schema_pin"), "document")
    service_at = ref_fetch_time(probe, "vuoro-shared.receipts.vuoro.fetch-time", cfg["service_repo"],
                                "origin/main")
    receipts = {
        "appservice": receipts_at(probe, "vuoro-shared.receipts.appservice", repo, ref,
                                  "verification/results",
                                  lambda d: "vuoro" in str(d.get("context_id", "")) or
                                  "shared" in str(d.get("context_id", ""))),
        "vuoro": receipts_at(probe, "vuoro-shared.receipts.vuoro", cfg["service_repo"], "origin/main",
                             "verification/results"),
    }
    restamp(receipts, ["appservice"], content_at)
    restamp(receipts, ["vuoro"], service_at)
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
    return known({"gate": "none", "detail": "desired == running and usable; no hold present or "
                  "unknown; nothing blocks"}, "derived", evidence, None)


def _need(*facts: dict[str, Any] | None) -> str | None:
    for fact in facts:
        if not is_known(fact):
            return (fact or {}).get("reason") or "input not observed"
    return None


SHARED_HOLDS = ("suspended_kustomizations", "suspended_cronjobs", "scaled_below_declared")


def migration_state(env: dict[str, Any]) -> tuple[str | None, str]:
    """State of the declared schema migration: ``committed``, ``pending`` (not started, so the
    change can still be cancelled), ``running``, ``failed``, or ``None`` when unknown.

    A Job that is gone from the cluster (TTL-deleted) is not evidence of anything by itself;
    it counts as committed only when the migration image is what serves and the live
    handshake reports work compatibility ``compatible``.
    """
    d, r, u = env["desired"], env["running"], env["usable"]
    if (why := _need(d.get("migration_job"), r.get("jobs"))):
        return None, why
    job = d["migration_job"]["value"]
    state = r["jobs"]["value"].get(job)
    if state is None:
        if not _need(u.get("handshake"), r.get("image_digests"), d.get("migration_job_image_digest")):
            work = (u["handshake"]["value"].get("domains") or {}).get("work", {})
            if (work.get("state") == "compatible"
                    and r["image_digests"]["value"] == [d["migration_job_image_digest"]["value"]]):
                return "committed", (f"Job {job} is absent from the cluster, but its image serves and the "
                                     "live handshake reports work compatibility 'compatible'")
        return None, (f"migration Job {job} is not in the cluster (TTL-deleted or never created) and the "
                      "handshake does not establish that its schema change committed")
    if state.get("failed"):
        return "failed", f"migration Job {job} Failed: the schema change is possibly partially applied"
    if state.get("complete"):
        return "committed", f"migration Job {job} Complete"
    if state.get("active"):
        return "running", f"migration Job {job} is running and may commit at any moment"
    if not state.get("started"):
        return "pending", f"migration Job {job} has not started"
    return None, f"migration Job {job} started but is neither active, Complete nor Failed"


def derive_vuoro_shared_gate(env: dict[str, Any]) -> dict[str, Any]:
    d, r, u, h = (env[k] for k in ("desired", "running", "usable", "held"))

    def flux_applied():
        if (why := _need(r.get("kustomizations"), d.get("deploying_repo_main_sha"))):
            return None, why
        want = d["deploying_repo_main_sha"]["value"]
        stale = {n: v["last_applied_revision"] for n, v in r["kustomizations"]["value"].items()
                 if not revision_is(v["last_applied_revision"], "main", want)}
        return not stale, f"Flux has not applied main {_short(want)}: {stale}"

    def ks_ready():
        if (why := _need(r.get("kustomizations"))):
            return None, why
        bad = {n: v["reason"] for n, v in r["kustomizations"]["value"].items() if v["ready"] != "True"}
        return not bad, f"Kustomization(s) not Ready: {bad}"

    def migration():
        state, detail = migration_state(env)
        if state is None:
            return None, detail
        return state == "committed", detail

    def rollout():
        if (why := _need(d.get("image_digest"), r.get("image_digests"), r.get("deployments"))):
            return None, why
        want, have = d["image_digest"]["value"], r["image_digests"]["value"]
        dep = r["deployments"]["value"].get(VUORO_SHARED["deployment"], {})
        ok = have == [want] and dep.get("ready") == dep.get("replicas") and dep.get("replicas", 0) > 0
        return ok, f"rollout incomplete: want {want}, pods run {have}, ready {dep.get('ready')}/{dep.get('replicas')}"

    def served():
        if (why := _need(u.get("handshake"), u.get("catalog"))):
            return None, why
        hs, cat = u["handshake"]["value"], u["catalog"]["value"]
        ok = hs["compatibility"] == "compatible" and hs["catalog_revision"] == cat["revision"]
        return ok, f"service not usable: compatibility={hs['compatibility']}, catalog revision match={hs['catalog_revision'] == cat['revision']}"

    gate = _gate([("desired-current", lambda: current_check(d.get("manifest_ref_is_remote_main"),
                                                            "local origin/main")),
                  ("holds", lambda: holds_check(h, SHARED_HOLDS)),
                  ("flux-applied", flux_applied), ("flux-ready", ks_ready),
                  ("schema-migration", migration), ("image-rollout", rollout),
                  ("served-compatibility", served)],
                 ["desired.manifest_ref_is_remote_main", *(f"held.{n}" for n in SHARED_HOLDS),
                  "running.kustomizations", "desired.deploying_repo_main_sha", "desired.migration_job",
                  "running.jobs", "desired.image_digest", "running.image_digests", "usable.handshake",
                  "usable.catalog"])
    return {"next_blocking_gate": gate, "recovery_class": derive_vuoro_shared_recovery(env)}


def derive_vuoro_shared_recovery(env: dict[str, Any]) -> dict[str, Any]:
    """Recovery class from facts, in this order: has the declared migration committed (if it
    has not started, the change can be cancelled; running, failed or unknowable is unknown),
    is that schema forward-only, and which image is serving relative to the desired one and
    the one that introduced the schema."""
    d, r, doc = env["desired"], env["running"], env["document"]
    inputs = ["desired.manifest_ref_is_remote_main", "desired.migration_job", "running.jobs",
              "usable.handshake", "document.schema_forward_only", "desired.migration_job_image_digest",
              "desired.image_digest", "running.image_digests"]
    evidence = "derived from " + ", ".join(inputs)
    # Desired state read from a stale (or uncomparable) local ref cannot ground a recovery.
    fresh, why_stale = current_check(d.get("manifest_ref_is_remote_main"), "local origin/main")
    if fresh is None:
        return unknown(why_stale, "derived", evidence)
    state, detail = migration_state(env)
    if state is None or state in ("running", "failed"):
        return unknown(f"{detail}; no recovery class can be chosen until it is resolved", "derived", evidence)
    if state == "pending":
        return known({"class": "cancel", "basis": f"{detail}: revert the Git change and resume the "
                      "previous Kustomizations before it runs"}, "derived", evidence, None)
    if (why := _need(doc.get("schema_forward_only"), d.get("migration_job_image_digest"),
                     d.get("image_digest"), r.get("image_digests"))):
        return unknown(why, "derived", evidence)
    running, desired_digest = r["image_digests"]["value"], d["image_digest"]["value"]
    migration_digest = d["migration_job_image_digest"]["value"]
    if doc["schema_forward_only"]["value"]:
        if running == [migration_digest]:
            return known({"class": "forward-fix-or-restore",
                          "basis": f"{detail}; the runbook marks the schema forward-only and the serving "
                          "image introduced it, so every earlier image is incompatible: ship a compatible "
                          "forward image or perform a coordinated stopped-service restore"},
                         "derived", evidence, None)
        if running != [desired_digest]:
            return known({"class": "forward-fix-or-restore",
                          "basis": f"{detail} and the schema is forward-only; pods are not on the desired "
                          "image (rollout incomplete), and no image older than the migration may serve: "
                          "fix forward or restore"}, "derived", evidence, None)
        return known({"class": "image-revert",
                      "basis": f"{detail}; the serving image is newer than the migration image, and "
                      "reverting to the migration image is a compatible deployment"},
                     "derived", evidence, None)
    if running != [desired_digest]:
        return known({"class": "cancel", "basis": f"{detail}; the schema is reversible and the desired "
                      "image is not yet serving: revert the Git change"}, "derived", evidence, None)
    return known({"class": "image-revert", "basis": f"{detail}; the runbook marks the schema reversible"},
                 "derived", evidence, None)


# -------------------------------------------------------------- vuoro-cloud

_REPORT_CARD = (
    "import json, sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "from vuoro_cloud.release import build_report_card\n"
    "args = json.load(sys.stdin)\n"
    "card = build_report_card(args['previous'], args['current'])\n"
    "card.pop('generated_at', None)\n"
    "print(json.dumps(card, sort_keys=True))\n"
)
_REPORT_CARD_PATHS = ("src/vuoro_cloud/__init__.py", "src/vuoro_cloud/release.py")


def _run_report_card(probe: Probe, repo: Path, tag: str, previous_tag: str,
                     previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """vuoro-cloud's release report card builder (behind scripts/release-report-card.py), taken
    from the release tag's own tree (git archive) and run as a recorded probe."""
    label = f"vuoro-cloud@{tag}:src/vuoro_cloud/release.py build_report_card({previous_tag} -> {tag})"
    with tempfile.TemporaryDirectory(prefix="estate-card-") as tmp:
        export = probe.run("vuoro-cloud.report-card-export",
                           ["bash", "-c", 'git -C "$1" archive "refs/tags/$2" -- "${@:4}" | tar -x -C "$3"',
                            "export", str(repo), tag, tmp, *_REPORT_CARD_PATHS], timeout=60,
                           evidence=f"git -C {repo} archive refs/tags/{tag} -- {' '.join(_REPORT_CARD_PATHS)}")
        if not export.get("ok"):
            return unknown(f"cannot export the report-card builder from {tag}: {export.get('error')}",
                           "artifact", export["evidence"], export.get("observed_at"))
        result = probe.run("vuoro-cloud.report-card", [sys.executable, "-I", "-c", _REPORT_CARD,
                                                       str(Path(tmp) / "src")],
                           stdin=json.dumps({"previous": previous, "current": current}), timeout=30,
                           evidence=label)
    return from_probe(result, "artifact", _json_out)


_COMPAT_KEYS = ("packages", "runtime", "tenant_schema", "client_protocol")


def _git_config(probe: Probe, key: str, repo: Path, name: str) -> str | None:
    result = git(probe, key, repo, "config", "--get", name)
    return result["stdout"].strip() if result.get("ok") else None


def _remote_for_url(probe: Probe, key: str, repo: Path, url: str) -> str | None:
    remotes = git(probe, key, repo, "remote", "-v")
    wanted = {url.rstrip("/"), url.rstrip("/").removesuffix(".git")}
    for line in remotes.get("stdout", "").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1].rstrip("/").removesuffix(".git") in wanted | {
                u.removesuffix(".git") for u in wanted}:
            return parts[0]
    return None


def _parse_flux_source(r: dict[str, Any]) -> dict[str, Any]:
    for doc in yaml_docs(r["stdout"]):
        if doc.get("kind") == "GitRepository":
            return {"url": doc["spec"]["url"], "ref": doc["spec"]["ref"]}
    raise ValueError("no GitRepository")


def _tag_tree_fact(probe: Probe, key: str, repo: Path, tag: str, remote_tags: dict[str, Any]
                   ) -> tuple[dict[str, Any], str | None]:
    """Whether the local tag is the remote's tag (same commit) and when that was observed."""
    remote_sha = (known(remote_tags["value"].get(tag), "live-api", remote_tags["evidence"],
                        remote_tags["observed_at"]) if is_known(remote_tags) and tag in remote_tags["value"]
                  else _carry(remote_tags, "live-api", f"tag {tag} not on the remote"))
    local, current, at = ref_current(probe, key, repo, f"refs/tags/{tag}", remote_sha)
    if is_known(current) and not current["value"]:
        return unknown(f"local tag {tag} ({_short(local['value'])}) differs from the remote's "
                       f"({_short(remote_sha['value'])}): the tag was moved or re-signed; rerun with --fetch",
                       "derived", current["evidence"], current["observed_at"]), None
    if not is_known(current):
        hint = " (rerun with --fetch)" if not is_known(local) else ""
        return unknown(f"{current.get('reason')}{hint}", "derived", current["evidence"]), None
    return current, at


def collect_vuoro_cloud(probe: Probe, *, fetch: bool) -> dict[str, Any]:
    cfg = VUORO_CLOUD
    repo = cfg["repo"]
    desired: dict[str, Any] = {}
    canonical = _git_config(probe, "vuoro-cloud.canonical-remote", repo, "claude.canonicalRemote") or "origin"
    first = git(probe, "vuoro-cloud.flux-source.canonical", repo, "show",
                f"{canonical}/main:{cfg['flux_source_file']}")
    source = from_probe(first, "artifact", _parse_flux_source)
    watched = None
    if is_known(source):
        url = source["value"]["url"]
        watched = _remote_for_url(probe, "vuoro-cloud.remotes", repo, url)
        desired["flux_watched_remote"] = (
            known({"remote": watched, "url": url, "canonical_remote": canonical}, "artifact",
                  f"git -C {repo} remote -v; claude.canonicalRemote={canonical}", source["observed_at"])
            if watched else unknown(f"no local remote tracks the Flux GitRepository url {url}", "artifact",
                                    f"git -C {repo} remote -v"))
        if fetch and watched:
            git(probe, "vuoro-cloud.fetch", repo, "fetch", "--quiet", "--tags", watched, timeout=90)
        desired["deploying_repo_main_sha"] = ls_remote_head(probe, "vuoro-cloud.ls-remote", url)
        if watched and watched != canonical:
            # The constraint Flux applies is the one on the remote it watches.
            second = git(probe, "vuoro-cloud.flux-source.watched", repo, "show",
                         f"{watched}/main:{cfg['flux_source_file']}")
            source = from_probe(second, "artifact", _parse_flux_source)
        if watched:
            _, current, at = ref_current(probe, "vuoro-cloud.watched-main", repo, f"{watched}/main",
                                         desired["deploying_repo_main_sha"])
            desired["flux_source_ref_is_remote_main"] = current
            restamp({"s": source}, ["s"], at)
        else:
            desired["flux_source_ref_is_remote_main"] = unknown(
                "the Flux source was read from the canonical remote, not the remote Flux watches",
                "derived", first["evidence"])
    desired["flux_source"] = source

    previous = None
    if is_known(source) and source["value"]["ref"].get("semver"):
        semver = source["value"]["ref"]["semver"]
        tags = ls_remote_tags(probe, "vuoro-cloud.tags", source["value"]["url"])
        eligible = (sorted((t for t in tags["value"] if semver_in_range(t, semver)), key=_semver_key)
                    if is_known(tags) else [])
        if eligible:
            note = (f"selected (predicted): highest tag on {source['value']['url']} matching semver "
                    f"{semver!r}; Flux's applied revision is running.kustomizations[*].last_applied_revision")
            desired["predicted_release_tag"] = known(eligible[-1], "live-api", f"{tags['evidence']} | {note}",
                                                     tags["observed_at"])
            desired["predicted_release_tag_sha"] = known(tags["value"][eligible[-1]], "live-api",
                                                         tags["evidence"], tags["observed_at"])
            if len(eligible) > 1:
                desired["previous_release_tag"] = known(eligible[-2], "live-api", tags["evidence"],
                                                        tags["observed_at"])
            else:
                desired["previous_release_tag"] = unknown("no earlier eligible tag", "live-api",
                                                          tags["evidence"], tags["observed_at"])
        else:
            desired["predicted_release_tag"] = (
                unknown(f"no tag matches {semver!r}", "live-api", tags["evidence"], tags["observed_at"])
                if is_known(tags) else _carry(tags, "live-api"))
    else:
        desired["predicted_release_tag"] = _carry(source, "artifact",
                                                  None if not is_known(source) else "flux source is not a semver ref")

    declared = None
    if is_known(desired.get("predicted_release_tag")):
        tag = desired["predicted_release_tag"]["value"]
        tree, at = _tag_tree_fact(probe, "vuoro-cloud.tag", repo, tag, tags)
        desired["predicted_release_tag_tree_current"] = tree
        if is_known(tree):
            ref = f"refs/tags/{tag}"
            files = manifest_files(probe, "vuoro-cloud.manifests", repo, ref, (cfg["apps_dir"],))
            if is_known(files):
                declared = declared_workloads(files["value"])
                desired["deployments"] = known(
                    {n: {"replicas": v["replicas"], "images": v["images"]}
                     for n, v in declared["deployments"].items()}, "artifact", files["evidence"], at)
            else:
                desired["deployments"] = _carry(files, "artifact")
            compat = git(probe, "vuoro-cloud.compat", repo, "show", f"{ref}:config/compatibility.json")
            desired["compatibility"] = from_probe(compat, "artifact", lambda r: json.loads(r["stdout"]))
            mirror = git(probe, "vuoro-cloud.compat-mirror", repo, "show",
                         f"{ref}:apps/runtime-config/compatibility.json")
            mirror_fact = from_probe(mirror, "artifact", lambda r: json.loads(r["stdout"]))
            restamp(desired, ["compatibility"], at)
            if is_known(desired["compatibility"]):
                comp = desired["compatibility"]["value"]
                desired["release_ready"] = known(comp.get("release_ready"), "artifact",
                                                 desired["compatibility"]["evidence"], at)
                desired["compatibility_mirror_agrees"] = (
                    known(mirror_fact["value"].get("packages", {}).get("vuoro-service")
                          == comp.get("packages", {}).get("vuoro-service"), "artifact",
                          f"{tag}: config/compatibility.json vs apps/runtime-config/compatibility.json "
                          "packages.vuoro-service (the non-secret half of verify-runtime-pin.py)", at)
                    if is_known(mirror_fact) else _carry(mirror_fact, "artifact"))
        else:
            for name in ("deployments", "compatibility", "release_ready"):
                desired[name] = _carry(tree, "derived")
        previous_tag = desired.get("previous_release_tag", {})
        if is_known(previous_tag) and is_known(desired.get("compatibility")):
            ptree, pat = _tag_tree_fact(probe, "vuoro-cloud.previous-tag", repo, previous_tag["value"], tags)
            if is_known(ptree):
                prev = git(probe, "vuoro-cloud.compat-previous", repo, "show",
                           f"refs/tags/{previous_tag['value']}:config/compatibility.json")
                previous = from_probe(prev, "artifact", lambda r: json.loads(r["stdout"]))
                restamp({"p": previous}, ["p"], pat)
            else:
                previous = ptree
        else:
            previous = _carry(previous_tag if not is_known(previous_tag) else desired.get("compatibility"),
                              "artifact")
        desired["previous_compatibility"] = previous
        if is_known(previous) and is_known(desired.get("compatibility")):
            desired["compatibility_discriminates"] = known(
                any(previous["value"].get(k) != desired["compatibility"]["value"].get(k) for k in _COMPAT_KEYS),
                "derived", f"{previous_tag['value']} vs {tag} over {list(_COMPAT_KEYS)}: when equal, matching "
                "served compatibility cannot tell which tag is applied", None)
            desired["release_report_card"] = _run_report_card(
                probe, repo, tag, previous_tag["value"], previous["value"], desired["compatibility"]["value"])
        else:
            desired["release_report_card"] = unknown(
                "the report card needs both the newest and the previous release compatibility; "
                f"previous: {(previous or {}).get('reason') or 'unknown'}", "derived", "build_report_card")
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
    fleet = usable["fleet_rollout"]
    held["tenants_in_maintenance"] = _rollout_field(
        fleet, "maintenance_workspaces",
        lambda v: [w["id"] for w in v],
        "rollout/status carries no `maintenance_workspaces` field yet (requested from the vuoro-cloud "
        "lane, docs/runbooks/estate-status.md); per-workspace routes need membership and the "
        "workspaces table is reachable only through an audited database path")
    running["tenant_runtime_pin"] = _rollout_field(
        fleet, "runtime_image",
        _runtime_digest,
        "the tenant-runtime pin (VUORO_CLOUD_RUNTIME_IMAGE) exists only inside the SOPS-encrypted "
        "vuoro-controller-runtime Secret and rollout/status has no digest-only `runtime_image` field "
        "yet (requested from the vuoro-cloud lane); this report never decrypts secrets")
    env = {"id": "vuoro-cloud", "kind": "cluster", "desired": desired, "running": running,
           "usable": usable, "held": held, "document": {}, "receipts": {}}
    env["gate"] = derive_vuoro_cloud_gate(env)
    return env


def _runtime_digest(value: Any) -> str:
    digest = value["digest"]
    if not isinstance(digest, str) or not DIGEST.fullmatch(digest):
        raise ValueError(f"not a sha256 digest: {digest!r}")
    return digest


def _rollout_field(fleet: dict[str, Any], field: str, parse: Callable[[Any], Any],
                   absent: str) -> dict[str, Any]:
    """A field of the operator rollout/status document, known only when the control plane serves it."""
    if not is_known(fleet):
        return _carry(fleet, "live-api")
    if field not in fleet["value"]:
        return unknown(absent, "live-api", fleet["evidence"], fleet["observed_at"])
    try:
        return known(parse(fleet["value"][field]), "live-api", f"{fleet['evidence']} .{field}",
                     fleet["observed_at"])
    except (KeyError, TypeError, ValueError) as error:
        return unknown(f"rollout/status .{field} is malformed: {error}", "live-api", fleet["evidence"],
                       fleet["observed_at"])


CLOUD_HOLDS = ("suspended_kustomizations", "suspended_cronjobs", "scaled_below_declared",
               "tenants_in_maintenance")


def _cloud_applied(d: dict[str, Any], r: dict[str, Any]) -> tuple[bool | None, str]:
    if (why := _need(r.get("kustomizations"), d.get("predicted_release_tag"), d.get("predicted_release_tag_sha"))):
        return None, why
    tag, sha = d["predicted_release_tag"]["value"], d["predicted_release_tag_sha"]["value"]
    stale = {n: v["last_applied_revision"] for n, v in r["kustomizations"]["value"].items()
             if not revision_is(v["last_applied_revision"], tag, sha)}
    return not stale, f"Flux has not applied the predicted tag {tag}: {stale}"


def revision_is(revision: Any, ref_name: str, sha: str | None) -> bool:
    """Whether a Flux revision (``<ref>@sha1:<sha>``, or a bare sha) names exactly this ref
    or commit. Anchored: tag ``v0.1.0-poc.7`` must not match ``v0.1.0-poc.76@sha1:...``."""
    if not isinstance(revision, str) or not revision:
        return False
    name, _, digest = revision.partition("@")
    digest = digest.split(":", 1)[-1] if digest else ""
    if sha and (revision == sha or digest == sha):
        return True
    return bool(digest) and name in (ref_name, f"refs/tags/{ref_name}", f"refs/heads/{ref_name}") \
        and (not sha or digest == sha)


def derive_vuoro_cloud_gate(env: dict[str, Any]) -> dict[str, Any]:
    d, r, u, h = env["desired"], env["running"], env["usable"], env["held"]

    def served_matches():
        if (why := _need(d.get("compatibility"), r.get("served_compatibility"))):
            return None, why
        diff = [k for k in _COMPAT_KEYS
                if d["compatibility"]["value"].get(k) != r["served_compatibility"]["value"].get(k)]
        # A match is necessary, not sufficient: when the previous tag declares the same set
        # (desired.compatibility_discriminates false) it cannot show which tag is applied;
        # flux-applied below decides that.
        return not diff, f"served compatibility differs from {d['predicted_release_tag']['value']} in {diff}"

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

    def mirror():
        if (why := _need(d.get("compatibility_mirror_agrees"))):
            return None, why
        return d["compatibility_mirror_agrees"]["value"], "compatibility mirror disagrees with config/compatibility.json"

    def pin():
        if (why := _need(r.get("tenant_runtime_pin"), d.get("compatibility"))):
            return None, why
        want = digest_of(d["compatibility"]["value"].get("packages", {}).get("vuoro-service"))
        have = r["tenant_runtime_pin"]["value"]
        return have == want, f"tenant runtime pin {have} != declared vuoro-service {want}"

    gate = _gate([("flux-source-current", lambda: current_check(d.get("flux_source_ref_is_remote_main"),
                                                                "Flux source read from the watched remote's main")),
                  ("desired-current", lambda: current_check(d.get("predicted_release_tag_tree_current"),
                                                            "local predicted release tag")),
                  ("served-compatibility", served_matches), ("compatibility-mirror", mirror),
                  ("holds", lambda: holds_check(h, CLOUD_HOLDS)),
                  ("flux-applied", lambda: _cloud_applied(d, r)), ("image-rollout", rollout),
                  ("fleet-converged", fleet), ("tenant-runtime-pin", pin)],
                 ["desired.flux_source_ref_is_remote_main", "desired.predicted_release_tag_tree_current", "desired.compatibility",
                  "running.served_compatibility", "desired.compatibility_mirror_agrees",
                  *(f"held.{n}" for n in CLOUD_HOLDS), "running.kustomizations", "desired.deployments",
                  "running.pod_images", "usable.fleet_rollout", "running.tenant_runtime_pin"])
    return {"next_blocking_gate": gate, "recovery_class": derive_vuoro_cloud_recovery(env)}


def derive_vuoro_cloud_recovery(env: dict[str, Any]) -> dict[str, Any]:
    """Cancel while the predicted tag is not applied; once it is, the report card's rollback
    boundary decides. Every input (cluster, holds, fleet, both compatibility sets) must be
    known: a recovery chosen without them would be assumed, not derived."""
    d, r, u, h = env["desired"], env["running"], env["usable"], env["held"]
    required = {
        "desired.predicted_release_tag": d.get("predicted_release_tag"),
        "desired.compatibility": d.get("compatibility"),
        "desired.previous_compatibility": d.get("previous_compatibility"),
        "desired.release_report_card": d.get("release_report_card"),
        "desired.release_ready": d.get("release_ready"),
        "running.kustomizations": r.get("kustomizations"),
        "running.deployments": r.get("deployments"),
        "running.pod_images": r.get("pod_images"),
        **{f"held.{n}": h.get(n) for n in CLOUD_HOLDS},
        "usable.fleet_rollout": u.get("fleet_rollout"),
    }
    evidence = "derived from " + ", ".join(required)
    missing = [name for name, fact in required.items() if not is_known(fact)]
    if missing:
        first = required[missing[0]]
        return unknown(f"unknown input(s) {missing}; first: {(first or {}).get('reason') or 'not observed'}",
                       "derived", evidence)
    applied, detail = _cloud_applied(d, r)
    if not applied:
        return known({"class": "cancel", "basis": f"{detail}; withdrawing it before Flux applies it "
                      "cancels the change"}, "derived", evidence, None)
    card = d["release_report_card"]["value"]
    if card.get("maintenance_required"):
        return known({"class": "forward-fix-or-restore", "basis": "release report card: tenant schema floor "
                      "raised (rollback_boundary=tenant-schema-floor-raised)"}, "derived", evidence, None)
    return known({"class": "image-revert", "basis": f"release report card: rollback_boundary="
                  f"{card.get('rollback_boundary')}; a new signed tag pinning the previous digests is a "
                  "compatible deployment"}, "derived", evidence, None)


# -------------------------------------------------------------- hosts

_DEVBOX_SCRIPT = r"""
set -u
printf '{"hostname":"%s",' "$(hostname)"
printf '"sprintctl_version":"%s",' "$(sprintctl --version 2>/dev/null | awk '{print $NF}')"
printf '"agentops_head":"%s",' "$(git -C {agentops} rev-parse HEAD 2>/dev/null)"
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


def _profile_summary(doc: dict[str, Any]) -> dict[str, Any]:
    return {"id": doc.get("id"), "revision": doc.get("revision"), "target": doc.get("target")}


def _well_formed_holds(holds: Any) -> bool:
    return isinstance(holds, list) and all(
        isinstance(h, dict) and isinstance(h.get("id"), str) and re.fullmatch(r"[a-z0-9][a-z0-9._-]*", h["id"])
        and isinstance(h.get("reason"), str) and h["reason"] for h in holds)


def collect_host(probe: Probe, host: str, *, agentops_main: dict[str, Any]) -> dict[str, Any]:
    cfg = HOSTS[host]
    local, current, content_at = ref_current(probe, f"{host}.agentops-main", ROOT, "origin/main", agentops_main)
    ref = local["value"] if is_known(local) else "origin/main"
    where = f"git:agentops@{_short(ref)}"
    desired: dict[str, Any] = {"agentops_main_sha": agentops_main, "record_ref_is_remote_main": current}
    for name, rel in (("environment_record", cfg["environment_record"]), ("client_profile", cfg["profile"])):
        shown = git(probe, f"{host}.{name}", ROOT, "show", f"{ref}:{rel}")
        keep = (("id", "revision", "environment_class", "roles", "constraints", "holds")
                if name == "environment_record"
                else ("id", "revision", "source_environment_id", "target", "required_authorities"))
        # Only present keys: an absent `holds` must stay distinguishable from `holds: []`.
        fact = from_probe(shown, "artifact", lambda r, keep=keep: {
            k: v for k, v in json.loads(r["stdout"]).items() if k in keep})
        fact["evidence"] = f"{where}:{rel}"
        desired[name] = fact
    restamp(desired, ["environment_record", "client_profile"], content_at)
    running: dict[str, Any] = {}
    usable: dict[str, Any] = {}
    if cfg["ssh"] is None:
        version = probe.run(f"{host}.sprintctl-version", ["sprintctl", "--version"], timeout=20)
        running["sprintctl_version"] = from_probe(version, "artifact", lambda r: r["stdout"].split()[-1])
        head = _ref_sha(probe, f"{host}.agentops-head", cfg["agentops_checkout"], "HEAD")
        running["agentops_head"] = head
        envrc = probe.run(f"{host}.envrc", ["grep", "-E", r"^\s*export\s+SPRINTCTL_VUORO_PROFILE=",
                                            str(cfg["envrc"])], timeout=10)
        running["served_profile_path"] = from_probe(envrc, "artifact", lambda r: _envrc_profile(r["stdout"]))
        profile_path = running["served_profile_path"]["value"] or str(DEV_ROOT / "agentops" / cfg["profile"])
        installed = probe.run(f"{host}.installed-profile", ["cat", profile_path], timeout=10)
        running["installed_profile"] = from_probe(installed, "artifact",
                                                  lambda r: _profile_summary(json.loads(r["stdout"])))
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
        script = (_DEVBOX_SCRIPT.replace("{profile}", cfg["installed_profile"])
                  .replace("{repo_id}", cfg["repo_id"]).replace("{agentops}", cfg["agentops_checkout"]))
        remote = probe.run(f"{host}.ssh", ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                                           cfg["ssh"], "bash", "-s"], stdin=script, timeout=120,
                           evidence=f"ssh {cfg['ssh']} bash -s <read-only probe: sprintctl --version, "
                                    f"rev-parse {cfg['agentops_checkout']} HEAD, cat {cfg['installed_profile']}, "
                                    "sprintctl doctor --json (served)>")
        envelope = from_probe(remote, "artifact", _json_out)
        running["reachable"] = (
            known(True, "artifact", remote["evidence"], remote.get("observed_at")) if remote.get("ok")
            else unknown(remote.get("error", "ssh failed"), "artifact", remote.get("evidence", "ssh"),
                         remote.get("observed_at")))
        if is_known(envelope):
            value, ev, at = envelope["value"], envelope["evidence"], envelope["observed_at"]
            running["hostname"] = known(value.get("hostname"), "artifact", ev, at)
            running["sprintctl_version"] = known(value.get("sprintctl_version"), "artifact", ev, at)
            running["agentops_head"] = (
                known(value["agentops_head"], "artifact", f"{cfg['ssh']}:{cfg['agentops_checkout']} HEAD", at)
                if value.get("agentops_head")
                else unknown(f"no agentops checkout at {cfg['agentops_checkout']} on {host}", "artifact", ev, at))
            prof = value.get("profile")
            running["installed_profile"] = (
                known(_profile_summary(prof), "artifact", f"{cfg['ssh']}:{cfg['installed_profile']}", at) if prof
                else unknown(f"{cfg['installed_profile']} absent on {host}", "artifact", ev, at))
            usable["served_doctor"] = (
                known(_doctor_summary(value["doctor"]), "live-api", ev + " (via profile on host)", at)
                if value.get("doctor") else unknown("sprintctl doctor produced no JSON", "live-api", ev, at))
        else:
            for name in ("sprintctl_version", "installed_profile", "agentops_head"):
                running[name] = _carry(envelope, "artifact")
            usable["served_doctor"] = _carry(envelope, "live-api")
    # Host holds are *declared*: they come from the agentops environment record, not from
    # observing the host, and the fact name and evidence say so.
    record = desired.get("environment_record")
    holds = record["value"].get("holds") if is_known(record) else None
    if is_known(record) and "holds" in record["value"] and not _well_formed_holds(holds):
        held = {"declared_host_holds": unknown(
            "the environment record's `holds` is malformed (it must be an array of objects with a "
            "token `id` and a non-empty `reason`), so the declared holds cannot be read",
            "artifact", f"declared (from the agentops record): {record['evidence']}", record["observed_at"])}
    elif is_known(record) and isinstance(holds, list):
        held = {"declared_host_holds": known(
            [h["id"] for h in holds], "artifact",
            f"declared (from the agentops record): {record['evidence']} holds", record["observed_at"])}
    elif is_known(record):
        held = {"declared_host_holds": unknown(
            "the environment record declares no `holds` field, so whether this host is held is not "
            "modelled (an empty `holds: []` would state that nothing is held)", "artifact",
            f"declared (from the agentops record): {record['evidence']}", record["observed_at"])}
    else:
        held = {"declared_host_holds": _carry(record, "artifact")}
    env = {"id": host, "kind": "host", "desired": desired, "running": running, "usable": usable,
           "held": held, "document": {}, "receipts": {}}
    env["gate"] = derive_host_gate(env)
    return env


def derive_host_gate(env: dict[str, Any]) -> dict[str, Any]:
    d, r, u, h = env["desired"], env["running"], env["usable"], env["held"]

    def reachable():
        if (why := _need(r.get("reachable"))):
            return None, why
        return bool(r["reachable"]["value"]), "host unreachable"

    def agentops_current():
        if (why := _need(r.get("agentops_head"), d.get("agentops_main_sha"))):
            return None, why
        have, want = r["agentops_head"]["value"], d["agentops_main_sha"]["value"]
        return have == want, f"agentops checkout HEAD {_short(have)} != main {_short(want)}"

    def profile():
        if (why := _need(r.get("installed_profile"), d.get("client_profile"))):
            return None, why
        have, want = r["installed_profile"]["value"], d["client_profile"]["value"]
        ok = have["revision"] == want["revision"] and have["id"] == want["id"]
        return ok, f"installed client profile {have['id']} rev {have['revision']} != declared {want['id']} rev {want['revision']}"

    def doctor():
        if (why := _need(u.get("served_doctor"))):
            return None, why
        doc = u["served_doctor"]["value"]
        return doc["status"] == "ok" and doc["compatible"] is True, \
            f"served doctor status={doc['status']} compatible={doc['compatible']} findings={doc['findings']}"

    gate = _gate([("desired-current", lambda: current_check(d.get("record_ref_is_remote_main"),
                                                            "local agentops origin/main")),
                  ("reachable", reachable), ("agentops-current", agentops_current),
                  ("client-profile", profile), ("served-doctor", doctor),
                  ("holds", lambda: holds_check(h, ("declared_host_holds",)))],
                 ["desired.record_ref_is_remote_main", "running.reachable", "running.agentops_head",
                  "desired.agentops_main_sha", "running.installed_profile", "desired.client_profile",
                  "usable.served_doctor", "held.declared_host_holds"])
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
    if fetch and any(e in HOSTS for e in envs):
        git(probe, "agentops.fetch", ROOT, "fetch", "--quiet", "origin", "main", timeout=60)
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


def report_age_warning(report: dict[str, Any], now: datetime | None = None) -> str:
    """Rendering a saved report: say how old it is, since every fact is as of then."""
    now = now or datetime.now(UTC)
    try:
        generated = datetime.fromisoformat(report["generated_at"].replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return "> **Warning:** saved report without a readable generated_at; its age is unknown."
    minutes = int((now - generated).total_seconds() // 60)
    age = f"{minutes // 1440}d {minutes % 1440 // 60}h" if minutes >= 1440 else f"{minutes // 60}h {minutes % 60}m"
    return (f"> **Warning:** rendered from a saved report generated {report['generated_at']} "
            f"({age} ago). Every fact is as of its observed_at; rerun `agentops estate status` "
            "for current state.")


def saved_report_age(report: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    """Machine-readable age of a saved report (`--from ... --json`)."""
    now = now or datetime.now(UTC)
    try:
        generated = datetime.fromisoformat(report["generated_at"].replace("Z", "+00:00"))
        seconds = max(0, int((now - generated).total_seconds()))
    except (KeyError, ValueError, AttributeError):
        seconds = None
    return {"rendered_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "age_seconds": seconds,
            "warning": report_age_warning(report, now).removeprefix("> **Warning:** ")}


def render_markdown(report: dict[str, Any], *, warning: str | None = None) -> str:
    lines = [f"# Estate status ({report['generated_at']})", ""]
    if warning:
        lines += [warning, ""]
    lines += [f"Generated by `{report['generator']['tool']}` at agentops "
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
            kept = [i for i, e in enumerate(report["environments"]) if e["id"] in ns.env]
            report["environments"] = [report["environments"][i] for i in kept]
            if "guard_redactions" in report:
                report["guard_redactions"] = remap_guard_paths(report["guard_redactions"], kept)
    else:
        if ns.record and ns.replay:
            parser.error("--record and --replay are exclusive")
        probe = Probe(record=ns.record, replay=ns.replay)
        report = build_report(probe, ns.env or list(ENVIRONMENTS), fetch=ns.fetch and not ns.replay)
    if ns.from_file:
        report["saved_report_age"] = saved_report_age(report)
    report = guard_report(report)
    if ns.json:
        sys.stdout.write(json.dumps(report, indent=2, sort_keys=False) + "\n")
    else:
        sys.stdout.write(render_markdown(report, warning=report_age_warning(report) if ns.from_file else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
