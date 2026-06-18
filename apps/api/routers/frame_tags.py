import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.asset import Asset
from ..models.frame_tag import FrameTag
from ..models.project import ProjectRole
from ..models.user import User
from ..schemas.frame_tag import FrameTagCreate, FrameTagResponse
from ..services.permissions import can_view_project, is_platform_admin, require_project_role

router = APIRouter(tags=["frame_tags"])


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_asset(db: Session, asset_id: uuid.UUID) -> Asset:
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.deleted_at.is_(None)).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


def _build_frame_tag_response(ft: FrameTag) -> FrameTagResponse:
    return FrameTagResponse(
        id=ft.id,
        asset_id=ft.asset_id,
        version_id=ft.version_id,
        timecode_start=ft.timecode_start,
        label=ft.label,
        created_by=ft.created_by,
        created_at=ft.created_at,
    )


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post(
    "/assets/{asset_id}/frame-tags",
    response_model=FrameTagResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_frame_tag(
    asset_id: uuid.UUID,
    body: FrameTagCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    asset = _get_asset(db, asset_id)

    if not is_platform_admin(current_user):
        require_project_role(db, asset.project_id, current_user, ProjectRole.editor)

    if body.timecode_start < 0:
        raise HTTPException(status_code=422, detail="timecode_start must be >= 0")

    label = body.label.strip().lower()
    if not label:
        raise HTTPException(status_code=422, detail="label must not be empty")

    ft = FrameTag(
        asset_id=asset_id,
        version_id=body.version_id,
        timecode_start=body.timecode_start,
        label=label,
        created_by=current_user.id,
    )
    db.add(ft)
    db.commit()
    db.refresh(ft)
    return _build_frame_tag_response(ft)


@router.get("/assets/{asset_id}/frame-tags", response_model=list[FrameTagResponse])
def list_frame_tags(
    asset_id: uuid.UUID,
    version_id: Optional[uuid.UUID] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    asset = _get_asset(db, asset_id)

    if not can_view_project(db, asset.project_id, current_user):
        raise HTTPException(status_code=403, detail="Access denied")

    query = db.query(FrameTag).filter(
        FrameTag.asset_id == asset_id,
        FrameTag.deleted_at.is_(None),
    )
    if version_id:
        query = query.filter(FrameTag.version_id == version_id)
    tags = query.order_by(FrameTag.timecode_start).all()
    return [_build_frame_tag_response(ft) for ft in tags]


@router.delete("/frame-tags/{frame_tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_frame_tag(
    frame_tag_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ft = db.query(FrameTag).filter(
        FrameTag.id == frame_tag_id,
        FrameTag.deleted_at.is_(None),
    ).first()
    if not ft:
        raise HTTPException(status_code=404, detail="Frame tag not found")

    asset = _get_asset(db, ft.asset_id)

    if not is_platform_admin(current_user):
        require_project_role(db, asset.project_id, current_user, ProjectRole.editor)

    ft.deleted_at = datetime.now(timezone.utc)
    db.commit()
