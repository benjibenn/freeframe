"""portal_service maps email->pk->apps via Authentik, caches per-email, fails loud."""
import json
import httpx
import pytest

from apps.api.services import portal_service as ps
from apps.api.config import settings


class FakeRedis:
    def __init__(self):
        self.store = {}
        self.setex_calls = 0

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, val):
        self.setex_calls += 1
        self.store[key] = val


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(settings, "authentik_api_base", "https://sso.test", raising=False)
    monkeypatch.setattr(settings, "authentik_service_token", "svc-tok", raising=False)
    fake = FakeRedis()
    monkeypatch.setattr(ps, "get_redis", lambda: fake)
    return fake


def _mock_httpx(monkeypatch, users_results, apps_results):
    calls = {"count": 0, "headers": []}

    def fake_get(url, params=None, headers=None, timeout=None):
        calls["count"] += 1
        calls["headers"].append(headers or {})
        if "/users/" in url:
            body = {"results": users_results}
        else:
            assert params and "for_user" in params
            body = {"results": apps_results}
        return httpx.Response(200, json=body, request=httpx.Request("GET", url))

    monkeypatch.setattr(ps.httpx, "get", fake_get)
    return calls


def test_maps_email_to_tiles(configured, monkeypatch):
    calls = _mock_httpx(
        monkeypatch,
        users_results=[{"pk": 7, "email": "a@b.com"}],
        apps_results=[
            {"slug": "freeframe", "name": "FreeFrame",
             "meta_launch_url": "https://review.x", "meta_description": "Review", "meta_icon": None},
            {"slug": "noluncher", "name": "X", "meta_launch_url": "", "meta_description": ""},
        ],
    )
    tiles = ps.get_apps_for_email("a@b.com")
    assert tiles == [
        {"slug": "freeframe", "name": "FreeFrame",
         "launch_url": "https://review.x", "description": "Review", "icon": None}
    ]
    assert calls["headers"][0]["Authorization"] == "Bearer svc-tok"


def test_unknown_email_returns_empty(configured, monkeypatch):
    _mock_httpx(monkeypatch, users_results=[], apps_results=[])
    assert ps.get_apps_for_email("nobody@b.com") == []


def test_second_call_is_cached(configured, monkeypatch):
    calls = _mock_httpx(monkeypatch, users_results=[{"pk": 7}], apps_results=[])
    ps.get_apps_for_email("a@b.com")
    first = calls["count"]
    ps.get_apps_for_email("a@b.com")
    assert calls["count"] == first


def test_authentik_error_propagates(configured, monkeypatch):
    def boom(url, params=None, headers=None, timeout=None):
        raise httpx.ConnectError("down", request=httpx.Request("GET", url))
    monkeypatch.setattr(ps.httpx, "get", boom)
    with pytest.raises(httpx.HTTPError):
        ps.get_apps_for_email("a@b.com")


def test_email_is_lowercased_for_lookup_and_cache(configured, monkeypatch):
    # Authentik stores canonical lowercase email; the user record reflects that.
    calls = _mock_httpx(monkeypatch, users_results=[{"pk": 7, "email": "a@b.com"}], apps_results=[])
    ps.get_apps_for_email("A@B.com")
    after_first = calls["count"]
    # Same address, different case -> must hit the SAME cache entry (no new HTTP calls)
    ps.get_apps_for_email("a@b.com")
    assert calls["count"] == after_first


def test_resolve_picks_exact_email_match(configured, monkeypatch):
    # Defensive: if Authentik ever returns a near-miss alongside the exact match,
    # we must resolve the pk of the EXACT (case-insensitive) email, not results[0].
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        if "/users/" in url:
            body = {"results": [
                {"pk": 99, "email": "joe@x.com.my"},  # near-miss, first in list
                {"pk": 7, "email": "joe@x.com"},       # the real one
            ]}
        else:
            captured["for_user"] = params["for_user"]
            body = {"results": []}
        return httpx.Response(200, json=body, request=httpx.Request("GET", url))

    monkeypatch.setattr(ps.httpx, "get", fake_get)
    ps.get_apps_for_email("joe@x.com")
    assert captured["for_user"] == 7  # not 99
