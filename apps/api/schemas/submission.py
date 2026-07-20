from pydantic import BaseModel
import uuid
from datetime import datetime
from typing import Any, Optional


class SubmissionLinkCreate(BaseModel):
    title: str
    instructions: Optional[str] = None
    expires_at: Optional[datetime] = None


class BriefJsonUpdate(BaseModel):
    # The structured brief object, or null to clear it. Free-form: stored as-is and
    # rendered defensively (only known sections are shown), so briefs can vary in shape.
    brief: Optional[dict[str, Any]] = None


class SubmissionLinkResponse(BaseModel):
    id: uuid.UUID
    token: str
    title: str
    instructions: Optional[str] = None
    is_enabled: bool
    expires_at: Optional[datetime] = None
    created_at: datetime
    submission_count: int = 0
    # True when a brief PDF is attached (flywheel-imported or hand-uploaded).
    has_brief: bool = False
    # True when a structured JSON brief is attached. brief_json itself is only
    # populated on the detail endpoint (kept out of list payloads).
    has_brief_json: bool = False
    brief_json: Optional[dict[str, Any]] = None
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


class ChildProjectItem(BaseModel):
    project_id: uuid.UUID
    name: str
    asset_count: int
    is_reference: bool = False


class SubmissionItem(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_name: str
    user_email: str
    display_name: Optional[str] = None  # Owner-set handle override (None => account name)
    project_id: uuid.UUID
    asset_count: int
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
