"""Media library — cross-project asset browser with per-user access grants.

Access rules:
  Platform admins (superadmin / sub-admin): see all assets across all projects.
  Everyone else: assets visible when ANY of the following is true:
    1. created_by == me (own uploads, including submission projects)
    2. explicit LibraryAccess grant for that project (folder_id IS NULL)
    3. explicit LibraryAccess grant for that project+folder
    4. user is a ProjectMember of the project (covers submission projects automatically)
"""
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, or_, exists, and_
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.user import User
from ..models.project import Project
from ..models.folder import Folder
from ..models.asset import Asset, AssetVersion, MediaFile, AssetType
from ..models.library_access import LibraryAccess
from ..models.project import ProjectMember
from ..services.permissions import is_platform_admin
from ..services.s3_service import generate_presigned_get_url

router = APIRouter(tags=["library"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class LibraryAssetItem(BaseModel):
    id: uuid.UUID
    name: str
    asset_type: AssetType
    project_id: uuid.UUID
    project_name: str
    folder_id: Optional[uuid.UUID] = None
    folder_name: Optional[str] = None
    keywords: Optional[list] = None
    thumbnail_url: Optional[str] = None
    created_by: uuid.UUID
    created_at: datetime


class LibraryAccessGrant(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    project_id: uuid.UUID
    project_name: str
    folder_id: Optional[uuid.UUID] = None
    folder_name: Optional[str] = None
    granted_by: uuid.UUID
    created_at: datetime


class LibraryAccessCreate(BaseModel):
    user_id: uuid.UUID
    project_id: uuid.UUID
    folder_id: Optional[uuid.UUID] = None


class LibraryUserSummary(BaseModel):
    id: uuid.UUID
    name: Optional[str]
    email: str
    grants: list[LibraryAccessGrant] = []


class LibraryProjectOption(BaseModel):
    id: uuid.UUID
    name: str


class LibraryFolderOption(BaseModel):
    id: uuid.UUID
    name: str


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _require_admin(current_user: User) -> None:
    if not is_platform_admin(current_user):
        raise HTTPException(status_code=403, detail="Platform admin required")


def _access_filter(query, current_user: User):
    """Apply access-control filter to an Asset query for non-admin users."""
    return query.filter(
        or_(
            # Own uploads (includes their submission project assets)
            Asset.created_by == current_user.id,
            # Explicit library access grant at project level
            exists().where(
                and_(
                    LibraryAccess.user_id == current_user.id,
                    LibraryAccess.project_id == Asset.project_id,
                    LibraryAccess.folder_id.is_(None),
                )
            ),
            # Explicit library access grant at folder level
            exists().where(
                and_(
                    LibraryAccess.user_id == current_user.id,
                    LibraryAccess.project_id == Asset.project_id,
                    LibraryAccess.folder_id == Asset.folder_id,
                )
            ),
            # ProjectMember: covers submission projects and any explicit membership
            exists().where(
                and_(
                    ProjectMember.user_id == current_user.id,
                    ProjectMember.project_id == Asset.project_id,
                    ProjectMember.deleted_at.is_(None),
                )
            ),
        )
    )


# ─── Asset listing ────────────────────────────────────────────────────────────

@router.get("/library", response_model=dict)
def list_library_assets(
    page: int = Query(1, ge=1),
    per_page: int = Query(24, ge=1, le=100),
    project_id: Optional[uuid.UUID] = Query(None),
    tag: Optional[list[str]] = Query(None),
    frame_label: Optional[list[str]] = Query(None),
    q: Optional[str] = Query(None, description="Name search"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Asset).filter(Asset.deleted_at.is_(None))

    if not is_platform_admin(current_user):
        query = _access_filter(query, current_user)

    if project_id:
        query = query.filter(Asset.project_id == project_id)

    if q:
        query = query.filter(Asset.name.ilike(f"%{q.strip()}%"))

    if tag:
        from sqlalchemy import cast
        from sqlalchemy.dialects.postgresql import JSONB
        for t in tag:
            query = query.filter(
                Asset.keywords.cast(JSONB).contains(cast([t], JSONB))
            )

    if frame_label:
        from ..models.frame_tag import FrameTag
        for label in frame_label:
            subq = (
                db.query(FrameTag.asset_id)
                .filter(FrameTag.label == label, FrameTag.deleted_at.is_(None))
                .subquery()
            )
            query = query.filter(Asset.id.in_(subq))

    total = query.count()
    assets = query.order_by(Asset.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()

    if not assets:
        return {"items": [], "total": total, "page": page, "per_page": per_page}

    asset_ids = [a.id for a in assets]
    project_ids = list({a.project_id for a in assets})
    folder_ids = list({a.folder_id for a in assets if a.folder_id})

    projects = {p.id: p for p in db.query(Project).filter(Project.id.in_(project_ids)).all()}
    folders = {f.id: f for f in db.query(Folder).filter(Folder.id.in_(folder_ids)).all()} if folder_ids else {}

    # Bulk load thumbnails (one per asset via latest version)
    latest_subq = (
        db.query(AssetVersion.asset_id, func.max(AssetVersion.version_number).label("max_v"))
        .filter(AssetVersion.asset_id.in_(asset_ids), AssetVersion.deleted_at.is_(None))
        .group_by(AssetVersion.asset_id)
        .subquery()
    )
    latest_versions = (
        db.query(AssetVersion)
        .join(latest_subq, (AssetVersion.asset_id == latest_subq.c.asset_id) & (AssetVersion.version_number == latest_subq.c.max_v))
        .all()
    )
    version_by_asset = {v.asset_id: v for v in latest_versions}
    version_ids = [v.id for v in latest_versions]
    thumb_by_version: dict = {}
    if version_ids:
        for f in db.query(MediaFile).filter(MediaFile.version_id.in_(version_ids)).all():
            if f.s3_key_thumbnail and f.version_id not in thumb_by_version:
                thumb_by_version[f.version_id] = f.s3_key_thumbnail

    items = []
    for a in assets:
        version = version_by_asset.get(a.id)
        thumb_key = thumb_by_version.get(version.id) if version else None
        project = projects.get(a.project_id)
        folder = folders.get(a.folder_id) if a.folder_id else None
        items.append(LibraryAssetItem(
            id=a.id,
            name=a.name,
            asset_type=a.asset_type,
            project_id=a.project_id,
            project_name=project.name if project else "Unknown",
            folder_id=a.folder_id,
            folder_name=folder.name if folder else None,
            keywords=a.keywords,
            thumbnail_url=generate_presigned_get_url(thumb_key) if thumb_key else None,
            created_by=a.created_by,
            created_at=a.created_at,
        ))

    return {"items": [i.model_dump() for i in items], "total": total, "page": page, "per_page": per_page}


# ─── Projects visible to this user (for filter dropdown) ─────────────────────

@router.get("/library/projects", response_model=list[LibraryProjectOption])
def list_library_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if is_platform_admin(current_user):
        projects = db.query(Project).filter(Project.deleted_at.is_(None)).order_by(Project.name).all()
    else:
        pid_set: set = set()
        # Library access grants
        for r in db.query(LibraryAccess.project_id).filter(LibraryAccess.user_id == current_user.id).distinct().all():
            pid_set.add(r[0])
        # Own uploaded assets
        for r in db.query(Asset.project_id).filter(Asset.created_by == current_user.id, Asset.deleted_at.is_(None)).distinct().all():
            pid_set.add(r[0])
        # ProjectMember (submission projects and other explicit memberships)
        for r in db.query(ProjectMember.project_id).filter(ProjectMember.user_id == current_user.id, ProjectMember.deleted_at.is_(None)).distinct().all():
            pid_set.add(r[0])
        if not pid_set:
            return []
        projects = db.query(Project).filter(Project.id.in_(pid_set), Project.deleted_at.is_(None)).order_by(Project.name).all()
    return [LibraryProjectOption(id=p.id, name=p.name) for p in projects]


# ─── Access grant management (admin only) ────────────────────────────────────

@router.get("/library/grants", response_model=list[LibraryUserSummary])
def list_library_grants(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)

    grants = db.query(LibraryAccess).all()
    project_ids = list({g.project_id for g in grants})
    folder_ids = list({g.folder_id for g in grants if g.folder_id})
    user_ids = list({g.user_id for g in grants})

    projects = {p.id: p for p in db.query(Project).filter(Project.id.in_(project_ids)).all()} if project_ids else {}
    folders = {f.id: f for f in db.query(Folder).filter(Folder.id.in_(folder_ids)).all()} if folder_ids else {}
    users = {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}

    # Group grants by user
    by_user: dict[uuid.UUID, list[LibraryAccessGrant]] = {}
    for g in grants:
        project = projects.get(g.project_id)
        folder = folders.get(g.folder_id) if g.folder_id else None
        by_user.setdefault(g.user_id, []).append(LibraryAccessGrant(
            id=g.id,
            user_id=g.user_id,
            project_id=g.project_id,
            project_name=project.name if project else "Unknown",
            folder_id=g.folder_id,
            folder_name=folder.name if folder else None,
            granted_by=g.granted_by,
            created_at=g.created_at,
        ))

    result = []
    for user_id, user_grants in by_user.items():
        u = users.get(user_id)
        if not u:
            continue
        result.append(LibraryUserSummary(
            id=u.id,
            name=u.name,
            email=u.email,
            grants=sorted(user_grants, key=lambda x: x.project_name),
        ))
    return sorted(result, key=lambda x: x.email)


@router.get("/library/users", response_model=list[LibraryUserSummary])
def list_grantable_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """All non-admin users — used to populate the grant management UI."""
    _require_admin(current_user)
    users = db.query(User).filter(
        User.deleted_at.is_(None),
        User.is_superadmin.is_(False),
        User.is_subadmin.is_(False),
    ).order_by(User.email).all()

    grants = db.query(LibraryAccess).filter(
        LibraryAccess.user_id.in_([u.id for u in users])
    ).all()
    project_ids = list({g.project_id for g in grants})
    folder_ids = list({g.folder_id for g in grants if g.folder_id})
    projects = {p.id: p for p in db.query(Project).filter(Project.id.in_(project_ids)).all()} if project_ids else {}
    folders = {f.id: f for f in db.query(Folder).filter(Folder.id.in_(folder_ids)).all()} if folder_ids else {}

    by_user: dict[uuid.UUID, list[LibraryAccessGrant]] = {}
    for g in grants:
        project = projects.get(g.project_id)
        folder = folders.get(g.folder_id) if g.folder_id else None
        by_user.setdefault(g.user_id, []).append(LibraryAccessGrant(
            id=g.id,
            user_id=g.user_id,
            project_id=g.project_id,
            project_name=project.name if project else "Unknown",
            folder_id=g.folder_id,
            folder_name=folder.name if folder else None,
            granted_by=g.granted_by,
            created_at=g.created_at,
        ))

    return [
        LibraryUserSummary(id=u.id, name=u.name, email=u.email, grants=by_user.get(u.id, []))
        for u in users
    ]


@router.post("/library/grants", status_code=status.HTTP_201_CREATED, response_model=LibraryAccessGrant)
def create_library_grant(
    body: LibraryAccessCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)

    # Idempotent: return existing if already granted
    existing_q = db.query(LibraryAccess).filter(
        LibraryAccess.user_id == body.user_id,
        LibraryAccess.project_id == body.project_id,
    )
    if body.folder_id is None:
        existing_q = existing_q.filter(LibraryAccess.folder_id.is_(None))
    else:
        existing_q = existing_q.filter(LibraryAccess.folder_id == body.folder_id)
    existing = existing_q.first()

    if not existing:
        grant = LibraryAccess(
            user_id=body.user_id,
            project_id=body.project_id,
            folder_id=body.folder_id,
            granted_by=current_user.id,
        )
        db.add(grant)
        db.commit()
        db.refresh(grant)
        existing = grant

    project = db.query(Project).filter(Project.id == existing.project_id).first()
    folder = db.query(Folder).filter(Folder.id == existing.folder_id).first() if existing.folder_id else None
    return LibraryAccessGrant(
        id=existing.id,
        user_id=existing.user_id,
        project_id=existing.project_id,
        project_name=project.name if project else "Unknown",
        folder_id=existing.folder_id,
        folder_name=folder.name if folder else None,
        granted_by=existing.granted_by,
        created_at=existing.created_at,
    )


@router.delete("/library/grants/{grant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_library_grant(
    grant_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    grant = db.query(LibraryAccess).filter(LibraryAccess.id == grant_id).first()
    if not grant:
        raise HTTPException(status_code=404, detail="Grant not found")
    db.delete(grant)
    db.commit()


@router.get("/library/folders/{project_id}", response_model=list[LibraryFolderOption])
def list_project_folders_for_grant(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Flat list of all folders in a project — used by the grant management UI."""
    _require_admin(current_user)
    folders = db.query(Folder).filter(
        Folder.project_id == project_id,
        Folder.deleted_at.is_(None),
    ).order_by(Folder.name).all()
    return [LibraryFolderOption(id=f.id, name=f.name) for f in folders]
