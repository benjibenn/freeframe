"""Default share links.

Every project (including the per-submitter projects provisioned from submission
links) gets one canonical share link created automatically: **private view +
comment enabled** (visibility=secure → must be logged in; permission=comment →
can view and leave feedback). This is the link the projects page exposes via its
"copy link" action.
"""
import secrets
import uuid

from sqlalchemy.orm import Session

from ..models.share import ShareLink, SharePermission
from ..schemas.share import ShareLinkAppearance

# Defaults for the auto-created link: private (auth required), view + comment.
DEFAULT_PERMISSION = SharePermission.comment
DEFAULT_VISIBILITY = "secure"


def build_default_project_share_link(
    project_id: uuid.UUID,
    created_by: uuid.UUID,
    title: str,
) -> ShareLink:
    """Construct (but do not persist) the default share link for a project.

    Caller is responsible for `db.add()` + commit so the link participates in the
    same transaction as the project creation.
    """
    return ShareLink(
        project_id=project_id,
        token=secrets.token_urlsafe(32),
        created_by=created_by,
        title=title or "",
        permission=DEFAULT_PERMISSION,
        visibility=DEFAULT_VISIBILITY,
        allow_download=False,
        show_versions=True,
        show_watermark=False,
        is_default=True,
        appearance=ShareLinkAppearance().model_dump(),
    )


def get_default_project_share_link(db: Session, project_id: uuid.UUID) -> ShareLink | None:
    """Return the project's canonical (default) share link, if one exists."""
    return (
        db.query(ShareLink)
        .filter(
            ShareLink.project_id == project_id,
            ShareLink.is_default.is_(True),
            ShareLink.deleted_at.is_(None),
        )
        .order_by(ShareLink.created_at.asc())
        .first()
    )


def get_or_create_default_project_share_link(
    db: Session,
    project_id: uuid.UUID,
    created_by: uuid.UUID,
    title: str,
) -> ShareLink:
    """Idempotently return the project's default share link, creating it if missing.

    Backfills projects that predate the auto-create behaviour. Does NOT commit —
    the caller commits.
    """
    existing = get_default_project_share_link(db, project_id)
    if existing:
        return existing
    link = build_default_project_share_link(project_id, created_by, title)
    db.add(link)
    db.flush()
    return link
