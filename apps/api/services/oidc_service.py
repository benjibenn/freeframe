"""
OIDC (Authentik SSO) helper.

Stateless OIDC Authorization Code flow built on the deps freeframe already
ships (httpx + python-jose). It does NOT replace freeframe's auth: the callback
router uses these helpers to verify the user's identity, then mints freeframe's
own access/refresh tokens (same as the magic-code flow).

State + nonce are held in Redis (short TTL) so no server-side session middleware
is required.
"""
from __future__ import annotations

import secrets
from typing import Optional

import httpx
from jose import jwt

from ..config import settings
from .redis_service import get_redis

# OIDC discovery document is immutable for an issuer — cache it per-process.
_discovery_cache: dict | None = None
_jwks_cache: dict | None = None

STATE_TTL_SECONDS = 600  # 10 minutes to complete the round-trip
OIDC_SCOPES = "openid email profile"


class OIDCError(Exception):
    """Raised when any step of the OIDC flow fails."""


def _state_key(state: str) -> str:
    return f"oidc:state:{state}"


def get_discovery() -> dict:
    """Fetch + cache the issuer's OpenID configuration."""
    global _discovery_cache
    if _discovery_cache is None:
        if not settings.oidc_issuer:
            raise OIDCError("OIDC is not configured")
        url = settings.oidc_issuer.rstrip("/") + "/.well-known/openid-configuration"
        resp = httpx.get(url, timeout=10.0)
        resp.raise_for_status()
        _discovery_cache = resp.json()
    return _discovery_cache


def get_jwks() -> dict:
    """Fetch + cache the issuer's JWKS (for ID-token signature verification)."""
    global _jwks_cache
    if _jwks_cache is None:
        jwks_uri = get_discovery()["jwks_uri"]
        resp = httpx.get(jwks_uri, timeout=10.0)
        resp.raise_for_status()
        _jwks_cache = resp.json()
    return _jwks_cache


def build_authorization_url() -> tuple[str, str]:
    """
    Generate a fresh state + nonce, persist them in Redis, and return
    (authorization_url, state). The caller MUST bind `state` to the initiating
    browser (HttpOnly cookie) to prevent login CSRF — see routers/oidc.py.
    """
    disc = get_discovery()
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    get_redis().setex(_state_key(state), STATE_TTL_SECONDS, nonce)

    params = {
        "response_type": "code",
        "client_id": settings.oidc_client_id,
        "redirect_uri": settings.oidc_redirect_uri,
        "scope": OIDC_SCOPES,
        "state": state,
        "nonce": nonce,
    }
    request = httpx.Request("GET", disc["authorization_endpoint"], params=params)
    return str(request.url), state


def consume_state(state: str) -> Optional[str]:
    """
    Return the nonce stored for `state` and delete it (single-use), or None if
    the state is unknown/expired (replay or CSRF protection).
    """
    if not state:
        return None
    r = get_redis()
    key = _state_key(state)
    nonce = r.get(key)
    if nonce is not None:
        r.delete(key)
    return nonce


def exchange_code(code: str) -> dict:
    """Exchange an authorization code for the token response (incl. id_token)."""
    disc = get_discovery()
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.oidc_redirect_uri,
        "client_id": settings.oidc_client_id,
        "client_secret": settings.oidc_client_secret,
    }
    resp = httpx.post(disc["token_endpoint"], data=data, timeout=10.0)
    if resp.status_code != 200:
        raise OIDCError(f"Token exchange failed: {resp.status_code} {resp.text}")
    return resp.json()


def validate_id_token(id_token: str, expected_nonce: str) -> dict:
    """
    Verify the ID token's signature (RS256 via JWKS), issuer, audience and
    nonce. Returns the validated claims. Raises OIDCError on any failure.
    """
    disc = get_discovery()
    try:
        claims = jwt.decode(
            id_token,
            get_jwks(),
            algorithms=["RS256"],
            audience=settings.oidc_client_id,
            issuer=disc["issuer"],
            options={"verify_at_hash": False},
        )
    except Exception as e:  # jose raises several subclasses; treat all as auth failure
        raise OIDCError(f"Invalid ID token: {e}") from e

    if expected_nonce and claims.get("nonce") != expected_nonce:
        raise OIDCError("Nonce mismatch")

    email = claims.get("email")
    if not email:
        raise OIDCError("ID token has no email claim")
    # We key local accounts on email, so the IdP must have verified it.
    # Without this, an unverified-email account at the IdP could be used to
    # take over a freeframe account with the same address.
    if claims.get("email_verified") is not True:
        raise OIDCError("ID token email is not verified")
    return claims


def end_session_url() -> Optional[str]:
    """RP-initiated logout URL at the IdP, if the issuer advertises one."""
    try:
        return get_discovery().get("end_session_endpoint")
    except Exception:
        return None
