from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Mapping, Protocol

from .model import ContextServiceError


class ContextServiceClient(Protocol):
    def project(self, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...

    def validate_mutation(self, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...

    def observe_mutation(self, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...

    def invalidate(self, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...


class HttpContextServiceClient:
    def __init__(self, endpoint: str, *, timeout: float = 2.0) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout

    def _post(self, path: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint + path,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ContextServiceError(f"context service request failed: {exc}") from exc
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ContextServiceError("context service returned invalid JSON") from exc
        if not isinstance(value, Mapping):
            raise ContextServiceError("context service response must be an object")
        return value

    def project(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._post("/v1/agent-context/project", payload)

    def validate_mutation(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._post("/v1/agent-context/mutations/validate", payload)

    def observe_mutation(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._post("/v1/agent-context/mutations/observe", payload)

    def invalidate(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._post("/v1/agent-context/invalidate", payload)
