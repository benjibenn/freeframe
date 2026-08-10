import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel

from ..models.asset import AssetType


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
    # video / image / audio — the board is no longer video-only, so a row has to
    # say what it is.
    asset_type: AssetType
    # Where the asset sits in the taxonomy, e.g. "Skincare/GlowCo/Serum".
    # Rooted at the project name, so submitted work — which lands in a
    # per-submitter project with no folder — still resolves to something.
    folder_id: Optional[uuid.UUID] = None
    folder_path: Optional[str] = None
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


class BriefEditor(BaseModel):
    """An editor who accepted the request — derived from `submissions`, not stored."""
    id: uuid.UUID
    name: Optional[str] = None
    email: Optional[str] = None


class BriefTaskItem(BaseModel):
    """A brief as a work item. Exists from creation, so it appears on the board
    before anything has been uploaded against it — the row a to-do list is for."""
    id: uuid.UUID
    title: str
    taxonomy_path: Optional[str] = None
    task_stage_id: Optional[uuid.UUID] = None
    # Internal owner: whose desk this is on.
    assignee_id: Optional[uuid.UUID] = None
    assignee_name: Optional[str] = None
    # Who is actually making it. Blank until someone accepts the link, which is
    # why it does not replace the owner.
    editors: list[BriefEditor] = []
    has_brief: bool = False
    has_brief_json: bool = False
    # Paid roll-up over this brief's submissions (per-editor paid_at). Admin-only:
    # for non-admin viewers both stay 0, so no payment state leaks to editors.
    paid_count: int = 0
    submission_count: int = 0
    # Public accept/upload URL. Editors open the brief through this — the
    # /projects/requests settings page is admin-only.
    submit_url: Optional[str] = None
    created_at: datetime
    assets: list[TaskItem] = []


class TaskBoardResponse(BaseModel):
    briefs: list[BriefTaskItem]
    # Assets uploaded straight into a project rather than against a request.
    # They still need somewhere to live or the board silently loses them.
    unbriefed: list[TaskItem] = []


class BriefAssigneeAssign(BaseModel):
    """Null clears the owner — an unowned brief is a real state, not an error."""
    assignee_id: Optional[uuid.UUID] = None
