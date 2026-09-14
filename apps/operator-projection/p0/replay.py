#!/usr/bin/env python3
"""P0 retrospective replay for operator-projection/v1.

Replays the registry's git-readable vocabularies over appservice history, derives moves by
the mechanical rules of DOSSIER-front-page-design.md §6.3, and scores them against the
pre-registered ground-truth.yaml (§6.4 board falsifier 1, §12 P0).

Every evaluator is read-only: git reads at named commits, plus one unauthenticated HTTP GET
source (the image tag map), cached with the time it was evaluated.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import subprocess
import sys
import urllib.request
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
DEV = HERE.parents[3]
UNDETERMINED = object()
RUNGS = {"D0": 0, "D1": 1, "D2": 2, "D3": 3, "D4": 4}
PLACEHOLDER = re.compile(r"replace|placeholder|changeme|todo", re.IGNORECASE)
DIGEST = re.compile(r"vuoro-service@(sha256:[0-9a-f]{64})")
RELEASE_LABEL = re.compile(r"release:\s*(vuoro-service-v[0-9.]+)")
VOCABULARIES = [
    "authority.service_release",
    "composition.release_lock",
    "audit.record_class",
    "credbroker.capability_rule",
    "credbroker.repository",
    "credbroker.binding",
    "durability.store",
]


@dataclass(frozen=True)
class Row:
    passed: bool
    value: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class Move:
    vocabulary: str
    member: str
    cls: str
    boundary: str
    boundary_at: str
    detail: str | None = None


# ── evaluators: pure functions over the text read at one commit ─────────────────


def service_rows(deployment: str | None, ks: str | None) -> dict[str, Row]:
    if deployment is None:
        return {}
    digest = DIGEST.search(deployment)
    replicas = re.search(r"^\s*replicas:\s*(\d+)", deployment, re.MULTILINE)
    suspended = bool(ks and re.search(r"^\s*suspend:\s*true\b", ks, re.MULTILINE))
    reachable = (replicas is None or int(replicas.group(1)) > 0) and not suspended
    return {"vuoro-shared": Row(reachable, digest.group(1) if digest else None)}


def lock_rows(pins: dict) -> dict[str, Row]:
    if "adapters" in pins:  # vuoro-composition/v1 named each lock by its domain
        entries = [{**a, "lock_id": f"{a['domain']}-adapter"} for a in pins["adapters"]]
    else:
        entries = pins["release_locks"]
    return {e["lock_id"]: Row(True, e["source_revision"], e.get("distribution_version")) for e in entries}


def record_classes(validation: str) -> set[str]:
    declared = re.search(r"^RECORD_CLASSES\s*=\s*\(([^)]*)\)", validation, re.MULTILINE)
    if declared:
        return set(re.findall(r"[\"']([^\"']+)[\"']", declared.group(1)))
    # Before RECORD_CLASSES existed the validator admitted exactly one literal class.
    return set(re.findall(r"record_class must be (\w+)", validation))


def configured(value) -> bool:
    return isinstance(value, str) and value.strip() != "" and not PLACEHOLDER.search(value)


def authorized(policy: dict, provider: str | None, capability: str, repository: str) -> bool:
    settings = policy.get("providers", {}).get(provider)
    if not settings:
        return False
    if provider == "forgejo":
        per_repository = settings.get("repository_audiences")
        if per_repository is not None:
            return configured(per_repository.get(capability, {}).get(repository))
        return configured(settings.get("audiences", {}).get(capability))
    return all(configured(v) for v in settings.values() if isinstance(v, str))


def broker_rows(policy: dict | None) -> dict[str, dict[str, Row]]:
    if policy is None:
        return {"credbroker.capability_rule": {}, "credbroker.repository": {}, "credbroker.binding": {}}
    rules = policy.get("policy", {})
    providers = {r["repository_id"]: r.get("provider") for r in policy.get("repositories", [])}
    active = {h["host_id"]: h.get("active", True) for h in rules.get("hosts", [])}
    bindings = {}
    for binding in rules.get("bindings", []):
        host, repository = binding["host_id"], binding["repository_id"]
        for capability in binding.get("capabilities", []):
            usable = active.get(host, False) and authorized(policy, providers.get(repository), capability, repository)
            bindings[f"{host}|{repository}|{capability}"] = Row(usable)
    return {
        "credbroker.capability_rule": {
            k: Row(True, json.dumps(v, sort_keys=True)) for k, v in rules.get("capabilities", {}).items()
        },
        "credbroker.repository": {r: Row(True) for r in providers},
        "credbroker.binding": bindings,
    }


def durability_rows(cockpit_pvc: bool, policy: dict | None, broker_pvc: bool) -> dict[str, Row]:
    receipts = bool(policy and policy.get("receipt_path")) and broker_pvc
    return {
        "cockpit.reconciliation-state": Row(True, "D2" if cockpit_pvc else "D0"),
        "credbroker.receipts": Row(True, "D2" if receipts else "D0"),
    }


# ── classification (§6.3) ───────────────────────────────────────────────────────


def classify(vocabulary: str, before: dict[str, Row], after: dict[str, Row]) -> list[tuple[str, str]]:
    moves = []
    for member in sorted(before.keys() | after.keys()):
        b, a = before.get(member), after.get(member)
        if vocabulary == "durability.store":
            if b and a and b.value != a.value:
                up = RUNGS[a.value] > RUNGS[b.value]
                moves.append((member, "DURABILITY-UP" if up else "DURABILITY-DOWN"))
        elif b is None:
            if a.passed:
                moves.append((member, "GAINED"))
        elif a is None:
            if b.passed:
                moves.append((member, "FORECLOSED"))
        else:
            if b.passed != a.passed:
                moves.append((member, "GAINED" if a.passed else "REGRESSED"))
            if b.value != a.value and (a.passed or b.passed):
                moves.append((member, "CONTRACT-CHANGE"))
    return moves


# ── sources ─────────────────────────────────────────────────────────────────────


class Git:
    def __init__(self, repo: Path):
        self.repo = repo
        self._shown: dict[tuple[str, str], str | None] = {}

    def run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(self.repo), *args], check=check, capture_output=True, text=True)

    def out(self, *args: str) -> str:
        return self.run(*args).stdout

    def show(self, commit: str, path: str) -> str | None:
        key = (commit, path)
        if key not in self._shown:
            result = self.run("show", f"{commit}:{path}", check=False)
            self._shown[key] = result.stdout if result.returncode == 0 else None
        return self._shown[key]


class ImageTags:
    def __init__(self, document: dict):
        self.document = document
        self.by_digest: dict[str, list[str]] = defaultdict(list)
        for tag, digest in document["tags"].items():
            self.by_digest[digest].append(tag)

    def source_commit(self, digest: str) -> str | None:
        return next((t[4:] for t in self.by_digest.get(digest, []) if t.startswith("sha-")), None)

    def release(self, digest: str | None) -> str | None:
        tags = sorted(self.by_digest.get(digest or "", []))
        return next((t for t in tags if t.startswith("vuoro-service-v")), None)


def fetch_image_tags(repository: str) -> dict:
    """Unauthenticated GET: anonymous pull token, tag list, then one manifest HEAD per tag."""
    accept = ", ".join([
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    ])
    token_url = f"https://ghcr.io/token?scope=repository:{repository}:pull&service=ghcr.io"
    token = json.load(urllib.request.urlopen(token_url, timeout=30))["token"]

    def request(url: str, method: str = "GET"):
        headers = {"Authorization": f"Bearer {token}", "Accept": accept}
        return urllib.request.urlopen(urllib.request.Request(url, method=method, headers=headers), timeout=30)

    tags, url = [], f"https://ghcr.io/v2/{repository}/tags/list?n=1000"
    while url:
        response = request(url)
        tags += json.load(response)["tags"]
        link = response.headers.get("Link")
        url = "https://ghcr.io" + link.split(";")[0].strip("<>") if link else None

    def digest(tag: str) -> tuple[str, str]:
        manifest = request(f"https://ghcr.io/v2/{repository}/manifests/{tag}", "HEAD")
        return tag, manifest.headers["Docker-Content-Digest"]

    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        resolved = dict(pool.map(digest, tags))
    return {
        "source": f"ghcr.io/v2/{repository}",
        "evaluator": "unauthenticated HTTP GET (anonymous pull token)",
        "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tags": dict(sorted(resolved.items())),
    }


# ── replay ──────────────────────────────────────────────────────────────────────


class Replay:
    def __init__(self, registry: dict, appservice: Git, vuoro: Git, auditctl: Git, tags: ImageTags):
        self.sources = registry["sources"]
        self.pins_path = registry["external"]["pins"]["path"]
        self.validation_path = registry["external"]["record_classes"]["path"]
        self.appservice, self.vuoro, self.auditctl, self.tags = appservice, vuoro, auditctl, tags
        self.declared_classes = record_classes(auditctl.show("origin/main", self.validation_path) or "")
        self.undetermined: list[tuple[str, str]] = []

    def snapshot(self, commit: str, previous: dict) -> dict:
        read = lambda key: self.appservice.show(commit, self.sources[key])  # noqa: E731
        deployment, config = read("shared_deployment"), read("broker_config")
        locks = self._locks(deployment)
        policy = self._policy(config)
        state = {
            "authority.service_release": service_rows(deployment, read("shared_ks")),
            "composition.release_lock": locks,
            "audit.record_class": self._record_classes(locks, deployment),
        }
        if policy is UNDETERMINED:
            state |= {v: UNDETERMINED for v in VOCABULARIES if v.startswith("credbroker.")}
            state["durability.store"] = UNDETERMINED
        else:
            state |= broker_rows(policy)
            state["durability.store"] = durability_rows(
                read("cockpit_pvc") is not None, policy, read("broker_pvc") is not None
            )
        for vocabulary in VOCABULARIES:
            if state[vocabulary] is UNDETERMINED:
                self.undetermined.append((commit, vocabulary))
                state[vocabulary] = previous.get(vocabulary, {})
        return state

    def _locks(self, deployment: str | None):
        if deployment is None:
            return {}
        digest = DIGEST.search(deployment)
        source = digest and self.tags.source_commit(digest.group(1))
        pins = source and self.vuoro.show(source, self.pins_path)
        return lock_rows(json.loads(pins)) if pins else UNDETERMINED

    def _record_classes(self, locks, deployment: str | None):
        if locks is UNDETERMINED:
            return UNDETERMINED
        reachable: set[str] = set()
        audit = locks.get("audit-adapter")
        if deployment is not None and audit:
            validation = self.auditctl.show(audit.value, self.validation_path)
            if validation is None:
                return UNDETERMINED
            reachable = record_classes(validation)
        return {c: Row(c in reachable) for c in sorted(self.declared_classes)}

    def _policy(self, config: str | None):
        if config is None:
            return None
        try:
            return json.loads(yaml.safe_load(config)["data"]["production.json"])
        except (KeyError, TypeError, ValueError, yaml.YAMLError):
            return UNDETERMINED

    def boundaries(self, start: datetime, end: datetime) -> list[tuple[str, datetime]]:
        log = self.appservice.out("log", "--format=%H %cI", "origin/main", "--", *self.sources.values())
        commits = [(sha, datetime.fromisoformat(when)) for sha, when in (line.split() for line in log.splitlines())]
        return [(sha, when) for sha, when in reversed(commits) if start <= when < end]

    def run(self, start: datetime, end: datetime) -> dict:
        base = self.appservice.out("rev-list", "-1", f"--before={start.isoformat()}", "origin/main").strip()
        state = self.snapshot(base, {}) if base else {v: {} for v in VOCABULARIES}
        moves: list[Move] = []
        quiet: list[str] = []
        diverged: list[dict] = []
        for sha, when in self.boundaries(start, end):
            after = self.snapshot(sha, state)
            found = [
                Move(v, member, cls, sha, when.isoformat(), self._detail(v, after.get(v, {}).get(member)))
                for v in VOCABULARIES
                for member, cls in classify(v, state.get(v, {}), after.get(v, {}))
            ]
            moves += found
            if not found:
                quiet.append(sha)
            deployment = self.appservice.show(sha, self.sources["shared_deployment"]) or ""
            label, digest = RELEASE_LABEL.search(deployment), DIGEST.search(deployment)
            served = self.tags.release(digest.group(1) if digest else None)
            if label and served and label.group(1) != served:
                diverged.append({"boundary": sha[:8], "label": label.group(1), "digest_release": served})
            state = after
        return {"base": base, "moves": moves, "quiet": quiet, "diverged": diverged, "final": state}

    def _detail(self, vocabulary: str, row: Row | None) -> str | None:
        if row is None:
            return None
        if vocabulary == "authority.service_release":
            return self.tags.release(row.value)
        return row.detail or (row.value if vocabulary == "durability.store" else None)


# ── scoring ─────────────────────────────────────────────────────────────────────


def score(truth: dict, moves: list[Move]) -> dict:
    expected: dict[tuple[str, str, str], dict] = {}
    for row in truth["moves"]:
        if not row.get("scored", True):
            continue
        key = (row["v"], str(row["at"])[:8], row["class"])
        if key in expected:
            raise ValueError(f"duplicate ground-truth group {key}")
        expected[key] = row
    produced: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for move in moves:
        produced[(move.vocabulary, move.boundary[:8], move.cls)].add(move.member)

    hits = expected.keys() & produced.keys()
    mismatched = []
    for key in sorted(hits):
        want, got = expected[key]["members"], produced[key]
        agree = len(got) == expected[key].get("count") if want == "*" else set(want) == got
        if not agree:
            mismatched.append({"group": key, "expected": want if want != "*" else f"{expected[key].get('count')} members", "produced": sorted(got)})

    def ratio(numerator: int, denominator: int) -> float:
        return numerator / denominator if denominator else 1.0

    per_vocabulary = {}
    for vocabulary in sorted({k[0] for k in expected} | {k[0] for k in produced}):
        e = {k for k in expected if k[0] == vocabulary}
        p = {k for k in produced if k[0] == vocabulary}
        per_vocabulary[vocabulary] = {
            "expected": len(e), "produced": len(p),
            "recall": ratio(len(e & p), len(e)), "precision": ratio(len(e & p), len(p)),
        }
    return {
        "expected": len(expected),
        "produced": len(produced),
        "recall": ratio(len(hits), len(expected)),
        "precision": ratio(len(hits), len(produced)),
        "misses": sorted(expected.keys() - produced.keys()),
        "false_positives": sorted(produced.keys() - expected.keys()),
        "member_mismatches": mismatched,
        "per_vocabulary": per_vocabulary,
    }


def pre_registration(agentops: Git, truth_path: Path, replay_path: Path) -> dict:
    """The ground truth must be committed, and committed strictly before the replay code."""

    def first_commit(path: Path) -> str | None:
        added = agentops.out("log", "--diff-filter=A", "--format=%H", "--", str(path.relative_to(agentops.repo))).split()
        return added[-1] if added else None

    truth, replay = first_commit(truth_path), first_commit(replay_path)
    if truth is None:
        raise SystemExit("refusing to score: ground-truth.yaml is not committed")
    if replay is not None:
        ordered = truth != replay and agentops.run("merge-base", "--is-ancestor", truth, replay, check=False).returncode == 0
        if not ordered:
            raise SystemExit(f"refusing to score: ground truth {truth[:8]} does not precede replay code {replay[:8]}")
    return {"ground_truth_commit": truth[:8], "replay_commit": replay[:8] if replay else "uncommitted"}


# ── report ──────────────────────────────────────────────────────────────────────


def render(meta: dict, result: dict, scored: dict, gate: dict, registry: dict) -> str:
    passed = scored["recall"] >= gate["recall"] and scored["precision"] >= gate["precision"]
    moves: list[Move] = result["moves"]
    lines = [
        "# P0 retrospective replay",
        "",
        f"- Window: {meta['window']['start']} → {meta['window']['end']} (appservice origin/main {meta['appservice_head']})",
        f"- Registry: `{registry['registry']}`; ground truth committed at `{meta['ground_truth_commit']}`, replay code at `{meta['replay_commit']}`",
        f"- Image tag map: {meta['image_tags_source']}, evaluated {meta['image_tags_evaluated_at']}",
        f"- Replayed at {meta['replayed_at']}; window base commit `{result['base'][:8]}`",
        "",
        f"## Gate: {'PASS' if passed else 'FAIL'}",
        "",
        f"Recall **{scored['recall']:.3f}** (gate {gate['recall']}), precision **{scored['precision']:.3f}** (gate {gate['precision']}) "
        f"over {scored['expected']} expected and {scored['produced']} produced move groups.",
        "",
        "| vocabulary | expected | produced | recall | precision |",
        "|---|---|---|---|---|",
    ]
    for vocabulary, s in scored["per_vocabulary"].items():
        lines.append(f"| {vocabulary} | {s['expected']} | {s['produced']} | {s['recall']:.2f} | {s['precision']:.2f} |")

    def groups(title: str, keys: list) -> None:
        lines.extend(["", f"### {title} ({len(keys)})", ""])
        lines.extend(f"- `{at}` {vocabulary} {cls}" for vocabulary, at, cls in keys)
        if not keys:
            lines.append("- none")

    groups("Misses: expected, not produced", scored["misses"])
    groups("False positives: produced, not expected", scored["false_positives"])
    lines.extend(["", f"### Member disagreements in matched groups ({len(scored['member_mismatches'])})", ""])
    lines.extend(f"- `{m['group'][1]}` {m['group'][0]} {m['group'][2]}: expected {m['expected']}, produced {len(m['produced'])}: {', '.join(m['produced'][:6])}" for m in scored["member_mismatches"])
    if not scored["member_mismatches"]:
        lines.append("- none")

    carried = next((m for m in moves if m.vocabulary == "composition.release_lock" and m.member == "work-adapter" and m.detail == "0.3.0"), None)
    lines.extend(["", "## Questions P0 was asked to resolve", ""])
    lines.append(
        f"- sprintctl 0.3.0 reached the deployed composition at `{carried.boundary[:8]}` ({carried.boundary_at[:10]})."
        if carried else "- sprintctl 0.3.0: no roll in the window carried it."
    )

    boundaries = len({m.boundary for m in moves}) + len(result["quiet"])
    final = result["final"]
    unreachable_classes = [c for c, row in final["audit.record_class"].items() if not row.passed]
    unusable_bindings = sorted(b for b, row in final["credbroker.binding"].items() if not row.passed)
    lines.extend([
        "",
        "## Substrate ledger",
        "",
        f"- {boundaries} boundary commits touched registry sources; {len(result['quiet'])} moved no enumerated member.",
        f"- Undetermined evaluations: {len(meta['undetermined'])}" + "".join(f"\n  - `{c[:8]}` {v}" for c, v in meta["undetermined"]),
        "",
        "## Hazards at window end (present state, not scored)",
        "",
    ])
    lines.extend(f"- DECLARED-UNREACHABLE audit.record_class `{c}`" for c in unreachable_classes)
    lines.extend(f"- DECLARED-UNREACHABLE credbroker.binding `{b}`" for b in unusable_bindings)
    lines.extend(f"- DIVERGED release label at `{d['boundary']}`: label {d['label']}, digest is {d['digest_release']}" for d in result["diverged"])
    lines.extend(["", "## Coverage gaps", ""])
    lines.extend(f"- `{g['id']}`: {g['reason']}" for g in registry["not_replayable"])

    lines.extend(["", f"## Move list ({len(moves)} member moves)", "", "| boundary | date | vocabulary | class | members |", "|---|---|---|---|---|"])
    grouped: dict[tuple[str, str, str, str], list[Move]] = defaultdict(list)
    for m in moves:
        grouped[(m.boundary[:8], m.boundary_at[:16], m.vocabulary, m.cls)].append(m)
    for (at, when, vocabulary, cls), members in grouped.items():
        names = [m.member + (f" ({m.detail})" if m.detail else "") for m in members]
        shown = ", ".join(names[:4]) + (f", +{len(names) - 4} more" if len(names) > 4 else "")
        lines.append(f"| `{at}` | {when} | {vocabulary} | {cls} | {shown} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--appservice", type=Path, default=DEV / "appservice")
    parser.add_argument("--vuoro", type=Path, default=DEV / "vuoro")
    parser.add_argument("--auditctl", type=Path, default=DEV / "auditctl")
    parser.add_argument("--out", type=Path, default=HERE / "out")
    parser.add_argument("--refresh-image-tags", action="store_true", help="re-fetch the ghcr tag map")
    args = parser.parse_args(argv)

    registry = yaml.safe_load((HERE / "registry.yaml").read_text())
    truth_path = HERE / "ground-truth.yaml"
    truth = yaml.safe_load(truth_path.read_text())
    agentops = Git(Path(Git(HERE).out("rev-parse", "--show-toplevel").strip()))
    registration = pre_registration(agentops, truth_path, Path(__file__).resolve())

    args.out.mkdir(parents=True, exist_ok=True)
    tags_path = args.out / "image-tags.json"
    if args.refresh_image_tags or not tags_path.exists():
        tags_path.write_text(json.dumps(fetch_image_tags(registry["external"]["image_tags"]["repository"]), indent=1) + "\n")
    tags = ImageTags(json.loads(tags_path.read_text()))

    appservice = Git(args.appservice)
    replay = Replay(registry, appservice, Git(args.vuoro), Git(args.auditctl), tags)
    start = datetime.fromisoformat(truth["window"]["start"])
    end = datetime.fromisoformat(truth["window"]["end"])
    result = replay.run(start, end)
    scored = score(truth, result["moves"])
    meta = {
        **registration,
        "window": truth["window"],
        "appservice_head": appservice.out("rev-parse", "--short=8", "origin/main").strip(),
        "image_tags_source": tags.document["source"],
        "image_tags_evaluated_at": tags.document["evaluated_at"],
        "replayed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "undetermined": replay.undetermined,
    }
    (args.out / "moves.json").write_text(json.dumps(
        {"meta": meta, "score": scored, "moves": [asdict(m) for m in result["moves"]]}, indent=1, default=list
    ) + "\n")
    (args.out / "report.md").write_text(render(meta, result, scored, truth["gate"], registry))

    passed = scored["recall"] >= truth["gate"]["recall"] and scored["precision"] >= truth["gate"]["precision"]
    print(f"{'PASS' if passed else 'FAIL'} recall={scored['recall']:.3f} precision={scored['precision']:.3f} "
          f"misses={len(scored['misses'])} false_positives={len(scored['false_positives'])} -> {args.out / 'report.md'}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
