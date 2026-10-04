"""GET /review-queue — the files waiting in the Review stage, oldest first.

Admin only (superadmin or sub-admin): it spans every editor's submissions.
Decisions go through PATCH /assets/{id}/task-stage (routers/tasks.py).
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.asset import Asset, AssetVersion, MediaFile
from ..models.comment import Comment
from ..models.project import Project
from ..models.submission import Submission, SubmissionLink
from ..models.task_stage import TaskStage
from ..models.user import User
from ..schemas.review_queue import ReviewQueuePage, ReviewStageIds
from ..services import source_link
from ..services.board_paging import DEFAULT_LIMIT, MAX_LIMIT
from ..services.permissions import require_platform_admin
from ..services.review_queue import MissingStage, QueueContext, build_item, resolve_review_stages
from ..services.s3_service import generate_presigned_get_url
from .hls_proxy import hls_stream_url

router = APIRouter(tags=["review-queue"])


def _stages_or_409(db: Session) -> dict:
    stages = (
        db.query(TaskStage)
        .filter(TaskStage.deleted_at.is_(None))
        .order_by(TaskStage.position.asc(), TaskStage.created_at.asc())
        .all()
    )
    try:
        return resolve_review_stages(stages)
    except MissingStage as e:
        raise HTTPException(status_code=409, detail=str(e))


def _queue_page(db: Session, review_id, *, project_id, editor_id, limit: int, offset: int):
    """(rows, total). rows are (Asset, newest AssetVersion), oldest submission first.

    "Submitted" is the newest version's created_at, so a file re-uploaded after a
    Revision queues by its new upload, not by when the asset was first created.
    """
    latest = (
        db.query(
            AssetVersion.asset_id.label("asset_id"),
            func.max(AssetVersion.version_number).label("vn"),
        )
        .filter(AssetVersion.deleted_at.is_(None))
        .group_by(AssetVersion.asset_id)
        .subquery()
    )
    q = (
        db.query(Asset, AssetVersion)
        .join(latest, latest.c.asset_id == Asset.id)
        .join(
            AssetVersion,
            and_(AssetVersion.asset_id == Asset.id, AssetVersion.version_number == latest.c.vn),
        )
        # A soft-deleted brief's project is not removed, just marked deleted_at.
        # Without this join+filter its files stay queued and 404 when clicked
        # through from the queue into a brief that no longer resolves.
        .join(Project, Project.id == Asset.project_id)
        .filter(
            Asset.task_stage_id == review_id,
            Asset.deleted_at.is_(None),
            Project.deleted_at.is_(None),
        )
    )
    if project_id is not None:
        q = q.filter(Asset.project_id == project_id)
    if editor_id is not None:
        q = q.filter(Asset.created_by == editor_id)
    total = q.count()
    rows = q.order_by(AssetVersion.created_at.asc(), Asset.id.asc()).offset(offset).limit(limit).all()
    return rows, total


def _context(db: Session, rows) -> QueueContext:
    """Bulk-load what every item on the page needs (no N+1)."""
    assets = [a for a, _ in rows]
    version_ids = [v.id for _, v in rows]
    project_ids = list({a.project_id for a in assets})
    user_ids = list({a.created_by for a in assets})

    files_by_version: dict = {}
    files = db.query(MediaFile).filter(MediaFile.version_id.in_(version_ids)).all()
    for f in sorted(files, key=lambda f: (f.sequence_order is None, f.sequence_order or 0)):
        files_by_version.setdefault(f.version_id, []).append(f)

    projects = {p.id: p for p in db.query(Project).filter(Project.id.in_(project_ids)).all()}
    link_ids = list({p.submission_link_id for p in projects.values() if p.submission_link_id})
    links = (
        {l.id: l for l in db.query(SubmissionLink).filter(SubmissionLink.id.in_(link_ids)).all()}
        if link_ids else {}
    )
    subs = {s.project_id: s for s in db.query(Submission).filter(Submission.project_id.in_(project_ids)).all()}
    users = {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()}
    source_rows = (
        db.query(Comment.version_id, Comment.body)
        .filter(
            Comment.version_id.in_(version_ids),
            Comment.visibility == source_link.VISIBILITY,
            Comment.deleted_at.is_(None),
            Comment.body.startswith(source_link.PREFIX),
        )
        .order_by(Comment.created_at.asc())
        .all()
    )
    return QueueContext(
        files_by_version=files_by_version,
        projects=projects,
        links=links,
        submissions_by_project=subs,
        users=users,
        source_by_version=source_link.links_by_version(source_rows),
        presign=generate_presigned_get_url,
        hls_url=hls_stream_url,
    )


@router.get("/review-queue", response_model=ReviewQueuePage)
def get_review_queue(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    editor_id: Optional[uuid.UUID] = Query(None, description="Only files this user uploaded."),
    project_id: Optional[uuid.UUID] = Query(None, description="Only files in this project."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_platform_admin(current_user)
    stages = _stages_or_409(db)
    rows, total = _queue_page(
        db, stages["review"], project_id=project_id, editor_id=editor_id, limit=limit, offset=offset,
    )
    ctx = _context(db, rows) if rows else QueueContext()
    return ReviewQueuePage(
        items=[build_item(a, v, ctx) for a, v in rows],
        total=total,
        stages=ReviewStageIds(**stages),
    )
