"""Admin task-pipeline endpoints.

Two surfaces, both platform-admin only (superadmin / sub-admin):
  * /task-stages — manage the configurable pipeline stages (Pending, In Progress,
    Review, Revision, Done, …): create / rename / recolour / reorder / remove.
  * /tasks — the platform-wide task list: every video asset with its current stage,
    submitter and a thumbnail. PATCH /assets/{id}/task-stage moves a video.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.user import User
from ..models.project import Project
from ..models.asset import Asset, AssetVersion, MediaFile, AssetType
from ..models.task_stage import TaskStage
from ..schemas.task_stage import (
    TaskStageResponse,
    TaskStageCreate,
    TaskStageUpdate,
    TaskStageReorder,
    TaskStageAssign,
    RunAsAdAssign,
    TaskItem,
)
from ..services.permissions import require_platform_admin
from ..services.s3_service import generate_presigned_get_url

router = APIRouter(tags=["tasks"])


def _get_stage(db: Session, stage_id: uuid.UUID) -> TaskStage:
    stage = db.query(TaskStage).filter(
        TaskStage.id == stage_id,
        TaskStage.deleted_at.is_(None),
    ).first()
    if not stage:
        raise HTTPException(status_code=404, detail="Task stage not found")
    return stage


# ── Stage management ─────────────────────────────────────────────────────────

@router.get("/task-stages", response_model=list[TaskStageResponse])
def list_task_stages(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_platform_admin(current_user)
    return db.query(TaskStage).filter(
        TaskStage.deleted_at.is_(None),
    ).order_by(TaskStage.position.asc(), TaskStage.created_at.asc()).all()


@router.post("/task-stages", response_model=TaskStageResponse, status_code=status.HTTP_201_CREATED)
def create_task_stage(
    body: TaskStageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_platform_admin(current_user)
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Stage name is required")
    max_pos = db.query(func.max(TaskStage.position)).filter(TaskStage.deleted_at.is_(None)).scalar()
    stage = TaskStage(
        name=name,
        color=body.color,
        position=(max_pos or 0) + 1,
    )
    db.add(stage)
    db.commit()
    db.refresh(stage)
    return stage


@router.post("/task-stages/reorder", response_model=list[TaskStageResponse])
def reorder_task_stages(
    body: TaskStageReorder,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_platform_admin(current_user)
    stages = {
        s.id: s for s in db.query(TaskStage).filter(TaskStage.deleted_at.is_(None)).all()
    }
    for index, stage_id in enumerate(body.ordered_ids):
        stage = stages.get(stage_id)
        if stage:
            stage.position = index + 1
    db.commit()
    return db.query(TaskStage).filter(
        TaskStage.deleted_at.is_(None),
    ).order_by(TaskStage.position.asc(), TaskStage.created_at.asc()).all()


@router.patch("/task-stages/{stage_id}", response_model=TaskStageResponse)
def update_task_stage(
    stage_id: uuid.UUID,
    body: TaskStageUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_platform_admin(current_user)
    stage = _get_stage(db, stage_id)
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Stage name cannot be empty")
        stage.name = name
    if "color" in body.model_fields_set:
        stage.color = body.color
    if body.is_default is not None:
        if body.is_default:
            # Only one default at a time — clear the flag on every other stage.
            db.query(TaskStage).filter(TaskStage.id != stage.id).update(
                {TaskStage.is_default: False}, synchronize_session=False
            )
        stage.is_default = body.is_default
    db.commit()
    db.refresh(stage)
    return stage


@router.delete("/task-stages/{stage_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task_stage(
    stage_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_platform_admin(current_user)
    stage = _get_stage(db, stage_id)
    # Detach any videos sitting in this stage so they fall back to "unassigned".
    db.query(Asset).filter(Asset.task_stage_id == stage.id).update(
        {Asset.task_stage_id: None}, synchronize_session=False
    )
    stage.deleted_at = datetime.now(timezone.utc)
    db.commit()


# ── Task list ────────────────────────────────────────────────────────────────

@router.get("/tasks", response_model=list[TaskItem])
def list_tasks(
    stage_id: Optional[str] = Query(
        None, description="Filter by stage UUID, or 'unassigned' for videos with no stage."
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Every video asset across all projects, with its current pipeline stage."""
    require_platform_admin(current_user)

    query = db.query(Asset).filter(
        Asset.asset_type == AssetType.video,
        Asset.deleted_at.is_(None),
    )
    if stage_id == "unassigned":
        query = query.filter(Asset.task_stage_id.is_(None))
    elif stage_id:
        query = query.filter(Asset.task_stage_id == uuid.UUID(stage_id))

    assets = query.order_by(Asset.created_at.desc()).all()
    if not assets:
        return []

    asset_ids = [a.id for a in assets]

    # Bulk-load the latest version per asset and its thumbnail (avoid N+1).
    latest_subq = (
        db.query(
            AssetVersion.asset_id,
            func.max(AssetVersion.version_number).label("max_version"),
        )
        .filter(AssetVersion.asset_id.in_(asset_ids), AssetVersion.deleted_at.is_(None))
        .group_by(AssetVersion.asset_id)
        .subquery()
    )
    latest_versions = (
        db.query(AssetVersion)
        .join(
            latest_subq,
            (AssetVersion.asset_id == latest_subq.c.asset_id)
            & (AssetVersion.version_number == latest_subq.c.max_version),
        )
        .all()
    )
    version_by_asset = {v.asset_id: v for v in latest_versions}
    version_ids = [v.id for v in latest_versions]
    thumb_by_version: dict = {}
    if version_ids:
        for f in db.query(MediaFile).filter(MediaFile.version_id.in_(version_ids)).all():
            if f.s3_key_thumbnail and f.version_id not in thumb_by_version:
                thumb_by_version[f.version_id] = f.s3_key_thumbnail

    # Bulk-load submitters and project names.
    submitter_ids = {a.created_by for a in assets}
    users = {
        u.id: u for u in db.query(User).filter(User.id.in_(submitter_ids)).all()
    } if submitter_ids else {}
    project_ids = {a.project_id for a in assets}
    projects = {
        p.id: p for p in db.query(Project).filter(Project.id.in_(project_ids)).all()
    } if project_ids else {}

    # Resolve request (submission link) titles for grouping.
    from ..models.submission import SubmissionLink
    link_ids = {p.submission_link_id for p in projects.values() if p.submission_link_id}
    links = {
        l.id: l for l in db.query(SubmissionLink).filter(SubmissionLink.id.in_(link_ids)).all()
    } if link_ids else {}

    out: list[TaskItem] = []
    for a in assets:
        version = version_by_asset.get(a.id)
        thumb_key = thumb_by_version.get(version.id) if version else None
        submitter = users.get(a.created_by)
        project = projects.get(a.project_id)
        req_id = project.submission_link_id if project else None
        req = links.get(req_id) if req_id else None
        out.append(TaskItem(
            asset_id=a.id,
            name=a.name,
            project_id=a.project_id,
            project_name=project.name if project else None,
            request_id=req_id,
            request_title=req.title if req else None,
            task_stage_id=a.task_stage_id,
            run_as_ad=a.run_as_ad,
            submitter_name=(submitter.name if submitter else None),
            submitter_email=(submitter.email if submitter else None),
            thumbnail_url=generate_presigned_get_url(thumb_key) if thumb_key else None,
            latest_version_number=version.version_number if version else None,
            created_at=a.created_at,
        ))
    return out


@router.patch("/assets/{asset_id}/task-stage", response_model=TaskItem)
def set_asset_task_stage(
    asset_id: uuid.UUID,
    body: TaskStageAssign,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Move a video to a pipeline stage (or back to unassigned)."""
    require_platform_admin(current_user)
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.deleted_at.is_(None)).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    if body.task_stage_id is not None:
        _get_stage(db, body.task_stage_id)  # validate it exists / not deleted
    asset.task_stage_id = body.task_stage_id
    db.commit()
    db.refresh(asset)

    submitter = db.query(User).filter(User.id == asset.created_by).first()
    project = db.query(Project).filter(Project.id == asset.project_id).first()
    from ..models.submission import SubmissionLink
    req = (
        db.query(SubmissionLink).filter(SubmissionLink.id == project.submission_link_id).first()
        if project and project.submission_link_id else None
    )
    return TaskItem(
        asset_id=asset.id,
        name=asset.name,
        project_id=asset.project_id,
        project_name=project.name if project else None,
        request_id=(project.submission_link_id if project else None),
        request_title=(req.title if req else None),
        task_stage_id=asset.task_stage_id,
        run_as_ad=asset.run_as_ad,
        submitter_name=(submitter.name if submitter else None),
        submitter_email=(submitter.email if submitter else None),
        thumbnail_url=None,
        latest_version_number=None,
        created_at=asset.created_at,
    )


@router.patch("/assets/{asset_id}/run-as-ad", response_model=TaskItem)
def set_asset_run_as_ad(
    asset_id: uuid.UUID,
    body: RunAsAdAssign,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a video as cleared to run as an ad (or clear the flag).

    External platforms can then pull only the ad-ready set via the public API."""
    require_platform_admin(current_user)
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.deleted_at.is_(None)).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    asset.run_as_ad = body.run_as_ad
    db.commit()
    db.refresh(asset)

    submitter = db.query(User).filter(User.id == asset.created_by).first()
    project = db.query(Project).filter(Project.id == asset.project_id).first()
    from ..models.submission import SubmissionLink
    req = (
        db.query(SubmissionLink).filter(SubmissionLink.id == project.submission_link_id).first()
        if project and project.submission_link_id else None
    )
    return TaskItem(
        asset_id=asset.id,
        name=asset.name,
        project_id=asset.project_id,
        project_name=project.name if project else None,
        request_id=(project.submission_link_id if project else None),
        request_title=(req.title if req else None),
        task_stage_id=asset.task_stage_id,
        run_as_ad=asset.run_as_ad,
        submitter_name=(submitter.name if submitter else None),
        submitter_email=(submitter.email if submitter else None),
        thumbnail_url=None,
        latest_version_number=None,
        created_at=asset.created_at,
    )
