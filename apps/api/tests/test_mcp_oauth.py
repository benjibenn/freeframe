"""Security tests for the MCP OAuth resource-server path.

These sign real RS256 tokens against a generated key and let the verifier do its
actual work. Mocking verify_bearer would leave the audience and expiry checks —
the two things standing between the tenants — completely untested.
"""
import base64
import time
import uuid
from unittest.mock import MagicMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt

from apps.api.services import mcp_oauth
from apps.api.services.mcp_oauth import MCPAuthError

ISSUER = "https://sso.example.test/application/o/freeframe"
RESOURCE = "https://freeframe.multiadsx.com/api/mcp/"
OTHER_TENANT = "https://review.debugged.com.my/api/mcp/"


def _b64u(n: int) -> str:
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


@pytest.fixture(scope="module")
def keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = key.public_key().public_numbers()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    jwks = {
        "keys": [{
            "kty": "RSA",
            "kid": "test-key",
            "use": "sig",
            "alg": "RS256",
            "n": _b64u(pub.n),
            "e": _b64u(pub.e),
        }]
    }
    return pem, jwks


@pytest.fixture(autouse=True)
def oauth_settings():
    """Point the verifier at the test issuer and this tenant's canonical URL."""
    with patch("apps.api.services.mcp_oauth.settings") as s:
        s.mcp_oauth_issuer_url = ISSUER
        s.mcp_oauth_enabled = True
        s.mcp_canonical_resource = RESOURCE
        s.mcp_resource_metadata_url = (
            "https://freeframe.multiadsx.com/api/.well-known/oauth-protected-resource"
        )
        yield s


def _token(keypair, **over):
    pem, _ = keypair
    claims = {
        "iss": ISSUER,
        "aud": over.pop("aud", RESOURCE),
        "sub": "user-1",
        "email": over.pop("email", "admin@example.test"),
        "exp": over.pop("exp", int(time.time()) + 600),
        "iat": int(time.time()),
        "scope": over.pop("scope", "briefs:read briefs:write"),
    }
    claims.update(over)
    return jwt.encode(claims, pem, algorithm="RS256", headers={"kid": "test-key"})


@pytest.fixture
def verify(keypair):
    _, jwks = keypair
    with patch.object(mcp_oauth, "get_jwks", return_value=jwks):
        yield


# ── Audience binding ─────────────────────────────────────────────────────────

def test_a_token_for_this_tenant_verifies(keypair, verify):
    claims = mcp_oauth.verify_bearer(_token(keypair))
    assert claims["email"] == "admin@example.test"


def test_a_token_minted_for_the_other_tenant_is_rejected(keypair, verify):
    """The whole reason audience binding is enforced.

    Both tenants run this same code off the same branch. Without this check, a
    token issued for client current would be spendable at MultiAdsX — the
    "access token privilege restriction" failure the MCP security guidance names.
    """
    with pytest.raises(MCPAuthError, match="audience does not include this server"):
        mcp_oauth.verify_bearer(_token(keypair, aud=OTHER_TENANT))


def test_a_token_with_no_audience_is_rejected(keypair, verify):
    with pytest.raises(MCPAuthError, match="audience"):
        mcp_oauth.verify_bearer(_token(keypair, aud=None))


def test_an_audience_list_containing_this_server_is_accepted(keypair, verify):
    """IdPs legitimately issue multi-audience tokens; only presence matters."""
    claims = mcp_oauth.verify_bearer(_token(keypair, aud=[OTHER_TENANT, RESOURCE]))
    assert claims["sub"] == "user-1"


# ── Signature, issuer, expiry ────────────────────────────────────────────────

def test_an_expired_token_is_rejected(keypair, verify):
    with pytest.raises(MCPAuthError):
        mcp_oauth.verify_bearer(_token(keypair, exp=int(time.time()) - 60))


def test_a_token_from_another_issuer_is_rejected(keypair, verify):
    with pytest.raises(MCPAuthError):
        mcp_oauth.verify_bearer(_token(keypair, iss="https://evil.example.test"))


def test_a_tampered_token_is_rejected(keypair, verify):
    tok = _token(keypair)
    head, payload, sig = tok.split(".")
    with pytest.raises(MCPAuthError, match="Invalid token"):
        mcp_oauth.verify_bearer(f"{head}.{payload}.{sig[:-4]}AAAA")


# ── Claims to user ───────────────────────────────────────────────────────────

def _user(email="admin@example.test", admin=True, deactivated=False):
    from apps.api.models.user import UserStatus

    u = MagicMock()
    u.id = uuid.uuid4()
    u.email = email
    u.is_superadmin = admin
    u.is_subadmin = False
    u.deleted_at = None
    u.status = UserStatus.deactivated if deactivated else UserStatus.active
    return u


def test_an_unknown_email_does_not_provision_an_account(mock_db):
    """Unlike the SSO login flow, which creates users on first sign-in.

    A token good enough to call tools is not evidence anyone intended to create a
    Freeframe account, and auto-provisioning here would let anyone the IdP trusts
    become an admin-adjacent user.
    """
    mock_db.first.return_value = None
    with pytest.raises(MCPAuthError, match="No Freeframe user"):
        mcp_oauth.resolve_token_user(mock_db, {"email": "stranger@example.test"})


def test_a_token_without_an_email_claim_is_rejected(mock_db):
    with pytest.raises(MCPAuthError, match="no email claim"):
        mcp_oauth.resolve_token_user(mock_db, {"sub": "abc"})


def test_a_non_admin_user_is_rejected(mock_db):
    mock_db.first.return_value = _user(admin=False)
    with pytest.raises(MCPAuthError, match="admin rights"):
        mcp_oauth.resolve_token_user(mock_db, {"email": "someone@example.test"})


def test_a_deactivated_user_is_rejected(mock_db):
    mock_db.first.return_value = _user(deactivated=True)
    with pytest.raises(MCPAuthError, match="deactivated"):
        mcp_oauth.resolve_token_user(mock_db, {"email": "admin@example.test"})


def test_an_active_admin_resolves(mock_db):
    u = _user()
    mock_db.first.return_value = u
    assert mcp_oauth.resolve_token_user(mock_db, {"email": "Admin@Example.Test"}) is u


# ── Scopes ───────────────────────────────────────────────────────────────────

def test_scopes_parse_from_either_shape():
    assert mcp_oauth.token_scopes({"scope": "briefs:read briefs:write"}) == [
        "briefs:read",
        "briefs:write",
    ]
    assert mcp_oauth.token_scopes({"scp": ["briefs:read"]}) == ["briefs:read"]
    assert mcp_oauth.token_scopes({}) == []


# ── Metadata and the 401 challenge ───────────────────────────────────────────

def test_protected_resource_metadata_shape():
    """`resource` must equal the URL the user types in, or discovery mismatches
    in a way that is invisible from the client side."""
    md = mcp_oauth.protected_resource_metadata()
    assert md["resource"] == RESOURCE
    assert md["authorization_servers"] == [ISSUER]
    assert md["scopes_supported"] == ["briefs:read", "briefs:write"]


def test_www_authenticate_points_at_the_metadata_document():
    """The most commonly missed requirement: without this a client never learns
    where the authorization server is, and nothing reaches the issuer at all."""
    h = mcp_oauth.www_authenticate_header(scope="briefs:read briefs:write")
    assert h.startswith("Bearer ")
    assert 'resource_metadata="https://freeframe.multiadsx.com/api/.well-known/oauth-protected-resource"' in h
    assert 'scope="briefs:read briefs:write"' in h


# ── Router-level scope enforcement ───────────────────────────────────────────

def test_an_api_key_is_unscoped_and_keeps_full_access():
    """Scope enforcement must not quietly demote the credential already in use.

    None means "not scope-limited" and is deliberately different from [], which is
    a token that was granted nothing.
    """
    from apps.api.routers import mcp as mcp_router

    tok = mcp_router._current_scopes.set(None)
    try:
        mcp_router._require_scope(mcp_router.SCOPE_WRITE)  # must not raise
    finally:
        mcp_router._current_scopes.reset(tok)


def test_a_read_only_token_cannot_reach_a_write_tool():
    from apps.api.routers import mcp as mcp_router

    tok = mcp_router._current_scopes.set([mcp_router.SCOPE_READ])
    try:
        mcp_router._require_scope(mcp_router.SCOPE_READ)  # allowed
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
