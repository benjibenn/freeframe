from pydantic import BaseModel
import uuid
from datetime import datetime
from typing import Optional


class ActivityLogResponse(BaseModel):
    id: uuid.UUID
    action: str
    user_id: Optional[uuid.UUID]
    org_id: Optional[uuid.UUID]
    project_id: Optional[uuid.UUID]
    asset_id: Optional[uuid.UUID]
    payload: dict
    created_at: datetime
    model_config = {"from_attributes": True}


class ActivityActor(BaseModel):
    id: uuid.UUID
    name: str
    avatar_url: Optional[str] = None


class ActivityFeedItem(BaseModel):
    """An enriched activity row for the platform-wide feed admins/sub-admins watch.

    ``deep_link`` points straight at the asset's latest revision so the viewer can
    comment without drilling into folders one by one.
    """
    id: uuid.UUID
    action: str
    created_at: datetime
    actor: Optional[ActivityActor] = None
    asset_id: Optional[uuid.UUID] = None
    asset_name: Optional[str] = None
    asset_type: Optional[str] = None
    project_id: Optional[uuid.UUID] = None
    project_name: Optional[str] = None
    latest_version_number: Optional[int] = None
    comment_preview: Optional[str] = None
    deep_link: Optional[str] = None
    payload: dict = {}


class ActivityUnreadCount(BaseModel):
    count: int
