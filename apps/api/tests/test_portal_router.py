"""GET /portal/apps: auth-gated, returns tiles, fails loud, never leaks the token."""
import httpx
import pytest

from apps.api.main import app
from apps.api.middleware.auth import get_current_user
from apps.api.services import portal_service
from apps.api.config import settings


@pytest.fixture
def portal_on(monkeypatch):
    monkeypatch.setattr(settings, "authentik_api_base", "https://sso.test", raising=False)
    monkeypatch.setattr(settings, "authentik_service_token", "svc-secret-tok", raising=False)


def test_requires_auth(client):
    resp = client.get("/portal/apps")
    assert resp.status_code in (401, 403)


def test_returns_tiles(client, test_user, portal_on, monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: test_user
    monkeypatch.setattr(
        portal_service, "get_apps_for_email",
        lambda email: [{"slug": "freeframe", "name": "FreeFrame",
                        "launch_url": "https://review.x", "description": "Review", "icon": None}],
    )
    resp = client.get("/portal/apps")
    app.dependency_overrides.pop(get_current_user, None)
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"apps": [{"slug": "freeframe", "name": "FreeFrame",
                              "launch_url": "https://review.x", "description": "Review", "icon": None}]}
    assert "svc-secret-tok" not in resp.text


def test_empty_when_no_apps(client, test_user, portal_on, monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: test_user
    monkeypatch.setattr(portal_service, "get_apps_for_email", lambda email: [])
    resp = client.get("/portal/apps")
    app.dependency_overrides.pop(get_current_user, None)
    assert resp.status_code == 200
    assert resp.json() == {"apps": []}


def test_authentik_down_is_502_not_default_list(client, test_user, portal_on, monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: test_user
    def boom(email):
        raise httpx.ConnectError("down", request=httpx.Request("GET", "https://sso.test"))
    monkeypatch.setattr(portal_service, "get_apps_for_email", boom)
    resp = client.get("/portal/apps")
    app.dependency_overrides.pop(get_current_user, None)
    assert resp.status_code == 502


def test_503_when_portal_unconfigured(client, test_user, monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: test_user
    monkeypatch.setattr(settings, "authentik_api_base", None, raising=False)
    monkeypatch.setattr(settings, "authentik_service_token", None, raising=False)
    resp = client.get("/portal/apps")
    app.dependency_overrides.pop(get_current_user, None)
    assert resp.status_code == 503
