"""generate(git, authority, registry, now): one operator-projection/v1 document. Reads only; no previous document."""

from __future__ import annotations

import json
import tomllib
from collections.abc import Callable
from datetime import date, datetime, timedelta
from functools import cached_property
from typing import Any

from .cell import blind, cell
from .evaluators import DIGEST, Move, broker_rows, durability_rows, lock_rows, orphan_authorities, policy_revision, record_classes
from .replay import APPSERVICE, BRANCH, RELEASE_LABEL, VOCABULARIES, Replay, read_policy, recall
from .sources import Authority, GitSource, ImageTags, SourceUnavailable, stamp

RANK = ["FORECLOSED", "REGRESSED", "DURABILITY-DOWN", "DURABILITY-UP", "GAINED", "CONTRACT-CHANGE"]


def unavailable(message: str):
    raise SourceUnavailable(message)


class Run:
    """One generation: its sources, their degraded envelopes, and the reads shared between panels."""

    def __init__(self, git: GitSource, authority: Authority | None, registry: dict, now: datetime, tags: Callable[[], dict]):
        self.git, self.authority, self.registry, self.now, self.at = git, authority, registry, now, stamp(now)
        self.transport = getattr(git, "transport", "git")
        self.sources: dict[str, dict] = {}
        self._tags = tags

    def guard(self, source: str, transport: str, fetch: Callable[[], Any]) -> Any:
        entry = self.sources.setdefault(source, {"id": source, "transport": transport, "ref": None, "revision": None,
                                                 "observed_at": self.at, "watermark": None, "degraded": None})
        try:
            return fetch()
        except Exception as error:  # a missing source never crashes a generation; it is carried as degraded
            entry["degraded"] = entry["degraded"] or {"message": f"{source} unavailable", "source": source, "detail": f"{type(error).__name__}: {error}"}
            raise SourceUnavailable(f"{source}: {error}") from error

    def quietly(self, source: str, transport: str, fetch: Callable[[], Any]) -> Any:
        try:
            return self.guard(source, transport, fetch)
        except SourceUnavailable:
            return None

    def show(self, repo: str, commit: str, path: str) -> str | None:
        return self.guard(f"git.{repo}", self.transport, lambda: self.git.show(repo, commit, path))

    def log(self, repo: str, ref: str, paths, since: datetime | None = None, until: datetime | None = None) -> list[tuple[str, datetime]]:
        return self.guard(f"git.{repo}", self.transport, lambda: self.git.log(repo, ref, paths, since, until))

    def resolve(self, repo: str, ref: str, before: datetime | None = None) -> str | None:
        return self.guard(f"git.{repo}", self.transport, lambda: self.git.resolve(repo, ref, before))

    def head(self, repo: str) -> str:
        sha = self.guard(f"git.{repo}", self.transport, lambda: self.git.resolve(repo, BRANCH))
        if not sha:
            raise SourceUnavailable(f"git.{repo}: no {BRANCH}")
        self.sources[f"git.{repo}"] |= {"ref": BRANCH, "revision": sha}
        return sha

    def degraded(self, source: str) -> str | None:
        entry = self.sources.get(source)
        return entry["degraded"]["detail"] if entry and entry["degraded"] else None

    @cached_property
    def handshake(self) -> dict | None:
        if self.authority is None:
            return self.quietly("authority.handshake", "http-get", lambda: unavailable("vuoro-client is not installed"))
        found = self.quietly("authority.handshake", "http-get", self.authority.handshake)
        if found:
            self.sources["authority.handshake"] |= {"ref": "/api/meta/v1/handshake", "revision": found["catalog_revision"]}
        return found

    @cached_property
    def catalog(self) -> dict | None:
        found = self.handshake is not None and self.quietly("authority.catalog", "http-get", self.authority.catalog)
        if found:
            self.sources["authority.catalog"] |= {"ref": "/api/catalog/v1", "revision": found["revision"]}
        return found or None

    @cached_property
    def tags(self) -> ImageTags:
        document = self.guard("ghcr.image-tags", "http-get", self._tags)
        self.sources["ghcr.image-tags"] |= {"ref": document["source"], "revision": f"{len(document['tags'])} tags", "watermark": document["evaluated_at"]}
        return ImageTags(document)

    @cached_property
    def deployed(self) -> dict:
        """The deployed vuoro-shared composition at appservice HEAD: digest, label, source commit, locks."""
        head = self.head(APPSERVICE)
        deployment = self.show(APPSERVICE, head, self.registry["sources"]["shared_deployment"]) or ""
        digest, label = DIGEST.search(deployment), RELEASE_LABEL.search(deployment)
        source = digest and self.tags.source_commit(digest.group(1))
        pins = source and self.show(self.registry["external"]["pins"]["repo"], source, self.registry["external"]["pins"]["path"])
        return {"head": head, "digest": digest and digest.group(1), "label": label and label.group(1), "source": source,
                "release": self.tags.release(digest and digest.group(1)), "locks": lock_rows(json.loads(pins)) if pins else {}}

    def served_authorities(self) -> set[str]:
        return {o["required_authority"] for o in self.catalog["operations"]}

    def declared(self, value: Any, repo: str, revision: str) -> dict:
        return cell("DECLARED", value, f"{self.transport} {repo}", revision, self.at)

    def observed(self, value: Any, ref: str, revision: str) -> dict:
        return cell("OBSERVED", value, f"http-get {ref}", revision, self.at)

    def blind(self, reason: str, transport: str = "none") -> dict:
        return blind(reason, transport, None, self.at)


def days_since(when: str | None, now: datetime) -> int | None:
    return (now.date() - date.fromisoformat(when[:10])).days if when else None


def row(kind: str, subject: str, detail: str, evidence: dict, consumers=(), since=None, falsifier="", sources=(), flags=()) -> dict:
    return {"kind": kind, "subject": subject, "detail": detail, "consumers": list(consumers), "since": since,
            "falsifier": {"check": falsifier, "sources": list(sources)}, "flags": list(flags), "evidence": evidence}


def unevaluated(run: Run, kind: str, error: Exception) -> dict:
    return row(kind, "not evaluated", str(error), run.blind(str(error)), flags=["UNDETERMINED"])


# ── panel 1: provenance ─────────────────────────────────────────────────────────


def provenance(run: Run) -> dict:
    hs, served = run.handshake, run.catalog
    if hs is None:
        reason = run.degraded("authority.handshake") or "authority unreachable"
        return {"authority": run.blind(reason, "http-get"), "catalog": run.blind(reason, "http-get"), "compatibility": run.blind(reason, "http-get")}
    ref = "/api/meta/v1/handshake"
    return {
        "authority": run.observed({"release": hs["service_release"]["version"], "environment": hs["environment"]["name"]}, ref, hs["catalog_revision"]),
        "catalog": run.observed({"revision": served["revision"], "operations": len(served["operations"]), "authorities": len(run.served_authorities())},
                                "/api/catalog/v1", served["revision"]) if served else run.blind(run.degraded("authority.catalog") or "catalog unread", "http-get"),
        "compatibility": run.observed({d: v["state"] for d, v in hs["compatibility"]["domains"].items()}, ref, hs["catalog_revision"]),
    }


# ── panel 3: hazards ────────────────────────────────────────────────────────────


def authority_hazards(run: Run) -> list[dict]:
    if run.catalog is None:
        raise SourceUnavailable(run.degraded("authority.catalog") or "catalog unread")
    consumers, head = run.registry["consumer_set"], run.head("agentops")
    requested: dict[str, int] = {}
    for path in consumers["profiles"]:
        for authority in json.loads(run.show("agentops", head, path) or "{}").get("required_authorities", []):
            requested[authority] = requested.get(authority, 0) + 1
    code = [(c, run.show(c["repo"], run.head(c["repo"]), c["path"]) or "") for c in consumers["code"]]
    served, rows = run.served_authorities(), []
    for authority, profiles in orphan_authorities(requested, served).items():
        verb = consumers.get("verbs", {}).get(authority)
        called = [f"{c['consumer']} {c['path']}:{n}" for c, text in code for n, line in enumerate(text.splitlines(), 1) if verb and f'"{verb}"' in line]
        validity = run.registry.get("validity", {}).get(authority)
        detail = f"requested by {profiles} client profiles · no live operation requires it ({len(served)} authorities)"
        rows.append(row("FORECLOSED" if validity else "ORPHAN", authority, detail + (f" · {validity['by']}" if validity else " · history undetermined"),
                        run.declared(authority, "agentops", head), called, validity and validity["since"],
                        f"catalog required_authority values contain {authority}", ["git.agentops", "authority.catalog"]))
    return rows


def schema_consts(schema: Any, key: str) -> set[str]:
    if isinstance(schema, dict):
        found = {schema[key].get("const")} if isinstance(schema.get(key), dict) and "const" in schema[key] else set()
        return found.union(*(schema_consts(v, key) for v in schema.values()))
    return set().union(*(schema_consts(v, key) for v in schema)) if isinstance(schema, list) else set()


def unreachable_hazards(run: Run) -> list[dict]:
    repo, path = run.registry["external"]["record_classes"]["repo"], run.registry["external"]["record_classes"]["path"]
    head, audit = run.head(repo), run.deployed["locks"].get("audit-adapter")
    declared = record_classes(run.show(repo, head, path) or "")
    admitted = record_classes(run.show(repo, audit.value, path) or "") if audit else set()
    submit = next((o for o in (run.catalog or {}).get("operations", []) if o["name"] == "audit.observation.submit"), None)
    consts = schema_consts(submit["input_schema"], "record_class") if submit else set()
    changed = run.log(repo, BRANCH, [path])
    since = stamp(changed[0][1])[:10] if changed else None
    return [
        row("UNREACHABLE", f"audit record_class={c}",
            f"HEAD {repo} admits · pinned {audit.detail if audit else 'none'} rejects" if c not in admitted else "pinned admits · served schema refuses",
            run.declared(c, repo, head), since=since, sources=[f"git.{repo}", "git.appservice", "ghcr.image-tags", "authority.catalog"],
            falsifier=f"git show {head[:8]}:{path} | grep RECORD_CLASSES; git show {audit.value[:8] if audit else '?'}:{path}; catalog audit.observation.submit record_class const",
            flags=[] if submit else ["UNDETERMINED"]) | {"served_const": sorted(consts)}
        for c in sorted(declared) if c not in admitted or (consts and c not in consts)
    ]


def diverged_hazards(run: Run) -> list[dict]:
    head, rows = run.head(APPSERVICE), []
    deployed = run.deployed
    if deployed["label"] and deployed["release"] and deployed["label"] != deployed["release"]:
        rows.append(row("DIVERGED", "vuoro-shared release label", f"label {deployed['label']} vs digest {deployed['release']}",
                        run.declared(deployed["label"], APPSERVICE, head), sources=["git.appservice", "ghcr.image-tags"]))
    for subject in run.registry.get("divergence", []):
        def digests(commit: str) -> dict[str, str | None]:
            texts = {name: run.show(APPSERVICE, commit, path) or "" for name, path in subject["manifests"].items()}
            return {name: m.group(1) if (m := DIGEST.search(text)) else None for name, text in texts.items()}
        now = digests(head)
        if len(set(now.values())) < 2:
            continue
        since = None
        lookback = run.now - timedelta(days=subject.get("lookback_days", 90))
        for sha, when in run.log(APPSERVICE, BRANCH, list(subject["manifests"].values()), lookback):
            if len(set(digests(sha).values())) < 2:
                break
            since = (sha, stamp(when)[:10])
        detail = " vs ".join(f"{name} {(d or 'none')[7:15]} ({(run.tags.release(d) or 'untagged').removeprefix('vuoro-service-v')})" for name, d in now.items())
        rows.append(row("DIVERGED", subject["subject"], detail + (f" · since {since[0][:8]}" if since else ""), run.declared(now, APPSERVICE, head),
                        subject.get("consumers", []), since and since[1], "digests equal across " + ", ".join(subject["manifests"]),
                        ["git.appservice", "ghcr.image-tags"]))
    return rows


def hazards(run: Run) -> dict:
    rows: list[dict] = []
    for kind, evaluate in (("FORECLOSED", authority_hazards), ("UNREACHABLE", unreachable_hazards), ("DIVERGED", diverged_hazards)):
        try:
            rows += evaluate(run)
        except SourceUnavailable as error:
            rows.append(unevaluated(run, kind, error))
    return {"rows": rows}


# ── panel 5: ground · tools ─────────────────────────────────────────────────────


def ground_tools(run: Run) -> dict:
    hs, panel = run.handshake, {"installed": run.blind(next(b["reason"] for b in run.registry["blind"] if b["id"] == "installed"))}
    try:
        deployed, head = run.deployed, run.head(APPSERVICE)
        release = hs and hs["service_release"]["version"]
        agrees = bool(release and deployed["label"] == f"vuoro-service-v{release}")
        panel["authority"] = run.declared({"served": release, "label": deployed["label"], "digest_release": deployed["release"], "agrees": agrees,
                                           "as_of": head}, APPSERVICE, head)
        pins = run.registry["external"]["pins"]
        pinned = lock_rows(json.loads(run.show(pins["repo"], run.head(pins["repo"]), pins["path"]) or '{"release_locks": []}'))
        adapters = {}
        for lock, source in run.registry["adapters"].items():
            text = run.show(source["repo"], run.head(source["repo"]), source["pyproject"])
            adapters[lock] = {"head": tomllib.loads(text)["project"]["version"] if text else None,
                              "pinned": getattr(pinned.get(lock), "detail", None), "deployed": getattr(deployed["locks"].get(lock), "detail", None)}
        panel["adapters"] = run.declared(adapters, f"{APPSERVICE}+{pins['repo']}", f"{head}+{deployed['source']}")
    except SourceUnavailable as error:
        panel |= {"authority": run.blind(str(error)), "adapters": run.blind(str(error))}
    panel["domains"] = run.observed({d: v["state"] for d, v in hs["compatibility"]["domains"].items()}, "/api/meta/v1/handshake", hs["catalog_revision"]) \
        if hs else run.blind(run.degraded("authority.handshake") or "authority unreachable", "http-get")
    return panel




# ── panel 4: moves ──────────────────────────────────────────────────────────────


def blind_reason(run: Run, key: str) -> str:
    return next(b["reason"] for b in run.registry["blind"] if b["id"] == key)


def debt(rows: list[dict], now: datetime) -> dict:
    oldest = max(rows, key=lambda r: days_since(r["since"], now) or -1, default=None)
    return {"count": len(rows), "oldest_days": oldest and days_since(oldest["since"], now), "subject": oldest and oldest["subject"]}


def moves(run: Run, hazard_rows: list[dict], limit: int = 5) -> dict:
    start = run.now - timedelta(days=run.registry["window_days"])
    panel: dict = {"window": {"start": stamp(start), "end": run.at}, "zero": None, "overflow": 0}
    try:
        result, head = Replay(run.registry, run, run.tags).run(start, run.now), run.head(APPSERVICE)
    except SourceUnavailable as error:
        return panel | {k: run.blind(str(error)) for k in ("counts", "attributed", "exercise_observable", "recall")} | {"rows": []}
    found: list[Move] = result["moves"]
    groups: dict[tuple[str, str, str], list[Move]] = {}
    for m in found:
        groups.setdefault((m.boundary, m.vocabulary, m.cls), []).append(m)
    rows = [{"at": b, "date": ms[0].boundary_at[:10], "class": cls, "vocabulary": v,
             "members": [m.member + (f" ({m.detail})" if m.detail else "") for m in ms], "evidence": run.declared(len(ms), APPSERVICE, b)}
            for (b, v, cls), ms in groups.items()]
    rows.sort(key=lambda r: r["date"], reverse=True)
    rows.sort(key=lambda r: RANK.index(r["class"]))
    n = len(found)
    panel |= {"counts": run.declared({cls: sum(m.cls == cls for m in found) for cls in RANK}, APPSERVICE, head),
              "attributed": run.declared(f"0/{n}", APPSERVICE, head), "exercise_observable": run.declared(f"0/{n}", APPSERVICE, head),
              "rows": rows[:limit], "overflow": max(0, len(rows) - limit), "recall": run.declared(recall(result), APPSERVICE, head)}
    if n == 0:
        counted = [r for r in hazard_rows if not r["flags"]]
        panel["zero"] = {"boundary_commits": len(result["boundaries"]), "vocabularies": len(VOCABULARIES),
                         "spend": run.blind(blind_reason(run, "spend")), "decayed": run.blind("no exercise is observable"),
                         "unreachable": debt([r for r in counted if r["kind"] == "UNREACHABLE"], run.now),
                         "unrepaired": debt([r for r in counted if r["kind"] != "UNREACHABLE"], run.now)}
    return panel


# ── panel 6: ground · may do ────────────────────────────────────────────────────


def may_do(run: Run) -> dict:
    panel = {k: run.blind(blind_reason(run, k)) for k in ("grants", "admitted_policy_revision")}
    try:
        path = run.registry["sources"]["broker_config"]
        changed = run.log(APPSERVICE, BRANCH, [path]) or unavailable("git.appservice: no cred-broker ConfigMap")
        commit, when = changed[0]
        policy = read_policy(run.show(APPSERVICE, commit, path))
        if not isinstance(policy, dict):
            raise SourceUnavailable("the cred-broker ConfigMap has no readable production.json")
        hosts = {h["host_id"]: {"trust_profile": h.get("trust_profile"), "repositories": set(), "capabilities": {}, "unusable": 0}
                 for h in policy.get("policy", {}).get("hosts", [])}
        for key, binding in broker_rows(policy)["credbroker.binding"].items():
            host, repository, capability = key.split("|")
            entry = hosts.setdefault(host, {"trust_profile": None, "repositories": set(), "capabilities": {}, "unusable": 0})
            entry["repositories"].add(repository)
            entry["capabilities"][capability] = entry["capabilities"].get(capability, 0) + 1
            entry["unusable"] += not binding.passed
        pvc = run.show(APPSERVICE, run.head(APPSERVICE), run.registry["sources"]["broker_pvc"]) is not None
        value = {"commit": commit, "date": stamp(when)[:10], "receipts": durability_rows(False, policy, pvc)["credbroker.receipts"].value,
                 "policy_revision": policy_revision(policy), "hosts": {h: e | {"repositories": len(e["repositories"])} for h, e in hosts.items()}}
        return panel | {"policy": run.declared(value, APPSERVICE, commit)}
    except SourceUnavailable as error:
        return panel | {"policy": run.blind(str(error))}
