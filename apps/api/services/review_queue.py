"""The /review queue: which files are waiting, and what a reviewer needs beside each.

Review is a pipeline stage, not Asset.status. A file is waiting when its stage
is Review; approving moves it to Done, rejecting to Revision. The three are
found by NAME because admins rename and reorder stages. If one is missing the
queue refuses (409) rather than guessing which stage was meant.

The legacy Asset.status approve/reject path (MCP review_file, routers/approvals.py)
is untouched and separate. Flagged for cleanup; out of scope here.
"""
from dataclasses import dataclass, field
from typing import Callable, Optional

from ..models.asset import AssetType, ProcessingStatus
from ..schemas.review_queue import ReviewQueueItem
from .thumbnails import thumbnail_key

REVIEW = "Review"
DONE = "Done"
REVISION = "Revision"


class MissingStage(Exception):
    def __init__(self, name: str):
        super().__init__(f"Missing task stage: {name}")
        self.name = name


def resolve_review_stages(stages) -> dict:
    """{'review': id, 'done': id, 'revision': id} from stages ordered by position.

    Names compare trimmed and case-insensitive. With two stages of one name, the
    first in board order wins, so the answer never depends on row order in the DB.
    """
    by_name: dict = {}
    for s in stages:
        by_name.setdefault((s.name or "").strip().casefold(), s.id)
    out = {}
    for name in (REVIEW, DONE, REVISION):
        sid = by_name.get(name.casefold())
        if sid is None:
            raise MissingStage(name)
        out[name.lower()] = sid
    return out


def is_revision(stage) -> bool:
    return (stage.name or "").strip().casefold() == REVISION.casefold()


@dataclass
class QueueContext:
    """Everything build_item reads, bulk-loaded once per page."""
    files_by_version: dict = field(default_factory=dict)   # version id -> [MediaFile] in slide order
    projects: dict = field(default_factory=dict)
    links: dict = field(default_factory=dict)
    submissions_by_project: dict = field(default_factory=dict)
    users: dict = field(default_factory=dict)
    source_by_version: dict = field(default_factory=dict)
    presign: Callable[[str], str] = lambda key: key
    hls_url: Callable[[str], str] = lambda key: key


def preview_url(asset, version, first_file, ctx: QueueContext) -> Optional[str]:
    """What the big pane plays. Nothing until the version is ready: a
    half-processed file has no playable output, and a broken player reads as a
    broken file."""
    if first_file is None or version.processing_status != ProcessingStatus.ready:
        return None
    if asset.asset_type == AssetType.video and first_file.s3_key_processed:
        return ctx.hls_url(first_file.s3_key_processed)
    return ctx.presign(first_file.s3_key_processed or first_file.s3_key_raw)


def build_item(asset, version, ctx: QueueContext) -> ReviewQueueItem:
    files = ctx.files_by_version.get(version.id, [])
    first = files[0] if files else None
    thumb = thumbnail_key(asset.asset_type, next((f.s3_key_thumbnail for f in files if f.s3_key_thumbnail), None))
    project = ctx.projects.get(asset.project_id)
    link = ctx.links.get(project.submission_link_id) if project and project.submission_link_id else None
    sub = ctx.submissions_by_project.get(asset.project_id)
    user = ctx.users.get(asset.created_by)
    return ReviewQueueItem(
        asset_id=asset.id,
        version_id=version.id,
        project_id=asset.project_id,
        asset_type=asset.asset_type,
        file_name=asset.name,
        brief_id=link.id if link else None,
        brief_title=link.title if link else None,
        brief_token=link.token if link else None,
        # The owner-set handle wins, as it does in the per-editor project name.
        editor_name=(sub.display_name if sub and sub.display_name else (user.display_name if user else None)),
        thumbnail_url=ctx.presign(thumb) if thumb else None,
        preview_url=preview_url(asset, version, first, ctx),
        canva_url=ctx.source_by_version.get(version.id),
        submitted_at=version.created_at,
    )
