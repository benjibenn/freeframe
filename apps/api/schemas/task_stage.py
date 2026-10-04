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
    """A stage move, for a file (PATCH /assets/{id}/task-stage) or for one editor
    on a brief (PATCH /submission-links/{link}/editors/{user}/task-stage)."""
    # Null moves it back to "unassigned" (no stage).
    task_stage_id: Optional[uuid.UUID] = None
    # Set by the /review page: the stage the reviewer saw the file or editor in.
    # The move is refused (409) if it has left that stage since. With this set,
    # a move to Revision requires `comment`.
    expected_stage_id: Optional[uuid.UUID] = None
    # Why it is going back. Accepted only on a move to Revision; saved as a
    # normal comment on `version_id` and emailed to the file's uploader / the
    # editor. For a file, `version_id` defaults to the newest; for an editor it
    # is required and must be a file in their project.
    comment: Optional[str] = None
    version_id: Optional[uuid.UUID] = None


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
    """An editor assigned to the request — by accepting the link, or by an admin.

    Derived from `submissions`, one row per (brief, editor). A non-admin viewer
    receives only their own row: co-editors' names and progress are exactly what
    per-submitter isolation exists to withhold.
    """
    id: uuid.UUID
    name: Optional[str] = None
    email: Optional[str] = None
    # This editor's own status. Null = not started. Independent of the brief's
    # task_stage_id above: two editors can be at different points on one brief.
    task_stage_id: Optional[uuid.UUID] = None


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


class TaskBoardPage(BaseModel):
    """One page of briefs, plus what the page needs about the whole filtered set."""
    items: list[BriefTaskItem]
    # Briefs matching the filters, across every page.
    total: int
    # Briefs per stage id ("unassigned" for none), counted BEFORE the stage
    # filter and by the reader's own stage on briefs they edit — what the
    # stage chips show.
    stage_counts: dict[str, int] = {}


class BriefAssigneeAssign(BaseModel):
    """Null clears the owner — an unowned brief is a real state, not an error."""
    assignee_id: Optional[uuid.UUID] = None


class BriefEditorAssign(BaseModel):
    """The editor to put on this brief.

    One-way: assigning provisions their private upload project, and there is no
    unassign — removing the row would orphan whatever they uploaded into it.
    """
    user_id: uuid.UUID
