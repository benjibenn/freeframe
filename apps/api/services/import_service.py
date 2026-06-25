"""Bucket-scan importer: register existing S3 objects as freeframe assets."""
import os
import uuid
from sqlalchemy.orm import Session

from ..models.asset import Asset, AssetVersion, MediaFile, AssetType, ProcessingStatus, FileType
from ..models.project import Project
from ..schemas.upload import mime_to_asset_type
from . import brief_import_service
from .s3_service import list_objects_v2
from ..tasks.celery_app import send_task_safe
from ..tasks.transcode_tasks import process_asset

# Map lowercase file extension -> MIME type (covers all ALLOWED_MIME_TYPES extensions)
EXT_TO_MIME: dict[str, str] = {
    # Video
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
    ".avi": "video/x-msvideo",
    ".wmv": "video/x-ms-wmv",
    ".mpeg": "video/mpeg",
    ".mpg": "video/mpeg",
    # Image
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".heic": "image/heic",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    # Audio
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".m4a": "audio/x-m4a",
}

_ASSET_TYPE_TO_FILE_TYPE: dict[AssetType, FileType] = {
    AssetType.video: FileType.video,
    AssetType.image: FileType.image,
    AssetType.audio: FileType.audio,
    AssetType.image_carousel: FileType.image,
}

# Maximum objects to scan per import request (prevents runaway listing)
MAX_IMPORT_OBJECTS = 1000


def register_s3_object_as_asset(
    db: Session,
    project_id: uuid.UUID,
    s3_key: str,
    name: str,
    size: int,
    mime_type: str,
    created_by: uuid.UUID,
    folder_id: uuid.UUID | None = None,
) -> Asset:
    """Create Asset + AssetVersion(processing) + MediaFile(s3_key_raw=s3_key) for an object
    already in S3, commit, enqueue process_asset transcode, and return the Asset."""
    asset_type = mime_to_asset_type(mime_type)
    file_type = _ASSET_TYPE_TO_FILE_TYPE[asset_type]

    project = db.query(Project).filter(Project.id == project_id).first()
    cf = brief_import_service.cf_ids_for_project(db, project) if project else {
        "cf_brief_id": None, "cf_persona_id": None, "cf_angle_id": None,
    }

    asset = Asset(
        project_id=project_id,
        name=name,
        asset_type=asset_type,
        created_by=created_by,
        folder_id=folder_id,
        **cf,
    )
    db.add(asset)
    db.flush()

    needs_transcode = asset_type == AssetType.video

    version = AssetVersion(
        asset_id=asset.id,
        version_number=1,
        processing_status=ProcessingStatus.processing if needs_transcode else ProcessingStatus.ready,
        created_by=created_by,
    )
    db.add(version)
    db.flush()

    media_file = MediaFile(
        version_id=version.id,
        file_type=file_type,
        original_filename=name,
        mime_type=mime_type,
        file_size_bytes=size,
        s3_key_raw=s3_key,
        s3_key_processed=None if needs_transcode else s3_key,
    )
    db.add(media_file)
    db.commit()

    if needs_transcode:
        send_task_safe(process_asset, str(asset.id), str(version.id))

    return asset


def import_prefix(
    db: Session,
    project_id: uuid.UUID,
    prefix: str,
    created_by: uuid.UUID,
    folder_id: uuid.UUID | None = None,
) -> dict:
    """Scan an S3 prefix; register each media object as an asset and enqueue transcode.

    Idempotent: skips objects whose s3 key is already a MediaFile.s3_key_raw in this project.

    Returns {"imported": int, "skipped": int, "failed": list[dict], "truncated": bool, "assets": [...]}.
    """
    imported = 0
    skipped = 0
    failed: list[dict] = []
    results: list[dict] = []

    objects = list_objects_v2(prefix, max_keys=MAX_IMPORT_OBJECTS)
    truncated = len(objects) >= MAX_IMPORT_OBJECTS

    for obj in objects:
        key: str = obj["key"]
        size: int = obj["size"]

        # Skip directory markers and empty objects
        if key.endswith("/") or size == 0:
            skipped += 1
            continue

        ext = os.path.splitext(key)[1].lower()
        if ext not in EXT_TO_MIME:
            skipped += 1
            continue

        mime_type = EXT_TO_MIME[ext]

        # Dedupe: skip if this S3 key is already registered in THIS project
        # (allows the same key to be imported into a different project, and allows
        #  re-import after soft-delete of the asset in this project)
        existing = (
            db.query(MediaFile.id)
            .join(AssetVersion, MediaFile.version_id == AssetVersion.id)
            .join(Asset, AssetVersion.asset_id == Asset.id)
            .filter(
                MediaFile.s3_key_raw == key,
                Asset.project_id == project_id,
                Asset.deleted_at.is_(None),
                AssetVersion.deleted_at.is_(None),
            )
            .first()
        )
        if existing:
            skipped += 1
            continue

        try:
            name = os.path.basename(key)
            asset = register_s3_object_as_asset(
                db, project_id, key, name, size, mime_type, created_by, folder_id
            )
            results.append({"id": str(asset.id), "name": name})
            imported += 1
        except Exception as e:
            db.rollback()
            failed.append({"key": key, "error": str(e)})
            continue

    return {
        "imported": imported,
        "skipped": skipped,
        "failed": failed,
        "truncated": truncated,
        "assets": results,
    }
