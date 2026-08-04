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
from sqlalchemy import and_, false, func, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.user import User
from ..models.project import Project
from ..models.asset import Asset, AssetVersion, MediaFile, AssetType
from ..models.task_stage import TaskStage
from ..models.submission import Submission, SubmissionLink
from ..services.folder_paths import (
    folder_paths,
    asset_path_filter,
    resolve_asset_path,
    link_home_paths,
    resolve_link_home_path,
)
from ..schemas.task_stage import (
    TaskStageResponse,
    TaskStageCreate,
    TaskStageUpdate,
    TaskStageReorder,
    TaskStageAssign,
    BulkTaskStageAssign,
    RunAsAdAssign,
    TaskItem,
    BriefEditor,
    BriefTaskItem,
    BriefAssigneeAssign,
    TaskBoardResponse,
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

def _build_task_items(db: Session, assets: list[Asset]) -> list[TaskItem]:
    """Turn Asset rows into TaskItems, bulk-loading every relation.

    Shared by /tasks and /task-board so the two can never drift on what a row
    means — the board is the same data grouped by brief.
    """
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

    folder_path_by_id = folder_paths(db, {a.folder_id for a in assets if a.folder_id})

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
            asset_type=a.asset_type,
            folder_id=a.folder_id,
            # Unfiled assets still get a path — the project name alone.
            folder_path=resolve_asset_path(a, folder_path_by_id, project.name if project else None),
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


@router.get("/tasks", response_model=list[TaskItem])
def list_tasks(
    stage_id: Optional[str] = Query(
        None, description="Filter by stage UUID, or 'unassigned' for videos with no stage."
    ),
    folder_path: Optional[str] = Query(
        None, description="Restrict to a taxonomy path and everything under it, e.g. 'Skincare/GlowCo'."
    ),
    asset_type: str = Query(
        "all", description="'all' (default), or a single AssetType such as 'video' or 'image'."
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Every video asset across all projects, with its current pipeline stage."""
    require_platform_admin(current_user)

    query = db.query(Asset).filter(Asset.deleted_at.is_(None))
    # The board used to be hardcoded to video. Static-image ads are a first-class
    # deliverable here, and excluding them meant a whole workflow had no board.
    if asset_type != "all":
        try:
            query = query.filter(Asset.asset_type == AssetType(asset_type))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown asset_type: {asset_type}")
    if stage_id == "unassigned":
        query = query.filter(Asset.task_stage_id.is_(None))
    elif stage_id:
        query = query.filter(Asset.task_stage_id == uuid.UUID(stage_id))

    if folder_path:
        # Covers real folders, stamped submission paths, and bare project
        # membership — a niche filter that omitted submitted work would be worse
        # than no filter at all.
        query = query.filter(asset_path_filter(db, folder_path))

    assets = query.order_by(Asset.created_at.desc()).all()
    return _build_task_items(db, assets)



@router.get("/task-board", response_model=TaskBoardResponse)
def get_task_board(
    folder_path: Optional[str] = Query(
        None, description="Restrict to a taxonomy path and everything under it."
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The to-do view: every brief as a work item, with its delivered files nested.

    Briefs come from submission_links, so one appears the moment it is created —
    before anything has been uploaded against it. That is the row /tasks can never
    show, because /tasks lists assets and an un-started brief has none.

    Assets uploaded straight into a project (no request behind them) are returned
    separately rather than dropped, so the board still accounts for everything.
    """
    require_platform_admin(current_user)

    asset_q = db.query(Asset).filter(Asset.deleted_at.is_(None))
    if folder_path:
        asset_q = asset_q.filter(asset_path_filter(db, folder_path))
    items = _build_task_items(db, asset_q.order_by(Asset.created_at.desc()).all())

    by_request: dict = {}
    unbriefed: list[TaskItem] = []
    for it in items:
        (by_request.setdefault(it.request_id, []) if it.request_id else unbriefed).append(it)

    links = (
        db.query(SubmissionLink)
        .filter(SubmissionLink.deleted_at.is_(None))
        .order_by(SubmissionLink.created_at.desc())
        .all()
    )
    # Derived from where each request is filed rather than read off the row, so a
    # renamed folder is reflected immediately. Filtering therefore happens here in
    # Python instead of in SQL — briefs number in the dozens, not the millions, and
    # a filter that disagreed with the path on screen would be worse than slower.
    link_path = link_home_paths(db, links)
    if folder_path:
        # A brief matches on its own path, so an un-started brief is still
        # filterable — it has no assets to match through.
        prefix = folder_path.strip("/")
        links = [
            l for l in links
            if (p := link_path.get(l.id)) and (p == prefix or p.startswith(prefix + "/"))
        ]

    owners = {
        u.id: u for u in db.query(User)
        .filter(User.id.in_({l.assignee_id for l in links if l.assignee_id}))
        .all()
    } if any(l.assignee_id for l in links) else {}

    # Editors per brief: whoever accepted the link. Derived, never stored.
    editors_by_link: dict = {}
    if links:
        rows = (
            db.query(Submission.submission_link_id, User)
            .join(User, User.id == Submission.user_id)
            .filter(Submission.submission_link_id.in_([l.id for l in links]))
            .all()
        )
        for link_id, user in rows:
            editors_by_link.setdefault(link_id, []).append(
                BriefEditor(id=user.id, name=user.name, email=user.email)
            )

    briefs = [
        BriefTaskItem(
            id=l.id,
            title=l.title,
            taxonomy_path=link_path.get(l.id),
            task_stage_id=l.task_stage_id,
            assignee_id=l.assignee_id,
            assignee_name=(owners[l.assignee_id].name if l.assignee_id in owners else None),
            editors=editors_by_link.get(l.id, []),
            has_brief=bool(l.brief_pdf_s3_key),
            has_brief_json=bool(l.brief_json),
            created_at=l.created_at,
            assets=by_request.get(l.id, []),
        )
        for l in links
    ]

    return TaskBoardResponse(briefs=briefs, unbriefed=unbriefed)


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


@router.patch("/assets/bulk/stage")
def bulk_set_asset_task_stage(
    body: BulkTaskStageAssign,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Move many videos to a pipeline stage at once (multi-select bulk edit)."""
    require_platform_admin(current_user)
    if not body.asset_ids:
        raise HTTPException(status_code=422, detail="asset_ids is empty")
    if len(body.asset_ids) > 200:
        raise HTTPException(status_code=413, detail="Too many asset_ids (max 200)")
    if body.task_stage_id is not None:
        _get_stage(db, body.task_stage_id)  # validate it exists / not deleted
    assets = db.query(Asset).filter(
        Asset.id.in_(body.asset_ids), Asset.deleted_at.is_(None)
    ).all()
    found = {a.id for a in assets}
    missing = [str(a) for a in body.asset_ids if a not in found]
    if missing:
        raise HTTPException(status_code=404, detail=f"Assets not found: {', '.join(missing)}")
    for asset in assets:
        asset.task_stage_id = body.task_stage_id
    db.commit()
    return {"updated": len(assets)}


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


@router.patch("/submission-links/{link_id}/task-stage", response_model=BriefTaskItem)
def set_brief_task_stage(
    link_id: uuid.UUID,
    body: TaskStageAssign,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Move a brief along the pipeline.

    Dedicated endpoint rather than PATCH /submission-links, which replaces the
    whole record — a board dropdown must not need the title and expiry in hand
    just to change a stage.
    """
    require_platform_admin(current_user)
    link = db.query(SubmissionLink).filter(
        SubmissionLink.id == link_id, SubmissionLink.deleted_at.is_(None)
    ).first()
    if not link:
        raise HTTPException(status_code=404, detail="Request not found")
    if body.task_stage_id is not None:
        _get_stage(db, body.task_stage_id)
    link.task_stage_id = body.task_stage_id
    db.commit()
    db.refresh(link)
    return _brief_item(db, link)


@router.patch("/submission-links/{link_id}/assignee", response_model=BriefTaskItem)
def set_brief_assignee(
    link_id: uuid.UUID,
    body: BriefAssigneeAssign,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Set the internal owner — whose desk the brief sits on. Distinct from the
    editors who accepted the link, which is derived and not settable here."""
    require_platform_admin(current_user)
    link = db.query(SubmissionLink).filter(
        SubmissionLink.id == link_id, SubmissionLink.deleted_at.is_(None)
    ).first()
    if not link:
        raise HTTPException(status_code=404, detail="Request not found")
    if body.assignee_id is not None:
        owner = db.query(User).filter(User.id == body.assignee_id).first()
        if not owner:
            raise HTTPException(status_code=404, detail="User not found")
    link.assignee_id = body.assignee_id
    db.commit()
    db.refresh(link)
    return _brief_item(db, link)


def _brief_item(db: Session, link: SubmissionLink) -> BriefTaskItem:
    """One brief, without its assets — the PATCH endpoints return the row the
    board just changed, and the board already holds the nested files."""
    owner = db.query(User).filter(User.id == link.assignee_id).first() if link.assignee_id else None
    editors = [
        BriefEditor(id=u.id, name=u.name, email=u.email)
        for _, u in db.query(Submission.submission_link_id, User)
        .join(User, User.id == Submission.user_id)
        .filter(Submission.submission_link_id == link.id)
        .all()
    ]
    return BriefTaskItem(
        id=link.id,
        title=link.title,
        taxonomy_path=resolve_link_home_path(db, link),
        task_stage_id=link.task_stage_id,
        assignee_id=link.assignee_id,
        assignee_name=owner.name if owner else None,
        editors=editors,
        has_brief=bool(link.brief_pdf_s3_key),
        has_brief_json=bool(link.brief_json),
        created_at=link.created_at,
        assets=[],
    )
