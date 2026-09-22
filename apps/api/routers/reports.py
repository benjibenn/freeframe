"""Superadmin reports: the whole submission pipeline as numbers.

Sibling of routers/admin.py rather than part of it because nothing here mutates
state and everything here is one read model. The aggregation lives in the pure
`build_report` below, NOT in SQL GROUP BY clauses: the API test suite mocks the
DB session (the models use PostgreSQL UUID types), so a grouped query would be
unverifiable, while a pure function over plain rows is tested directly.
"""
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.asset import Asset
from ..models.submission import Submission, SubmissionLink
from ..models.user import User
from ..schemas.reports import (
    ReportBriefRow,
    ReportFileRow,
    ReportPayload,
    ReportTotals,
    ReportUserRow,
)
from ..services.folder_paths import link_home_paths

router = APIRouter(prefix="/reports", tags=["reports"])


def _require_superadmin(current_user: User) -> None:
    """Sub-admins are excluded deliberately, matching the rest of the cross-owner
    admin surface: a sub-admin may review assets, but this spans every owner."""
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can access this endpoint",
        )


def person_name(user: Optional[User]) -> str:
    """How a submitter is labelled everywhere in the report.

    The admin-granted nickname wins over the account name so one person reads the
    same in every tab; a missing user row (hard-deleted account with history left
    behind) degrades to an empty string rather than blowing up the whole report.
    """
    if user is None:
        return ""
    return (user.nickname or user.name or "") or ""


def build_report(
    links: list,
    subs: list,
    asset_rows: list,
    users: dict,
    home_paths: dict,
) -> ReportPayload:
    """Fold the brief → submission → project → asset join into all four pivots.

    `asset_rows` are (asset_id, project_id, name, created_at) tuples. Assets are
    tied to a submitter through the per-submitter PROJECT, not through a column on
    the asset — that indirection is the whole join, so it is resolved once here and
    every pivot is derived from the same resolved rows. Anything uploaded into a
    project that is not a submitter project is not submitted work and is ignored.
    """
    sub_by_project = {s.project_id: s for s in subs}
    link_by_id = {l.id: l for l in links}

    files: list[ReportFileRow] = []
    for asset_id, project_id, name, created_at in asset_rows:
        s = sub_by_project.get(project_id)
        if s is None:
            continue
        link = link_by_id.get(s.submission_link_id)
        if link is None:
            continue
        files.append(
            ReportFileRow(
                asset_id=asset_id,
                name=name or "",
                created_at=created_at,
                project_id=project_id,
                brief_id=link.id,
                brief_title=link.title,
                user_id=s.user_id,
                user_name=person_name(users.get(s.user_id)),
            )
        )

    files_per_brief: dict = {}
    last_upload_per_brief: dict = {}
    files_per_user: dict = {}
    last_upload_per_user: dict = {}
    for f in files:
        files_per_brief[f.brief_id] = files_per_brief.get(f.brief_id, 0) + 1
        files_per_user[f.user_id] = files_per_user.get(f.user_id, 0) + 1
        prev_b = last_upload_per_brief.get(f.brief_id)
        if prev_b is None or f.created_at > prev_b:
            last_upload_per_brief[f.brief_id] = f.created_at
        prev_u = last_upload_per_user.get(f.user_id)
        if prev_u is None or f.created_at > prev_u:
            last_upload_per_user[f.user_id] = f.created_at

    subs_per_link: dict = {}
    for s in subs:
        subs_per_link.setdefault(s.submission_link_id, []).append(s)

    briefs: list[ReportBriefRow] = []
    for l in links:
        rows = subs_per_link.get(l.id, [])
        briefs.append(
            ReportBriefRow(
                id=l.id,
                title=l.title,
                home_path=home_paths.get(l.id) or l.taxonomy_path,
                created_at=l.created_at,
                is_enabled=l.is_enabled,
                persona_label=l.persona_label,
                angle_label=l.angle_label,
                submission_count=len(rows),
                file_count=files_per_brief.get(l.id, 0),
                submitter_ids=[s.user_id for s in rows],
                submitter_names=[person_name(users.get(s.user_id)) for s in rows],
                last_upload_at=last_upload_per_brief.get(l.id),
            )
        )

    briefs_per_user: dict = {}
    for s in subs:
        briefs_per_user.setdefault(s.user_id, set()).add(s.submission_link_id)

    user_rows: list[ReportUserRow] = []
    for user_id, brief_ids in briefs_per_user.items():
        u = users.get(user_id)
        user_rows.append(
            ReportUserRow(
                user_id=user_id,
                name=person_name(u),
                email=(u.email if u else "") or "",
                brief_count=len(brief_ids),
                file_count=files_per_user.get(user_id, 0),
                last_upload_at=last_upload_per_user.get(user_id),
            )
        )
    # Busiest first: the reason to open the per-user tab is to see who is carrying
    # the work, so the answer should not need a click to sort.
    user_rows.sort(key=lambda r: (-r.file_count, r.name.lower()))

    totals = ReportTotals(
        brief_count=len(links),
        submission_count=len(subs),
        file_count=len(files),
        submitter_count=len(briefs_per_user),
        briefs_awaiting_work=sum(1 for b in briefs if b.file_count == 0),
    )
    return ReportPayload(totals=totals, briefs=briefs, users=user_rows, files=files)


@router.get("", response_model=ReportPayload)
def get_reports(
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
        return ReportPayload(
            totals=ReportTotals(
                brief_count=0,
                submission_count=0,
                file_count=0,
                submitter_count=0,
                briefs_awaiting_work=0,
            ),
            briefs=[],
            users=[],
            files=[],
        )

    subs = (
        db.query(Submission)
        .filter(Submission.submission_link_id.in_([l.id for l in links]))
        .all()
    )

    project_ids = [s.project_id for s in subs]
    asset_rows = (
        db.query(Asset.id, Asset.project_id, Asset.name, Asset.created_at)
        .filter(Asset.project_id.in_(project_ids), Asset.deleted_at.is_(None))
        .order_by(Asset.created_at.desc())
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

    return build_report(links, subs, asset_rows, users, link_home_paths(db, links))
