from pydantic import BaseModel
import uuid
from datetime import datetime
from typing import Optional


class DriveSyncConnectionCreate(BaseModel):
    folder_link: str
    target_project_id: uuid.UUID


class DriveSyncConnectionUpdate(BaseModel):
    enabled: Optional[bool] = None


class DriveSyncConnectionResponse(BaseModel):
    id: uuid.UUID
    drive_folder_id: str
    folder_name: Optional[str]
    target_project_id: uuid.UUID
    enabled: bool
    last_synced_at: Optional[datetime]
    last_error: Optional[str]
    synced_count: int = 0
    model_config = {"from_attributes": True}
