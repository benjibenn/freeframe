"""
Portal service (Phase 2 Shell).

Reads each user's *launchable* apps from Authentik and shapes them into tiles
for the freeframe portal. Authentik is the single source of truth for both
access (its policy bindings, evaluated via ?for_user=) and tile content
(app name / launch URL / description / icon). Results are cached per-email for
60s so a busy portal does not hammer the IdP; access changes propagate within
the cache window.
"""
from __future__ import annotations

import json
from typing import Optional

import httpx

from ..config import settings
from .redis_service import get_redis

_CACHE_TTL = 60  # seconds


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.authentik_service_token}"}


def _cache_key(email: str) -> str:
    return f"portal:apps:{email}"


def resolve_user_pk(email: str) -> Optional[int]:
    """Map an email to the Authentik user pk, or None if there is no such user."""
    url = f"{settings.authentik_api_base}/api/v3/core/users/"
    resp = httpx.get(url, params={"email": email}, headers=_headers(), timeout=10.0)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return results[0]["pk"] if results else None


def list_launchable_apps(pk: int) -> list[dict]:
    """Tiles for the apps the given Authentik user can launch."""
    url = f"{settings.authentik_api_base}/api/v3/core/applications/"
    resp = httpx.get(url, params={"for_user": pk}, headers=_headers(), timeout=10.0)
    resp.raise_for_status()
    return [
        {
            "slug": a["slug"],
            "name": a.get("name") or a["slug"],
            "launch_url": a.get("meta_launch_url") or "",
            "description": a.get("meta_description") or "",
            "icon": a.get("meta_icon") or None,
        }
        for a in resp.json().get("results", [])
        if a.get("meta_launch_url")
    ]


def get_apps_for_email(email: str) -> list[dict]:
    """Cached per-user tile list. Raises httpx.HTTPError if Authentik is unreachable."""
    r = get_redis()
    key = _cache_key(email)
    cached = r.get(key)
    if cached is not None:
        return json.loads(cached)
    pk = resolve_user_pk(email)
    apps = [] if pk is None else list_launchable_apps(pk)
    r.setex(key, _CACHE_TTL, json.dumps(apps))
    return apps
