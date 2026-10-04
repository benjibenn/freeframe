"""GET /review-queue — the editors waiting in the Review stage, oldest first.

One item per editor per brief (a Submission), with the files they delivered.
Admin only (superadmin or sub-admin): it spans every editor's submissions.
Decisions go through PATCH /submission-links/{link_id}/editors/{user_id}/task-stage
(routers/tasks.py), the same endpoint the /tasks board uses.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.asset import MediaFile
from ..models.comment import Comment
from ..models.task_stage import TaskStage
from ..models.user import User
from ..schemas.review_queue import ReviewQueuePage, ReviewStageIds
from ..services import source_link
from ..services.board_paging import DEFAULT_LIMIT, MAX_LIMIT
from ..services.permissions import require_platform_admin
from ..services.review_queue import (
    MissingStage,
    build_file,
    build_item,
    files_statement,
    queue_statement,
    resolve_review_stages,
)
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


def _queue_page(db: Session, review_id, *, editor_id, limit: int, offset: int):
    """(rows, total). rows are (Submission, brief_title, brief_token, waited_since)."""
    stmt = queue_statement(review_id, editor_id=editor_id)
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one()
    rows = db.execute(stmt.offset(offset).limit(limit)).all()
    return rows, total


def _files_by_project(db: Session, project_ids: list) -> dict:
    """{project_id: [ReviewFile]} for the whole page in three queries (no N+1)."""
    rows = db.execute(files_statement(project_ids)).all()
    if not rows:
        return {}
    version_ids = [v.id for _, v in rows]

    media_by_version: dict = {}
    media = db.query(MediaFile).filter(MediaFile.version_id.in_(version_ids)).all()
    for m in sorted(media, key=lambda m: (m.sequence_order is None, m.sequence_order or 0)):
        media_by_version.setdefault(m.version_id, []).append(m)

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
    sources = source_link.links_by_version(source_rows)

    out: dict = {}
    for asset, version in rows:
        out.setdefault(asset.project_id, []).append(build_file(
            asset, version, media_by_version.get(version.id, []), sources.get(version.id),
            presign=generate_presigned_get_url, hls_url=hls_stream_url,
        ))
    return out


@router.get("/review-queue", response_model=ReviewQueuePage)
def get_review_queue(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    editor_id: Optional[uuid.UUID] = Query(None, description="Only this editor's submissions."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_platform_admin(current_user)
    stages = _stages_or_409(db)
    rows, total = _queue_page(db, stages["review"], editor_id=editor_id, limit=limit, offset=offset)
    items = []
    if rows:
        subs = [r[0] for r in rows]
        users = {u.id: u for u in db.query(User).filter(User.id.in_(list({s.user_id for s in subs}))).all()}
        files = _files_by_project(db, [s.project_id for s in subs])
        items = [
            build_item(sub, title, token, users.get(sub.user_id), waited, files.get(sub.project_id, []), stages["review"])
            for sub, title, token, waited in rows
        ]
    return ReviewQueuePage(items=items, total=total, stages=ReviewStageIds(**stages))
