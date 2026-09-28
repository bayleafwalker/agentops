#!/usr/bin/env python3
"""Minimal stdlib client for TypeSafe's System One API (Jev).

Jev answers bounded questions -- Choice, Noul (yes/no), Score -- with typed answers
and probabilities. Agentops uses it only in *shadow*: answers are logged next to the
decision the workflow actually made and never feed back into dispatch. See
``docs/dispatch/model-routing.md`` ("Jev shadow judgments").

Why stdlib rather than ``typesafe-sdk``: CI installs only ``pyyaml pytest``, and the
surface used here is one POST.

The key follows the convention bindery-core already set: a 0600 operator-owned file
named by ``TYPESAFE_API_KEY_FILE`` (default ``~/.config/typesafe/api-key``), read at
call time and never exported as a value, logged, or placed in argv. Without the file
the client runs in ``fake`` mode and returns deterministic placeholder answers, so the
whole shadow path can be exercised with no credential and no network.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
KEY_FILE_ENV = "TYPESAFE_API_KEY_FILE"
DEFAULT_KEY_FILE = Path.home() / ".config" / "typesafe" / "api-key"
RETRYABLE = (429, 529)
MAX_ATTEMPTS = 3
BUNDLE_DIR = Path(__file__).resolve().parents[1] / "jev" / "bundles"


class JevError(RuntimeError):
    """A call that did not produce answers. Never carries the key."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def key_path() -> Path:
    configured = os.environ.get(KEY_FILE_ENV)
    return Path(configured).expanduser() if configured else DEFAULT_KEY_FILE


def load_key() -> str | None:
    """The API key, or ``None`` (fake mode) when the key file is absent or empty."""
    try:
        key = key_path().read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return key or None


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def load_bundle(name_or_path: str | os.PathLike[str]) -> dict[str, Any]:
    """Load a pinned question bundle and stamp it with ``bundle_sha256``.

    The hash covers the bundle exactly as committed (model, questions, thresholds), so
    every logged answer names the precise question set that produced it.
    """
    path = Path(name_or_path)
    if not path.suffix:
        path = BUNDLE_DIR / f"{path.name}.json"
    bundle = json.loads(path.read_text(encoding="utf-8"))
    for field in ("bundle_id", "model", "questions"):
        if field not in bundle:
            raise ValueError(f"{path}: bundle is missing {field!r}")
    bundle["bundle_sha256"] = hashlib.sha256(canonical_json(bundle).encode("utf-8")).hexdigest()
    return bundle


def fake_answers(questions: dict[str, Any]) -> dict[str, Any]:
    """Deterministic placeholders: first Choice option, Noul 0.5, Score midpoint.

    Confidence is 0 throughout so a fake answer can never be mistaken for a measured one.
    """
    answers: dict[str, Any] = {}
    for key, question in questions.items():
        kind = question["type"]
        if kind == "choice":
            options = list(question["criteria"])
            answers[key] = {
                "type": "choice",
                "choice": options[0],
                "probabilities": {option: 1 / len(options) for option in options},
                "confidence": 0.0,
            }
        elif kind == "noul":
            answers[key] = {"type": "noul", "noul": 0.5}
        elif kind == "score":
            levels = len(question["criteria"])
            answers[key] = {
                "type": "score",
                "score": (levels - 1) / 2,
                "probabilities": [1 / levels] * levels,
                "confidence": 0.0,
            }
        else:
            raise ValueError(f"question {key!r} has unknown type {kind!r}")
    return answers


Opener = Callable[..., Any]


def system_one(
    state: Any,
    questions: dict[str, Any],
    *,
    model: str,
    timeout: float = 30.0,
    key: str | None = None,
    opener: Opener | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Ask ``questions`` over ``state``; returns answers plus mode, model and latency.

    ``key=None`` reads the key file; when there is none the call is answered in fake
    mode without touching the network. Retries 429/529 with backoff; 401/422 and other
    errors fail immediately with a ``JevError`` whose message never includes the key.
    """
    if key is None:
        key = load_key()
    started = time.monotonic()
    if key is None:
        return {
            "mode": "fake",
            "model": model,
            "answers": fake_answers(questions),
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "latency_ms": 0,
        }
    opener = opener or urllib.request.urlopen
    body = json.dumps({"model": model, "state": state, "questions": questions}).encode("utf-8")
    last_status: int | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        request = urllib.request.Request(
            ENDPOINT,
            data=body,
            method="POST",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        try:
            with opener(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            last_status = error.code
            if error.code in RETRYABLE and attempt < MAX_ATTEMPTS:
                sleep(0.5 * 2 ** (attempt - 1))
                continue
            raise JevError(f"System One returned HTTP {error.code}", status=error.code) from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise JevError(f"System One unreachable: {type(error).__name__}") from None
        except json.JSONDecodeError:
            raise JevError("System One returned a non-JSON body") from None
        if not isinstance(payload, dict) or not isinstance(payload.get("answers"), dict):
            raise JevError("System One response has no answers map")
        return {
            "mode": "live",
            "model": payload.get("model", model),
            "answers": payload["answers"],
            "usage": payload.get("usage") or {},
            "latency_ms": round((time.monotonic() - started) * 1000),
        }
    raise JevError(f"System One still returned HTTP {last_status} after {MAX_ATTEMPTS} attempts", status=last_status)


def ask(bundle: dict[str, Any], state: Any, **kwargs: Any) -> dict[str, Any]:
    """``system_one`` over a bundle's questions, stamped with the bundle identity."""
    result = system_one(state, bundle["questions"], model=bundle["model"], **kwargs)
    result["bundle_id"] = bundle["bundle_id"]
    result["bundle_sha256"] = bundle["bundle_sha256"]
    return result
