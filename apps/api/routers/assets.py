from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
import os
import uuid
from datetime import datetime, timezone
from typing import Literal, Optional
from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.user import User
from ..models.asset import Asset, AssetVersion, MediaFile, AssetType, AssetStatus, FileType, ProcessingStatus
from ..models.frame_tag import FrameTag
from ..models.project import Project, ProjectMember, ProjectRole
from ..models.share import AssetShare
from ..models.activity import Mention, Notification, NotificationType, ActivityAction
from ..schemas.asset import AssetResponse, AssetVersionResponse, AssetUpdate, StreamUrlResponse, MediaFileResponse, TagsUpdate, TagCount
from ..schemas.notification import AssignmentUpdate
from ..services.permissions import require_project_role, require_asset_access, can_access_asset, is_public_project, get_project_member, can_view_project, is_platform_admin, require_platform_admin
from ..services.s3_service import generate_presigned_get_url, build_download_filename
from .hls_proxy import create_hls_token
from ..schemas.upload import InitiateUploadRequest, InitiateUploadResponse, ALLOWED_MIME_TYPES, MAX_FILE_SIZE_BYTES, mime_to_asset_type
from ..services.s3_service import create_multipart_upload
from ..services.tags import normalize_tags
from ..services.activity_service import log_asset_activity
from ..config import settings
from ..tasks.celery_app import send_task_safe

router = APIRouter(tags=["assets"])

# Tags are stored in Asset.keywords (a JSONB string array). We normalize on write so
# "B-roll", "b-roll " and "b-roll" all collapse to one canonical tag — that keeps
# search and grouping-by-tag consistent.
MAX_TAGS = 50
MAX_TAG_LEN = 50


def _build_asset_response(asset: Asset, db: Session) -> AssetResponse:
    """Build AssetResponse with latest version and its files."""
    latest_version = db.query(AssetVersion).filter(
        AssetVersion.asset_id == asset.id,
        AssetVersion.deleted_at.is_(None),
    ).order_by(AssetVersion.version_number.desc()).first()

    version_response = None
    thumbnail_url = None
    if latest_version:
        files = db.query(MediaFile).filter(MediaFile.version_id == latest_version.id).all()
        version_response = AssetVersionResponse.model_validate(latest_version)
        version_response.files = [MediaFileResponse.model_validate(f) for f in files]
        # Get thumbnail from first file that has one.
        # Audio stores waveform JSON in s3_key_thumbnail — skip it, it's not an image.
        if asset.asset_type != AssetType.audio:
            for f in files:
                if f.s3_key_thumbnail:
                    thumbnail_url = generate_presigned_get_url(f.s3_key_thumbnail)
                    break

    resp = AssetResponse.model_validate(asset)
    resp.latest_version = version_response
    resp.thumbnail_url = thumbnail_url
    return resp


def _build_asset_responses_bulk(assets: list[Asset], db: Session) -> list[AssetResponse]:
    """Build AssetResponse list with bulk-loaded versions and files (no N+1)."""
    if not assets:
        return []

    asset_ids = [a.id for a in assets]

    # Bulk load latest version per asset using a subquery
    latest_version_subq = (
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
        .join(latest_version_subq, (AssetVersion.asset_id == latest_version_subq.c.asset_id) & (AssetVersion.version_number == latest_version_subq.c.max_version))
        .all()
    )
    version_by_asset = {v.asset_id: v for v in latest_versions}

    # Bulk load media files for all those versions
    version_ids = [v.id for v in latest_versions]
    all_files = db.query(MediaFile).filter(MediaFile.version_id.in_(version_ids)).all() if version_ids else []
    files_by_version: dict = {}
    for f in all_files:
        files_by_version.setdefault(f.version_id, []).append(f)

    result = []
    for asset in assets:
        version = version_by_asset.get(asset.id)
        version_response = None
        thumbnail_url = None
        if version:
            files = files_by_version.get(version.id, [])
            version_response = AssetVersionResponse.model_validate(version)
            version_response.files = [MediaFileResponse.model_validate(f) for f in files]
            # Audio stores waveform JSON in s3_key_thumbnail — skip it, it's not an image.
            if asset.asset_type != AssetType.audio:
                for f in files:
                    if f.s3_key_thumbnail:
                        thumbnail_url = generate_presigned_get_url(f.s3_key_thumbnail)
                        break

        asset_resp = AssetResponse.model_validate(asset)
        asset_resp.latest_version = version_response
        asset_resp.thumbnail_url = thumbnail_url
        result.append(asset_resp)
    return result


@router.get("/projects/{project_id}/assets", response_model=list[AssetResponse])
def list_assets(
    project_id: uuid.UUID,
    include_failed: bool = Query(False, description="Include assets whose latest version failed processing"),
    folder_id: Optional[str] = Query(None, description="Filter by folder. 'root' for root level, UUID for specific folder."),
    tag: Optional[list[str]] = Query(None, description="Filter to assets carrying ALL of these tags. Searches the whole project (ignores folder)."),
    frame_label: Optional[list[str]] = Query(None, description="Filter to assets that have at least one frame tag with ANY of these labels."),
    exclude_archived: bool = Query(False, description="Exclude assets with status=archived. Defaults to False so the project grid is unchanged."),
    skip: int = Query(0, ge=0, description="Pagination offset (newest-first)."),
    limit: Optional[int] = Query(None, ge=1, le=200, description="Page size. Omit to return all (backward compatible)."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Allow access if user is a project member, the project is public, or platform admin
    if not can_view_project(db, project_id, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a project member")

    query = db.query(Asset).filter(
        Asset.project_id == project_id,
        Asset.deleted_at.is_(None),
    )

    if exclude_archived:
        query = query.filter(Asset.status != AssetStatus.archived)

    tags = normalize_tags(tag)
    labels = [l.strip().lower() for l in (frame_label or []) if l.strip()]
    filtering = bool(tags or labels)

    if tags:
        # Tag filtering is project-wide (across all folders) — selecting a tag is a
        # search, not folder navigation. Each tag narrows further (AND / containment).
        for t in tags:
            query = query.filter(Asset.keywords.contains([t]))

    if labels:
        # Filter to assets that have at least one non-deleted frame tag with any of the given labels.
        subq = (
            db.query(FrameTag.asset_id)
            .filter(FrameTag.label.in_(labels), FrameTag.deleted_at.is_(None))
            .distinct()
            .subquery()
        )
        query = query.filter(Asset.id.in_(subq))

    if not filtering:
        if folder_id == "root":
            query = query.filter(Asset.folder_id.is_(None))
        elif folder_id is not None:
            query = query.filter(Asset.folder_id == uuid.UUID(folder_id))

    if not include_failed:
        # Exclude assets whose only version failed or is still uploading. Done in
        # SQL (not Python) so that `offset/limit` below returns full pages — keep an
        # asset if it has a usable version, OR has no versions yet (just created).
        usable_version = (
            db.query(AssetVersion.id)
            .filter(
                AssetVersion.asset_id == Asset.id,
                AssetVersion.deleted_at.is_(None),
                AssetVersion.processing_status.notin_([ProcessingStatus.failed, ProcessingStatus.uploading]),
            )
            .exists()
        )
        any_version = (
            db.query(AssetVersion.id)
            .filter(
                AssetVersion.asset_id == Asset.id,
                AssetVersion.deleted_at.is_(None),
            )
            .exists()
        )
        query = query.filter(or_(usable_version, ~any_version))

    # Newest-first so paginated loads stay in a stable order matching the grid's
    # default sort. The frontend detects "end of list" when a page is short.
    query = query.order_by(Asset.created_at.desc())

    if limit is not None:
        query = query.offset(skip).limit(limit)

    assets = query.all()
    return _build_asset_responses_bulk(assets, db)


@router.get("/assets/{asset_id}", response_model=AssetResponse)
def get_asset(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.deleted_at.is_(None)).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    require_asset_access(db, asset, current_user)
    return _build_asset_response(asset, db)


@router.patch("/assets/{asset_id}", response_model=AssetResponse)
def update_asset(
    asset_id: uuid.UUID,
    body: AssetUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.deleted_at.is_(None)).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    # Platform admins manage every project; others need editor role or higher.
    if not is_platform_admin(current_user):
        require_project_role(db, asset.project_id, current_user, ProjectRole.editor)
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "keywords":
            value = normalize_tags(value)
        setattr(asset, field, value)
    db.commit()
    db.refresh(asset)
    return _build_asset_response(asset, db)


class BulkStatusRequest(BaseModel):
    asset_ids: list[uuid.UUID]
    status: AssetStatus


@router.patch("/assets/bulk/status")
def bulk_update_asset_status(
    body: BulkStatusRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Set the review status on many assets at once (multi-select bulk edit).

    Same permission rule as the single-asset PATCH: platform admins manage every
    project; everyone else needs editor role or higher on each asset's project."""
    if not body.asset_ids:
        raise HTTPException(status_code=422, detail="asset_ids is empty")
    if len(body.asset_ids) > 200:
        raise HTTPException(status_code=413, detail="Too many asset_ids (max 200)")
    assets = db.query(Asset).filter(
        Asset.id.in_(body.asset_ids), Asset.deleted_at.is_(None)
    ).all()
    found = {a.id for a in assets}
    missing = [str(a) for a in body.asset_ids if a not in found]
    if missing:
        raise HTTPException(status_code=404, detail=f"Assets not found: {', '.join(missing)}")
    # Enforce edit permission on every asset before mutating any of them.
    if not is_platform_admin(current_user):
        for asset in assets:
            require_project_role(db, asset.project_id, current_user, ProjectRole.editor)
    for asset in assets:
        asset.status = body.status
    db.commit()
    return {"updated": len(assets)}


class BulkRunAsAdRequest(BaseModel):
    asset_ids: list[uuid.UUID]
    run_as_ad: bool


@router.patch("/assets/bulk/run-as-ad")
def bulk_update_run_as_ad(
    body: BulkRunAsAdRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Toggle the run-as-ad flag on many assets at once (multi-select bulk edit).

    Same permission rule as the single-asset PATCH: platform-admin only. run_as_ad
    is the clearance flag external ad platforms filter by, so it isn't delegable
    to project editors the way status/tags are."""
    require_platform_admin(current_user)
    if not body.asset_ids:
        raise HTTPException(status_code=422, detail="asset_ids is empty")
    if len(body.asset_ids) > 200:
        raise HTTPException(status_code=413, detail="Too many asset_ids (max 200)")
    assets = db.query(Asset).filter(
        Asset.id.in_(body.asset_ids), Asset.deleted_at.is_(None)
    ).all()
    found = {a.id for a in assets}
    missing = [str(a) for a in body.asset_ids if a not in found]
    if missing:
        raise HTTPException(status_code=404, detail=f"Assets not found: {', '.join(missing)}")
    for asset in assets:
        asset.run_as_ad = body.run_as_ad
    db.commit()
    return {"updated": len(assets)}


@router.put("/assets/{asset_id}/tags", response_model=AssetResponse)
def set_asset_tags(
    asset_id: uuid.UUID,
    body: TagsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Replace an asset's tags (stored in keywords). Editor role or higher required."""
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.deleted_at.is_(None)).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    # Platform admins (superadmin / sub-admin) manage every project and run triage, so
    # they can tag any asset; otherwise editor role or higher on the project is required.
    if not is_platform_admin(current_user):
        require_project_role(db, asset.project_id, current_user, ProjectRole.editor)
    asset.keywords = normalize_tags(body.tags)
    db.commit()
    db.refresh(asset)
    return _build_asset_response(asset, db)


def _load_editable_asset(asset_id: uuid.UUID, db: Session, current_user: User) -> Asset:
    """Fetch a live asset and enforce tag-edit permission (admin or editor+)."""
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.deleted_at.is_(None)).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    if not is_platform_admin(current_user):
        require_project_role(db, asset.project_id, current_user, ProjectRole.editor)
    return asset


@router.post("/assets/{asset_id}/tags/{tag}", response_model=AssetResponse)
def add_asset_tag(
    asset_id: uuid.UUID,
    tag: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a single normalized keyword. Idempotent. Atomic vs PUT /tags so fast
    keyboard tagging can't clobber concurrent writes."""
    asset = _load_editable_asset(asset_id, db, current_user)
    normalized = normalize_tags([tag])
    if not normalized:
        raise HTTPException(status_code=422, detail="Tag is empty after normalization")
    canonical = normalized[0]
    current = list(asset.keywords or [])
    if canonical not in current:
        if len(current) >= MAX_TAGS:
            raise HTTPException(status_code=409, detail=f"Tag limit ({MAX_TAGS}) reached")
        current.append(canonical)
        asset.keywords = current
        db.commit()
        db.refresh(asset)
    return _build_asset_response(asset, db)


@router.delete("/assets/{asset_id}/tags/{tag}", response_model=AssetResponse)
def remove_asset_tag(
    asset_id: uuid.UUID,
    tag: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a single normalized keyword. Idempotent."""
    asset = _load_editable_asset(asset_id, db, current_user)
    normalized = normalize_tags([tag])
    if not normalized:
        return _build_asset_response(asset, db)
    canonical = normalized[0]
    current = list(asset.keywords or [])
    if canonical in current:
        asset.keywords = [t for t in current if t != canonical]
        db.commit()
        db.refresh(asset)
    return _build_asset_response(asset, db)


class AutotagBatchRequest(BaseModel):
    asset_ids: list[uuid.UUID]
    skip_if_tagged: bool = True


@router.post("/assets/autotag-batch")
def autotag_batch_endpoint(
    body: AutotagBatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not is_platform_admin(current_user):
        raise HTTPException(status_code=403, detail="AI tagging is limited to platform admins")
    if not settings.gemini_api_key:
        raise HTTPException(status_code=503, detail="AI tagging is not configured")
    if not body.asset_ids:
        raise HTTPException(status_code=422, detail="asset_ids is empty")
    if len(body.asset_ids) > 200:
        raise HTTPException(status_code=413, detail="Too many asset_ids (max 200)")
    for aid in body.asset_ids:
        _load_editable_asset(aid, db, current_user)
    from ..tasks.autotag_tasks import autotag_batch
    send_task_safe(autotag_batch, [str(a) for a in body.asset_ids], body.skip_if_tagged)
    return {"status": "queued", "count": len(body.asset_ids)}


@router.post("/assets/{asset_id}/autotag")
def autotag_single(
    asset_id: uuid.UUID,
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not is_platform_admin(current_user):
        raise HTTPException(status_code=403, detail="AI tagging is limited to platform admins")
    if not settings.gemini_api_key:
        raise HTTPException(status_code=503, detail="AI tagging is not configured")
    _load_editable_asset(asset_id, db, current_user)  # 404 + asset-level access
    # ready-only: skip versions still uploading/processing (incomplete S3 object → futile retries)
    version = db.query(AssetVersion).filter(
        AssetVersion.asset_id == asset_id,
        AssetVersion.deleted_at.is_(None),
        AssetVersion.processing_status == ProcessingStatus.ready,
    ).order_by(AssetVersion.version_number.desc()).first()
    if not version:
        raise HTTPException(status_code=404, detail="No version to tag")
    from ..tasks.autotag_tasks import autotag_asset
    send_task_safe(autotag_asset, str(asset_id), str(version.id), force)
    return {"status": "queued"}


@router.post("/projects/{project_id}/autotag")
def autotag_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Queue AI tagging for every asset in the project (already-tagged skipped).
    Selection happens server-side so the bulk action covers the whole project,
    not just the asset pages the browser has loaded."""
    if not is_platform_admin(current_user):
        raise HTTPException(status_code=403, detail="AI tagging is limited to platform admins")
    if not settings.gemini_api_key:
        raise HTTPException(status_code=503, detail="AI tagging is not configured")
    project = db.query(Project).filter(Project.id == project_id, Project.deleted_at.is_(None)).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    ids = [str(row[0]) for row in db.query(Asset.id).filter(
        Asset.project_id == project_id,
        Asset.deleted_at.is_(None),
    ).all()]
    if not ids:
        return {"status": "queued", "count": 0}
    from ..tasks.autotag_tasks import autotag_batch
    send_task_safe(autotag_batch, ids, True)
    return {"status": "queued", "count": len(ids)}


@router.get("/projects/{project_id}/tags", response_model=list[TagCount])
def list_project_tags(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Every distinct tag used in the project, with how many assets carry it —
    powers the project tag filter and tag autocomplete."""
    if not can_view_project(db, project_id, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a project member")
    rows = db.query(Asset.keywords).filter(
        Asset.project_id == project_id,
        Asset.deleted_at.is_(None),
        Asset.keywords.isnot(None),
    ).all()
    counter: dict[str, int] = {}
    for (kw,) in rows:
        for t in (kw or []):
            if isinstance(t, str) and t:
                counter[t] = counter.get(t, 0) + 1
    # Most-used first, then alphabetical for a stable order.
    ordered = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    return [TagCount(tag=t, count=c) for t, c in ordered]


@router.delete("/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.deleted_at.is_(None)).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    require_project_role(db, asset.project_id, current_user, ProjectRole.editor)
    asset.deleted_at = datetime.now(timezone.utc)
    db.commit()


@router.get("/assets/{asset_id}/versions", response_model=list[AssetVersionResponse])
def list_asset_versions(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.deleted_at.is_(None)).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    require_asset_access(db, asset, current_user)

    versions = db.query(AssetVersion).filter(
        AssetVersion.asset_id == asset_id,
        AssetVersion.deleted_at.is_(None),
    ).order_by(AssetVersion.version_number.desc()).all()

    result = []
    version_ids = [v.id for v in versions]
    all_files = db.query(MediaFile).filter(MediaFile.version_id.in_(version_ids)).all() if version_ids else []
    files_by_version: dict = {}
    for f in all_files:
        files_by_version.setdefault(f.version_id, []).append(f)

    for v in versions:
        vr = AssetVersionResponse.model_validate(v)
        vr.files = [MediaFileResponse.model_validate(f) for f in files_by_version.get(v.id, [])]
        result.append(vr)
    return result


class AssetTrackRequest(BaseModel):
    action: Literal["clicked", "viewed"]


_TRACK_ACTION_MAP = {
    "clicked": ActivityAction.asset_clicked.value,
    "viewed": ActivityAction.asset_viewed.value,
}


@router.post("/assets/{asset_id}/track", status_code=status.HTTP_204_NO_CONTENT)
def track_asset_activity(
    asset_id: uuid.UUID,
    body: AssetTrackRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Record a soft click/view signal for the current user on an asset.

    Only callable by users who can access the asset. Download is intentionally
    not trackable here — it is logged server-side by the download endpoint.
    """
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.deleted_at.is_(None)).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    require_asset_access(db, asset, current_user)

    log_asset_activity(
        db,
        user_id=current_user.id,
        asset_id=asset.id,
        project_id=asset.project_id,
        action=_TRACK_ACTION_MAP[body.action],
        payload={"asset_name": asset.name},
    )
    db.commit()


@router.get("/assets/{asset_id}/stream", response_model=StreamUrlResponse)
def get_stream_url(
    asset_id: uuid.UUID,
    version_id: Optional[uuid.UUID] = Query(default=None),
    download: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.deleted_at.is_(None)).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    require_asset_access(db, asset, current_user)

    # Get the requested version or latest
    if version_id:
        version = db.query(AssetVersion).filter(
            AssetVersion.id == version_id,
            AssetVersion.asset_id == asset_id,
            AssetVersion.deleted_at.is_(None),
        ).first()
    else:
        version = db.query(AssetVersion).filter(
            AssetVersion.asset_id == asset_id,
            AssetVersion.deleted_at.is_(None),
        ).order_by(AssetVersion.version_number.desc()).first()

    if not version:
        raise HTTPException(status_code=404, detail="No version found")

    media_file = db.query(MediaFile).filter(MediaFile.version_id == version.id).first()
    if not media_file:
        raise HTTPException(status_code=404, detail="Media file not found")

    # Streaming/playback needs the transcoded HLS output, which only exists once
    # the version is `ready`. A download, however, can serve the original raw
    # upload as soon as it's stored — so users can pull the file down while
    # transcoding is still running instead of waiting for the whole ladder. The
    # raw file exists from `processing` onward (it's still absent during
    # `uploading`), so only unblock download once we're past that.
    raw_downloadable = (
        download
        and media_file.s3_key_raw
        and version.processing_status in (
            ProcessingStatus.processing,
            ProcessingStatus.ready,
            ProcessingStatus.failed,
        )
    )
    if version.processing_status != ProcessingStatus.ready and not raw_downloadable:
        raise HTTPException(status_code=409, detail="Asset version is not ready yet")

    if asset.asset_type == AssetType.video and media_file.s3_key_processed:
        if download:
            # For video downloads, use the raw file (original upload) so user gets a single file
            s3_key = media_file.s3_key_raw or media_file.s3_key_processed
            filename = build_download_filename(asset.name, media_file.original_filename or s3_key)
            url = generate_presigned_get_url(s3_key, download_filename=filename)
        else:
            # Route through the HLS proxy so the master playlist, variant
            # playlists, and .ts segments all get served via short-lived
            # presigned URLs — the S3 bucket can stay fully private. (#51)
            token = create_hls_token(media_file.s3_key_processed)
            url = f"/stream/hls/master.m3u8?token={token}"
    else:
        s3_key = media_file.s3_key_processed or media_file.s3_key_raw
        if download:
            filename = build_download_filename(asset.name, media_file.original_filename or s3_key)
            url = generate_presigned_get_url(s3_key, download_filename=filename)
        else:
            url = generate_presigned_get_url(s3_key)

    if download:
        log_asset_activity(
            db,
            user_id=current_user.id,
            asset_id=asset.id,
            project_id=asset.project_id,
            action=ActivityAction.asset_downloaded.value,
            payload={"asset_name": asset.name},
        )
        db.commit()

    return StreamUrlResponse(url=url, asset_type=asset.asset_type)


@router.post("/assets/{asset_id}/versions", response_model=InitiateUploadResponse)
def initiate_new_version(
    asset_id: uuid.UUID,
    body: InitiateUploadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Initiate upload of a new version for an existing asset."""
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.deleted_at.is_(None)).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    require_project_role(db, asset.project_id, current_user, ProjectRole.editor)

    if body.mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    if body.file_size_bytes > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds 10GB limit")

    last_version = db.query(AssetVersion).filter(
        AssetVersion.asset_id == asset_id,
        AssetVersion.deleted_at.is_(None),
    ).order_by(AssetVersion.version_number.desc()).first()
    next_version_number = (last_version.version_number + 1) if last_version else 1

    version = AssetVersion(
        asset_id=asset_id,
        version_number=next_version_number,
        processing_status=ProcessingStatus.uploading,
        created_by=current_user.id,
    )
    db.add(version)
    db.flush()

    ext = os.path.splitext(body.original_filename)[1].lower()
    s3_key = f"raw/{asset.project_id}/{asset_id}/{version.id}/original{ext}"
    upload_id = create_multipart_upload(s3_key, body.mime_type)

    file_type_map = {AssetType.image: FileType.image, AssetType.audio: FileType.audio, AssetType.video: FileType.video, AssetType.image_carousel: FileType.image}
    media_file = MediaFile(
        version_id=version.id,
        file_type=file_type_map.get(asset.asset_type, FileType.video),
        original_filename=body.original_filename,
        mime_type=body.mime_type,
        file_size_bytes=body.file_size_bytes,
        s3_key_raw=s3_key,
    )
    db.add(media_file)
    db.commit()

    return InitiateUploadResponse(
        upload_id=upload_id,
        s3_key=s3_key,
        asset_id=asset_id,
        version_id=version.id,
    )


@router.patch("/assets/{asset_id}/assignment", response_model=AssetResponse)
def update_assignment(
    asset_id: uuid.UUID,
    body: AssignmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.deleted_at.is_(None)).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    require_project_role(db, asset.project_id, current_user, ProjectRole.editor)

    if "assignee_id" in body.model_fields_set:
        asset.assignee_id = body.assignee_id
    if "due_date" in body.model_fields_set:
        asset.due_date = body.due_date

    if "assignee_id" in body.model_fields_set and body.assignee_id is not None:
        notification = Notification(
            user_id=body.assignee_id,
            type=NotificationType.assignment,
            asset_id=asset.id,
        )
        db.add(notification)

    db.commit()
    db.refresh(asset)
    return _build_asset_response(asset, db)


@router.post("/assets/{asset_id}/versions/{version_id}/reprocess")
def reprocess_asset_version(
    asset_id: uuid.UUID,
    version_id: uuid.UUID,
    priority: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.deleted_at.is_(None)).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    require_asset_access(db, asset, current_user)

    version = db.query(AssetVersion).filter(
        AssetVersion.id == version_id,
        AssetVersion.asset_id == asset_id,
        AssetVersion.deleted_at.is_(None),
    ).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    version.processing_status = ProcessingStatus.processing
    db.commit()

    from ..tasks.transcode_tasks import process_asset
    from ..tasks.celery_app import send_task_safe
    queue = "transcoding_priority" if priority else None
    send_task_safe(process_asset, str(asset_id), str(version_id), queue=queue)

    return {"status": "requeued", "queue": queue or "transcoding"}


@router.get("/assets/{asset_id}/assignment")
def get_assignment(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.deleted_at.is_(None)).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    require_project_role(db, asset.project_id, current_user, ProjectRole.viewer)
    return {
        "assignee_id": str(asset.assignee_id) if asset.assignee_id else None,
        "due_date": asset.due_date.isoformat() if asset.due_date else None,
    }
