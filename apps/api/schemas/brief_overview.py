"""Response shapes for the superadmin brief overview."""
import uuid
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel


class BriefOverviewFile(BaseModel):
    asset_id: uuid.UUID
    name: str
    # Presigned thumbnail for the asset's latest ready version. None when the
    # asset has no thumbnail yet (still processing, or an audio waveform).
    thumbnail_url: Optional[str] = None


class BriefOverviewSubmission(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_name: str
    user_email: str
    display_name: Optional[str] = None
    project_id: uuid.UUID
    paid_at: Optional[date] = None
    created_at: datetime
    asset_count: int = 0
    files: list[BriefOverviewFile] = []


class BriefOverviewRow(BaseModel):
    id: uuid.UUID
    token: str
    title: str
    instructions: Optional[str] = None
    is_enabled: bool
    expires_at: Optional[datetime] = None
    created_at: datetime
    home_project_id: Optional[uuid.UUID] = None
    home_folder_id: Optional[uuid.UUID] = None
    home_path: Optional[str] = None
    persona_label: Optional[str] = None
    angle_label: Optional[str] = None
    problem: Optional[str] = None
    has_brief: bool = False
    # Carried in the LIST payload on purpose — this is what removes the trip to
    # the edit page.
    brief_json: Optional[dict[str, Any]] = None
    reference_image_count: int = 0
    reference_video_count: int = 0
    submission_count: int = 0
    asset_count: int = 0
    submissions: list[BriefOverviewSubmission] = []
