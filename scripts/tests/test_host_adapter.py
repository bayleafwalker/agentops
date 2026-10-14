"""Oracle for the host adapter (roadmap M2b).

The adapter's one hard promise is that an ambiguous launch is never turned into a
second launch. Everything else here protects the steps that make that promise
checkable: a record is committed before each external act, a decision has one
winner, and policy and cancellation are looked at again immediately before launch.

The owner and the harness are fakes. The owner fake implements the contract's
receipt rules (already-decided, not-accepted, run-already-linked, already-resulted,
replay by field digest); the harness fake counts creates and prompts. Crashes are
injected through the adapter's `checkpoint` hook, which raises a BaseException so
the adapter's own error handling cannot swallow it.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import host_adapter as ha  # noqa: E402

REPO = "agentops"
SENDER = "iss:workstation:1"
ME = "iss:devbox:1"
NOW = 1_800_000_000.0


class Crash(BaseException):
    pass


# ---------------------------------------------------------------- fakes

class FakeOwner:
    """Contract semantics for the operations the adapter uses."""

    def __init__(self) -> None:
        self.messages: dict[str, dict] = {}
        self.receipts: dict[str, list[dict]] = {}
        self.runs: dict[str, tuple[str, str]] = {}  # key -> (digest, run_id)
        self.instance_principal: dict[str, str] = {}
        self.observations: list[dict] = []
        self.seq = 0
        self.run_register_calls = 0
        self.calls: list[tuple[str, str]] = []
        self.register_conflict = False
        self.fail_once: set[str] = set()   # receipt kinds that raise a transport error once
        self.fail_messages: set[str] = set()  # message ids whose receipts always raise
        self.no_run_id = False

    # test helpers
    def send(self, mid: str = "msg_A", *, sender: str = SENDER, kind: str = "continue", pred: str | None = "run_P",
             not_after: str | None = None, instance: str | None = None, text: str = "please continue") -> str:
        self.seq += 1
        context = {"item_id": "item_1"}
        if pred:
            context["predecessor_run_id"] = pred
        recipient: dict = {"principal_id": ME}
        if instance:
            recipient["instance_id"] = instance
        env = {"schema": "agent-message/v1", "message_id": mid, "recipient": recipient, "kind": kind,
               "mode": "request", "context": context, "body": {"text": text}, "sender_principal_id": sender,
               "repo_id": REPO, "inbox_seq": self.seq}
        if not_after:
            env["not_after"] = not_after
        self.messages[mid] = env
        self.receipts[mid] = []
        return mid

    def cancel(self, mid: str) -> None:
        self.receipts[mid].append({"kind": "cancel-requested", "principal_id": SENDER, "reason": "stop"})

    def kinds(self, mid: str) -> list[str]:
        return [r["kind"] for r in self.receipts[mid]]

    def receipt_of(self, mid: str, kind: str) -> dict | None:
        return next((r for r in self.receipts[mid] if r["kind"] == kind), None)

    # port
    def agent_register(self, repo, *, instance_id, declaration, idempotency_key):
        self.instance_principal.setdefault(instance_id, ME)
        return {"ok": True}

    def agent_observe(self, repo, *, instance_id, fact, valid_for_seconds, idempotency_key, channel=None, run_id=None):
        self.observations.append({"instance_id": instance_id, "fact": fact, "valid": valid_for_seconds,
                                  "channel": channel, "run_id": run_id})
        return {"ok": True}

    def message_read(self, repo, *, after_seq, limit, instance_id):
        out = [copy.deepcopy(dict(m, receipts=self.receipts[m["message_id"]]))
               for m in sorted(self.messages.values(), key=lambda m: m["inbox_seq"])
               if m["inbox_seq"] > after_seq
               and m["recipient"].get("instance_id") in (None, instance_id)][:limit]
        return {"messages": out, "next_after_seq": out[-1]["inbox_seq"] if out else after_seq}

    def message_status(self, repo, *, message_id):
        return {"message": self.messages[message_id], "receipts": copy.deepcopy(self.receipts[message_id])}

    def message_receipt(self, repo, *, message_id, instance_id, kind, **fields):
        self.calls.append((message_id, kind))
        if message_id in self.fail_messages:
            raise RuntimeError("boom")
        if kind in self.fail_once:
            self.fail_once.discard(kind)
            raise ha.OwnerError("transport", "injected")
        rs = self.receipts[message_id]
        mine = lambda k: next((r for r in rs if r["kind"] == k and r["instance_id"] == instance_id), None)  # noqa: E731
        rec = {"kind": kind, "instance_id": instance_id, "principal_id": ME, **fields}

        def replay(existing):
            return dict(existing, replayed=True)

        if kind in ("observed", "acknowledged"):
            return replay(mine(kind)) if mine(kind) else self._add(rs, rec)
        if kind in ("accepted", "refused"):
            decided = next((r for r in rs if r["kind"] in ("accepted", "refused")), None)
            if decided:
                if decided["instance_id"] == instance_id and decided["kind"] == kind and decided.get("reason") == fields.get("reason"):
                    return replay(decided)
                raise ha.OwnerError("already-decided", f"decided by {decided['instance_id']} as {decided['kind']}")
            return self._add(rs, rec)
        if kind == "run-linked":
            acc = next((r for r in rs if r["kind"] == "accepted" and r["instance_id"] == instance_id), None)
            if not acc:
                raise ha.OwnerError("not-accepted")
            linked = next((r for r in rs if r["kind"] == "run-linked"), None)
            if linked:
                if linked["run_id"] == fields["run_id"]:
                    return replay(linked)
                raise ha.OwnerError("run-already-linked")
            return self._add(rs, rec)
        if kind == "launch-ambiguous":
            if not mine("accepted"):
                raise ha.OwnerError("not-accepted", "needs accepted")
            return replay(mine(kind)) if mine(kind) else self._add(rs, rec)
        if kind == "result-linked":
            outcome = fields["outcome"]
            if outcome in ("completed", "failed", "canceled") and not mine("run-linked"):
                raise ha.OwnerError("not-accepted", "needs run-linked")
            if not mine("accepted"):
                raise ha.OwnerError("not-accepted")
            if outcome == "not-started" and "reason" not in fields:
                raise ha.OwnerError("invalid-arguments")
            existing = next((r for r in rs if r["kind"] == "result-linked"), None)
            if existing:
                same = ha.canonical({k: existing[k] for k in fields}) == ha.canonical(fields)
                if same:
                    return replay(existing)
                raise ha.OwnerError("already-resulted")
            return self._add(rs, rec)
        raise ha.OwnerError("invalid-arguments", kind)

    @staticmethod
    def _add(rs, rec):
        rs.append(rec)
        return dict(rec, replayed=False)

    def run_register(self, repo, arguments):
        self.run_register_calls += 1
        if self.no_run_id:
            return {"repo_id": repo, "run": {}}
        key = arguments["idempotency_key"]
        digest = ha.canonical(arguments)
        if key in self.runs:
            if self.runs[key][0] != digest or self.register_conflict:
                raise ha.OwnerError("idempotency-conflict", "configuration changed")
            return {"repo_id": repo, "run": {"run_id": self.runs[key][1]}}
        run_id = ha.new_ulid("run")
        self.runs[key] = (digest, run_id)
        return {"repo_id": repo, "run": {"run_id": run_id}}


class FakeHarness:
    def __init__(self) -> None:
        self.sessions: dict[str, dict] = {}
        self.creates = 0
        self.prompts: list[tuple[str, str]] = []
        self.aborts: list[str] = []
        self.healthy = True
        self.hide_search = False
        self.finish_on_poll = True  # a prompted session is complete when next observed
        self.fail_with: str | None = None
        self.note_text = ""
        self.manual_start = False  # a prompted session does not become busy until start() is called

    def health(self):
        return self.healthy

    def create_session(self, title, directory):
        self.creates += 1
        sid = f"ses_{self.creates:04d}"
        self.sessions[sid] = {"title": title, "messages": 0, "aborted": False, "started": False}
        return sid

    def find_sessions(self, title, directory):
        if self.hide_search:
            return []
        return [sid for sid, s in self.sessions.items() if s["title"] == title]

    def send_prompt(self, sid, text, directory, model):
        self.prompts.append((sid, text))
        self.sessions[sid]["messages"] = 1  # the user message; the assistant message comes with start
        self.sessions[sid]["started"] = not self.manual_start

    def start(self):
        for s in self.sessions.values():
            s["started"] = s["messages"] > 0

    def session_state(self, sid, directory):
        s = self.sessions[sid]
        if s["aborted"]:
            return ha.SessionState(busy=False, message_count=s["messages"], assistant_completed=True,
                                   error="MessageAbortedError")
        if not s["started"]:
            return ha.SessionState(busy=False, message_count=s["messages"])
        if s["messages"] and self.finish_on_poll:
            return ha.SessionState(busy=False, message_count=s["messages"], assistant_completed=not self.fail_with,
                                   error=self.fail_with, text=self.note_text)
        return ha.SessionState(busy=bool(s["messages"]), message_count=s["messages"])

    def abort(self, sid, directory):
        self.aborts.append(sid)
        s = self.sessions[sid]
        if s["started"] and not self.finish_on_poll:  # a no-op before the session is busy or after it ended
            s["aborted"] = True


# ---------------------------------------------------------------- fixtures

def write_policy(path: Path, **over) -> None:
    pol = {"enabled": True, "launches_enabled": True, "allowed_senders": [SENDER], "allowed_repos": [REPO],
           "kinds": ["continue"], "max_concurrent": 2,
           "harness": {"harness_id": "opencode", "harness_build": "1.19.0", "model_id": "prov/model",
                       "recipe_id": "inbox-continue-v1", "observed_profile": {"sandbox": "none"}}}
    pol.update(over)
    path.write_text(json.dumps(pol))


class Rig:
    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.owner, self.harness = FakeOwner(), FakeHarness()
        self.policy = tmp / "policy.json"
        write_policy(self.policy)
        self.now = NOW
        self.checkpoint = None
        self.adapter: ha.Adapter | None = None
        self.boot()

    def boot(self) -> ha.Adapter:
        if self.adapter:
            self.adapter.state.close()
        state = ha.State(self.tmp / "state", clock=lambda: self.now)
        self.adapter = ha.Adapter(
            owner=self.owner, harness=self.harness, state=state, policy_path=self.policy,
            config=ha.Config(poll_interval=10, directory="/work"), clock=lambda: self.now,
            checkpoint=lambda name: self.checkpoint(name) if self.checkpoint else None, log=lambda m: None)
        return self.adapter

    def tick(self, n: int = 1) -> None:
        for _ in range(n):
            self.adapter.tick()

    def rec(self, mid: str = "msg_A"):
        return self.adapter.state.get(REPO, mid)

    def crash_at(self, step: str) -> None:
        def hook(name):
            if name == step:
                self.checkpoint = None
                raise Crash(step)
        self.checkpoint = hook


@pytest.fixture
def rig(tmp_path):
    r = Rig(tmp_path)
    yield r
    r.adapter.state.close()


# ---------------------------------------------------------------- happy path

def test_happy_path_launches_once_and_records_the_chain(rig):
    rig.owner.send()
    rig.tick(2)
    rec = rig.rec()
    assert (rec["state"], rec["outcome"], rec["closed"]) == (ha.S_FINISHED, "completed", 1)
    assert rig.owner.kinds("msg_A") == ["observed", "acknowledged", "accepted", "run-linked", "result-linked"]
    res = rig.owner.receipt_of("msg_A", "result-linked")
    assert res["evidence_refs"] == [{"kind": "run", "ref": rec["run_id"]},
                                    {"kind": "harness-session", "ref": "ses_0001"}]
    assert rig.harness.sessions["ses_0001"]["title"] == "vuoro-msg:msg_A"
    assert rig.harness.creates == 1 and len(rig.harness.prompts) == 1
    # register-v1 arguments come from policy verbatim; key and predecessor from the envelope
    args = json.loads(rig.owner.runs["inbox.msg_A"][0])
    assert args == {"harness_id": "opencode", "harness_build": "1.19.0", "model_id": "prov/model",
                    "recipe_id": "inbox-continue-v1", "observed_profile": {"sandbox": "none"},
                    "idempotency_key": "inbox.msg_A", "predecessor_run_id": "run_P"}


def test_launch_prompt_is_deterministic_and_names_the_sprintctl_verbs(rig):
    rig.owner.send()
    rig.tick(2)
    env = json.loads(rig.rec()["envelope"])
    prompt = rig.harness.prompts[0][1]
    run_id = rig.rec()["run_id"]
    assert prompt == ha.build_prompt(env, run_id)
    assert f"sprintctl run context --run-id {run_id}" in prompt
    assert f"sprintctl run note --run-id {run_id}" in prompt and "--idempotency-key inbox.msg_A.note" in prompt


def test_observations_carry_valid_for_three_poll_intervals(rig):
    rig.tick()
    facts = {(o["fact"], o["channel"]) for o in rig.owner.observations}
    assert ("observed", None) in facts and ("reachable", "opencode-serve") in facts
    assert {o["valid"] for o in rig.owner.observations} == {30}
    rig.harness.healthy = False
    rig.owner.observations.clear()
    rig.tick()
    assert [o["fact"] for o in rig.owner.observations] == ["observed"]  # no reachable without a health check


def test_session_note_is_linked_when_discoverable(rig):
    rig.harness.note_text = "wrote note_01ABCDEFGH ok"
    rig.owner.send()
    rig.tick(2)
    refs = rig.owner.receipt_of("msg_A", "result-linked")["evidence_refs"]
    assert {"kind": "session-note", "ref": "note_01ABCDEFGH"} in refs


def test_failed_session_records_failed(rig):
    rig.harness.fail_with = "APIError"
    rig.owner.send()
    rig.tick(2)
    assert rig.owner.receipt_of("msg_A", "result-linked")["outcome"] == "failed"


# ---------------------------------------------------------------- duplicates

def test_duplicate_delivery_yields_one_record_one_run_one_launch(rig):
    rig.owner.send()
    rig.tick(2)
    rig.adapter.state.db.execute("DELETE FROM cursors")  # reader replays from 0
    rig.tick(2)
    rig.boot()
    rig.adapter.state.db.execute("DELETE FROM cursors")
    rig.tick(2)
    assert len(rig.adapter.state.all_records()) == 1
    assert rig.owner.run_register_calls == 1 and rig.harness.creates == 1


def test_instance_id_is_minted_once_and_survives_restart(rig):
    first = rig.adapter.instance_id
    assert first.startswith("ins_") and len(first) == 30
    assert rig.boot().instance_id == first


def test_one_adapter_per_state_dir(rig):
    with pytest.raises(ha.StateLocked):
        ha.State(rig.tmp / "state")


# ---------------------------------------------------------------- authorization

@pytest.mark.parametrize("over,send,code", [
    ({"allowed_senders": []}, {}, "sender-not-allowed"),
    ({"allowed_repos": ["other"]}, {}, "repo-not-allowed"),
    ({"kinds": []}, {}, "kind-not-allowed"),
    ({"launches_enabled": False}, {}, "launches-disabled"),
    ({}, {"not_after": "2020-01-01T00:00:00Z"}, "sender-validity-elapsed"),
    ({}, {"instance": "ins_01ARZ3NDEKTSV4RRFFQ69G5FAV"}, "recipient-mismatch"),
])
def test_refusals_carry_reason_codes_and_launch_nothing(rig, over, send, code):
    write_policy(rig.policy, **over)
    rig.owner.send(**send)
    if over.get("allowed_repos"):  # polled repo list changes: poll the repo the message lives in
        rig.adapter.state.ingest(REPO, [rig.owner.message_read(REPO, after_seq=0, limit=5, instance_id=None)["messages"][0]], 1)
    elif "instance" in send:
        rig.adapter.state.ingest(REPO, [rig.owner.message_read(REPO, after_seq=0, limit=5, instance_id=send["instance"])["messages"][0]], 1)
    rig.tick(2)
    refusal = rig.owner.receipt_of("msg_A", "refused")
    assert refusal and refusal["reason"]["code"] == code
    assert rig.harness.creates == 0 and rig.owner.run_register_calls == 0
    assert rig.rec()["closed"] == 1


def test_missing_policy_fails_closed(rig):
    rig.policy.unlink()
    rig.owner.send()
    rig.tick(2)
    assert rig.harness.creates == 0 and rig.adapter.state.all_records() == []


# ---------------------------------------------------------------- policy and cancel races

def test_policy_revoked_between_accept_and_launch_closes_not_started(rig):
    rig.owner.send()
    revoke_after = "run_linked_sent"

    def hook(name):
        if name == revoke_after:
            write_policy(rig.policy, allowed_senders=[])
    rig.checkpoint = hook
    rig.tick(2)
    res = rig.owner.receipt_of("msg_A", "result-linked")
    assert res["outcome"] == "not-started" and res["reason"]["code"] == "sender-not-allowed"
    assert rig.harness.creates == 0 and rig.rec()["state"] == ha.S_NOT_STARTED


def test_cancel_before_decision_refuses_canceled_by_sender(rig):
    rig.owner.send()
    rig.owner.cancel("msg_A")
    rig.tick(2)
    assert rig.owner.receipt_of("msg_A", "refused")["reason"]["code"] == "canceled-by-sender"
    assert "accepted" not in rig.owner.kinds("msg_A") and rig.harness.creates == 0


def test_cancel_after_accept_before_launch_closes_not_started(rig):
    rig.owner.send()
    rig.checkpoint = lambda name: rig.owner.cancel("msg_A") if name == "run_linked_sent" else None
    rig.tick(2)
    res = rig.owner.receipt_of("msg_A", "result-linked")
    assert res["outcome"] == "not-started" and res["reason"]["code"] == "canceled-by-sender"
    assert rig.harness.creates == 0


def test_cancel_after_launch_aborts_and_records_canceled(rig):
    rig.harness.finish_on_poll = False
    rig.owner.send()
    rig.tick()
    assert rig.rec()["state"] == ha.S_LAUNCHED and rig.harness.aborts == []
    rig.owner.cancel("msg_A")
    rig.tick()
    assert rig.harness.aborts == ["ses_0001"]
    assert rig.owner.receipt_of("msg_A", "result-linked")["outcome"] == "canceled"
    assert rig.owner.receipt_of("msg_A", "accepted") and rig.owner.receipt_of("msg_A", "run-linked")


def test_second_instance_loses_the_decision(rig):
    rig.owner.send()
    rig.owner.receipts["msg_A"].append({"kind": "accepted", "instance_id": "ins_OTHER", "principal_id": ME})
    rig.tick(2)
    assert rig.rec()["state"] == ha.S_LOST and rig.rec()["closed"] == 1
    assert rig.owner.run_register_calls == 0 and rig.harness.creates == 0
    assert "ins_OTHER" in rig.rec()["detail"]


def test_max_concurrent_defers_the_second_launch(rig):
    write_policy(rig.policy, max_concurrent=1)
    rig.harness.finish_on_poll = False
    rig.owner.send("msg_A")
    rig.owner.send("msg_B")
    rig.tick()
    assert rig.harness.creates == 1 and rig.rec("msg_B")["state"] == ha.S_RUN_REGISTERED
    rig.harness.finish_on_poll = True
    rig.tick(3)
    assert rig.harness.creates == 2


# ---------------------------------------------------------------- crash recovery

STEPS_BEFORE_INTENT = ["ingested", "decided_persisted", "acknowledged_sent", "accepted_sent",
                       "run_registered_persisted", "run_linked_sent"]
STEPS_AFTER_CREATE = ["launched_persisted", "prompt_sent", "finished_persisted", "closed"]


@pytest.mark.parametrize("step", STEPS_BEFORE_INTENT + STEPS_AFTER_CREATE)
def test_crash_at_any_persisted_step_resumes_with_exactly_one_launch(rig, step):
    rig.owner.send()
    rig.crash_at(step)
    with pytest.raises(Crash):
        rig.tick(3)
    rig.boot()
    rig.tick(4)
    assert rig.harness.creates == 1 and len(rig.harness.prompts) == 1
    assert rig.rec()["outcome"] == "completed" and rig.rec()["closed"] == 1
    assert rig.owner.run_register_calls == 1 and len(rig.owner.runs) == 1


def test_crash_after_intent_before_create_is_ambiguous_not_relaunched(rig):
    rig.owner.send()
    rig.crash_at("launch_intent_persisted")
    with pytest.raises(Crash):
        rig.tick()
    rig.boot()
    rig.tick(3)
    assert rig.harness.creates == 0
    assert rig.rec()["state"] == ha.S_AMBIGUOUS
    assert rig.owner.receipt_of("msg_A", "launch-ambiguous")


def test_crash_after_create_before_session_id_is_adopted_by_title_search(rig):
    rig.owner.send()
    rig.crash_at("session_created")
    with pytest.raises(Crash):
        rig.tick()
    assert rig.rec()["session_id"] is None and rig.harness.creates == 1
    rig.boot()
    rig.tick(3)
    assert rig.harness.creates == 1
    assert rig.rec()["session_id"] == "ses_0001" and rig.rec()["outcome"] == "completed"
    assert len(rig.harness.prompts) == 1


def test_crash_after_create_with_empty_search_is_ambiguous_with_zero_relaunches(rig):
    rig.owner.send()
    rig.crash_at("session_created")
    with pytest.raises(Crash):
        rig.tick()
    rig.harness.hide_search = True
    rig.boot()
    rig.tick(5)
    rec = rig.rec()
    assert rec["state"] == ha.S_AMBIGUOUS and rec["closed"] == 0
    assert rig.harness.creates == 1 and rig.harness.prompts == []
    amb = rig.owner.receipt_of("msg_A", "launch-ambiguous")
    assert amb and "not relaunching" in amb["detail"]
    assert rig.owner.kinds("msg_A").count("launch-ambiguous") == 1
    assert rig.owner.receipt_of("msg_A", "result-linked") is None


def test_resolve_abandon_is_the_only_way_out_and_never_launches(rig):
    rig.owner.send()
    rig.crash_at("session_created")
    with pytest.raises(Crash):
        rig.tick()
    rig.harness.hide_search = True
    rig.boot()
    rig.tick(2)
    rig.adapter.resolve_abandon("msg_A")
    res = rig.owner.receipt_of("msg_A", "result-linked")
    assert res["outcome"] == "abandoned" and rig.rec()["closed"] == 1
    rig.tick(3)
    assert rig.harness.creates == 1
    with pytest.raises(SystemExit):
        rig.adapter.resolve_abandon("msg_A")  # no longer ambiguous


def test_prompt_is_not_sent_twice_when_session_already_has_messages(rig):
    rig.owner.send()
    rig.crash_at("launched_persisted")
    with pytest.raises(Crash):
        rig.tick()
    rig.harness.sessions["ses_0001"].update(messages=1, started=True)  # prompt landed just before the crash
    rig.boot()
    rig.tick(3)
    assert rig.harness.prompts == [] and rig.rec()["outcome"] == "completed"


def test_run_registration_conflict_is_ambiguous_and_mints_no_new_key(rig):
    rig.owner.send()
    rig.crash_at("accepted_sent")
    with pytest.raises(Crash):
        rig.tick()
    write_policy(rig.policy, harness={"harness_id": "opencode", "harness_build": "2.0", "model_id": "m",
                                      "recipe_id": "r", "observed_profile": {}})
    rig.owner.runs["inbox.msg_A"] = ("different", "run_X")
    rig.boot()
    rig.tick(3)
    assert rig.rec()["state"] == ha.S_AMBIGUOUS and "conflict" in rig.rec()["detail"]
    amb = rig.owner.receipt_of("msg_A", "launch-ambiguous")
    assert amb and "run_id" not in amb and rig.rec()["ambiguous_sent"] == 1
    assert list(rig.owner.runs) == ["inbox.msg_A"] and rig.harness.creates == 0


def test_status_rows_include_ambiguous(rig):
    rig.owner.send()
    rig.crash_at("launch_intent_persisted")
    with pytest.raises(Crash):
        rig.tick()
    rig.boot()
    rig.tick(2)
    ro = ha.State(rig.tmp / "state", read_only=True)  # status does not take the adapter lock
    assert [r["state"] for r in ha._status_rows(ro)] == ["ambiguous"]
    ro.close()


# ---------------------------------------------------------------- OpenCodeServe wire shape

def test_opencode_serve_speaks_the_verified_endpoints():
    import http.server
    import threading
    import urllib.parse

    seen = []

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body):
            raw = b"" if body is None else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("content-length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _handle(self):
            u = urllib.parse.urlsplit(self.path)
            n = int(self.headers.get("content-length") or 0)
            body = json.loads(self.rfile.read(n)) if n else None
            seen.append((self.command, u.path, dict(urllib.parse.parse_qsl(u.query)), body))
            if u.path == "/global/health":
                return self._send(200, {"healthy": True, "version": "1.19.0"})
            if (self.command, u.path) == ("POST", "/session"):
                return self._send(200, {"id": "ses_x", "title": body["title"]})
            if (self.command, u.path) == ("GET", "/session"):
                return self._send(200, [{"id": "ses_x", "title": "vuoro-msg:msg_A"},
                                        {"id": "ses_y", "title": "vuoro-msg:msg_AB"}])
            if u.path.endswith("/prompt_async"):
                return self._send(204, None)
            if u.path == "/session/status":
                return self._send(200, {"ses_x": {"type": "busy"}})
            if u.path.endswith("/message"):
                return self._send(200, [{"info": {"role": "assistant", "time": {"created": 1, "completed": 2},
                                                  "error": {"name": "APIError"}},
                                         "parts": [{"type": "text", "text": "hi"}]}])
            if u.path.endswith("/abort"):
                return self._send(200, True)
            return self._send(404, None)

        do_GET = do_POST = _handle

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        oc = ha.OpenCodeServe(f"http://127.0.0.1:{srv.server_address[1]}")
        assert oc.health()
        assert oc.create_session("vuoro-msg:msg_A", "/work") == "ses_x"
        assert oc.find_sessions("vuoro-msg:msg_A", "/work") == ["ses_x"]  # exact title, not substring
        oc.send_prompt("ses_x", "go", "/work", "prov/model")
        st = oc.session_state("ses_x", "/work")
        assert st.busy and st.assistant_completed and st.error == "APIError" and st.text == "hi"
        oc.abort("ses_x", "/work")
    finally:
        srv.shutdown()
    by = {(m, p): (q, b) for m, p, q, b in seen}
    assert by[("POST", "/session")] == ({"directory": "/work"}, {"title": "vuoro-msg:msg_A"})
    assert by[("GET", "/session")][0] == {"directory": "/work", "search": "vuoro-msg:msg_A", "limit": "100"}
    assert by[("POST", "/session/ses_x/prompt_async")][1] == {
        "parts": [{"type": "text", "text": "go"}], "model": {"providerID": "prov", "modelID": "model"}}
    assert ("POST", "/session/ses_x/abort") in by


def test_opencode_serve_refuses_a_non_loopback_url():
    with pytest.raises(ValueError):
        ha.OpenCodeServe("http://10.0.0.5:4096")


def test_health_is_false_when_the_server_is_down():
    assert ha.OpenCodeServe("http://127.0.0.1:1", timeout=0.5).health() is False


# ---------------------------------------------------------------- review round: abort, robustness, receipts

def test_abort_before_busy_is_a_noop_so_it_is_repeated_while_busy(rig):
    rig.harness.finish_on_poll = False
    rig.harness.manual_start = True
    rig.owner.send()
    rig.tick()
    rig.owner.cancel("msg_A")
    rig.tick()
    assert len(rig.harness.aborts) == 1 and rig.rec()["closed"] == 0  # no-op abort, no evidence: not canceled yet
    rig.harness.start()
    rig.tick()
    assert len(rig.harness.aborts) == 2
    assert rig.owner.receipt_of("msg_A", "result-linked")["outcome"] == "canceled"


def test_cancel_that_loses_the_race_records_what_actually_happened(rig):
    rig.owner.send()
    rig.checkpoint = lambda name: rig.owner.cancel("msg_A") if name == "prompt_sent" else None
    rig.tick(3)
    assert rig.owner.receipt_of("msg_A", "result-linked")["outcome"] == "completed"


def test_cancel_of_a_session_that_never_starts_is_canceled_after_a_grace_tick(rig):
    rig.harness.manual_start = True
    rig.owner.send()
    rig.tick()
    rig.owner.cancel("msg_A")
    rig.tick()
    assert rig.rec()["closed"] == 0
    rig.tick()
    assert rig.owner.receipt_of("msg_A", "result-linked")["outcome"] == "canceled"


def test_crash_after_abort_sent_resumes_to_canceled(rig):
    rig.harness.finish_on_poll = False
    rig.owner.send()
    rig.tick()
    rig.owner.cancel("msg_A")
    rig.crash_at("abort_sent")
    with pytest.raises(Crash):
        rig.tick()
    rig.boot()
    rig.tick(2)
    assert rig.owner.receipt_of("msg_A", "result-linked")["outcome"] == "canceled" and rig.harness.creates == 1


def test_crash_after_not_started_persisted_still_writes_the_result_once(rig):
    write_policy(rig.policy, allowed_senders=[])
    rig.owner.send()
    rig.crash_at("not_started_persisted")
    # accept needs the sender allowed at decision time, so revoke only after run-linked
    write_policy(rig.policy)
    orig = rig.checkpoint

    def hook(name):
        if name == "run_linked_sent":
            write_policy(rig.policy, allowed_senders=[])
        orig(name)
    rig.checkpoint = hook
    with pytest.raises(Crash):
        rig.tick(2)
    rig.boot()
    rig.tick(2)
    assert rig.owner.kinds("msg_A").count("result-linked") == 1 and rig.harness.creates == 0
    assert rig.rec()["state"] == ha.S_NOT_STARTED and rig.rec()["closed"] == 1


def test_crash_while_adopting_is_recoverable(rig):
    rig.owner.send()
    rig.crash_at("session_created")
    with pytest.raises(Crash):
        rig.tick()
    rig.boot()
    rig.crash_at("adopted_persisted")
    with pytest.raises(Crash):
        rig.tick()
    rig.boot()
    rig.tick(3)
    assert rig.harness.creates == 1 and rig.rec()["outcome"] == "completed"


def test_crash_after_ambiguous_persisted_still_sends_launch_ambiguous(rig):
    rig.owner.send()
    rig.crash_at("launch_intent_persisted")
    with pytest.raises(Crash):
        rig.tick()
    rig.boot()
    rig.crash_at("ambiguous_persisted")
    with pytest.raises(Crash):
        rig.tick()
    assert rig.owner.receipt_of("msg_A", "launch-ambiguous") is None
    rig.boot()
    rig.tick(2)
    assert rig.owner.kinds("msg_A").count("launch-ambiguous") == 1 and rig.harness.creates == 0


def test_one_failing_record_does_not_stop_the_others(rig):
    rig.owner.send("msg_A")
    rig.owner.send("msg_B")
    rig.owner.fail_messages.add("msg_A")
    rig.tick(3)
    assert rig.rec("msg_B")["outcome"] == "completed"
    assert "RuntimeError" in rig.rec("msg_A")["last_error"] and rig.rec("msg_A")["closed"] == 0


def test_vuoro_client_errors_without_a_code_become_transport_errors():
    import asyncio

    class Client:
        def __init__(self, exc):
            self.exc = exc

        async def invoke(self, *a, **k):
            raise self.exc

    class Coded(Exception):
        code = "already-decided"

    for exc, code in ((ConnectionError("down"), "transport"), (Coded("x"), "already-decided")):
        o = ha.VuoroOwner("unused")
        o._client, o._loop = Client(exc), asyncio.new_event_loop()
        with pytest.raises(ha.OwnerError) as ei:
            o.message_status(REPO, message_id="msg_A")
        assert ei.value.code == code
        o._loop.close()


@pytest.mark.parametrize("value", ["tomorrow", "2030-01-01T00:00:00", 12])
def test_malformed_or_offsetless_not_after_is_refused(rig, value):
    rig.owner.send(not_after=value)
    rig.tick(2)
    assert rig.owner.receipt_of("msg_A", "refused")["reason"]["code"] == "invalid-not-after"
    assert rig.harness.creates == 0


def test_a_valid_future_not_after_is_honoured(rig):
    rig.owner.send(not_after="2999-01-01T00:00:00Z")
    rig.tick(2)
    assert rig.rec()["outcome"] == "completed"


def test_refusal_that_loses_to_another_instances_decision_is_lost_decision(rig):
    write_policy(rig.policy, allowed_senders=[])
    rig.owner.send()
    rig.owner.receipts["msg_A"].append({"kind": "accepted", "instance_id": "ins_OTHER", "principal_id": ME})
    rig.tick(2)
    assert rig.rec()["state"] == ha.S_LOST and rig.rec()["closed"] == 1


def test_run_already_linked_writes_launch_ambiguous_with_the_known_run(rig):
    rig.owner.send()
    me = rig.adapter.instance_id
    rig.owner.receipts["msg_A"] += [
        {"kind": "accepted", "instance_id": me, "principal_id": ME},
        {"kind": "run-linked", "instance_id": me, "principal_id": ME, "run_id": "run_OTHER"}]
    rig.tick(2)
    amb = rig.owner.receipt_of("msg_A", "launch-ambiguous")
    assert rig.rec()["state"] == ha.S_AMBIGUOUS and amb and amb["run_id"] == rig.rec()["run_id"]
    assert rig.harness.creates == 0


def test_ambiguous_is_not_marked_sent_until_the_receipt_is_written(rig):
    rig.owner.send()
    rig.crash_at("launch_intent_persisted")
    with pytest.raises(Crash):
        rig.tick()
    rig.boot()
    rig.owner.fail_once.add("launch-ambiguous")
    rig.tick()
    assert rig.rec()["state"] == ha.S_AMBIGUOUS and rig.rec()["ambiguous_sent"] == 0
    rig.tick()
    assert rig.rec()["ambiguous_sent"] == 1 and rig.owner.receipt_of("msg_A", "launch-ambiguous")


def test_an_unresolved_ambiguous_run_counts_toward_max_concurrent(rig):
    write_policy(rig.policy, max_concurrent=1)
    rig.owner.send("msg_A")
    rig.crash_at("launch_intent_persisted")
    with pytest.raises(Crash):
        rig.tick()
    rig.boot()
    rig.owner.send("msg_B")
    rig.tick(3)
    assert rig.rec("msg_A")["state"] == ha.S_AMBIGUOUS
    assert rig.harness.creates == 0 and rig.rec("msg_B")["state"] == ha.S_RUN_REGISTERED


def test_a_run_registration_without_run_id_is_an_error_and_persists_nothing(rig):
    rig.owner.no_run_id = True
    rig.owner.send()
    rig.tick()
    assert rig.rec()["state"] == ha.S_DECIDED and rig.rec()["run_id"] is None
    assert "invalid-result" in rig.rec()["last_error"]


@pytest.mark.parametrize("payload", ["<html>not json</html>", "{}"])
def test_unexpected_harness_responses_are_harness_errors(payload):
    import http.server
    import threading

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _go(self):
            raw = payload.encode()
            self.send_response(200)
            self.send_header("content-length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        do_GET = do_POST = _go

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        oc = ha.OpenCodeServe(f"http://127.0.0.1:{srv.server_address[1]}")
        for call in (lambda: oc.create_session("t", "/w"), lambda: oc.session_state("ses_x", "/w")):
            with pytest.raises(ha.HarnessError):
                call()
        assert oc.health() is False
    finally:
        srv.shutdown()
