"""Freeframe as the OAuth 2.1 authorization server for MCP.

Delegating to an IdP is what most MCP servers do, and it was the first plan — but
client2.0 has no IdP, and client current's Authentik stamps the client_id into
`aud` rather than this server's URI, so it cannot satisfy the audience binding
that keeps the two tenants apart. Issuing our own tokens fixes that at the root:
if Freeframe mints the token, Freeframe sets the audience.

The SDK mounts /authorize, /token, /register and /revoke and calls into the nine
methods below. What lives here is the storage and the security decisions:

  * Tokens are opaque and stored hashed, so revoke_token genuinely revokes.
  * Refresh tokens rotate on every use; replaying a rotated one revokes the chain.
  * Authorization codes are single-use via a conditional UPDATE, so two
    concurrent redemptions cannot both win.
  * Redirect URIs match by exact string equality, never by prefix.
  * The audience is stamped from the request's resource indicator and validated
    on every call.

Consent is not skippable: Anthropic's connector docs are explicit that a pure
machine-to-machine client_credentials grant is unsupported and "every connection
requires user consent", so /authorize always routes through a human.
"""
import json
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl

from ..config import settings
from ..database import SessionLocal
from ..models.oauth import (
    ACCESS_TOKEN_TTL_SECONDS,
    AUTHORIZATION_CODE_TTL_SECONDS,
    REFRESH_TOKEN_TTL_SECONDS,
    OAuthAuthorizationCode,
    OAuthClient,
    OAuthToken as TokenRow,
    generate_secret,
    hash_secret,
    json_list,
    new_client_id,
)
from .redis_service import get_redis

# A pending authorization lives only as long as it takes a human to log in and
# approve. It is held in Redis rather than the database because an abandoned
# consent should evaporate, not accumulate rows that look like real grants.
PENDING_TTL_SECONDS = 600


def _pending_key(request_id: str) -> str:
    return f"mcp:oauth:pending:{request_id}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FreeframeAuthorizationServer(
    OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]
):
    # ── Clients ──────────────────────────────────────────────────────────────

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        db = SessionLocal()
        try:
            row = (
                db.query(OAuthClient)
                .filter(OAuthClient.client_id == client_id, OAuthClient.revoked_at.is_(None))
                .first()
            )
            if row is None:
                return None
            return OAuthClientInformationFull(
                client_id=row.client_id,
                # Public client, deliberately. The SDK authenticates a
                # confidential client with `client.client_secret != presented`, a
                # plaintext comparison — so supporting one would mean storing the
                # secret recoverably, which is worse than not having it. Returning
                # the hash here would instead require the client to send the hash,
                # making the "secret" a password-equivalent that a database dump
                # hands over.
                #
                # A public client is the standard, spec-blessed shape for this:
                # Claude registers itself as one under both DCR and CIMD, and its
                # docs describe the Client Secret field as needed "only if your
                # authorization server requires confidential-client
                # authentication". Security rests on PKCE S256, exact redirect-URI
                # matching, and user consent — all enforced here.
                client_secret=None,
                client_name=row.client_name,
                redirect_uris=[AnyUrl(u) for u in json_list(row.redirect_uris)],
                grant_types=["authorization_code", "refresh_token"],
                scope=row.scope or None,
                token_endpoint_auth_method="none",
            )
        finally:
            db.close()

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        """Dynamic registration. Off unless MCP_OAUTH_ALLOW_DCR is set.

        RFC 7591 makes DCR a SHOULD, and Claude accepts a manually issued client
        ID and secret, so an open registration endpoint on the public internet
        buys nothing and adds an abuse surface.
        """
        if not settings.mcp_oauth_allow_dcr:
            raise ValueError("Dynamic client registration is disabled on this server")
        db = SessionLocal()
        try:
            db.add(
                OAuthClient(
                    client_id=client_info.client_id,
                    client_secret_hash=(
                        hash_secret(client_info.client_secret)
                        if client_info.client_secret
                        else None
                    ),
                    client_name=client_info.client_name or "Dynamically registered client",
                    redirect_uris=[str(u) for u in client_info.redirect_uris],
                    scope=client_info.scope or "",
                    grant_types=list(client_info.grant_types or []),
                )
            )
            db.commit()
        finally:
            db.close()

    # ── Authorization ────────────────────────────────────────────────────────

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        """Park the request and send the user to the consent page.

        No authorization code exists yet. It is minted only after a human
        approves, so an abandoned or denied consent leaves nothing redeemable.
        """
        # Exact-match the redirect against the registered list. Prefix or
        # wildcard matching here is the standard open-redirect hole.
        requested = str(params.redirect_uri)
        if requested not in [str(u) for u in client.redirect_uris]:
            raise ValueError("redirect_uri is not registered for this client")

        request_id = secrets.token_urlsafe(24)
        get_redis().setex(
            _pending_key(request_id),
            PENDING_TTL_SECONDS,
            json.dumps({
                "client_id": client.client_id,
                "client_name": client.client_name or client.client_id,
                "redirect_uri": requested,
                "code_challenge": params.code_challenge,
                "state": params.state,
                "scopes": params.scopes or [],
                # Carried through to the token so the audience is whatever the
                # client actually asked for, defaulting to this server.
                "resource": params.resource or settings.mcp_canonical_resource,
            }),
        )
        return f"{settings.frontend_url.rstrip('/')}/oauth/consent?request_id={request_id}"

    def load_pending(self, request_id: str) -> Optional[dict[str, Any]]:
        raw = get_redis().get(_pending_key(request_id))
        return json.loads(raw) if raw else None

    def approve(self, request_id: str, user_id: uuid.UUID) -> Optional[dict[str, Any]]:
        """Mint the authorization code for an approved request.

        The pending record is deleted as it is read, so a replayed approval — a
        double-clicked button, a resubmitted form — cannot mint a second code.
        """
        r = get_redis()
        raw = r.get(_pending_key(request_id))
        if not raw:
            return None
        if not r.delete(_pending_key(request_id)):
            return None
        pending = json.loads(raw)

        code = generate_secret()
        db = SessionLocal()
        try:
            db.add(
                OAuthAuthorizationCode(
                    code_hash=hash_secret(code),
                    client_id=pending["client_id"],
                    user_id=user_id,
                    redirect_uri=pending["redirect_uri"],
                    code_challenge=pending["code_challenge"],
                    code_challenge_method="S256",
                    scopes=pending["scopes"],
                    resource=pending["resource"],
                    expires_at=_now() + timedelta(seconds=AUTHORIZATION_CODE_TTL_SECONDS),
                )
            )
            db.commit()
        finally:
            db.close()
        return {"code": code, "redirect_uri": pending["redirect_uri"], "state": pending["state"]}

    def deny(self, request_id: str) -> Optional[dict[str, Any]]:
        r = get_redis()
        raw = r.get(_pending_key(request_id))
        if not raw:
            return None
        r.delete(_pending_key(request_id))
        return json.loads(raw)

    # ── Authorization code exchange ──────────────────────────────────────────

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        db = SessionLocal()
        try:
            row = (
                db.query(OAuthAuthorizationCode)
                .filter(
                    OAuthAuthorizationCode.code_hash == hash_secret(authorization_code),
                    OAuthAuthorizationCode.consumed_at.is_(None),
                )
                .first()
            )
            # The code must belong to the client presenting it: a code leaked to
            # another registered client must not be redeemable by it.
            if row is None or row.client_id != client.client_id:
                return None
            if row.expires_at <= _now():
                return None
            return AuthorizationCode(
                code=authorization_code,
                scopes=json_list(row.scopes),
                expires_at=row.expires_at.timestamp(),
                client_id=row.client_id,
                code_challenge=row.code_challenge,
                redirect_uri=AnyUrl(row.redirect_uri),
                redirect_uri_provided_explicitly=True,
                resource=row.resource,
            )
        finally:
            db.close()

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        """Redeem a code once. PKCE is verified by the SDK before this is called."""
        db = SessionLocal()
        try:
            # Single-use enforced in the database, not in Python: a conditional
            # UPDATE means two concurrent redemptions cannot both see it unused.
            claimed = (
                db.query(OAuthAuthorizationCode)
                .filter(
                    OAuthAuthorizationCode.code_hash == hash_secret(authorization_code.code),
                    OAuthAuthorizationCode.consumed_at.is_(None),
                )
                .update({"consumed_at": _now()}, synchronize_session=False)
            )
            if not claimed:
                db.rollback()
                raise ValueError("Authorization code has already been used")
            row = (
                db.query(OAuthAuthorizationCode)
                .filter(
                    OAuthAuthorizationCode.code_hash == hash_secret(authorization_code.code)
                )
                .first()
            )
            tokens = self._issue_pair(
                db,
                client_id=client.client_id,
                user_id=row.user_id,
                scopes=json_list(row.scopes),
                resource=row.resource,
            )
            db.commit()
            return tokens
        finally:
            db.close()

    # ── Refresh ──────────────────────────────────────────────────────────────

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        db = SessionLocal()
        try:
            row = self._find_token(db, refresh_token, kind="refresh")
            if row is None or row.client_id != client.client_id:
                return None
            if row.revoked_at is not None:
                # Presenting an already-revoked refresh token is replay: the real
                # holder rotated it, so someone else has a copy. Kill the chain
                # rather than just failing this request.
                self._revoke_chain(db, row)
                db.commit()
                return None
            if row.expires_at <= _now():
                return None
            return RefreshToken(
                token=refresh_token,
                client_id=row.client_id,
                scopes=json_list(row.scopes),
                expires_at=int(row.expires_at.timestamp()),
            )
        finally:
            db.close()

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        db = SessionLocal()
        try:
            row = self._find_token(db, refresh_token.token, kind="refresh")
            if row is None or row.revoked_at is not None:
                raise ValueError("invalid_grant")
            # Narrowing is allowed, widening is not — a refresh must never gain
            # scopes the original grant did not carry.
            held = json_list(row.scopes)
            granted = [s for s in (scopes or held) if s in held]
            row.revoked_at = _now()
            tokens = self._issue_pair(
                db,
                client_id=client.client_id,
                user_id=row.user_id,
                scopes=granted,
                resource=row.resource,
                rotated_from=row.id,
            )
            db.commit()
            return tokens
        finally:
            db.close()

    # ── Access tokens ────────────────────────────────────────────────────────

    async def load_access_token(self, token: str) -> AccessToken | None:
        db = SessionLocal()
        try:
            row = self._find_token(db, token, kind="access")
            if row is None or not row.is_live(_now()):
                return None
            return AccessToken(
                token=token,
                client_id=row.client_id,
                scopes=json_list(row.scopes),
                expires_at=int(row.expires_at.timestamp()),
                resource=row.resource,
            )
        finally:
            db.close()

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        db = SessionLocal()
        try:
            for kind in ("access", "refresh"):
                row = self._find_token(db, token.token, kind=kind)
                if row is not None:
                    # RFC 7009: revoking a refresh token should take its access
                    # tokens with it, so the chain goes rather than one row.
                    self._revoke_chain(db, row)
            db.commit()
        finally:
            db.close()

    # ── Internals ────────────────────────────────────────────────────────────

    @staticmethod
    def _find_token(db, raw: str, kind: str) -> Optional[TokenRow]:
        return (
            db.query(TokenRow)
            .filter(TokenRow.token_hash == hash_secret(raw), TokenRow.kind == kind)
            .first()
        )

    @staticmethod
    def _revoke_chain(db, row: TokenRow) -> None:
        """Revoke a token, everything it was rotated from, and everything rotated
        from it — so replay detection cannot be sidestepped by holding an older
        link in the chain."""
        now = _now()
        seen: set[uuid.UUID] = set()
        frontier = [row]
        while frontier:
            current = frontier.pop()
            if current.id in seen:
                continue
            seen.add(current.id)
            current.revoked_at = current.revoked_at or now
            children = db.query(TokenRow).filter(TokenRow.rotated_from == current.id).all()
            frontier.extend(children)
            if current.rotated_from:
                parent = db.query(TokenRow).filter(TokenRow.id == current.rotated_from).first()
                if parent:
                    frontier.append(parent)

    def _issue_pair(
        self,
        db,
        *,
        client_id: str,
        user_id: uuid.UUID,
        scopes: list[str],
        resource: Optional[str],
        rotated_from: Optional[uuid.UUID] = None,
    ) -> OAuthToken:
        access = generate_secret()
        refresh = generate_secret()
        now = _now()
        access_row = TokenRow(
            token_hash=hash_secret(access),
            kind="access",
            client_id=client_id,
            user_id=user_id,
            scopes=scopes,
            resource=resource,
            expires_at=now + timedelta(seconds=ACCESS_TOKEN_TTL_SECONDS),
        )
        refresh_row = TokenRow(
            token_hash=hash_secret(refresh),
            kind="refresh",
            client_id=client_id,
            user_id=user_id,
            scopes=scopes,
            resource=resource,
            expires_at=now + timedelta(seconds=REFRESH_TOKEN_TTL_SECONDS),
            rotated_from=rotated_from,
        )
        db.add(access_row)
        db.add(refresh_row)
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL_SECONDS,
            scope=" ".join(scopes) if scopes else None,
            refresh_token=refresh,
        )


def create_client(
    db,
    *,
    name: str,
    redirect_uris: list[str],
    scope: str,
    created_by: Optional[uuid.UUID],
) -> tuple[OAuthClient, str]:
    """Mint a public OAuth client for the admin UI. Returns (row, client_id).

    No secret is issued. Confidential clients are not offered rather than offered
    badly: the SDK compares the secret in plaintext, so supporting one would mean
    storing it recoverably, and a "secret" that a database dump reveals is worse
    than a public client protected by PKCE. Leave the connector's OAuth Client
    Secret field empty.
    """
    client_id = new_client_id()
    row = OAuthClient(
        client_id=client_id,
        client_secret_hash=None,
        client_name=name,
        redirect_uris=redirect_uris,
        scope=scope,
        grant_types=["authorization_code", "refresh_token"],
        created_by=created_by,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, client_id
