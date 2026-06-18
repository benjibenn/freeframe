import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.project import ProjectRole
from ..models.tag_palette import TagPaletteLabel
from ..models.user import User
from ..schemas.tag_palette import TagPaletteCreate, TagPaletteUpdate, TagPaletteResponse
from ..services.permissions import can_view_project, is_platform_admin, require_project_role

router = APIRouter(tags=["tag_palette"])


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_label(db: Session, label_id: uuid.UUID) -> TagPaletteLabel:
    row = db.query(TagPaletteLabel).filter(
        TagPaletteLabel.id == label_id,
        TagPaletteLabel.deleted_at.is_(None),
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Tag palette label not found")
    return row


def _build_response(row: TagPaletteLabel) -> TagPaletteResponse:
    return TagPaletteResponse(
        id=row.id,
        project_id=row.project_id,
        label=row.label,
        color=row.color,
        position=row.position,
    )


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/tag-palette", response_model=list[TagPaletteResponse])
def list_tag_palette(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not can_view_project(db, project_id, current_user):
        raise HTTPException(status_code=403, detail="Access denied")

    rows = (
        db.query(TagPaletteLabel)
        .filter(
            TagPaletteLabel.project_id == project_id,
            TagPaletteLabel.deleted_at.is_(None),
        )
        .order_by(TagPaletteLabel.position.asc(), TagPaletteLabel.created_at.asc())
        .all()
    )
    return [_build_response(r) for r in rows]


@router.post(
    "/projects/{project_id}/tag-palette",
    response_model=TagPaletteResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_tag_palette_label(
    project_id: uuid.UUID,
    body: TagPaletteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not is_platform_admin(current_user):
        require_project_role(db, project_id, current_user, ProjectRole.editor)

    label = body.label.strip()
    if not label:
        raise HTTPException(status_code=422, detail="label must not be empty")

    # next position = current max + 1
    from sqlalchemy import func as sqlfunc
    max_pos = db.query(sqlfunc.max(TagPaletteLabel.position)).filter(
        TagPaletteLabel.project_id == project_id,
        TagPaletteLabel.deleted_at.is_(None),
    ).scalar()
    next_position = (max_pos or 0) + 1

    row = TagPaletteLabel(
        project_id=project_id,
        label=label,
        color=body.color,
        position=next_position,
        created_by=current_user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _build_response(row)


@router.patch("/tag-palette/{label_id}", response_model=TagPaletteResponse)
def update_tag_palette_label(
    label_id: uuid.UUID,
    body: TagPaletteUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = _get_label(db, label_id)

    if not is_platform_admin(current_user):
        require_project_role(db, row.project_id, current_user, ProjectRole.editor)

    if body.label is not None:
        label = body.label.strip()
        if not label:
            raise HTTPException(status_code=422, detail="label must not be empty")
        row.label = label

    if body.color is not None:
        row.color = body.color

    if body.position is not None:
        row.position = body.position

    db.commit()
    db.refresh(row)
    return _build_response(row)


@router.delete("/tag-palette/{label_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag_palette_label(
    label_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = _get_label(db, label_id)

    if not is_platform_admin(current_user):
        require_project_role(db, row.project_id, current_user, ProjectRole.editor)

    row.deleted_at = datetime.now(timezone.utc)
    db.commit()
