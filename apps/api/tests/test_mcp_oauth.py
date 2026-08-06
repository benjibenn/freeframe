"""Security tests for MCP OAuth, with Freeframe as the authorization server.

Tokens are opaque rows rather than JWTs, so these exercise the lookup path:
revocation, expiry, audience binding, and the admin check that runs on every
request rather than only at consent.

The end-to-end flow (authorize → consent → token → refresh → replay) needs a real
Postgres and is covered separately; see test_mcp_oauth_flow.py.
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from apps.api.models.oauth import hash_secret, verify_code_challenge
from apps.api.services import mcp_oauth
from apps.api.services.mcp_oauth import MCPAuthError

RESOURCE = "https://freeframe.multiadsx.com/api/mcp/"
OTHER_TENANT = "https://review.debugged.com.my/api/mcp/"


@pytest.fixture(autouse=True)
def oauth_settings():
    with patch("apps.api.services.mcp_oauth.settings") as s:
        s.mcp_oauth_enabled = True
        s.mcp_oauth_issuer_url = "https://freeframe.multiadsx.com/api"
        s.mcp_canonical_resource = RESOURCE
        s.mcp_resource_metadata_url = (
            "https://freeframe.multiadsx.com/api/.well-known/oauth-protected-resource"
        )
        yield s


def _user(admin=True, deactivated=False):
    from apps.api.models.user import UserStatus

    u = MagicMock()
    u.id = uuid.uuid4()
    u.is_superadmin = admin
    u.is_subadmin = False
    u.deleted_at = None
    u.status = UserStatus.deactivated if deactivated else UserStatus.active
    return u


def _row(user_id, *, resource=RESOURCE, revoked=False, expired=False, scopes=None):
    r = MagicMock()
    r.user_id = user_id
    r.resource = resource
    r.revoked_at = datetime.now(timezone.utc) if revoked else None
    r.expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=-60 if expired else 3600
    )
    r.scopes = scopes if scopes is not None else ["briefs:read", "briefs:write"]
    return r


def _db(token_row, user):
    """A mock session returning the token row first, then the user."""
    db = MagicMock()
    db.query.return_value = db
    db.filter.return_value = db
    db.first.side_effect = [token_row, user]
    return db


# ── Happy path ───────────────────────────────────────────────────────────────

def test_a_live_token_resolves_to_its_user_and_scopes():
    u = _user()
    user, scopes = mcp_oauth.verify_access_token(_db(_row(u.id), u), "tok")
    assert user is u
    assert scopes == ["briefs:read", "briefs:write"]


# ── Revocation and expiry ────────────────────────────────────────────────────

def test_a_revoked_token_stops_working_immediately():
    """The reason tokens are opaque rows instead of JWTs.

    A JWT can only be revoked via a blocklist — which is this table with extra
    steps, plus a window where the revoked token still works.
    """
    u = _user()
    with pytest.raises(MCPAuthError, match="revoked"):
        mcp_oauth.verify_access_token(_db(_row(u.id, revoked=True), u), "tok")


def test_an_expired_token_is_rejected():
    u = _user()
    with pytest.raises(MCPAuthError, match="expired"):
        mcp_oauth.verify_access_token(_db(_row(u.id, expired=True), u), "tok")


def test_an_unknown_token_is_rejected():
    db = MagicMock()
    db.query.return_value = db
    db.filter.return_value = db
    db.first.return_value = None
    with pytest.raises(MCPAuthError, match="Unknown access token"):
        mcp_oauth.verify_access_token(db, "nope")


# ── Audience binding ─────────────────────────────────────────────────────────

def test_a_token_minted_for_the_other_tenant_is_rejected():
    """Both tenants run this same code off the same branch.

    Without this check a token issued at client current would be spendable at
    MultiAdsX — the "access token privilege restriction" failure the MCP security
    guidance names. Because Freeframe now issues the token, it also sets the
    audience, which is what Authentik could not do.
    """
    u = _user()
    with pytest.raises(MCPAuthError, match="not this server"):
        mcp_oauth.verify_access_token(_db(_row(u.id, resource=OTHER_TENANT), u), "tok")


# ── Authorisation is re-checked per request ──────────────────────────────────

def test_rights_revoked_after_issuance_take_effect_immediately():
    """Admin status is checked on every call, not just at consent.

    Otherwise demoting someone would leave their connector working until the
    token happened to expire.
    """
    u = _user(admin=False)
    with pytest.raises(MCPAuthError, match="admin rights"):
        mcp_oauth.verify_access_token(_db(_row(u.id), u), "tok")


def test_a_deactivated_account_stops_working_immediately():
    u = _user(deactivated=True)
    with pytest.raises(MCPAuthError, match="deactivated"):
        mcp_oauth.verify_access_token(_db(_row(u.id), u), "tok")


def test_a_deleted_user_is_rejected():
    u = _user()
    db = MagicMock()
    db.query.return_value = db
    db.filter.return_value = db
    db.first.side_effect = [_row(u.id), None]  # token found, user gone
    with pytest.raises(MCPAuthError, match="no longer exists"):
        mcp_oauth.verify_access_token(db, "tok")


# ── PKCE ─────────────────────────────────────────────────────────────────────

def test_pkce_s256_round_trips_and_rejects_a_wrong_verifier():
    import base64
    import hashlib
    import secrets

    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    assert verify_code_challenge(verifier, challenge) is True
    assert verify_code_challenge("not-the-verifier", challenge) is False


def test_secrets_are_stored_only_as_hashes():
    """A database dump must not hand over usable credentials."""
    raw = "ffmcp_example_secret"
    assert hash_secret(raw) != raw
    assert len(hash_secret(raw)) == 64


# ── Metadata and the 401 challenge ───────────────────────────────────────────

def test_protected_resource_metadata_points_at_our_own_issuer():
    md = mcp_oauth.protected_resource_metadata()
    assert md["resource"] == RESOURCE
    assert md["authorization_servers"] == ["https://freeframe.multiadsx.com/api"]
    assert md["scopes_supported"] == ["briefs:read", "briefs:write"]


def test_www_authenticate_points_at_the_metadata_document():
    """Without this a client never learns where the authorization server is, and
    the connection fails with nothing reaching the issuer at all."""
    h = mcp_oauth.www_authenticate_header(scope="briefs:read briefs:write")
    assert h.startswith("Bearer ")
    assert 'resource_metadata="https://freeframe.multiadsx.com/api/.well-known/oauth-protected-resource"' in h
    assert 'scope="briefs:read briefs:write"' in h


# ── Router-level scope enforcement ───────────────────────────────────────────

def test_an_api_key_is_unscoped_and_keeps_full_access():
    """Scope enforcement must not quietly demote the credential already in use.

    None means "not scope-limited" and is deliberately distinct from [], which is
    a token granted nothing.
    """
    from apps.api.routers import mcp as mcp_router

    tok = mcp_router._current_scopes.set(None)
    try:
        mcp_router._require_scope(mcp_router.SCOPE_WRITE)
    finally:
        mcp_router._current_scopes.reset(tok)


def test_a_read_only_token_cannot_reach_a_write_tool():
    from apps.api.routers import mcp as mcp_router

    tok = mcp_router._current_scopes.set([mcp_router.SCOPE_READ])
    try:
        mcp_router._require_scope(mcp_router.SCOPE_READ)
        with pytest.raises(ValueError, match="missing the briefs:write scope"):
            mcp_router._require_scope(mcp_router.SCOPE_WRITE)
    finally:
        mcp_router._current_scopes.reset(tok)


def test_a_token_granted_nothing_reaches_no_tool():
    from apps.api.routers import mcp as mcp_router

    tok = mcp_router._current_scopes.set([])
    try:
        with pytest.raises(ValueError, match="no scopes"):
            mcp_router._require_scope(mcp_router.SCOPE_READ)
    finally:
        mcp_router._current_scopes.reset(tok)
