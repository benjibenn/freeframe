"""
Portal router (Phase 2 Shell).

GET /portal/apps returns the tiles the logged-in user may launch, read live
from Authentik. Auth is freeframe's normal session (get_current_user). The
Authentik service token is used server-side only and never reaches the client.
On Authentik failure we 502 (fail loud) rather than substitute a default list.
"""
import httpx
from fastapi import APIRouter, Depends, HTTPException

from ..config import settings
from ..middleware.auth import get_current_user
from ..models.user import User
from ..services import portal_service

router = APIRouter(prefix="/portal", tags=["portal"])


@router.get("/apps")
def list_portal_apps(current_user: User = Depends(get_current_user)):
    if not settings.portal_enabled:
        raise HTTPException(status_code=503, detail="Portal not configured")
    try:
        apps = portal_service.get_apps_for_email(current_user.email)
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Could not reach identity provider")
    return {"apps": apps}
