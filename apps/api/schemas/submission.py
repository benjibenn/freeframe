from pydantic import BaseModel
import uuid
from datetime import datetime
from typing import Any, Optional


class SubmissionLinkCreate(BaseModel):
    title: str
    instructions: Optional[str] = None
    # Where the request is filed. A project is required — a request with no home
    # is invisible in the tree, which is the state this replaces. The folder is
    # optional: no folder means the project root.
    home_project_id: uuid.UUID
    home_folder_id: Optional[uuid.UUID] = None
    expires_at: Optional[datetime] = None


class DuplicateLinkRequest(BaseModel):
    """Optional overrides for POST /submission-links/{id}/duplicate. Anything
    omitted is copied from the source; the dialog pre-fills these so the user can
    retitle and re-file the copy before it is created."""
    title: Optional[str] = None
    instructions: Optional[str] = None
    home_project_id: Optional[uuid.UUID] = None
    # Only applied when home_project_id is also given (a folder is meaningless
    # without its project).
    home_folder_id: Optional[uuid.UUID] = None
    brief_json: Optional[dict[str, Any]] = None


class BriefJsonUpdate(BaseModel):
    # The structured brief object, or null to clear it. Free-form: stored as-is and
    # rendered defensively (only known sections are shown), so briefs can vary in shape.
    brief: Optional[dict[str, Any]] = None


class ReferenceVideoPresignRequest(BaseModel):
    filename: str
    content_type: str


class ReferenceVideoPresignResponse(BaseModel):
    # Presigned S3 PUT URL the browser uploads the file to, plus the key it must
    # then confirm back so the server records it on the link.
    url: str
    s3_key: str


class ReferenceVideoConfirm(BaseModel):
    s3_key: str


class SubmissionLinkResponse(BaseModel):
    id: uuid.UUID
    token: str
    title: str
    instructions: Optional[str] = None
    is_enabled: bool
    # Where the request is filed in the shared tree.
    home_project_id: Optional[uuid.UUID] = None
    home_folder_id: Optional[uuid.UUID] = None
    # Full path derived from the folder above ("ecom/Phones/Store 1"), recomputed
    # on read so folder renames carry. Null only for legacy links filed nowhere.
    home_path: Optional[str] = None
    taxonomy_path: Optional[str] = None
    expires_at: Optional[datetime] = None
    created_at: datetime
    submission_count: int = 0
    # True when a brief PDF is attached (flywheel-imported or hand-uploaded).
    has_brief: bool = False
    # True when a structured JSON brief is attached. brief_json itself is only
    # populated on the detail endpoint (kept out of list payloads).
    has_brief_json: bool = False
    brief_json: Optional[dict[str, Any]] = None
    # True when owner-uploaded reference videos are attached.
    has_reference_video: bool = False
    # True when owner-uploaded static reference images are attached.
    has_reference_image: bool = False
    # How many of each — the brief page builds its indexed public URLs from these.
    reference_video_count: int = 0
    reference_image_count: int = 0
    # Shared reference project (None = strict isolation, the default).
    reference_project_id: Optional[uuid.UUID] = None
    # CF campaign labels (None for hand-made requests).
    persona_label: Optional[str] = None
    angle_label: Optional[str] = None
    problem: Optional[str] = None
    model_config = {"from_attributes": True}


# Public payload returned to a visitor opening /submit/{token}.
# Deliberately minimal: title + instructions only, never the submitter list.
class SubmissionLinkPublic(BaseModel):
    title: str
    instructions: Optional[str] = None
    requires_auth: bool
    has_brief: bool = False
    # The structured JSON brief, rendered inline on the submit page (null if none).
    brief_json: Optional[dict[str, Any]] = None
    # True when owner-uploaded reference videos are attached (streamed inline).
    has_reference_video: bool = False
    # True when owner-uploaded static reference images are attached (carousel).
    has_reference_image: bool = False
    # How many of each — the submit page builds its indexed URLs from these.
    reference_video_count: int = 0
    reference_image_count: int = 0
    # CF campaign labels (None for hand-made requests).
    persona_label: Optional[str] = None
    angle_label: Optional[str] = None
    problem: Optional[str] = None


class SubmissionAcceptResponse(BaseModel):
    project_id: uuid.UUID


class ReferenceResponse(BaseModel):
    reference_project_id: Optional[uuid.UUID] = None


class AttachProjectRequest(BaseModel):
    # True => attach as the request's shared reference; False => as a child folder.
    as_reference: bool = False
    # Where the new request is filed. Only read when creating a request
    # (from-project), not when attaching to an existing one — an existing request
    # already has a home. Defaults to the project being converted.
    home_project_id: Optional[uuid.UUID] = None
    home_folder_id: Optional[uuid.UUID] = None


class BulkRefileRequest(BaseModel):
    """Move many requests into one folder at once."""
    link_ids: list[uuid.UUID]
    home_project_id: uuid.UUID
    # Null files them at the project root.
    home_folder_id: Optional[uuid.UUID] = None


class BulkDeleteRequest(BaseModel):
    link_ids: list[uuid.UUID]


class BulkResult(BaseModel):
    # How many rows the call actually changed. Reported rather than assumed: a
    # caller can pass ids it no longer owns, and silently doing nothing would
    # look identical to success.
    updated: int


class ChildProjectItem(BaseModel):
    project_id: uuid.UUID
    name: str
    asset_count: int
    is_reference: bool = False


class SubmissionFile(BaseModel):
    asset_id: uuid.UUID
    name: str


class SubmissionItem(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_name: str
    user_email: str
    display_name: Optional[str] = None  # Owner-set handle override (None => account name)
    project_id: uuid.UUID
    asset_count: int
    files: list[SubmissionFile] = []
    created_at: datetime


class SubmissionUpdate(BaseModel):
    # Empty/whitespace clears the override (falls back to the submitter's account name).
    display_name: Optional[str] = None


class MySubmissionItem(BaseModel):
    submission_id: uuid.UUID
    project_id: uuid.UUID
    project_name: str
    link_id: uuid.UUID
    link_title: str
    link_token: str
    asset_count: int
    created_at: datetime
