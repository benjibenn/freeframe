"""Platform-wide activity feed for admins and sub-admins.

A single chronological stream of everything happening across every project —
new uploads/submissions, comments, approvals and shares — so an admin or
sub-admin can watch all activity in one place and click straight through to the
latest revision of an asset to comment, instead of opening each folder one by one.

Access is restricted to platform admins (superadmin) and sub-admins.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.user import User
from ..models.asset import Asset, AssetVersion
from ..models.project import Project
from ..models.activity import ActivityLog, TRACKING_ACTIONS
from ..schemas.activity import ActivityActor, ActivityFeedItem, ActivityUnreadCount
from ..services.permissions import require_platform_admin

router = APIRouter(prefix="/activity", tags=["activity"])

SEEN_PREF_KEY = "activity_seen_at"


def _parse_seen(user: User) -> Optional[datetime]:
    raw = (user.preferences or {}).get(SEEN_PREF_KEY)
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _enrich(db: Session, logs: list[ActivityLog]) -> list[ActivityFeedItem]:
    """Batch-load actors, assets, projects and latest versions for a page of logs."""
    asset_ids = {l.asset_id for l in logs if l.asset_id}
    user_ids = {l.user_id for l in logs if l.user_id}

    assets = {a.id: a for a in db.query(Asset).filter(Asset.id.in_(asset_ids)).all()} if asset_ids else {}
    project_ids = {a.project_id for a in assets.values()} | {l.project_id for l in logs if l.project_id}
    projects = {p.id: p for p in db.query(Project).filter(Project.id.in_(project_ids)).all()} if project_ids else {}
    users = {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}

    # Latest (non-deleted) version number per asset, in one grouped query.
    latest_versions: dict[uuid.UUID, int] = {}
    if asset_ids:
        rows = (
            db.query(AssetVersion.asset_id, func.max(AssetVersion.version_number))
            .filter(AssetVersion.asset_id.in_(asset_ids), AssetVersion.deleted_at.is_(None))
            .group_by(AssetVersion.asset_id)
            .all()
        )
        latest_versions = {aid: int(n) for aid, n in rows}

    items: list[ActivityFeedItem] = []
    for log in logs:
        asset = assets.get(log.asset_id) if log.asset_id else None
        project_id = log.project_id or (asset.project_id if asset else None)
        project = projects.get(project_id) if project_id else None
        actor_user = users.get(log.user_id) if log.user_id else None
        payload = log.payload or {}

        deep_link = None
        if project_id and asset:
            deep_link = f"/projects/{project_id}/assets/{asset.id}"
            comment_id = payload.get("comment_id")
            if comment_id:
                deep_link += f"?commentId={comment_id}"

        items.append(ActivityFeedItem(
            id=log.id,
            action=log.action,
            created_at=log.created_at,
            actor=ActivityActor(id=actor_user.id, name=actor_user.name, avatar_url=actor_user.avatar_url) if actor_user else None,
            asset_id=asset.id if asset else log.asset_id,
            asset_name=asset.name if asset else None,
            asset_type=(asset.asset_type.value if asset and asset.asset_type else None),
            project_id=project_id,
            project_name=project.name if project else None,
            latest_version_number=latest_versions.get(asset.id) if asset else None,
            comment_preview=payload.get("preview"),
            deep_link=deep_link,
            payload=payload,
        ))
    return items


@router.get("", response_model=list[ActivityFeedItem])
def list_activity(
    limit: int = Query(default=50, le=100),
    before: Optional[datetime] = Query(default=None, description="Return activity strictly older than this timestamp (for pagination)."),
    action: Optional[str] = Query(default=None, description="Comma-separated action names to filter by (e.g. 'created' or 'approved,rejected'). Omit for all."),
    user_id: Optional[uuid.UUID] = Query(default=None, description="Restrict to a single user's activity (per-user drill-down)."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Chronological platform-wide activity feed. Admin / sub-admin only.

    Pass ``action`` to filter by category (uploads=created, comments=commented,mentioned,
    approvals=approved,rejected, shares=shared). Filtering is server-side so pagination
    via ``before`` stays correct.
    """
    require_platform_admin(current_user)
    query = db.query(ActivityLog)
    if action:
        actions = [a.strip() for a in action.split(",") if a.strip()]
        if actions:
            query = query.filter(ActivityLog.action.in_(actions))
    if user_id:
        query = query.filter(ActivityLog.user_id == user_id)
    if before:
        query = query.filter(ActivityLog.created_at < before)
    logs = query.order_by(ActivityLog.created_at.desc()).limit(limit).all()
    return _enrich(db, logs)


@router.get("/unread-count", response_model=ActivityUnreadCount)
def unread_activity_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Number of activity events since the caller last viewed the feed (their own
    actions excluded). Drives the alert badge.

    Tracking actions (asset_clicked/viewed/downloaded) are excluded — this badge
    signals new TEAM activity worth reviewing, not passive view/download noise.
    """
    require_platform_admin(current_user)
    query = (
        db.query(func.count(ActivityLog.id))
        .filter(ActivityLog.user_id != current_user.id)
        .filter(ActivityLog.action.notin_(TRACKING_ACTIONS))
    )
    seen = _parse_seen(current_user)
    if seen:
        query = query.filter(ActivityLog.created_at > seen)
    return ActivityUnreadCount(count=int(query.scalar() or 0))


@router.post("/seen", status_code=status.HTTP_204_NO_CONTENT)
def mark_activity_seen(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark the feed as read up to now — clears the alert badge."""
    require_platform_admin(current_user)
    # Reassign a new dict so SQLAlchemy detects the JSON change.
    prefs = dict(current_user.preferences or {})
    prefs[SEEN_PREF_KEY] = datetime.now(timezone.utc).isoformat()
    current_user.preferences = prefs
    db.commit()
