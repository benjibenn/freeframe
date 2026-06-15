"""
OIDC / SSO (Authentik) login endpoints.

These are an *alternative front door*. After Authentik verifies the user, we
find-or-create the local user by email (same policy as the magic-code flow) and
mint freeframe's own access/refresh tokens. Everything downstream is unchanged.

Disabled (404) unless settings.oidc_enabled is true, so an unconfigured deploy
behaves exactly as today (local login only).
"""
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models.user import User, UserStatus
from ..services.auth_service import (
    create_access_token,
    create_refresh_token,
    get_user_by_email,
)
from ..services import oidc_service

router = APIRouter(prefix="/auth/oidc", tags=["auth", "sso"])

# Name of the HttpOnly cookie that binds the OAuth `state` to the browser that
# started the flow (login-CSRF / session-fixation protection).
STATE_COOKIE = "oidc_state"


def _require_enabled() -> None:
    if not settings.oidc_enabled:
        raise HTTPException(status_code=404, detail="SSO is not enabled")


def _is_https() -> bool:
    return bool(settings.oidc_redirect_uri and settings.oidc_redirect_uri.startswith("https"))


def _set_state_cookie(resp: Response, state: str) -> None:
    resp.set_cookie(
        STATE_COOKIE,
        state,
        max_age=oidc_service.STATE_TTL_SECONDS,
        httponly=True,
        secure=_is_https(),
        samesite="lax",  # sent on the top-level GET redirect back from the IdP
        path="/",
    )


def _clear_state_cookie(resp: Response) -> None:
    resp.delete_cookie(STATE_COOKIE, path="/")


@router.get("/login")
def oidc_login():
    """Redirect the browser to Authentik to begin the OIDC flow."""
    _require_enabled()
    try:
        url, state = oidc_service.build_authorization_url()
    except Exception:
        return RedirectResponse(f"{settings.frontend_url}/login?error=sso_unavailable", status_code=302)
    resp = RedirectResponse(url, status_code=302)
    _set_state_cookie(resp, state)
    return resp


@router.get("/callback")
def oidc_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    """
    Authentik redirects here with ?code&state. Validate, find-or-create the
    user by email, mint freeframe tokens, and hand them to the SPA via URL
    fragment (fragments are never sent to servers or logged).
    """
    _require_enabled()

    def _fail(reason: str = "sso_failed") -> RedirectResponse:
        resp = RedirectResponse(f"{settings.frontend_url}/login?error={reason}", status_code=302)
        _clear_state_cookie(resp)
        return resp

    if error or not code or not state:
        return _fail()

    # Login-CSRF guard: the `state` must match the cookie set on *this* browser
    # when the flow began. Checked before touching Redis.
    cookie_state = request.cookies.get(STATE_COOKIE)
    if not cookie_state or cookie_state != state:
        return _fail()

    nonce = oidc_service.consume_state(state)
    if nonce is None:
        return _fail()  # unknown/expired/replayed state

    try:
        tokens = oidc_service.exchange_code(code)
        claims = oidc_service.validate_id_token(tokens["id_token"], nonce)
    except (oidc_service.OIDCError, KeyError):
        return _fail()

    email = claims["email"].lower()
    user = get_user_by_email(db, email)

    if user is None:
        # First user in a fresh install becomes super admin (matches magic-code flow).
        is_first_user = db.query(User).filter(User.deleted_at.is_(None)).count() == 0
        user = User(
            email=email,
            name=claims.get("name") or claims.get("preferred_username") or email.split("@")[0],
            status=UserStatus.active,
            email_verified=True,
            is_superadmin=is_first_user,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        if user.status == UserStatus.deactivated:
            return _fail("account_deactivated")
        # SSO proves email ownership; activate pending users.
        user.email_verified = True
        if user.status == UserStatus.pending_verification:
            user.status = UserStatus.active
        db.commit()

    fragment = urlencode({
        "access_token": create_access_token(str(user.id)),
        "refresh_token": create_refresh_token(str(user.id)),
    })
    resp = RedirectResponse(f"{settings.frontend_url}/auth/oidc/callback#{fragment}", status_code=302)
    _clear_state_cookie(resp)
    return resp


@router.get("/config")
def oidc_config():
    """Public: lets the SPA decide whether to render the 'Continue with SSO' button."""
    return {"enabled": settings.oidc_enabled}


@router.get("/logout")
def oidc_logout():
    """Return the IdP's RP-initiated logout URL (frontend redirects here last)."""
    _require_enabled()
    url = oidc_service.end_session_url()
    return {"end_session_url": url}
