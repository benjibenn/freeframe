from pydantic import BaseModel
import uuid
from datetime import datetime


class FrameTagCreate(BaseModel):
    version_id: uuid.UUID
    timecode_start: float
    label: str


class FrameTagResponse(BaseModel):
    id: uuid.UUID
    asset_id: uuid.UUID
    version_id: uuid.UUID
    timecode_start: float
    label: str
    created_by: uuid.UUID
    created_at: datetime
    model_config = {"from_attributes": True}
