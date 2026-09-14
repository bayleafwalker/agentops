"""generate(git, authority, registry, now): one operator-projection/v1 document. Reads only; no previous document."""

from __future__ import annotations

import json
import tomllib
from collections.abc import Callable
from datetime import date, datetime, timedelta
from functools import cached_property
from typing import Any

from . import SCHEMA
from .cell import blind, cell, demote
from .evaluators import DIGEST, Move, broker_rows, durability_rows, lock_rows, orphan_authorities, policy_revision, record_classes
from .replay import APPSERVICE, BRANCH, RELEASE_LABEL, VOCABULARIES, Replay, read_policy, recall
from .sources import Authority, GitSource, ImageTags, SourceUnavailable, fetch_image_tags, stamp

RANK = ["FORECLOSED", "REGRESSED", "DURABILITY-DOWN", "DURABILITY-UP", "GAINED", "CONTRACT-CHANGE"]


def unavailable(message: str):
    raise SourceUnavailable(message)


def describe(error: Exception) -> str:
    """Never an empty reason: str(httpx.ReadTimeout()) is '', so anything but a worded SourceUnavailable is named by type."""
    named = f"{type(error).__name__}: {error}".removesuffix(": ")
    return str(error) if isinstance(error, SourceUnavailable) and str(error) else named


class Run:
    """One generation: its sources, their degraded envelopes, and the reads shared between panels."""

    def __init__(self, git: GitSource, authority: Authority | None, registry: dict, now: datetime, tags: Callable[[], dict]):
        self.git, self.authority, self.registry, self.now, self.at = git, authority, registry, now, stamp(now)
        self.transport = getattr(git, "transport", "git")
        self.sources: dict[str, dict] = {}
        self.moved: list[Move] = []
        self._tags = tags

    def guard(self, source: str, transport: str, fetch: Callable[[], Any]) -> Any:
        entry = self.sources.setdefault(source, {"id": source, "transport": transport, "ref": None, "revision": None,
                                                 "observed_at": self.at, "watermark": None, "degraded": None})
        try:
            return fetch()
        except Exception as error:  # a missing source never crashes a generation; it is carried as degraded
            entry["degraded"] = entry["degraded"] or {"message": f"{source} unavailable", "source": source, "detail": f"{type(error).__name__}: {error}".removesuffix(": ")}
            raise SourceUnavailable(f"{source}: {describe(error)}") from error

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
                        run.declared(deployed["label"], APPSERVICE, head), falsifier=f"ghcr tag {deployed['label']} resolves to {deployed['digest']}",
                        sources=["git.appservice", "ghcr.image-tags"]))
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
        rows.append(row("DIVERGED", subject["subject"], detail + (f" · diverged at appservice {since[0][:8]}" if since else ""), run.declared(now, APPSERVICE, head),
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
    run.moved = found
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
        panel["zero"] = {"boundary_commits": len(result["boundaries"]), "vocabularies": len(VOCABULARIES), "evidence": panel["recall"],
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


# ── panel 2: pick up here ───────────────────────────────────────────────────────

CLASSES = {"NEEDS YOU": ("conflicts", "blocked_items"), "STALE HOLD": ("stale_items",),
           "ACTIVE, NO HOLDER": ("active_unreserved_items",), "READY": ("next_actions",)}
COUNTS = dict(zip(CLASSES, ("needs_you", "stale_holds", "active_no_holder", "ready")))
UNCONTRACTED = "touch time: not contracted"


def boundary(run: Run, item: dict, sprints: list[dict]) -> str:
    """A row carries no sprint: its repo's active sprint has a checkpoint (HANDOFF), the item has candidates (CONTEXT), else NONE."""
    repo = item["origin_repo"]
    sprint = next((s["id"] for s in sprints if s.get("origin_repo") == repo and s.get("status") == "active"), None)
    if sprint is None:
        return "NONE"
    if run.degraded("authority.work"):
        return "UNDETERMINED"  # one timeout already spent this generation; do not queue more behind it
    read = lambda op, args: run.guard("authority.work", "vuoro-invoke", lambda: run.authority.read(op, args, repo_id=repo))  # noqa: E731
    try:
        if read("work.read.handoff", {"sprint_id": sprint, "events_limit": 1}).get("last_checkpoint"):
            return "HANDOFF"
        if item["id"] is None:
            return "NONE"
        found = read("work.read.context-candidates", {"sprint_id": sprint, "item_id": item["id"], "limit": 1})
        return "CONTEXT" if found.get("candidates") else "NONE"
    except SourceUnavailable:
        return "UNDETERMINED"


SEVERITY = ("critical", "high", "error", "warning", "medium", "low", "info")  # unknown next; non-conflict entries last


def entries(key: str, raw: dict) -> list[dict]:
    """One entry per item a list names: a conflict names every item in item_ids, or itself (repo:kind) when it names none.
    Only idle_seconds is a contracted age; no list carries a holder."""
    repo, kind, conflict = raw.get("origin_repo"), raw.get("kind"), key == "conflicts"
    idents = (raw.get("item_ids") or [None]) if conflict else [raw.get("item_id") if key == "next_actions" else raw.get("id")]
    severity = SEVERITY.index(raw["severity"]) if raw.get("severity") in SEVERITY else len(SEVERITY) + (not conflict)
    return [{"origin_repo": repo, "id": i, "ref": f"{repo}#{i}" if i is not None else f"{repo}:{kind or key}",
             "text": raw.get("title") or raw.get("summary"), "idle_seconds": raw.get("idle_seconds"), "severity": severity,
             "detail": f"{kind} · {len(raw.get('item_ids') or [])} items" if conflict else None,
             "holder": "no holder" if key == "active_unreserved_items" else "not contracted"} for i in idents]


def candidates_of(context: dict) -> list[tuple[str, dict]]:
    """Every item once, at its highest class, then most severe conflict, oldest, ref; a no-action next action is not ready work."""
    order, seen = list(CLASSES), set()
    found = [(cls, item) for cls, keys in CLASSES.items() for key in keys for raw in context.get(key) or []
             if key != "next_actions" or raw.get("kind") != "no-action" for item in entries(key, raw)]
    found.sort(key=lambda c: (order.index(c[0]), c[1]["severity"], -(c[1]["idle_seconds"] or 0),
                              str(c[1]["origin_repo"]), c[1]["id"] is None, c[1]["id"] or 0, c[1]["ref"]))
    return [c for c in found if not (c[1]["ref"] in seen or seen.add(c[1]["ref"]))]


def pickup(run: Run, found: list[Move]) -> tuple[dict, list[str] | None]:
    operation, limit = run.registry["pickup"]["operation"], run.registry["pickup"]["rows"]
    try:
        if run.catalog is None:
            raise SourceUnavailable(run.degraded("authority.catalog") or "catalog unread")
        context = run.guard("authority.work", "vuoro-invoke", lambda: run.authority.read(operation, {}))
    except SourceUnavailable as error:
        return run.blind(str(error), "vuoro-invoke"), None
    revision, order = f"catalog:{run.catalog['revision']}", list(CLASSES)
    run.sources["authority.work"] |= {"ref": operation, "revision": revision}
    observed = lambda value: cell("OBSERVED", value, f"vuoro-invoke {operation}", revision, run.at)  # noqa: E731
    candidates = candidates_of(context)
    rank = {item["ref"]: (order.index(cls), item["severity"]) for cls, item in candidates}
    rows = []
    for cls, item in candidates[:limit]:
        idle = item["idle_seconds"]
        touched = run.now - timedelta(seconds=idle) if idle is not None else None
        rows.append({"ref": item["ref"], "class": cls, "next_action": item["text"], "detail": item["detail"], "holder": item["holder"],
                     "age": idle // 86400 if touched else UNCONTRACTED, "boundary": boundary(run, item, context.get("sprints") or []),
                     "moved_since_touch": sum(datetime.fromisoformat(m.boundary_at) > touched for m in found) if touched else UNCONTRACTED,
                     "evidence": observed(item["ref"])})
    rows.sort(key=lambda r: (*rank[r["ref"]], r["boundary"] != "NONE"))  # stable: within a severity, boundary NONE first
    counts = observed({COUNTS[cls]: sum(c == cls for c, _ in candidates) for cls in CLASSES})
    return {"counts": counts, "rows": rows, "overflow": len(candidates) - len(rows)},[r.get("origin_repo") for r in context.get("repositories") or []]


# ── panel 7: blind spots ────────────────────────────────────────────────────────


def blind_spots(run: Run, repositories: list[str] | None, pickup_panel: dict) -> dict:
    registry = run.registry
    stated = lambda value: cell("DECLARED", value, "registry", registry.get("commit") or "uncommitted", run.at)  # noqa: E731
    try:
        head = run.head("agentops")
        members = [m["repo_id"] for m in tomllib.loads(run.show("agentops", head, "project.toml") or "").get("members", [])]
        declared = run.declared(members, "agentops", head)
    except SourceUnavailable as error:
        members, declared = [], run.blind(str(error))
    if repositories is None:
        served = run.blind(f"scope: {pickup_panel['reason']}", "vuoro-invoke")
    else:
        served = cell("OBSERVED", {"repositories": repositories, "undeclared": sorted(set(repositories) - set(members)),
                                   "not_served": sorted(set(members) - set(repositories))},
                      "vuoro-invoke work.project.context", pickup_panel["counts"]["prov"]["record_revision"], run.at)
    return {"scope": {"served": served, "declared": declared, "other": stated("other scopes not enumerable: repo list unavailable in served mode")},
            "coverage_s1": stated(registry["coverage_s1"]),
            "not_seen": stated({"not_seen": registry["not_seen"], "blind": registry["blind"], "later_panels": registry["later_panels"]})}


# ── the document ────────────────────────────────────────────────────────────────


def attest(run: Run, rows: list[dict]) -> list[dict]:
    """§6.4 build-time auto-demotion: a row whose falsifier does not resolve this generation is CLAIMED-UNATTESTED."""
    for r in rows:
        missing = [s for s in r["falsifier"]["sources"] if s not in run.sources or run.degraded(s)]
        if not r["flags"] and (missing or not r["falsifier"]["check"]):
            r["flags"].append("CLAIMED-UNATTESTED")
            r["evidence"] = demote(r["evidence"], "falsifier did not resolve: " + (", ".join(missing) or "no check"))
    return rows


def generate(git: GitSource, authority: Authority | None, registry: dict, now: datetime, tags: Callable[[], dict] | None = None) -> dict:
    run = Run(git, authority, registry, now, tags or (lambda: fetch_image_tags(registry["external"]["image_tags"]["repository"])))
    panels = {"provenance": provenance(run)}
    rows = attest(run, hazards(run)["rows"])
    counted = [r for r in rows if not r["flags"]]
    derived = lambda value: cell("DECLARED", value, "derived hazards", registry.get("commit") or "uncommitted", run.at)  # noqa: E731
    moved = moves(run, rows)
    pickup_panel, repositories = pickup(run, run.moved)
    panels |= {"pickup": pickup_panel, "moves": moved, "ground_tools": ground_tools(run), "may_do": may_do(run),
               "hazards": {"open": derived(len(counted)), "oldest_days": derived(max((days_since(r["since"], now) for r in counted if r["since"]), default=None)),
                           "rows": rows},
               "blind_spots": blind_spots(run, repositories, pickup_panel)}
    order = ["provenance", "pickup", "hazards", "moves", "ground_tools", "may_do", "blind_spots"]
    return {"schema": SCHEMA, "derived": "DERIVED — not a record", "generated_at": run.at, "cadence_s": registry["cadence_s"],
            "stale_after_s": registry["stale_after_s"], "registry": {"id": registry["id"], "commit": registry.get("commit") or "uncommitted"},
            "sources": list(run.sources.values()), "panels": {name: panels[name] for name in order}}
