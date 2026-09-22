"""Superadmin reports: the whole submission pipeline as facts to count.

Sibling of routers/admin.py rather than part of it because nothing here mutates
state and everything here is one read model. The shaping lives in the pure
`build_report` below, NOT in SQL GROUP BY clauses: the API test suite mocks the
DB session (the models use PostgreSQL UUID types), so a grouped query would be
unverifiable, while a pure function over plain rows is tested directly.

This endpoint deliberately computes NO totals. It returns briefs, the people who
accepted them and when, and one row per delivered file with its date; the page
derives every number from those against whatever window is being asked about.
An earlier version returned all-time counts and let the page filter rows, which
put lifetime totals underneath a two-day filter.
"""
import uuid
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
    ReportSubmitter,
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
    """Resolve the brief -> submission -> project -> asset join into flat rows.

    `asset_rows` are (asset_id, project_id, name, created_at) tuples. A file is
    tied to a person only through the per-submitter PROJECT — assets carry no
    uploader column — so that indirection is resolved once, here. Anything
    uploaded into a project that is not a submitter project is not submitted work
    and is dropped.
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

    subs_per_link: dict = {}
    for s in subs:
        subs_per_link.setdefault(s.submission_link_id, []).append(s)

    briefs = [
        ReportBriefRow(
            id=l.id,
            title=l.title,
            home_path=home_paths.get(l.id) or l.taxonomy_path,
            created_at=l.created_at,
            is_enabled=l.is_enabled,
            persona_label=l.persona_label,
            angle_label=l.angle_label,
            submitters=[
                ReportSubmitter(
                    user_id=s.user_id,
                    name=person_name(users.get(s.user_id)),
                    submitted_at=s.created_at,
                )
                for s in subs_per_link.get(l.id, [])
            ],
        )
        for l in links
    ]

    # Everyone who has ever accepted a brief, whether or not they delivered.
    # Someone who accepted and uploaded nothing is exactly who an admin opens
    # this page to find, so they must survive into the payload.
    seen: dict = {}
    for s in subs:
        if s.user_id not in seen:
            u = users.get(s.user_id)
            seen[s.user_id] = ReportUserRow(
                user_id=s.user_id,
                name=person_name(u),
                email=(u.email if u else "") or "",
            )
    user_rows = sorted(seen.values(), key=lambda r: (r.name or "￿").lower())

    return ReportPayload(briefs=briefs, users=user_rows, files=files)


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
        return ReportPayload(briefs=[], users=[], files=[])

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
