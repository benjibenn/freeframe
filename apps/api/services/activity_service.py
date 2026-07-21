"""Service helper for creating ActivityLog entries."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.orm import Session

from ..models.activity import ActivityLog, ActivityAction


def log_activity(
    db: Session,
    action: str,
    user_id: Optional[uuid.UUID] = None,
    org_id: Optional[uuid.UUID] = None,
    project_id: Optional[uuid.UUID] = None,
    asset_id: Optional[uuid.UUID] = None,
    payload: Optional[dict] = None,
) -> None:
    """Create an ActivityLog entry. Call before ``db.commit()``."""
    entry = ActivityLog(
        action=action,
        user_id=user_id,
        org_id=org_id,
        project_id=project_id,
        asset_id=asset_id,
        payload=payload or {},
    )
    db.add(entry)


def log_asset_activity(
    db: Session,
    *,
    user_id: uuid.UUID,
    asset_id: uuid.UUID,
    project_id: Optional[uuid.UUID],
    action: str,
    payload: Optional[dict] = None,
    dedup_window_minutes: int = 5,
) -> bool:
    """Log an asset click/view/download, collapsing repeats within a window.

    Returns True if a row was written, False if a matching (user, asset, action)
    row already exists inside the last ``dedup_window_minutes``. Caller commits.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=dedup_window_minutes)
    recent = (
        db.query(ActivityLog)
        .filter(
            ActivityLog.user_id == user_id,
            ActivityLog.asset_id == asset_id,
            ActivityLog.action == action,
            ActivityLog.created_at >= cutoff,
        )
        .first()
    )
    if recent is not None:
        return False
    log_activity(
        db,
        action=action,
        user_id=user_id,
        project_id=project_id,
        asset_id=asset_id,
        payload=payload or {},
    )
    return True
