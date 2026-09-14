"""CLI text rendering of operator-projection/v1: screen one in order (DOSSIER-front-page-design.md §4)."""

from __future__ import annotations

from datetime import datetime, timezone

COVERS = frozenset({
    "schema", "derived", "generated_at", "cadence_s", "stale_after_s", "registry", "sources",
    "panels.provenance.authority", "panels.provenance.catalog", "panels.provenance.compatibility",
    "panels.pickup.counts", "panels.pickup.rows", "panels.pickup.overflow",
    "panels.hazards.open", "panels.hazards.oldest_days", "panels.hazards.rows",
    "panels.moves.window", "panels.moves.counts", "panels.moves.attributed", "panels.moves.exercise_observable",
    "panels.moves.rows", "panels.moves.overflow", "panels.moves.zero", "panels.moves.recall",
    "panels.ground_tools.installed", "panels.ground_tools.authority", "panels.ground_tools.adapters", "panels.ground_tools.domains",
    "panels.may_do.grants", "panels.may_do.admitted_policy_revision", "panels.may_do.policy",
    "panels.blind_spots.scope", "panels.blind_spots.coverage_s1", "panels.blind_spots.not_seen",
})
LIMIT = 5
Line = tuple[str, str]  # (style class, text)


def show(value: dict, fmt=str) -> str:
    return f"BLIND({value['reason']})" if value["kind"] == "BLIND" else fmt(value["value"])


def age(generated_at: str, now: datetime) -> tuple[int, str]:
    seconds = int((now - datetime.fromisoformat(generated_at)).total_seconds())
    return seconds, f"{seconds // 60}m" if seconds < 5400 else f"{seconds // 3600}h" if seconds < 172800 else f"{seconds // 86400}d"


def overflow(count: int) -> list[Line]:
    return [("sub", f" +{count} more below")] if count > 0 else []


def pairs(value: dict) -> str:
    return " · ".join(f"{k} {v}" for k, v in value.items())


def header(doc: dict, now: datetime) -> list[Line]:
    p, (seconds, ago) = doc["panels"]["provenance"], age(doc["generated_at"], now)
    degraded = [s["id"] for s in doc["sources"] if s["degraded"]]
    stale = [("stale", f"STALE · generated {ago} ago, past {doc['stale_after_s'] // 60}m · every value keeps its own record timestamp")]
    authority = show(p["authority"], lambda v: "vuoro-service " + v["release"] + " (" + v["environment"] + ")")
    catalog = show(p["catalog"], lambda v: f"{v['revision'][:8]} ({v['operations']} operations, {v['authorities']} authorities)")
    return (stale if seconds > doc["stale_after_s"] else []) + [
        ("head", f"OPERATOR PROJECTION {doc['schema'].rsplit('/', 1)[-1]} · {doc['derived']} · generated {doc['generated_at']} ({ago} ago, cadence {doc['cadence_s'] // 60}m)"),
        ("", f"authority {authority} · catalog {catalog} · {show(p['compatibility'], pairs)}"),
        ("", f"registry {doc['registry']['id']} @ {doc['registry']['commit'][:8]} · {len(doc['sources'])} sources · degraded: {', '.join(degraded) or 'none'}"),
    ]


def pickup(doc: dict, now: datetime) -> list[Line]:
    p = doc["panels"]["pickup"]
    if p.get("kind") == "BLIND":
        return [("blind", f"PICK UP HERE   {show(p)}")]
    counts = show(p["counts"], lambda c: f"needs you {c['needs_you']} · stale holds {c['stale_holds']} · active, no holder {c['active_no_holder']} · ready {c['ready']}")
    lines = [("head", f"PICK UP HERE   {counts}")]
    for r in p["rows"]:
        touch = f"{r['age']}d · ground moved since touch: {r['moved_since_touch']}" if isinstance(r["age"], int) else r["age"]
        detail = f" · {r['detail']}" if r.get("detail") else ""
        lines.append(("row", f" {r['ref']}  {r['class']}  {r['next_action']}{detail} · {r['holder']} · {r['boundary']} · {touch}"))
    return lines + overflow(p["overflow"])


def hazards(doc: dict, now: datetime) -> list[Line]:
    h = doc["panels"]["hazards"]
    rows = sorted(h["rows"], key=lambda r: bool(r["flags"]))
    lines = [("head", f"HAZARDS   {show(h['open'])} open · oldest {show(h['oldest_days'], lambda d: 'none' if d is None else f'{d}d')}")]
    for r in rows[:LIMIT]:
        if r["flags"]:
            lines.append(("sub", f"   ({' '.join(r['flags'])}) {r['kind']} {r['subject']} · {show(r['evidence'], lambda _: r['detail'])}"))
            continue
        consumers = f" · consumers: {', '.join(r['consumers'])}" if r["consumers"] else ""
        lines.append(("row", f" {r['kind']:<12} {r['subject']} · {r['detail']}{consumers}" + (f" · since {r['since']}" if r["since"] else "")))
    return lines + overflow(len(rows) - LIMIT)


def debt(d: dict, noun: str) -> str:
    oldest = f"{d['oldest_days']}d" if d["oldest_days"] is not None else "age undetermined"
    return f"{d['count']} {noun}" + (f" (oldest {oldest}: {d['subject']})" if d["subject"] else "")


def moves(doc: dict, now: datetime) -> list[Line]:
    m = doc["panels"]["moves"]
    span = f"{m['window']['start'][:10]} → {m['window']['end'][:10]}"
    if m["counts"]["kind"] == "BLIND":
        return [("blind", f"MOVES  {span} · {show(m['counts'])}")]
    c = m["counts"]["value"]
    tally = (f"{sum(c.values())} moves ({c['GAINED']} gained · {c['FORECLOSED']} foreclosed · {c['REGRESSED']} regressed"
             f" · {c['DURABILITY-UP'] + c['DURABILITY-DOWN']} durability)")
    if z := m["zero"]:
        return [
            ("head", f"MOVES  {span} · {tally}"),
            ("", f" while   {z['boundary_commits']} deployment-boundary commits touched agent-plane manifests and registry sources"),
            ("", f"         · spend: {show(z['spend'])}"),
            ("", f" still   {debt(z['unreachable'], 'rows DECLARED-UNREACHABLE')}"),
            ("", f"         · {debt(z['unrepaired'], 'hazards unrepaired')} · decayed: {show(z['decayed'])}"),
            ("", f" note    0 moves means no member of the {z['vocabularies']} enumerated vocabularies moved at the deployment"),
            ("", "         boundary. It does not mean nothing changed: unenumerated vocabularies are invisible here."),
        ]
    lines = [("head", f"MOVES  {span} · {tally} · attributed {show(m['attributed'])} · exercise observable {show(m['exercise_observable'])}")]
    for r in m["rows"]:
        members = ", ".join(r["members"][:3]) + (f", +{len(r['members']) - 3} more" if len(r["members"]) > 3 else "")
        lines.append(("row", f" {r['date']} {r['class']:<15} {r['vocabulary']} {members} · appservice {r['at'][:8]}"))
    misses = show(m["recall"], lambda v: f"{v['boundary_commits']} boundary commits · {v['mapped']} mapped · {len(v['misses'])} misses"
                  + (" (" + ", ".join(s[:8] for s in v["misses"]) + ")" if v["misses"] else ""))
    return lines + overflow(m["overflow"]) + [("sub", f" recall   {misses}")]


def adapters(value: dict) -> str:
    return " · ".join(f"{lock} {v['head']}/{v['pinned']}/{v['deployed']}" for lock, v in value.items())


def authority(v: dict) -> str:
    verdict = "agrees" if v["agrees"] else "DISAGREES"
    return f"authority {v['served'] or 'unobserved'} {verdict} with appservice label {v['label']} as of {v['as_of'][:8]} (digest is {v['digest_release']})"


def policy(v: dict) -> str:
    hosts = " · ".join(f"{h} ({e['trust_profile']}) {e['repositories']} repos ({pairs(e['capabilities'])})" + (f", {e['unusable']} unusable" if e["unusable"] else "")
                       for h, e in v["hosts"].items())
    return f"cred-broker policy declared @ {v['commit'][:8]} {v['date']} · policy_revision {v['policy_revision'][:19]} · receipts {v['receipts']}\n          · {hosts}"


def ground(doc: dict, now: datetime) -> list[Line]:
    t, may = doc["panels"]["ground_tools"], doc["panels"]["may_do"]
    return [
        ("head", "GROUND"),
        ("", f" tools    {show(t['authority'], authority)} · domains {show(t['domains'], pairs)}"),
        ("", f"          · adapters HEAD/pinned/deployed: {show(t['adapters'], adapters)} · installed: {show(t['installed'])}"),
        *[("", line) for line in f" may do   {show(may['policy'], policy)}".split("\n")],
        ("", f"          · live grants/refusals: {show(may['grants'])} · admitted policy revision: {show(may['admitted_policy_revision'])}"),
    ]


def blind_spots(doc: dict, now: datetime) -> list[Line]:
    b = doc["panels"]["blind_spots"]
    scope = b["scope"]
    served = show(scope["served"], lambda v: f"{len(v['repositories'])} repos authoritative · undeclared {v['undeclared']} · not served {v['not_served']}")
    later = show(b["not_seen"], lambda v: " · ".join(f"panel {p['panel']} BLIND({p['producer']})" for p in v["later_panels"]))
    return [
        ("head", "BLIND SPOTS"),
        ("", f" scope    served: {served} · project.toml declares {show(scope['declared'], lambda v: str(len(v)) + ' members')} · {show(scope['other'])}"),
        ("", f" §1       {show(b['coverage_s1'], lambda v: ' · '.join(c['id'] + ': ' + c['state'] + ' (' + c['reason'] + ')' for c in v))}"),
        ("", f" not seen {show(b['not_seen'], lambda v: ' · '.join(v['not_seen']))}"),
        ("", f"          · always BLIND: {show(b['not_seen'], lambda v: ' · '.join(x['reason'] for x in v['blind']))}"),
        ("", f"          · {later}"),
    ]


SECTIONS = (header, pickup, hazards, moves, ground, blind_spots)


def sections(doc: dict, now: datetime | None = None) -> list[list[Line]]:
    return [section(doc, now or datetime.now(timezone.utc)) for section in SECTIONS]


def render(doc: dict, now: datetime | None = None) -> str:
    return "\n\n".join("\n".join(text for _, text in lines) for lines in sections(doc, now)) + "\n"
