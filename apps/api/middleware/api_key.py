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
