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

from pydantic import AnyHttpUrl
from sqlalchemy.orm import Session

from ..config import settings
from ..models.oauth import OAuthToken, hash_secret, json_list
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


def verify_access_token(db: Session, raw_token: str) -> tuple[User, list[str]]:
    """Resolve an opaque access token to its user and scopes.

    Opaque, not a JWT, so revocation is real: a revoked row stops working on the
    next request rather than when some short expiry catches up.

    Audience binding has no override. Both tenants run this same code, so without
    it a token minted for one would be spendable at the other — the "access token
    privilege restriction" failure the MCP security guidance names.
    """
    row = (
        db.query(OAuthToken)
        .filter(OAuthToken.token_hash == hash_secret(raw_token), OAuthToken.kind == "access")
        .first()
    )
    if row is None:
        raise MCPAuthError("Unknown access token")
    if row.revoked_at is not None:
        raise MCPAuthError("This token has been revoked")
    if row.expires_at <= datetime.now(timezone.utc):
        raise MCPAuthError("Token has expired")

    resource = settings.mcp_canonical_resource
    if row.resource and row.resource != resource:
        raise MCPAuthError(
            f"Token was issued for {row.resource}, not this server ({resource})"
        )

    user = (
        db.query(User)
        .filter(User.id == row.user_id, User.deleted_at.is_(None))
        .first()
    )
    if user is None:
        raise MCPAuthError("The user this token was issued to no longer exists")
    if user.status == UserStatus.deactivated:
        raise MCPAuthError("This account is deactivated")
    # Checked per request, not just at consent: rights revoked after a token was
    # issued must take effect immediately, not at expiry.
    if not is_platform_admin(user):
        raise MCPAuthError("Managing requests needs admin rights")
    return user, json_list(row.scopes)


def protected_resource_metadata() -> dict[str, Any]:
    """The RFC 9728 document.

    Served unauthenticated, by requirement. `resource` must equal the URL the user
    typed into the client exactly — path and trailing slash included — or discovery
    fails with a mismatch that is invisible from the client side.
    """
    return {
        "resource": settings.mcp_canonical_resource,
        # Normalised through AnyHttpUrl, the same type create_auth_routes renders
        # the AS document's `issuer` from. The two strings must be byte-identical
        # or a client treats it as a different authorization server; matching them
        # by construction avoids a trailing slash silently breaking discovery.
        "authorization_servers": [str(AnyHttpUrl(settings.mcp_oauth_issuer_url))],
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
