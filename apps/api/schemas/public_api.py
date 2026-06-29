"""Schemas for the public (machine-to-machine) integration API."""
from pydantic import BaseModel
import uuid
from datetime import datetime
from typing import Optional
from ..models.asset import AssetType, AssetStatus


class PublicVideoItem(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    status: AssetStatus
    asset_type: AssetType
    # Whether this video has been cleared (by an admin) to run as an ad.
    run_as_ad: bool = False
    project_id: uuid.UUID
    project_name: Optional[str] = None
    # The user who created/submitted the asset.
    author_name: Optional[str] = None
    author_email: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    # Latest ready version + its media file.
    version_id: Optional[uuid.UUID] = None
    version_number: Optional[int] = None
    duration_seconds: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    original_filename: Optional[str] = None
    thumbnail_url: Optional[str] = None
    # Short-lived presigned URL to download the original video file.
    download_url: Optional[str] = None
    # External (CF) lineage stamped onto the asset at creation (NULL if the asset
    # wasn't created under an imported request). The handoff to UploadUnicorn.
    cf_brief_id: Optional[str] = None
    cf_persona_id: Optional[str] = None
    cf_angle_id: Optional[str] = None


class PublicVideoListResponse(BaseModel):
    items: list[PublicVideoItem]
    total: int
    page: int
    per_page: int


class PublicVideoDownload(BaseModel):
    id: uuid.UUID
    name: str
    download_url: str
    mime_type: Optional[str] = None
    file_size_bytes: Optional[int] = None
    original_filename: Optional[str] = None
    expires_in: int


class PublicUserItem(BaseModel):
    """A user the external integration can attribute work to. Only users with an
    admin-granted `uid` are exposed here — the uid is the deliberate "known
    editor" marker. The internal UUID is intentionally NOT included."""
    uid: int
    name: str
    email: str
    nickname: Optional[str] = None
