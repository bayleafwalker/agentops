"""The Jev client is safe to call from a shadow path.

Fake mode must work with no key and no network. Live mode retries only the two
statuses TypeSafe documents as transient (429 rate limit, 529 overload), fails fast
on everything else, and never lets the key reach an error message.
"""

from __future__ import annotations

import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jev_client  # noqa: E402

KEY = "ts-secret-key-value"
QUESTIONS = {
    "pick": {"type": "choice", "instructions": "x", "criteria": {"a": "A", "b": "B"}},
    "yes": {"type": "noul", "instructions": "y"},
    "grade": {"type": "score", "instructions": "z", "criteria": ["low", "mid", "high"]},
}


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _http_error(status: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(jev_client.ENDPOINT, status, "err", {}, io.BytesIO(b"{}"))


def _opener(*outcomes):
    calls = []

    def opener(request, timeout):
        calls.append(request)
        outcome = outcomes[len(calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return _Response(json.dumps(outcome).encode("utf-8"))

    opener.calls = calls
    return opener


LIVE_BODY = {
    "model": "jev-1.13.0",
    "answers": {"pick": {"type": "choice", "choice": "b", "probabilities": {"a": 0.2, "b": 0.8}, "confidence": 0.7}},
    "usage": {"input_tokens": 10, "output_tokens": 2},
}


def test_absent_key_file_means_fake_mode(tmp_path, monkeypatch):
    monkeypatch.setenv(jev_client.KEY_FILE_ENV, str(tmp_path / "missing"))
    assert jev_client.load_key() is None

    def no_network(*args, **kwargs):
        raise AssertionError("fake mode must not open a connection")

    result = jev_client.system_one({"s": 1}, QUESTIONS, model="jev-latest", opener=no_network)
    assert result["mode"] == "fake"
    assert result["answers"]["pick"]["choice"] == "a"
    assert result["answers"]["pick"]["confidence"] == 0.0
    assert result["answers"]["yes"]["noul"] == 0.5
    assert result["answers"]["grade"]["score"] == 1.0


def test_key_is_read_from_file(tmp_path, monkeypatch):
    key_file = tmp_path / "api-key"
    key_file.write_text(f"{KEY}\n", encoding="utf-8")
    monkeypatch.setenv(jev_client.KEY_FILE_ENV, str(key_file))
    assert jev_client.load_key() == KEY


def test_live_call_sends_bearer_and_returns_answers():
    opener = _opener(LIVE_BODY)
    result = jev_client.system_one({"s": 1}, QUESTIONS, model="jev-latest", key=KEY, opener=opener)
    assert result["mode"] == "live"
    assert result["model"] == "jev-1.13.0"
    assert result["answers"]["pick"]["choice"] == "b"
    request = opener.calls[0]
    assert request.get_header("Authorization") == f"Bearer {KEY}"
    assert json.loads(request.data)["model"] == "jev-latest"


@pytest.mark.parametrize("status", [429, 529])
def test_transient_statuses_are_retried(status):
    sleeps = []
    opener = _opener(_http_error(status), LIVE_BODY)
    result = jev_client.system_one({}, QUESTIONS, model="m", key=KEY, opener=opener, sleep=sleeps.append)
    assert result["mode"] == "live"
    assert len(opener.calls) == 2
    assert sleeps == [0.5]


def test_retries_are_bounded():
    opener = _opener(*[_http_error(529)] * jev_client.MAX_ATTEMPTS)
    with pytest.raises(jev_client.JevError) as raised:
        jev_client.system_one({}, QUESTIONS, model="m", key=KEY, opener=opener, sleep=lambda _: None)
    assert raised.value.status == 529
    assert len(opener.calls) == jev_client.MAX_ATTEMPTS


@pytest.mark.parametrize("status", [401, 422, 500])
def test_other_statuses_fail_fast_without_leaking_the_key(status):
    opener = _opener(_http_error(status), LIVE_BODY)
    with pytest.raises(jev_client.JevError) as raised:
        jev_client.system_one({}, QUESTIONS, model="m", key=KEY, opener=opener, sleep=lambda _: None)
    assert len(opener.calls) == 1
    assert raised.value.status == status
    assert KEY not in str(raised.value)
    assert KEY not in repr(raised.value)
    assert raised.value.__cause__ is None


def test_unreachable_service_is_a_jev_error():
    opener = _opener(urllib.error.URLError("down"))
    with pytest.raises(jev_client.JevError):
        jev_client.system_one({}, QUESTIONS, model="m", key=KEY, opener=opener)


def test_response_without_answers_is_rejected():
    with pytest.raises(jev_client.JevError):
        jev_client.system_one({}, QUESTIONS, model="m", key=KEY, opener=_opener({"model": "m"}))


@pytest.mark.parametrize("name", ["route-v1", "verify-v1"])
def test_committed_bundles_load_with_a_stable_hash(name):
    first = jev_client.load_bundle(name)
    second = jev_client.load_bundle(name)
    assert first["bundle_id"] == name
    assert len(first["bundle_sha256"]) == 64
    assert first["bundle_sha256"] == second["bundle_sha256"]


@pytest.mark.parametrize("name", ["route-v1", "verify-v1"])
def test_every_choice_offers_a_no_match_answer(name):
    bundle = jev_client.load_bundle(name)
    no_match = {"needs_planning", "insufficient_evidence", "needs_clarification"}
    for key, question in bundle["questions"].items():
        if question["type"] == "choice":
            assert no_match & set(question["criteria"]), key
            assert len(question["criteria"]) <= 255


def test_bundle_hash_changes_with_the_questions(tmp_path):
    bundle = json.loads((jev_client.BUNDLE_DIR / "route-v1.json").read_text(encoding="utf-8"))
    original = tmp_path / "a.json"
    original.write_text(json.dumps(bundle), encoding="utf-8")
    bundle["questions"]["tier"]["instructions"] += " Changed."
    changed = tmp_path / "b.json"
    changed.write_text(json.dumps(bundle), encoding="utf-8")
    assert jev_client.load_bundle(original)["bundle_sha256"] != jev_client.load_bundle(changed)["bundle_sha256"]


@pytest.mark.parametrize("content", [f"{KEY}\r\nsecond-line", f"{KEY} # comment", f"{KEY}\x00", "ключ"])
def test_malformed_key_file_falls_back_to_fake_mode(tmp_path, monkeypatch, content, capsys):
    key_file = tmp_path / "api-key"
    key_file.write_text(content, encoding="utf-8")
    monkeypatch.setenv(jev_client.KEY_FILE_ENV, str(key_file))
    assert jev_client.load_key() is None
    assert KEY not in capsys.readouterr().err


def test_unexpected_request_errors_never_quote_the_key():
    def opener(request, timeout):
        raise ValueError(f"Invalid header value b'Bearer {KEY}'")

    with pytest.raises(jev_client.JevError) as raised:
        jev_client.system_one({}, QUESTIONS, model="m", key=KEY, opener=opener)
    assert KEY not in str(raised.value)
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__
