"""Public integration API (machine-to-machine, X-API-Key auth).

Exposes ready videos out to external platforms so they can be searched,
picked, downloaded, and re-uploaded elsewhere (e.g. Meta). Read-only and
scoped across all projects — guarded by a single shared API key, not user JWT.

Served behind the `/api` prefix, so external callers hit:
    GET /api/public/v1/videos
    GET /api/public/v1/videos/{asset_id}/download
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
import uuid
from typing import Optional
from ..database import get_db
from ..middleware.api_key import require_api_key
from ..models.asset import Asset, AssetVersion, MediaFile, AssetType, AssetStatus, ProcessingStatus
from ..models.user import User
from ..models.project import Project
from ..schemas.public_api import PublicVideoItem, PublicVideoListResponse, PublicVideoDownload
from ..services.s3_service import generate_presigned_get_url, build_download_filename

router = APIRouter(prefix="/public/v1", tags=["public-api"], dependencies=[Depends(require_api_key)])

# Presigned download URLs live long enough to fetch a large video and hand it off.
DOWNLOAD_URL_EXPIRY = 6 * 3600


def _pick_media_file(files: list[MediaFile]) -> Optional[MediaFile]:
    """Prefer a video file; otherwise the first file on the version."""
    if not files:
        return None
    for f in files:
        if f.s3_key_raw or f.s3_key_processed:
            if (f.duration_seconds is not None) or (f.width is not None):
                return f
    return files[0]


@router.get("/videos", response_model=PublicVideoListResponse)
def list_videos(
    search: Optional[str] = Query(None, description="Filter by video name (partial, case-insensitive)"),
    author: Optional[str] = Query(None, description="Filter by author name or email (partial, case-insensitive)"),
    asset_status: Optional[AssetStatus] = Query(None, alias="status", description="Filter by review status"),
    asset_type: str = Query("video", description="'video' (default) or 'all' to include every media type"),
    project_id: Optional[uuid.UUID] = Query(None, description="Restrict to a single project"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List ready videos with their download URLs. Only assets that have a
    fully-processed (ready) version are returned, so every item is downloadable."""
    query = (
        db.query(Asset)
        .join(User, Asset.created_by == User.id)
        .filter(Asset.deleted_at.is_(None))
    )

    if asset_type != "all":
        query = query.filter(Asset.asset_type == AssetType.video)
    if search:
        query = query.filter(Asset.name.ilike(f"%{search}%"))
    if asset_status is not None:
        query = query.filter(Asset.status == asset_status)
    if author:
        like = f"%{author}%"
        query = query.filter(or_(User.name.ilike(like), User.email.ilike(like)))
    if project_id is not None:
        query = query.filter(Asset.project_id == project_id)

    # Only assets that have at least one ready version (i.e. downloadable).
    ready_exists = (
        db.query(AssetVersion.id)
        .filter(
            AssetVersion.asset_id == Asset.id,
            AssetVersion.deleted_at.is_(None),
            AssetVersion.processing_status == ProcessingStatus.ready,
        )
        .exists()
    )
    query = query.filter(ready_exists)

    total = query.count()
    assets = (
        query.order_by(Asset.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    if not assets:
        return PublicVideoListResponse(items=[], total=total, page=page, per_page=per_page)

    asset_ids = [a.id for a in assets]

    # Latest READY version per asset (bulk, no N+1).
    latest_ready_subq = (
        db.query(
            AssetVersion.asset_id,
            func.max(AssetVersion.version_number).label("mv"),
        )
        .filter(
            AssetVersion.asset_id.in_(asset_ids),
            AssetVersion.deleted_at.is_(None),
            AssetVersion.processing_status == ProcessingStatus.ready,
        )
        .group_by(AssetVersion.asset_id)
        .subquery()
    )
    versions = (
        db.query(AssetVersion)
        .join(
            latest_ready_subq,
            (AssetVersion.asset_id == latest_ready_subq.c.asset_id)
            & (AssetVersion.version_number == latest_ready_subq.c.mv),
        )
        .all()
    )
    version_by_asset = {v.asset_id: v for v in versions}

    version_ids = [v.id for v in versions]
    all_files = (
        db.query(MediaFile).filter(MediaFile.version_id.in_(version_ids)).all()
        if version_ids
        else []
    )
    files_by_version: dict = {}
    for f in all_files:
        files_by_version.setdefault(f.version_id, []).append(f)

    authors = {u.id: u for u in db.query(User).filter(User.id.in_({a.created_by for a in assets})).all()}
    projects = {p.id: p for p in db.query(Project).filter(Project.id.in_({a.project_id for a in assets})).all()}

    items: list[PublicVideoItem] = []
    for a in assets:
        v = version_by_asset.get(a.id)
        mf = _pick_media_file(files_by_version.get(v.id, [])) if v else None
        author_user = authors.get(a.created_by)
        project = projects.get(a.project_id)

        download_url = None
        thumbnail_url = None
        if mf:
            s3_key = mf.s3_key_raw or mf.s3_key_processed
            if s3_key:
                filename = build_download_filename(a.name, mf.original_filename or s3_key)
                download_url = generate_presigned_get_url(
                    s3_key, expires_in=DOWNLOAD_URL_EXPIRY, download_filename=filename
                )
            if mf.s3_key_thumbnail and a.asset_type != AssetType.audio:
                thumbnail_url = generate_presigned_get_url(mf.s3_key_thumbnail)

        items.append(
            PublicVideoItem(
                id=a.id,
                name=a.name,
                description=a.description,
                status=a.status,
                asset_type=a.asset_type,
                project_id=a.project_id,
                project_name=project.name if project else None,
                author_name=author_user.name if author_user else None,
                author_email=author_user.email if author_user else None,
                created_at=a.created_at,
                updated_at=a.updated_at,
                version_id=v.id if v else None,
                version_number=v.version_number if v else None,
                duration_seconds=mf.duration_seconds if mf else None,
                width=mf.width if mf else None,
                height=mf.height if mf else None,
                file_size_bytes=mf.file_size_bytes if mf else None,
                mime_type=mf.mime_type if mf else None,
                original_filename=mf.original_filename if mf else None,
                thumbnail_url=thumbnail_url,
                download_url=download_url,
            )
        )

    return PublicVideoListResponse(items=items, total=total, page=page, per_page=per_page)


@router.get("/videos/{asset_id}/download", response_model=PublicVideoDownload)
def get_video_download(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Return a fresh presigned URL to download the original video file.

    Use this when a URL from /videos has expired, or to fetch one item directly."""
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.deleted_at.is_(None)).first()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")

    version = (
        db.query(AssetVersion)
        .filter(
            AssetVersion.asset_id == asset_id,
            AssetVersion.deleted_at.is_(None),
            AssetVersion.processing_status == ProcessingStatus.ready,
        )
        .order_by(AssetVersion.version_number.desc())
        .first()
    )
    if not version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No ready version available")

    mf = _pick_media_file(db.query(MediaFile).filter(MediaFile.version_id == version.id).all())
    s3_key = (mf.s3_key_raw or mf.s3_key_processed) if mf else None
    if not mf or not s3_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media file not found")

    filename = build_download_filename(asset.name, mf.original_filename or s3_key)
    url = generate_presigned_get_url(
        s3_key, expires_in=DOWNLOAD_URL_EXPIRY, download_filename=filename
    )

    return PublicVideoDownload(
        id=asset.id,
        name=asset.name,
        download_url=url,
        mime_type=mf.mime_type,
        file_size_bytes=mf.file_size_bytes,
        original_filename=mf.original_filename,
        expires_in=DOWNLOAD_URL_EXPIRY,
    )
