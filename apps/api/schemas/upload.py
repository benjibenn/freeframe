from pydantic import BaseModel, field_validator

from ..services import source_link
import uuid
from ..models.asset import AssetType

ALLOWED_MIME_TYPES = {
    # Images
    "image/jpeg", "image/png", "image/webp", "image/heic", "image/tiff", "image/gif",
    # Audio
    "audio/mpeg", "audio/wav", "audio/flac", "audio/aac", "audio/ogg", "audio/x-m4a",
    # Video
    "video/mp4", "video/quicktime", "video/x-msvideo", "video/x-matroska",
    "video/webm", "video/mpeg", "video/x-ms-wmv",
}

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024 * 1024  # 10 GB
CHUNK_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

def mime_to_asset_type(mime_type: str) -> AssetType:
    if mime_type.startswith("image/"):
        return AssetType.image
    elif mime_type.startswith("audio/"):
        return AssetType.audio
    elif mime_type.startswith("video/"):
        return AssetType.video
    raise ValueError(f"Unsupported mime type: {mime_type}")

class InitiateUploadRequest(BaseModel):
    project_id: uuid.UUID
    asset_name: str
    original_filename: str
    mime_type: str
    file_size_bytes: int
    # For new version of existing asset
    asset_id: uuid.UUID | None = None
    folder_id: uuid.UUID | None = None
    # Which of the brief's output_languages this file is. Required only when the
    # request's brief lists more than one; ignored everywhere else.
    language: str | None = None
    # Where the artwork lives (Figma, Canva, …). Required on every upload, new
    # asset or new version: initiate is the last moment the uploader is present,
    # and a delivered render carries no trace of what it was made from. Kept as
    # the version's first comment — see services/source_link.
    source_url: str

    @field_validator("source_url")
    @classmethod
    def _source_url_present(cls, v: str) -> str:
        return source_link.normalize(v)

class InitiateUploadResponse(BaseModel):
    upload_id: str
    s3_key: str
    asset_id: uuid.UUID
    version_id: uuid.UUID

class PresignPartRequest(BaseModel):
    s3_key: str
    upload_id: str
    part_number: int  # 1-indexed

class PresignPartResponse(BaseModel):
    presigned_url: str
    part_number: int

class UploadPart(BaseModel):
    PartNumber: int
    ETag: str

class CompleteUploadRequest(BaseModel):
    s3_key: str
    upload_id: str
    asset_id: uuid.UUID
    version_id: uuid.UUID
    parts: list[UploadPart]

class CompleteUploadResponse(BaseModel):
    status: str
    asset_id: uuid.UUID
    version_id: uuid.UUID

class AbortUploadRequest(BaseModel):
    s3_key: str
    upload_id: str
    version_id: uuid.UUID
