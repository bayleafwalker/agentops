"""Remote-leg redaction (§16.1): the public page is REMOTE applied to the document; a field REMOTE does not name is dropped.

Masks keep each field's type, so the same two renderers draw the remote page. Counts, shas and digests stay; names, paths,
host ids and free text stay on the LAN.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from .generate import UNCONTRACTED

# Source ids that name public repositories or public reads; any other id renders as private-source-<n>.
PUBLIC_SOURCES = frozenset({"authority.handshake", "authority.catalog", "authority.work", "ghcr.image-tags",
                            "git.agentops", "git.auditctl", "git.vuoro", "git.sprintctl"})
# Vocabularies whose members come from public sources; members of any other vocabulary render as a count.
PUBLIC_VOCABULARIES = frozenset({"authority.service_release", "composition.release_lock", "audit.record_class",
                                 "catalog.operation", "catalog.authority"})
BOUNDARIES = frozenset({"HANDOFF", "CONTEXT", "NONE"})
UNHELD = frozenset({"no holder", "not contracted"})
LAN_ONLY = "unavailable (reason on the LAN)"

Mask = Callable[[object, dict], object]


def keep(value, doc):
    return value


def declared(doc: dict) -> set[str]:
    """Registry-declared BLIND reasons are static text; any other reason is a runtime error and may name hosts or paths."""
    seen = doc["panels"]["blind_spots"]["not_seen"]
    return set() if seen["kind"] == "BLIND" else {b["reason"] for b in seen["value"]["blind"]}


def cell(mask: Mask = keep) -> Mask:
    def apply(c: dict, doc: dict) -> dict:
        if c["kind"] == "BLIND":
            return {**c, "reason": c["reason"] if c["reason"] in declared(doc) else LAN_ONLY}
        return {**c, "value": mask(c["value"], doc)}
    return apply


def count(noun: str) -> Callable[[list], list[str]]:
    return lambda values: [f"{len(values)} {noun}"] if values else []


evidence = cell(lambda value, doc: None)


def sources(value: list[dict], doc: dict) -> list[dict]:
    private = iter(range(1, len(value) + 1))
    return [{"id": s["id"] if s["id"] in PUBLIC_SOURCES else f"private-source-{next(private)}", "transport": s["transport"], "ref": "",
             "revision": s["revision"], "observed_at": s["observed_at"], "watermark": None,
             "degraded": {"detail": "degraded"} if s["degraded"] else None} for s in value]


def pickup_rows(rows: list[dict], doc: dict) -> list[dict]:
    return [{"ref": (m.group() if (m := re.search(r"#\d+$", r["ref"])) else "#"), "class": r["class"], "next_action": "", "detail": "",
             "holder": r["holder"] if r["holder"] in UNHELD else "held",
             "age": r["age"] if isinstance(r["age"], int) else UNCONTRACTED,
             "boundary": r["boundary"] if r["boundary"] in BOUNDARIES else "",
             "moved_since_touch": r["moved_since_touch"] if isinstance(r["moved_since_touch"], int) else UNCONTRACTED,
             "evidence": evidence(r["evidence"], doc)} for r in rows]


def hazard_rows(rows: list[dict], doc: dict) -> list[dict]:
    return [{"kind": r["kind"], "subject": "", "detail": "", "consumers": count("consumers")(r["consumers"]), "since": r["since"],
             "falsifier": {"check": "", "sources": []}, "flags": r["flags"], "evidence": evidence(r["evidence"], doc)} for r in rows]


def move_rows(rows: list[dict], doc: dict) -> list[dict]:
    return [{"at": r["at"], "date": r["date"], "class": r["class"], "vocabulary": r["vocabulary"],
             "members": r["members"] if r["vocabulary"] in PUBLIC_VOCABULARIES else count("members")(r["members"]),
             "evidence": evidence(r["evidence"], doc)} for r in rows]


def zero(z: dict | None, doc: dict) -> dict | None:
    def debt(d: dict) -> dict:
        return {"count": d["count"], "oldest_days": d["oldest_days"], "subject": ""}
    return z and {"boundary_commits": z["boundary_commits"], "vocabularies": z["vocabularies"], "spend": cell()(z["spend"], doc),
                  "decayed": cell(lambda v, d: len(v) if isinstance(v, list) else v)(z["decayed"], doc),
                  "unreachable": debt(z["unreachable"]), "unrepaired": debt(z["unrepaired"])}


def recall(v: dict, doc: dict) -> dict:
    return {"boundary_commits": v["boundary_commits"], "mapped": v["mapped"], "misses": ["redacted"] * len(v["misses"])}


def policy(v: dict, doc: dict) -> dict:
    hosts = {f"host-{n}": {"trust_profile": e["trust_profile"].replace(host, f"host-{n}"), "repositories": e["repositories"],
                           "capabilities": e["capabilities"], "unusable": e["unusable"]} for n, (host, e) in enumerate(v["hosts"].items(), 1)}
    return {"commit": v["commit"], "date": v["date"], "receipts": v["receipts"], "policy_revision": v["policy_revision"], "hosts": hosts}


def scope(s: dict, doc: dict) -> dict:
    served = cell(lambda v, d: {"repositories": [""] * len(v["repositories"]), "undeclared": len(v["undeclared"]), "not_served": len(v["not_served"])})
    return {"served": served(s["served"], doc), "declared": cell(lambda v, d: [""] * len(v))(s["declared"], doc),
            "other": cell(lambda v, d: "")(s["other"], doc)}


REMOTE: dict[str, Mask] = {
    "schema": keep, "derived": keep, "generated_at": keep, "cadence_s": keep, "stale_after_s": keep, "registry": keep, "sources": sources,
    **{f"panels.provenance.{k}": cell() for k in ("authority", "catalog", "compatibility")},
    "panels.pickup.counts": cell(), "panels.pickup.rows": pickup_rows, "panels.pickup.overflow": keep,
    "panels.hazards.open": cell(), "panels.hazards.oldest_days": cell(), "panels.hazards.rows": hazard_rows,
    "panels.moves.window": keep, "panels.moves.counts": cell(), "panels.moves.attributed": cell(), "panels.moves.exercise_observable": cell(),
    "panels.moves.rows": move_rows, "panels.moves.overflow": keep, "panels.moves.zero": zero, "panels.moves.recall": cell(recall),
    **{f"panels.ground_tools.{k}": cell() for k in ("installed", "authority", "adapters", "domains")},
    "panels.may_do.grants": cell(), "panels.may_do.admitted_policy_revision": cell(), "panels.may_do.policy": cell(policy),
    "panels.blind_spots.scope": scope, "panels.blind_spots.coverage_s1": cell(), "panels.blind_spots.not_seen": cell(),
}


def redact(doc: dict) -> dict:
    out: dict = {}
    for path, mask in REMOTE.items():
        *parents, leaf = path.split(".")
        source, target = doc, out
        for key in parents:
            source = source[key]
            if "kind" in source:  # a panel that is one BLIND cell as a whole
                target[key] = cell()(source, doc)
                break
            target = target.setdefault(key, {})
        else:
            target[leaf] = mask(source[leaf], doc)
    return out
