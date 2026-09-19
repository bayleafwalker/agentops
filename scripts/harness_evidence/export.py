"""Post a batch built by `spans`/`metrics` to an OTLP/HTTP collector.

Stdlib only (`urllib`, `json` via the batch dicts already being JSON-shaped),
per scope. Fail-open, per `docs/architecture/harness-evidence-policy.md`'s
"Fail-open posture": every request runs with a short, bounded timeout, and a
timeout, connection failure or non-2xx response is swallowed rather than
raised -- an exporter on this path must never change a hook's exit code.

`$OTEL_EXPORTER_OTLP_ENDPOINT` unset means "no telemetry is enabled" and
`export()` returns having performed **no I/O of any kind** -- it does not
even construct a `urllib.request.Request`. That is the behaviour
`test_harness_evidence_export.py` monkeypatches `urllib.request.urlopen` to
verify.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

_DEFAULT_TIMEOUT_SECONDS = 5.0


def _headers_from_env(raw: str) -> dict[str, str]:
    """Parse `$OTEL_EXPORTER_OTLP_HEADERS`'s `key1=value1,key2=value2` shape."""
    headers: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        key, _, value = pair.partition("=")
        key = key.strip()
        if key:
            headers[key] = value.strip()
    return headers


def _post(url: str, body: dict[str, Any], headers: dict[str, str], timeout: float) -> None:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    request.add_header("Content-Type", "application/json")
    for key, value in headers.items():
        request.add_header(key, value)
    try:
        urllib.request.urlopen(request, timeout=timeout)
    except (urllib.error.URLError, OSError, ValueError):
        # Fail-open: a broken collector must never raise through to the caller.
        return


def export(batch: dict[str, Any], *, timeout: float = _DEFAULT_TIMEOUT_SECONDS) -> None:
    """Post `batch["spans"]` to `/v1/traces` and `batch["metrics"]` to `/v1/metrics`.

    `batch` is `{"spans": [<build_session_span() result>, ...], "metrics":
    [<build_rate_limit_gauges() result>, ...]}`; either key may be absent or
    empty. When `$OTEL_EXPORTER_OTLP_ENDPOINT` is unset this returns
    immediately and performs no I/O -- not even a DNS lookup.
    """
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return
    endpoint = endpoint.rstrip("/")
    headers = _headers_from_env(os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", ""))

    for span_batch in batch.get("spans") or []:
        _post(f"{endpoint}/v1/traces", span_batch, headers, timeout)
    for metric_batch in batch.get("metrics") or []:
        _post(f"{endpoint}/v1/metrics", metric_batch, headers, timeout)
