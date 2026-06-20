from pydantic import BaseModel
import uuid
from datetime import datetime
from typing import Optional


class SubmissionLinkCreate(BaseModel):
    title: str
    instructions: Optional[str] = None
    expires_at: Optional[datetime] = None


class SubmissionLinkResponse(BaseModel):
    id: uuid.UUID
    token: str
    title: str
    instructions: Optional[str] = None
    is_enabled: bool
    expires_at: Optional[datetime] = None
    created_at: datetime
    submission_count: int = 0
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
