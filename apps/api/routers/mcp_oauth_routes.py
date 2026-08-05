"""Authorization-server endpoints and the consent round-trip.

The SDK's `create_auth_routes` supplies /authorize, /token, /register, /revoke and
the RFC 8414 metadata document. They are mounted on the main app rather than
inside the /mcp mount for two reasons: the issuer is then a clean `/api` rather
than `/api/mcp`, and — more importantly — the MCP mount is wrapped in an auth
guard, which would make /authorize unreachable for the very user who is trying to
authenticate.

The consent endpoints are ours. `authorize()` parks the request and redirects
here; nothing redeemable exists until a human approves.
"""
from typing import Any, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, status
from mcp.server.auth.routes import create_auth_routes
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from pydantic import AnyHttpUrl, BaseModel
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.oauth import OAuthClient, json_list
from ..models.user import User
from ..services import mcp_oauth
from ..services.mcp_oauth_provider import FreeframeAuthorizationServer, create_client
from ..services.permissions import require_platform_admin

router = APIRouter(tags=["mcp-oauth"])

provider = FreeframeAuthorizationServer()


def authorization_server_routes() -> list:
    """The SDK-provided AS routes, for mounting on the main app."""
    return create_auth_routes(
        provider=provider,
        issuer_url=AnyHttpUrl(settings.mcp_oauth_issuer_url),
        client_registration_options=ClientRegistrationOptions(
            enabled=settings.mcp_oauth_allow_dcr,
            valid_scopes=mcp_oauth.SUPPORTED_SCOPES,
            default_scopes=mcp_oauth.SUPPORTED_SCOPES,
        ),
        revocation_options=RevocationOptions(enabled=True),
    )


# ── Consent ──────────────────────────────────────────────────────────────────

class ConsentInfo(BaseModel):
    client_name: str
    scopes: list[str]
    # Shown to the user verbatim. The MCP authorization spec requires the redirect
    # host to be displayed on the consent screen, because a loopback redirect can
    # be claimed by any local process.
    redirect_uri: str


class ConsentDecision(BaseModel):
    request_id: str
    approve: bool


class ConsentResult(BaseModel):
    # Where the browser should go next. Always the client's registered redirect,
    # carrying either a code or an error.
    redirect_to: str


@router.get("/oauth/consent/{request_id}", response_model=ConsentInfo)
def consent_info(
    request_id: str,
    current_user: User = Depends(get_current_user),
):
    """What the consent page renders. Requires a logged-in Freeframe user."""
    pending = provider.load_pending(request_id)
    if not pending:
        raise HTTPException(status_code=404, detail="This authorization request has expired")
    return ConsentInfo(
        client_name=pending["client_name"],
        scopes=pending["scopes"] or mcp_oauth.SUPPORTED_SCOPES,
        redirect_uri=pending["redirect_uri"],
    )


@router.post("/oauth/consent", response_model=ConsentResult)
def consent_decide(
    body: ConsentDecision,
    current_user: User = Depends(get_current_user),
):
    """Approve or deny. Approval is the only thing that mints a code.

    Admin rights are required here, not merely at token use: consenting is the
    moment a human authorises the connector, and a non-admin cannot authorise
    access they do not themselves have.
    """
    require_platform_admin(current_user)

    if not body.approve:
        pending = provider.deny(body.request_id)
        if not pending:
            raise HTTPException(status_code=404, detail="This authorization request has expired")
        params = {"error": "access_denied"}
        if pending.get("state"):
            params["state"] = pending["state"]
        return ConsentResult(redirect_to=f"{pending['redirect_uri']}?{urlencode(params)}")

    granted = provider.approve(body.request_id, current_user.id)
    if not granted:
        raise HTTPException(status_code=404, detail="This authorization request has expired")
    params = {"code": granted["code"]}
    if granted.get("state"):
        params["state"] = granted["state"]
    return ConsentResult(redirect_to=f"{granted['redirect_uri']}?{urlencode(params)}")


# ── Client administration ────────────────────────────────────────────────────

class OAuthClientCreate(BaseModel):
    name: str
    # Defaults cover the hosted Claude surfaces and Claude Code's loopback. Claude
    # Code uses an ephemeral port, so the port is ignored when matching.
    redirect_uris: Optional[list[str]] = None


class OAuthClientOut(BaseModel):
    id: str
    client_id: str
    client_name: str
    redirect_uris: list[str]
    created_at: Optional[str] = None
    revoked_at: Optional[str] = None


DEFAULT_REDIRECT_URIS = [
    "https://claude.ai/api/mcp/auth_callback",
    "http://localhost/callback",
    "http://127.0.0.1/callback",
]


@router.get("/admin/oauth-clients", response_model=list[OAuthClientOut])
def list_oauth_clients(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_platform_admin(current_user)
    rows = db.query(OAuthClient).order_by(OAuthClient.created_at.desc()).all()
    return [_client_out(r) for r in rows]


@router.post("/admin/oauth-clients", response_model=OAuthClientOut, status_code=status.HTTP_201_CREATED)
def create_oauth_client(
    body: OAuthClientCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mint a public OAuth client.

    No secret is returned because none is issued — see create_client. Leave the
    connector's OAuth Client Secret field empty.
    """
    require_platform_admin(current_user)
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    row, _ = create_client(
        db,
        name=name,
        redirect_uris=body.redirect_uris or DEFAULT_REDIRECT_URIS,
        scope=" ".join(mcp_oauth.SUPPORTED_SCOPES),
        created_by=current_user.id,
    )
    return _client_out(row)


@router.delete("/admin/oauth-clients/{client_id}", response_model=OAuthClientOut)
def revoke_oauth_client(
    client_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Revoke a client. Soft, like api_keys: the row stays for audit."""
    require_platform_admin(current_user)
    row = db.query(OAuthClient).filter(OAuthClient.client_id == client_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Client not found")
    if row.revoked_at is None:
        from datetime import datetime, timezone

        row.revoked_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
    return _client_out(row)


def _client_out(row: OAuthClient) -> OAuthClientOut:
    return OAuthClientOut(
        id=str(row.id),
        client_id=row.client_id,
        client_name=row.client_name,
        redirect_uris=json_list(row.redirect_uris),
        created_at=row.created_at.isoformat() if row.created_at else None,
        revoked_at=row.revoked_at.isoformat() if row.revoked_at else None,
    )
