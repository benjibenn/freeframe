"""
Unit tests for the OIDC helper (no DB / network — Redis and discovery are faked).

These verify the security-relevant logic: the authorization URL carries the
right params, state+nonce are persisted, and state is single-use (replay-safe).
"""
from urllib.parse import urlparse, parse_qs

import pytest

from apps.api.services import oidc_service
from apps.api.config import settings


class FakeRedis:
    def __init__(self):
        self.store = {}

    def setex(self, key, ttl, val):
        self.store[key] = val

    def get(self, key):
        return self.store.get(key)

    def delete(self, key):
        self.store.pop(key, None)


@pytest.fixture
def oidc_configured(monkeypatch):
    monkeypatch.setattr(settings, "oidc_issuer", "https://auth.test/application/o/freeframe/", raising=False)
    monkeypatch.setattr(settings, "oidc_client_id", "freeframe", raising=False)
    monkeypatch.setattr(settings, "oidc_client_secret", "secret", raising=False)
    monkeypatch.setattr(settings, "oidc_redirect_uri", "https://app.test/api/auth/oidc/callback", raising=False)
    monkeypatch.setattr(
        oidc_service, "get_discovery",
        lambda: {
            "issuer": "https://auth.test/application/o/freeframe/",
            "authorization_endpoint": "https://auth.test/application/o/authorize/",
            "token_endpoint": "https://auth.test/application/o/token/",
            "jwks_uri": "https://auth.test/application/o/freeframe/jwks/",
        },
    )
    fake = FakeRedis()
    monkeypatch.setattr(oidc_service, "get_redis", lambda: fake)
    return fake


def test_authorization_url_has_required_params(oidc_configured):
    url, state = oidc_service.build_authorization_url()
    q = parse_qs(urlparse(url).query)

    assert q["response_type"] == ["code"]
    assert q["client_id"] == ["freeframe"]
    assert q["redirect_uri"] == ["https://app.test/api/auth/oidc/callback"]
    assert "openid" in q["scope"][0] and "email" in q["scope"][0]
    assert q["state"] == [state]
    assert q["nonce"]


def test_state_is_persisted_and_single_use(oidc_configured):
    url, state = oidc_service.build_authorization_url()
    q = parse_qs(urlparse(url).query)
    nonce = q["nonce"][0]
    assert state == q["state"][0]

    # nonce is recoverable once...
    assert oidc_service.consume_state(state) == nonce
    # ...and never again (replay protection)
    assert oidc_service.consume_state(state) is None


def test_unknown_state_returns_none(oidc_configured):
    assert oidc_service.consume_state("never-issued") is None
