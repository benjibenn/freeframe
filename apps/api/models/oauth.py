"""OAuth 2.1 authorization-server storage for the MCP endpoint.

Freeframe is its own authorization server rather than delegating to an IdP: client
current has Authentik but client2.0 has none, and tenancy rules forbid pointing one
tenant at the other's SSO. Issuing our own tokens works identically on both with no
new infrastructure.

Secrets, codes and tokens are stored as SHA-256 hashes only, the same way api_keys
does it — a database dump must not hand over usable credentials.
"""
import hashlib
import secrets
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

try:
    from ..database import Base
except ImportError:
    from database import Base


CLIENT_ID_PREFIX = "ffmcp_"
# Access tokens are short-lived; a leaked one stops working within the hour. The
# refresh flow keeps that invisible to the user.
ACCESS_TOKEN_TTL_SECONDS = 3600
REFRESH_TOKEN_TTL_SECONDS = 30 * 24 * 3600
# 60s is the OAuth 2.1 recommendation. A code is single-use anyway; the short life
# limits the window for an intercepted one.
AUTHORIZATION_CODE_TTL_SECONDS = 60


def generate_secret(nbytes: int = 32) -> str:
    """Return a new plaintext secret. Shown once, never stored."""
    return secrets.token_urlsafe(nbytes)


def hash_secret(raw: str) -> str:
    """SHA-256 hex digest, for storage and lookup.

    Deliberately the same construction as api_keys.hash_api_key: these are
    high-entropy random strings, not user-chosen passwords, so a slow KDF buys
    nothing against a brute force that is already infeasible.
    """
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class OAuthClient(Base):
    """A registered MCP client (e.g. a claude.ai custom connector)."""

    __tablename__ = "oauth_clients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    # Null for public clients, which authenticate with PKCE alone.
    client_secret_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    client_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Matched by exact string equality — never prefix or wildcard, which is the
    # standard open-redirect hole.
    redirect_uris: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    scope: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    grant_types: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # Who minted it, for the admin list. Null when created by dynamic registration.
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Soft state, like api_keys: a revoked client keeps its row for audit but can no
    # longer authorize or exchange.
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class OAuthAuthorizationCode(Base):
    """A single-use authorization code, created only after the user consents."""

    __tablename__ = "oauth_authorization_codes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    # Persisted so the token request can be checked against the authorize request:
    # OAuth 2.1 requires the two redirect_uris to match.
    redirect_uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    code_challenge: Mapped[str] = mapped_column(String(255), nullable=False)
    # Stored even though only S256 is accepted, so a rejected value is visible in
    # the row rather than silently coerced.
    code_challenge_method: Mapped[str] = mapped_column(String(16), nullable=False, default="S256")
    scopes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # RFC 8707 resource indicator. Carried onto the token so a token minted for one
    # tenant cannot be spent at the other.
    resource: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Consumption is a conditional UPDATE on this column, so two concurrent
    # redemptions cannot both succeed.
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OAuthToken(Base):
    """An access or refresh token. Opaque and revocable by design.

    JWTs were rejected here: revoke_token has to actually revoke, and a JWT can only
    be revoked via a blocklist — which is this table with extra steps plus a window
    where a revoked token still works.
    """

    __tablename__ = "oauth_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # access | refresh
    client_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    scopes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    resource: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Chain link, walked in both directions when revoking. Two kinds of edge:
    # a rotated refresh token points at the one it replaced, and an access token
    # points at the refresh token it was issued alongside. The second edge is what
    # makes replay detection reach the access token — the credential actually in
    # use — rather than only killing refresh tokens.
    rotated_from: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("oauth_tokens.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def is_live(self, now: datetime) -> bool:
        return self.revoked_at is None and self.expires_at > now


def new_client_id() -> str:
    return CLIENT_ID_PREFIX + secrets.token_urlsafe(16)


def verify_code_challenge(verifier: str, challenge: str) -> bool:
    """PKCE S256 check, in constant time.

    Only S256 is supported — `plain` offers no protection against an intercepted
    authorization code, and accepting it for compatibility would undermine the
    reason PKCE is mandatory.
    """
    import base64

    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return secrets.compare_digest(expected, challenge)


def json_list(value: Any) -> list[str]:
    """Coerce a JSONB column to a list of strings, defensively.

    JSONB columns can hold anything a past migration or hand-edit put there, and a
    scope check that crashes on unexpected shape fails open in the worst way.
    """
    if isinstance(value, list):
        return [str(v) for v in value]
    return []
