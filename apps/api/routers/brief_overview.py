"""Superadmin-only read model behind the brief overview page.

Lives in its own module rather than in routers/submissions.py on purpose: that
file is the single largest point of divergence between the two tenant branches,
so a shared feature that edits it merges badly. Nothing here mutates state.

The payload deliberately carries `brief_json` and the per-submitter file list in
ONE response. That is the whole feature: an admin reads the brief, sees who
uploaded and previews what they uploaded without opening an edit form or walking
into a per-submitter project.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.asset import Asset, AssetVersion, MediaFile, ProcessingStatus
from ..models.submission import Submission, SubmissionLink
from ..models.user import User
from ..schemas.brief_overview import (
    BriefOverviewFile,
    BriefOverviewRow,
    BriefOverviewSubmission,
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


@router.get("", response_model=list[BriefOverviewRow])
def get_brief_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_superadmin(current_user)

    links = (
        db.query(SubmissionLink)
        .filter(SubmissionLink.deleted_at.is_(None))
        .order_by(SubmissionLink.created_at.desc())
        .all()
    )
    if not links:
        return []

    link_ids = [l.id for l in links]
    subs = db.query(Submission).filter(Submission.submission_link_id.in_(link_ids)).all()

    project_ids = [s.project_id for s in subs]
    asset_rows = (
        db.query(Asset.id, Asset.project_id, Asset.name)
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

    thumbs = thumbnails_for_assets(db, [r[0] for r in asset_rows])
    home = link_home_paths(db, links)

    files_by_project: dict = {}
    for aid, pid, name in asset_rows:
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
                brief_json=l.brief_json,
                reference_image_count=len(l.brief_reference_image_s3_keys or []),
                reference_video_count=len(l.brief_reference_video_s3_keys or []),
                submission_count=len(rows),
                asset_count=sum(r.asset_count for r in rows),
                submissions=rows,
            )
        )
    return out
