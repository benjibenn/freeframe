"""Superadmin-only read model behind the brief overview page.

Lives in its own module rather than in routers/submissions.py on purpose: that
file is the single largest point of divergence between the two tenant branches,
so a shared feature that edits it merges badly. Nothing here mutates state.

The list carries who uploaded and a thumbnail of each upload, one page at a
time. The structured brief loads when a row is opened (GET
/submission-links/{id}), so a page of 25 does not carry 25 brief bodies.
"""
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.asset import Asset, AssetType, AssetVersion, MediaFile, ProcessingStatus
from ..models.submission import Submission, SubmissionLink
from ..models.user import User
from ..schemas.brief_overview import (
    BriefOverviewFile,
    BriefOverviewPage,
    BriefOverviewRow,
    BriefOverviewSubmission,
)
from ..services.board_paging import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    aware,
    brief_matches,
    intersect,
    light_brief_rows,
    page_briefs,
    parse_stage_filter,
)
from ..services.folder_paths import link_home_paths
from ..services.s3_service import generate_presigned_get_url

router = APIRouter(prefix="/brief-overview", tags=["brief-overview"])


def _require_superadmin(current_user: User) -> None:
    """Sub-admins are excluded deliberately. They may review any asset, but this
    view spans every owner's briefs and submitters, which stays superadmin-only."""
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can access this endpoint",
        )


def thumbnails_for_assets(db: Session, asset_ids: list[uuid.UUID]) -> dict:
    """Map asset id -> a presigned thumbnail URL for its latest ready version.

    Split out from the endpoint so the request handler can be tested without
    standing up the three-table version/media join.
    """
    if not asset_ids:
        return {}

    latest = (
        db.query(
            AssetVersion.asset_id.label("asset_id"),
            func.max(AssetVersion.version_number).label("mv"),
        )
        .filter(
            AssetVersion.asset_id.in_(asset_ids),
            AssetVersion.deleted_at.is_(None),
            AssetVersion.processing_status == ProcessingStatus.ready,
        )
        .group_by(AssetVersion.asset_id)
        .subquery()
    )
    versions = (
        db.query(AssetVersion)
        .join(
            latest,
            (AssetVersion.asset_id == latest.c.asset_id)
            & (AssetVersion.version_number == latest.c.mv),
        )
        .all()
    )
    if not versions:
        return {}

    asset_by_version = {v.id: v.asset_id for v in versions}
    files = (
        db.query(MediaFile)
        .filter(MediaFile.version_id.in_(list(asset_by_version.keys())))
        .all()
    )

    out: dict = {}
    for f in files:
        aid = asset_by_version.get(f.version_id)
        if aid and aid not in out and f.s3_key_thumbnail:
            out[aid] = generate_presigned_get_url(f.s3_key_thumbnail)
    return out


@router.get("", response_model=BriefOverviewPage)
def get_brief_overview(
    q: Optional[str] = Query(None, description="Case-insensitive match on the title or the folder path."),
    editor_id: Optional[uuid.UUID] = Query(None, description="Only briefs this user has a submission on."),
    stage_id: Optional[str] = Query(None, description="The brief's stage UUID, or 'unassigned'."),
    created_from: Optional[datetime] = Query(None, description="Inclusive lower bound on created_at."),
    created_to: Optional[datetime] = Query(None, description="Exclusive upper bound on created_at."),
    has_files: bool = Query(False, description="Only briefs with at least one uploaded file."),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_superadmin(current_user)
    stage_filter = parse_stage_filter(stage_id)

    # Read before light_brief_rows() so the query order the mocked-session tests
    # assert on stays: [editor filter], [has_files filter], light rows, page rows.
    with_files = (
        {lid for (lid,) in db.query(Submission.submission_link_id)
            .join(Asset, Asset.project_id == Submission.project_id)
            .filter(Asset.deleted_at.is_(None))
            .distinct()
            .all()}
        if has_files else None
    )

    light, editor_filter_ids = light_brief_rows(db, owned_link_ids=None, editor_id=editor_id)

    home = link_home_paths(db, light)
    only = intersect(editor_filter_ids, with_files)
    lo, hi = aware(created_from), aware(created_to)
    light = [
        r for r in light
        if brief_matches(r, home.get(r.id), q=q, only_ids=only, created_from=lo, created_to=hi)
    ]
    # An admin's view: the brief's own stage, so no per-editor stages.
    page_ids, total, _ = page_briefs(
        light, my_stage_by_link={}, stage_filter=stage_filter, offset=offset, limit=limit,
    )
    if not page_ids:
        return BriefOverviewPage(items=[], total=total)

    by_id = {l.id: l for l in db.query(SubmissionLink).filter(SubmissionLink.id.in_(page_ids)).all()}
    links = [by_id[i] for i in page_ids if i in by_id]

    subs = db.query(Submission).filter(Submission.submission_link_id.in_([l.id for l in links])).all()
    project_ids = [s.project_id for s in subs]
    asset_rows = (
        db.query(Asset.id, Asset.project_id, Asset.name, Asset.asset_type)
        .filter(Asset.project_id.in_(project_ids), Asset.deleted_at.is_(None))
        .order_by(Asset.created_at.asc())
        .all()
        if project_ids
        else []
    )

    user_ids = {s.user_id for s in subs}
    users = (
        {u.id: u for u in db.query(User).filter(User.id.in_(list(user_ids))).all()}
        if user_ids
        else {}
    )

    # Audio keeps waveform JSON where an image thumbnail would be (see assets.py).
    thumbs = thumbnails_for_assets(
        db, [aid for aid, _, _, atype in asset_rows if atype != AssetType.audio]
    )

    files_by_project: dict = {}
    for aid, pid, name, _ in asset_rows:
        files_by_project.setdefault(pid, []).append(
            BriefOverviewFile(asset_id=aid, name=name or "", thumbnail_url=thumbs.get(aid))
        )

    subs_by_link: dict = {}
    for s in subs:
        u = users.get(s.user_id)
        files = files_by_project.get(s.project_id, [])
        subs_by_link.setdefault(s.submission_link_id, []).append(
            BriefOverviewSubmission(
                id=s.id,
                user_id=s.user_id,
                user_name=(u.display_name if u else "") or "",
                user_email=(u.email if u else "") or "",
                display_name=s.display_name,
                project_id=s.project_id,
                paid_at=s.paid_at,
                created_at=s.created_at,
                asset_count=len(files),
                files=files,
            )
        )

    out: list[BriefOverviewRow] = []
    for l in links:
        rows = subs_by_link.get(l.id, [])
        out.append(
            BriefOverviewRow(
                id=l.id,
                token=l.token,
                title=l.title,
                instructions=l.instructions,
                is_enabled=l.is_enabled,
                expires_at=l.expires_at,
                created_at=l.created_at,
                home_project_id=l.home_project_id,
                home_folder_id=l.home_folder_id,
                home_path=home.get(l.id) or l.taxonomy_path,
                persona_label=l.persona_label,
                angle_label=l.angle_label,
                problem=l.problem,
                has_brief=bool(l.brief_pdf_s3_key),
                has_brief_json=bool(l.brief_json),
                reference_image_count=len(l.brief_reference_image_s3_keys or []),
                reference_video_count=len(l.brief_reference_video_s3_keys or []),
                submission_count=len(rows),
                asset_count=sum(r.asset_count for r in rows),
                submissions=rows,
            )
        )
    return BriefOverviewPage(items=out, total=total)
