"""Response shapes for the /review queue."""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from ..models.asset import AssetType


class ReviewStageIds(BaseModel):
    """The three stages a decision moves between, resolved by name, so the page
    never has to guess them."""
    review: uuid.UUID
    done: uuid.UUID
    revision: uuid.UUID


class ReviewQueueItem(BaseModel):
    asset_id: uuid.UUID
    # The newest version: the one being reviewed, and where a reject comment goes.
    version_id: uuid.UUID
    project_id: uuid.UUID
    asset_type: AssetType
    file_name: str
    brief_id: Optional[uuid.UUID] = None
    brief_title: Optional[str] = None
    brief_token: Optional[str] = None
    editor_name: Optional[str] = None
    thumbnail_url: Optional[str] = None
    # Null until the version is ready. Video is a relative /stream/hls/... URL.
    preview_url: Optional[str] = None
    # The version's "Source: " comment. Null when the uploader gave none; the
    # page shows that gap rather than hiding the button.
    canva_url: Optional[str] = None
    submitted_at: datetime


class ReviewQueuePage(BaseModel):
    items: list[ReviewQueueItem]
    total: int
    stages: ReviewStageIds
