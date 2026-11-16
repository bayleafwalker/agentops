"""Fixed-origin, bounded Hindsight transport. No redirects or fallback routes."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from urllib.parse import quote

from .policy import Policy, canonical


class UpstreamError(RuntimeError):
    """An uncertain upstream result; credentials and response bodies stay private."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise UpstreamError("upstream redirect refused")


class HindsightClient:
    def __init__(self, policy: Policy):
        self.policy = policy
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, method: str, bank: str, suffix: str, payload: dict | None = None) -> dict:
        # bank and suffix originate in trusted facade code, never caller paths.
        url = self.policy.upstream_url + "/v1/default/banks/" + quote(bank, safe="") + suffix
        token = self.policy.upstream_token_file.read_text().strip()
        if not token or "\n" in token or "\r" in token:
            raise UpstreamError("invalid upstream credential")
        request = urllib.request.Request(url, data=canonical(payload) if payload is not None else None,
                                         headers={"Authorization": "Bearer " + token,
                                                  "Content-Type": "application/json"}, method=method)
        try:
            with self.opener.open(request, timeout=20) as response:
                body = response.read(2097153)
            if len(body) > 2097152:
                raise UpstreamError("upstream response exceeds bound")
            value = json.loads(body)
            if not isinstance(value, dict):
                raise UpstreamError("invalid upstream response")
            return value
        except (OSError, ValueError, urllib.error.URLError) as exc:
            raise UpstreamError("upstream request failed") from None

    def retain(self, bank: str, payload: dict) -> dict:
        return self.request("POST", bank, "/memories", payload)

    def operation(self, bank: str, operation_id: str) -> dict:
        return self.request("GET", bank, "/operations/" + quote(operation_id, safe=""))

    def recall(self, bank: str, query: str, tags: list[str]) -> dict:
        return self.request("POST", bank, "/memories/recall", {
            "query": query, "budget": "low", "max_tokens": 4096, "trace": False,
            "types": ["world", "experience", "observation"],
            "tags": tags, "tags_match": "all_strict",
            "include": {"entities": None, "chunks": None,
                        "source_facts": {"max_tokens": 8192, "max_tokens_per_observation": -1}},
        })
