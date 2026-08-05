"""OAuth resource-server support for the MCP endpoint.

Freeframe validates tokens; it does not issue them. Running an authorization
server means owning consent screens, PKCE, an authorization-code store, refresh
rotation and replay detection — and in practice almost no MCP server does that.
The common pattern is to delegate to an IdP and implement only this half: verify
the token, publish RFC 9728 metadata, and return a conformant 401.

Nothing here is required for API-key auth, which remains the default. When no
issuer is configured every function short-circuits and the MCP endpoint behaves
exactly as it did before.
"""
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from ..config import settings
from ..models.user import User, UserStatus
from ..services.permissions import is_platform_admin

# Read scopes cover the tools that only report; write scopes cover the four that
# change something. A read-only connector is a reasonable thing to want, and the
# tools split cleanly along that line.
SCOPE_READ = "briefs:read"
SCOPE_WRITE = "briefs:write"
SUPPORTED_SCOPES = [SCOPE_READ, SCOPE_WRITE]

# An issuer's discovery document and signing keys are stable, so cache per issuer.
# Keyed by issuer rather than global because the MCP issuer may differ from the
# SSO one, and verifying against the wrong JWKS would fail confusingly.
_discovery_cache: dict[str, dict] = {}
_jwks_cache: dict[str, dict] = {}


class MCPAuthError(Exception):
    """Raised for any token that must not be honoured. Carries no detail from the
    token itself — error strings reach the caller, and tokens do not belong there."""


def _issuer() -> str:
    issuer = settings.mcp_oauth_issuer_url
    if not issuer:
        raise MCPAuthError("OAuth is not configured on this server")
    return issuer.rstrip("/")


def get_discovery() -> dict:
    issuer = _issuer()
    if issuer not in _discovery_cache:
        # Try OIDC discovery first: Authentik and most IdPs serve it, and it
        # carries jwks_uri either way. RFC 8414 is the OAuth-only fallback.
        last: Exception | None = None
        for suffix in ("/.well-known/openid-configuration", "/.well-known/oauth-authorization-server"):
            try:
                resp = httpx.get(issuer + suffix, timeout=10.0)
                resp.raise_for_status()
                _discovery_cache[issuer] = resp.json()
                break
            except Exception as exc:  # noqa: BLE001 - try the next well-known path
                last = exc
        else:
            raise MCPAuthError(f"Could not read issuer metadata: {last}")
    return _discovery_cache[issuer]


def get_jwks() -> dict:
    issuer = _issuer()
    if issuer not in _jwks_cache:
        jwks_uri = get_discovery().get("jwks_uri")
        if not jwks_uri:
            raise MCPAuthError("Issuer metadata has no jwks_uri")
        resp = httpx.get(jwks_uri, timeout=10.0)
        resp.raise_for_status()
        _jwks_cache[issuer] = resp.json()
    return _jwks_cache[issuer]


def _audiences(claims: dict[str, Any]) -> list[str]:
    aud = claims.get("aud")
    if isinstance(aud, str):
        return [aud]
    if isinstance(aud, list):
        return [str(a) for a in aud]
    return []


def verify_bearer(token: str) -> dict[str, Any]:
    """Validate a Bearer token and return its claims.

    Audience validation is not optional and has no override. Both tenants run this
    same code, so without it a token minted for one would be spendable at the
    other — the "access token privilege restriction" failure the MCP security
    guidance calls out by name. It requires the issuer to honour RFC 8707 resource
    indicators; if it does not, the right fix is at the issuer, not a weakened
    check here.
    """
    resource = settings.mcp_canonical_resource
    try:
        claims = jwt.decode(
            token,
            get_jwks(),
            algorithms=["RS256", "RS512", "ES256"],
            issuer=_issuer(),
            # Checked explicitly below so the failure names the audience problem
            # rather than surfacing as a generic signature error.
            options={"verify_aud": False},
        )
    except JWTError as exc:
        raise MCPAuthError(f"Invalid token: {exc}") from exc

    if resource not in _audiences(claims):
        raise MCPAuthError(
            "Token audience does not include this server "
            f"({resource}) — the client must request it as the resource"
        )

    exp = claims.get("exp")
    if exp is None or datetime.fromtimestamp(exp, tz=timezone.utc) <= datetime.now(timezone.utc):
        raise MCPAuthError("Token has expired")

    return claims


def token_scopes(claims: dict[str, Any]) -> list[str]:
    """Scopes from either shape IdPs use: space-delimited `scope`, or `scp` list."""
    raw = claims.get("scope")
    if isinstance(raw, str):
        return [s for s in raw.split() if s]
    scp = claims.get("scp")
    if isinstance(scp, list):
        return [str(s) for s in scp]
    return []


def resolve_token_user(db: Session, claims: dict[str, Any]) -> User:
    """Map verified claims onto an existing Freeframe user.

    Deliberately does not create users, unlike the SSO login flow: a token good
    enough to call tools is not evidence anyone intended to provision an account.
    Admin rights are checked here for the same reason as in resolve_api_key_user —
    a non-admin would otherwise fail twice, in two unrelated places.
    """
    email = (claims.get("email") or "").lower().strip()
    if not email:
        raise MCPAuthError("Token has no email claim, so it cannot be mapped to a user")

    user = (
        db.query(User)
        .filter(User.email == email, User.deleted_at.is_(None))
        .first()
    )
    if user is None:
        raise MCPAuthError(f"No Freeframe user for {email}")
    if user.status == UserStatus.deactivated:
        raise MCPAuthError("This account is deactivated")
    if not is_platform_admin(user):
        raise MCPAuthError("Managing requests needs admin rights")
    return user


def protected_resource_metadata() -> dict[str, Any]:
    """The RFC 9728 document.

    Served unauthenticated, by requirement. `resource` must equal the URL the user
    typed into the client exactly — path and trailing slash included — or discovery
    fails with a mismatch that is invisible from the client side.
    """
    return {
        "resource": settings.mcp_canonical_resource,
        "authorization_servers": [_issuer()] if settings.mcp_oauth_enabled else [],
        "scopes_supported": SUPPORTED_SCOPES,
        "bearer_methods_supported": ["header"],
    }


def www_authenticate_header(scope: Optional[str] = None) -> str:
    """The `WWW-Authenticate` value for a 401.

    Without this a compliant client has no way to discover where to authenticate;
    it is the single most commonly missed requirement, and it is only honoured on a
    401 — never on a 200.
    """
    parts = [f'resource_metadata="{settings.mcp_resource_metadata_url}"']
    if scope:
        parts.append(f'scope="{scope}"')
    return "Bearer " + ", ".join(parts)
