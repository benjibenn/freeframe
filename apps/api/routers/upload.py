import os
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
import uuid
from datetime import datetime, timezone
from ..config import settings
from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.user import User
from ..models.asset import Asset, AssetVersion, MediaFile, AssetType, ProcessingStatus, FileType
from ..models.activity import ActivityLog, ActivityAction
from ..models.project import Project
from ..services.s3_service import (
    create_multipart_upload, presign_upload_part,
    complete_multipart_upload, abort_multipart_upload,
)
from ..services.permissions import get_project_member, require_project_role
from ..models.project import ProjectRole
from ..schemas.upload import (
    InitiateUploadRequest, InitiateUploadResponse,
    PresignPartRequest, PresignPartResponse,
    CompleteUploadRequest, CompleteUploadResponse, AbortUploadRequest,
    ALLOWED_MIME_TYPES, MAX_FILE_SIZE_BYTES, mime_to_asset_type,
)

router = APIRouter(prefix="/upload", tags=["upload"])

@router.post("/initiate", response_model=InitiateUploadResponse)
def initiate_upload(
    body: InitiateUploadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Validate mime type
    if body.mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {body.mime_type}")
    if body.file_size_bytes > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds 10GB limit")

    # Verify project access (editor or above)
    project = db.query(Project).filter(Project.id == body.project_id, Project.deleted_at.is_(None)).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    require_project_role(db, body.project_id, current_user, ProjectRole.editor)

    # Get or create asset
    if body.asset_id:
        asset = db.query(Asset).filter(Asset.id == body.asset_id, Asset.deleted_at.is_(None)).first()
        if not asset:
            raise HTTPException(status_code=404, detail="Asset not found")
        if asset.project_id != body.project_id:
            raise HTTPException(status_code=400, detail="Asset does not belong to the specified project")
    else:
        from ..services import brief_import_service
        from ..services.hook_naming import next_hook_name, variation_names
        from ..models.submission import SubmissionLink
        from ..services.folder_paths import resolve_link_home_path
        asset_type = mime_to_asset_type(body.mime_type)
        cf = brief_import_service.cf_ids_for_project(db, project)
        name = body.asset_name
        taxonomy_path = None
        if project.submission_link_id:
            # Submitters never free-name uploads. When the link's brief prescribes
            # deliverable names, the client must pick one of them; otherwise every
            # new asset is auto-numbered "Hook N". Lock the project row first so
            # concurrent initiates (one per file in a multi-file selection) are
            # numbered Hook 1..N instead of all reading the same highest number.
            link = db.query(SubmissionLink).filter(
                SubmissionLink.id == project.submission_link_id
            ).first()
            # The link is what knows which product this request is for; the
            # per-submitter project cannot express it, having no folder tree.
            # Resolved live from where the request is filed, so an upload after a
            # folder rename is stamped with the new name rather than a stale one.
            taxonomy_path = resolve_link_home_path(db, link) if link else None
            allowed = variation_names(link.brief_json) if link else []
            if allowed:
                if body.asset_name not in allowed:
                    raise HTTPException(
                        status_code=400,
                        detail="Asset name must be one of the brief's deliverable names",
                    )
                name = body.asset_name
            else:
                db.query(Project).filter(Project.id == project.id).with_for_update().first()
                name = next_hook_name(db, project.id)
        asset = Asset(
            project_id=body.project_id,
            name=name,
            asset_type=asset_type,
            created_by=current_user.id,
            folder_id=body.folder_id,
            taxonomy_path=taxonomy_path,
            **cf,
        )
        # New media lands in the configured default task stage (e.g. "Pending")
        # so it shows up triaged in the admin task list right away. Images are
        # included: static ads are a deliverable in their own right, and skipping
        # them left every one of them permanently unassigned on the board.
        #
        # The References library is the exception: it is a swipe file, not work.
        # The task board is global (`db.query(Asset)` with no project filter), so
        # stamping a stage here would put every clipped competitor ad on it.
        is_references = (
            settings.references_project_id
            and str(body.project_id) == settings.references_project_id
        )
        if asset_type in (AssetType.video, AssetType.image) and not is_references:
            from ..models.task_stage import TaskStage
            default_stage = db.query(TaskStage).filter(
                TaskStage.is_default.is_(True),
                TaskStage.deleted_at.is_(None),
            ).first()
            if default_stage:
                asset.task_stage_id = default_stage.id
        db.add(asset)
        db.flush()

    # Get next version number
    last_version = db.query(AssetVersion).filter(
        AssetVersion.asset_id == asset.id,
        AssetVersion.deleted_at.is_(None),
    ).order_by(AssetVersion.version_number.desc()).first()
    next_version_number = (last_version.version_number + 1) if last_version else 1

    # Build S3 key: raw/{project_id}/{asset_id}/{version_id}/{filename}
    version = AssetVersion(
        asset_id=asset.id,
        version_number=next_version_number,
        processing_status=ProcessingStatus.uploading,
        created_by=current_user.id,
    )
    db.add(version)
    db.flush()

    ext = os.path.splitext(body.original_filename)[1].lower()
    s3_key = f"raw/{body.project_id}/{asset.id}/{version.id}/original{ext}"

    # Initiate S3 multipart upload
    upload_id = create_multipart_upload(s3_key, body.mime_type)

    # Create MediaFile record
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
        asset_id=asset.id,
        version_id=version.id,
    )


@router.post("/presign-part", response_model=PresignPartResponse)
def presign_part(
    body: PresignPartRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.part_number < 1 or body.part_number > 10000:
        raise HTTPException(status_code=400, detail="Part number must be between 1 and 10000")

    # Verify the s3_key belongs to an upload initiated by this user
    media_file = db.query(MediaFile).filter(MediaFile.s3_key_raw == body.s3_key).first()
    if not media_file:
        raise HTTPException(status_code=404, detail="Upload not found")
    version = db.query(AssetVersion).filter(AssetVersion.id == media_file.version_id).first()
    if not version or version.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this upload")

    url = presign_upload_part(body.s3_key, body.upload_id, body.part_number)
    return PresignPartResponse(presigned_url=url, part_number=body.part_number)


@router.post("/complete", response_model=CompleteUploadResponse)
def complete_upload(
    body: CompleteUploadRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Validate DB first
    version = db.query(AssetVersion).filter(
        AssetVersion.id == body.version_id,
        AssetVersion.deleted_at.is_(None),
    ).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    if version.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this upload")

    # Then complete S3 multipart
    complete_multipart_upload(body.s3_key, body.upload_id, [p.model_dump() for p in body.parts])

    asset = db.query(Asset).filter(Asset.id == version.asset_id).first()
    media_file = db.query(MediaFile).filter(MediaFile.version_id == version.id).first() if asset else None

    # Images and audio don't need transcoding — serve the raw file directly.
    # Videos still need HLS transcoding for adaptive streaming and private bucket access.
    needs_transcode = asset and asset.asset_type == AssetType.video
    # Images serve raw immediately, but still need a processing pass for the
    # WebP + thumbnail the grids render from (and so HEIC/HEIF is viewable at all).
    needs_processing = needs_transcode or (
        asset and asset.asset_type in (AssetType.image, AssetType.image_carousel)
    )
    if needs_transcode:
        version.processing_status = ProcessingStatus.processing
    else:
        version.processing_status = ProcessingStatus.ready
        if media_file:
            media_file.s3_key_processed = media_file.s3_key_raw

    # Record activity so the upload surfaces in the activity feed.
    if asset:
        db.add(ActivityLog(
            user_id=current_user.id,
            asset_id=asset.id,
            project_id=asset.project_id,
            action=ActivityAction.created,
            payload={
                "version_number": version.version_number,
                "is_new_asset": version.version_number == 1,
                "filename": media_file.original_filename if media_file else None,
            },
        ))

    db.commit()

    if needs_processing:
        background_tasks.add_task(_trigger_processing, body.asset_id, body.version_id)

    return CompleteUploadResponse(status="processing" if needs_transcode else "ready", asset_id=body.asset_id, version_id=body.version_id)


def _trigger_processing(asset_id: uuid.UUID, version_id: uuid.UUID):
    """Dispatch Celery task to process the uploaded asset."""
    from ..tasks.transcode_tasks import process_asset
    from ..tasks.celery_app import send_task_safe
    send_task_safe(process_asset, str(asset_id), str(version_id))


@router.post("/abort", status_code=status.HTTP_204_NO_CONTENT)
def abort_upload(
    body: AbortUploadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    version = db.query(AssetVersion).filter(
        AssetVersion.id == body.version_id,
        AssetVersion.deleted_at.is_(None),
    ).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    if version.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this upload")

    abort_multipart_upload(body.s3_key, body.upload_id)
    version.processing_status = ProcessingStatus.failed
    db.commit()
