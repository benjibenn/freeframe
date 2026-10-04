"""The /review queue: which editors are waiting, and what a reviewer needs beside each.

The queue works off the EDITOR's stage on a brief (Submission.task_stage_id), not
the files' stage: the team moves the editor along the pipeline, and leaves the
files in Pending. An item is one editor on one brief whose stage is Review;
approving moves them to Done, sending back moves them to Revision. The three are
found by NAME because admins rename and reorder stages. If one is missing the
queue refuses (409) rather than guessing which stage was meant.

The legacy Asset.status approve/reject path (MCP review_file, routers/approvals.py)
is untouched and separate. Flagged for cleanup; out of scope here.
"""
from typing import Callable, Optional

from sqlalchemy import and_, func, select

from ..models.asset import Asset, AssetStatus, AssetType, AssetVersion, ProcessingStatus
from ..models.project import Project
from ..models.submission import Submission, SubmissionLink
from ..schemas.review_queue import ReviewFile, ReviewQueueItem
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


def _live_asset():
    """A file the editor still delivers: not deleted, not archived. status is
    nullable, and `!= 'archived'` would silently drop NULL rows."""
    return and_(Asset.deleted_at.is_(None), Asset.status.is_distinct_from(AssetStatus.archived))


def queue_statement(review_id, *, editor_id=None):
    """SELECT (Submission, brief_title, brief_token, waited_since) for every editor
    in Review, longest-waiting first. Only the brief's title and token: the full
    row carries brief_json, which the queue never reads.

    waited_since is the newest live upload in the editor's project, or when they
    joined the brief if they have uploaded nothing.
    """
    newest = (
        select(Asset.project_id.label("project_id"), func.max(AssetVersion.created_at).label("at"))
        .join(AssetVersion, AssetVersion.asset_id == Asset.id)
        .where(_live_asset(), AssetVersion.deleted_at.is_(None))
        .group_by(Asset.project_id)
        .subquery("newest_upload")
    )
    waited = func.coalesce(newest.c.at, Submission.created_at).label("waited_since")
    stmt = (
        select(
            Submission,
            SubmissionLink.title.label("brief_title"),
            SubmissionLink.token.label("brief_token"),
            waited,
        )
        .join(SubmissionLink, SubmissionLink.id == Submission.submission_link_id)
        # A deleted brief's per-editor project is soft-deleted, not removed.
        # Without these the editor stays queued and 404s on click-through.
        .join(Project, Project.id == Submission.project_id)
        .outerjoin(newest, newest.c.project_id == Submission.project_id)
        .where(
            Submission.task_stage_id == review_id,
            SubmissionLink.deleted_at.is_(None),
            Project.deleted_at.is_(None),
        )
    )
    if editor_id is not None:
        stmt = stmt.where(Submission.user_id == editor_id)
    return stmt.order_by(waited.asc(), Submission.id.asc())


def files_statement(project_ids):
    """SELECT (Asset, newest AssetVersion) for every live file in these projects,
    in upload order."""
    latest = (
        select(AssetVersion.asset_id.label("asset_id"), func.max(AssetVersion.version_number).label("vn"))
        .where(AssetVersion.deleted_at.is_(None))
        .group_by(AssetVersion.asset_id)
        .subquery("latest_version")
    )
    return (
        select(Asset, AssetVersion)
        .join(latest, latest.c.asset_id == Asset.id)
        .join(AssetVersion, and_(AssetVersion.asset_id == Asset.id, AssetVersion.version_number == latest.c.vn))
        .where(Asset.project_id.in_(project_ids), _live_asset())
        .order_by(Asset.created_at.asc(), Asset.id.asc())
    )


def preview_url(asset, version, first_file, presign: Callable, hls_url: Callable) -> Optional[str]:
    """What the big pane plays. Nothing until the version is ready: a
    half-processed file has no playable output, and a broken player reads as a
    broken file."""
    if first_file is None or version.processing_status != ProcessingStatus.ready:
        return None
    if asset.asset_type == AssetType.video and first_file.s3_key_processed:
        return hls_url(first_file.s3_key_processed)
    return presign(first_file.s3_key_processed or first_file.s3_key_raw)


def build_file(asset, version, media_files, canva_url, *, presign: Callable, hls_url: Callable) -> ReviewFile:
    """media_files: the version's MediaFile rows in slide order."""
    first = media_files[0] if media_files else None
    thumb = thumbnail_key(asset.asset_type, next((f.s3_key_thumbnail for f in media_files if f.s3_key_thumbnail), None))
    return ReviewFile(
        asset_id=asset.id,
        version_id=version.id,
        file_name=asset.name,
        asset_type=asset.asset_type,
        thumbnail_url=presign(thumb) if thumb else None,
        preview_url=preview_url(asset, version, first, presign, hls_url),
        canva_url=canva_url,
    )


def build_item(submission, brief_title, brief_token, user, waited_since, files, review_id) -> ReviewQueueItem:
    return ReviewQueueItem(
        submission_id=submission.id,
        brief_id=submission.submission_link_id,
        brief_title=brief_title,
        brief_token=brief_token,
        project_id=submission.project_id,
        editor_id=submission.user_id,
        # The owner-set handle wins, as it does in the per-editor project name.
        editor_name=submission.display_name or (user.display_name if user else None),
        expected_stage_id=review_id,
        waited_since=waited_since,
        files=files,
    )
