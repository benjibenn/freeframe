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


class ReviewFile(BaseModel):
    """One file the editor delivered, at its newest version."""
    asset_id: uuid.UUID
    # The newest version: the one being reviewed, and where a revision comment goes.
    version_id: uuid.UUID
    file_name: str
    asset_type: AssetType
    thumbnail_url: Optional[str] = None
    # Null until the version is ready. Video is a relative /stream/hls/... URL.
    preview_url: Optional[str] = None
    # The version's "Source: " comment. Null when the uploader gave none; the
    # page shows that gap rather than hiding the button.
    canva_url: Optional[str] = None


class ReviewQueueItem(BaseModel):
    """One editor on one brief, waiting in the Review stage."""
    submission_id: uuid.UUID
    brief_id: uuid.UUID
    brief_title: str
    brief_token: str
    # The editor's private upload project, where their files live.
    project_id: uuid.UUID
    editor_id: uuid.UUID
    editor_name: Optional[str] = None
    # The stage the reviewer saw this editor in. Sent back with the decision so
    # the server can refuse it (409) if someone else moved the editor since.
    expected_stage_id: uuid.UUID
    # Newest live upload, or when the editor joined the brief if there is none.
    waited_since: datetime
    files: list[ReviewFile] = []


class ReviewQueuePage(BaseModel):
    items: list[ReviewQueueItem]
    total: int
    stages: ReviewStageIds
