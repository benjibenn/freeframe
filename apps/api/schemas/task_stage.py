import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class TaskStageResponse(BaseModel):
    id: uuid.UUID
    name: str
    position: int
    color: Optional[str] = None
    is_default: bool = False
    model_config = {"from_attributes": True}


class TaskStageCreate(BaseModel):
    name: str
    color: Optional[str] = None


class TaskStageUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    is_default: Optional[bool] = None


class TaskStageReorder(BaseModel):
    # Stage ids in the desired display order (top → bottom / left → right).
    ordered_ids: list[uuid.UUID]


class TaskStageAssign(BaseModel):
    # Null moves the video back to "unassigned" (no stage).
    task_stage_id: Optional[uuid.UUID] = None


class BulkTaskStageAssign(BaseModel):
    # Move many videos to a pipeline stage at once (or back to unassigned).
    asset_ids: list[uuid.UUID]
    task_stage_id: Optional[uuid.UUID] = None


class RunAsAdAssign(BaseModel):
    # Whether this video is cleared to run as an ad (exposed to external platforms).
    run_as_ad: bool


class TaskItem(BaseModel):
    asset_id: uuid.UUID
    name: str
    project_id: uuid.UUID
    project_name: Optional[str] = None
    # The video request (submission link) this asset's project belongs to, if any.
    request_id: Optional[uuid.UUID] = None
    request_title: Optional[str] = None
    task_stage_id: Optional[uuid.UUID] = None
    run_as_ad: bool = False
    submitter_name: Optional[str] = None
    submitter_email: Optional[str] = None
    thumbnail_url: Optional[str] = None
    latest_version_number: Optional[int] = None
    created_at: datetime
