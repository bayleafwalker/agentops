"""Remote redaction (§16.1): no masked or dropped value reaches the remote JSON, text or HTML; unnamed fields are dropped."""

import http.client
import json
import threading
from datetime import datetime
from http.server import ThreadingHTTPServer

from operator_projection import redact, render_html, render_text
from operator_projection.serve import Latest, handler
from test_serve import document

SENTINEL = "zz-private-sentinel"


def observed(value):
    return {"kind": "OBSERVED", "value": value, "prov": {"transport": "t", "record_revision": "r", "observed_at": "2026-09-14T12:00:00Z"}}


def seeded() -> dict:
    """The fixture document with SENTINEL in every field §16.1 masks or drops."""
    doc = document()
    p = doc["panels"]
    doc["sources"].append({"id": f"git.{SENTINEL}", "transport": "github-rest", "ref": SENTINEL, "revision": "abc", "observed_at": doc["generated_at"],
                           "watermark": SENTINEL, "degraded": {"detail": SENTINEL}})
    p["pickup"] = {"counts": observed({"needs_you": 1, "stale_holds": 0, "active_no_holder": 0, "ready": 0}),
                   "rows": [{"ref": f"{SENTINEL}#2123", "class": "NEEDS YOU", "next_action": SENTINEL, "detail": SENTINEL, "holder": SENTINEL,
                             "age": 3, "boundary": SENTINEL, "moved_since_touch": 0, "evidence": observed(SENTINEL)}], "overflow": 0}
    p["hazards"]["rows"][4:] = [{"kind": "DIVERGED", "subject": SENTINEL, "detail": SENTINEL, "consumers": [SENTINEL], "since": "2026-09-01",
                                 "falsifier": {"check": SENTINEL, "sources": [SENTINEL]}, "flags": [], "evidence": observed(SENTINEL)}]
    p["moves"]["rows"].append({"at": "0" * 40, "date": "2026-09-01", "class": "GAINED", "vocabulary": "credbroker.repository",
                               "members": [SENTINEL], "evidence": observed(SENTINEL)})
    p["moves"]["recall"] = observed({"boundary_commits": 1, "mapped": 0, "misses": [SENTINEL]})
    p["ground_tools"]["installed"] = {**observed(None), "kind": "BLIND", "reason": f"ConnectError: {SENTINEL}.svc.cluster.local"}
    hosts = p["may_do"]["policy"]["value"]["hosts"]
    hosts[SENTINEL] = {**next(iter(hosts.values())), "trust_profile": f"{SENTINEL}-trusted"}
    p["blind_spots"]["scope"] = {"served": observed({"repositories": [SENTINEL], "undeclared": [SENTINEL], "not_served": [SENTINEL]}),
                                 "declared": observed([SENTINEL]), "other": observed(SENTINEL)}
    return doc


def renders(doc: dict) -> list[str]:
    now = datetime.fromisoformat(doc["generated_at"])
    return [json.dumps(doc), render_text.render(doc, now), render_html.render(doc, now)]


def test_no_masked_or_dropped_value_reaches_any_remote_render():
    doc = seeded()
    assert all(SENTINEL in out for out in renders(doc))
    assert not [out for out in renders(redact.redact(doc)) if SENTINEL in out]


def test_repository_names_host_ids_and_private_source_ids_of_the_fixture_stay_off_the_remote_json():
    doc = document()
    hosts = list(doc["panels"]["may_do"]["policy"]["value"]["hosts"])
    private = [s["id"] for s in doc["sources"] if s["id"] not in redact.PUBLIC_SOURCES]
    remote = json.dumps(redact.redact(doc))
    assert hosts and private and not [name for name in hosts + private if name in remote]


def test_counts_shas_and_declared_blind_reasons_survive():
    doc = seeded()
    remote = redact.redact(doc)["panels"]
    assert remote["hazards"]["open"] == doc["panels"]["hazards"]["open"]
    assert remote["pickup"]["rows"][0]["ref"] == "#2123" and remote["pickup"]["rows"][0]["holder"] == "held"
    assert remote["moves"]["rows"][-1]["members"] == ["1 members"] and remote["moves"]["rows"][-1]["at"] == "0" * 40
    assert remote["ground_tools"]["installed"]["reason"] == redact.LAN_ONLY
    assert remote["may_do"]["grants"] == doc["panels"]["may_do"]["grants"]  # a registry-declared BLIND reason stays


def test_a_panel_blind_as_a_whole_keeps_only_a_declared_reason():
    doc = document()
    assert doc["panels"]["pickup"]["kind"] == "BLIND"
    assert redact.redact(doc)["panels"]["pickup"]["reason"] == redact.LAN_ONLY


def test_a_field_the_table_does_not_name_is_dropped():
    doc = {**document(), SENTINEL: SENTINEL}
    doc["panels"]["hazards"][SENTINEL] = SENTINEL
    assert SENTINEL not in json.dumps(redact.redact(doc))


def test_the_remote_listener_serves_only_the_redacted_document():
    latest = Latest()
    latest.document = seeded()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler(latest, redact.redact))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        for path in ("/", "/v1.json", "/v1.txt"):
            connection = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=5)
            connection.request("GET", path)
            response = connection.getresponse()
            assert response.status == 200 and SENTINEL not in response.read().decode()
    finally:
        httpd.shutdown()
