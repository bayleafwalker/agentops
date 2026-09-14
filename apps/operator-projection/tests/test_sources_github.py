"""GitHubRest over a recorded, synthetic api.github.com (httpx.MockTransport)."""

import httpx
import pytest

from operator_projection.sources import GitHubRest, SourceUnavailable

SHA = "a" * 40


def github(requests: list):
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path, params = request.url.path, dict(request.url.params)
        if path == "/repos/o/private":
            return httpx.Response(404)
        if path == "/repos/o/public":
            return httpx.Response(200, json={"full_name": "o/public"})
        if path == "/repos/o/public/contents/app/config.yaml":
            if request.headers.get("if-none-match") == '"v1"':
                return httpx.Response(304)
            return httpx.Response(200, text="data: {}\n", headers={"etag": '"v1"'})
        if path.startswith("/repos/o/public/contents/"):
            return httpx.Response(404)
        if path == "/repos/o/public/commits":
            by_path = {
                "a.yaml": [{"sha": "2" * 40, "commit": {"committer": {"date": "2026-09-02T00:00:00Z"}}}],
                "b.yaml": [{"sha": "1" * 40, "commit": {"committer": {"date": "2026-09-01T00:00:00Z"}}},
                           {"sha": "2" * 40, "commit": {"committer": {"date": "2026-09-02T00:00:00Z"}}}],
            }
            if "path" in params:
                return httpx.Response(200, json=by_path[params["path"]])
            return httpx.Response(200, json=[{"sha": "1" * 40}])
        if path == "/repos/o/public/commits/main":
            return httpx.Response(200, json={"sha": SHA})
        if path == "/repos/o/limited":
            return httpx.Response(403)
        return httpx.Response(500)

    return httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler))


def rest(requests, token=None):
    return GitHubRest({"pub": "o/public", "priv": "o/private", "lim": "o/limited"}, token, client=github(requests))


def test_show_reads_raw_content_and_absent_paths_are_none():
    requests = []
    git = rest(requests, token="synthetic-token")
    assert git.show("pub", "main", "app/config.yaml") == "data: {}\n"
    assert git.show("pub", "main", "app/missing.yaml") is None
    assert requests[-1].headers["authorization"] == "Bearer synthetic-token"
    assert all(r.method == "GET" for r in requests)


def test_etag_revalidation_and_immutable_cache():
    requests = []
    git = rest(requests)
    assert git.show("pub", "main", "app/config.yaml") == git.show("pub", "main", "app/config.yaml")
    assert requests[-1].headers["if-none-match"] == '"v1"'
    count = len(requests)
    git.show("pub", SHA, "app/config.yaml")
    git.show("pub", SHA, "app/config.yaml")
    assert len(requests) == count + 1


def test_unreadable_repository_is_unavailable_not_empty():
    with pytest.raises(SourceUnavailable, match="not readable"):
        rest([]).show("priv", "main", "x")
    with pytest.raises(SourceUnavailable, match="403"):
        rest([]).show("lim", "main", "x")


def test_log_unions_paths_newest_first_and_resolve():
    git = rest([])
    assert [sha[0] for sha, _ in git.log("pub", "main", ["a.yaml", "b.yaml"])] == ["2", "1"]
    assert git.resolve("pub", "main") == SHA
    from datetime import datetime, timezone
    assert git.resolve("pub", "main", before=datetime(2026, 9, 2, tzinfo=timezone.utc)) == "1" * 40
