"""Machine-to-machine API key auth for the public integration endpoints.

Unlike the user-facing JWT flow (`get_current_user`), this guards the
`/public/*` API consumed by external platforms. The caller sends a secret in
the `X-API-Key` header. Two sources are accepted:

  1. Admin-managed keys stored (hashed) in the `api_keys` table — the normal
     path, created/revoked from the admin UI.
  2. The static `settings.public_api_key` env var — a bootstrap/fallback key.
"""
import secrets
from datetime import datetime, timezone
from fastapi import Security, HTTPException, status, Depends
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session
from ..config import settings
from ..database import get_db
from ..models.api_key import APIKey, hash_api_key
from ..models.user import User
from ..services.permissions import is_platform_admin

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(
    api_key: str | None = Security(api_key_header),
    db: Session = Depends(get_db),
) -> None:
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )

    # 1) Static bootstrap key from the environment (constant-time compare).
    if settings.public_api_key and secrets.compare_digest(api_key, settings.public_api_key):
        return

    # 2) Admin-managed key: look up by hash, must exist and not be revoked.
    record = (
        db.query(APIKey)
        .filter(APIKey.key_hash == hash_api_key(api_key), APIKey.revoked_at.is_(None))
        .first()
    )
    if record:
        record.last_used_at = datetime.now(timezone.utc)
        db.commit()
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or revoked API key",
    )


def resolve_api_key_user(db: Session, api_key: str | None) -> User:
    """Resolve an admin-managed key to the user who created it.

    `require_api_key` only answers "is this key valid" — enough for the public
    read API, which acts on nobody's behalf. The MCP tools call the same code the
    owner-facing routes call, so they need a real `User` to pass as `current_user`.
    `api_keys.created_by` already names one, so the key doubles as an identity and
    no service account is needed.

    The static bootstrap key is rejected here: it has no row, so no `created_by`,
    so there is nobody to act as.

    Admin rights are checked at resolution rather than being left to the routes.
    Every write path calls `require_platform_admin`, and `_resolve_home` separately
    falls back to project membership for non-admins — so a non-admin key fails
    twice, in two places, with two unrelated messages. Failing once here gives the
    agent something it can actually report.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )

    if settings.public_api_key and secrets.compare_digest(api_key, settings.public_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The bootstrap API key has no user identity. Create a key from the admin UI.",
        )

    record = (
        db.query(APIKey)
        .filter(APIKey.key_hash == hash_api_key(api_key), APIKey.revoked_at.is_(None))
        .first()
    )
    if not record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key",
        )

    user = (
        db.query(User)
        .filter(User.id == record.created_by, User.deleted_at.is_(None))
        .first()
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The user who created this API key no longer exists",
        )
    if not is_platform_admin(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This API key belongs to a non-admin user; managing requests needs admin rights",
        )

    record.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return user
