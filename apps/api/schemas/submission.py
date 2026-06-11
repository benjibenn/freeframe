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
    model_config = {"from_attributes": True}


# Public payload returned to a visitor opening /submit/{token}.
# Deliberately minimal: title + instructions only, never the submitter list.
class SubmissionLinkPublic(BaseModel):
    title: str
    instructions: Optional[str] = None
    requires_auth: bool


class SubmissionAcceptResponse(BaseModel):
    project_id: uuid.UUID


class SubmissionItem(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_name: str
    user_email: str
    project_id: uuid.UUID
    asset_count: int
    created_at: datetime
