"""
Brief import service (data spine: Brief → FreeFrame).

Creates/updates a FreeFrame submission request from an external brief. The
request is owned by the brief's owner (by email, find-or-create) or a
configured fallback account. The brief PDF is stored in object storage and is
the only carrier of the brief body — we deliberately do not copy the brief
markdown into the request instructions. Upsert is keyed by
(source, source_brief_id) so re-finalizing a brief updates the same request.
"""
from __future__ import annotations

import re
import secrets
from typing import Optional

from sqlalchemy.orm import Session

from ..config import settings
from ..models.submission import SubmissionLink
from ..models.project import ProjectRole
from ..models.user import User, UserStatus
from ..services.auth_service import get_user_by_email
from ..services import s3_service

SOURCE = "creative-flywheel"


def _resolve_owner(db: Session, owner_email: Optional[str]) -> User:
    email = (owner_email or "").strip().lower()
    user = get_user_by_email(db, email) if email else None
    if user is not None:
        return user
    fallback = (settings.brief_import_fallback_email or "").strip().lower()
    if not fallback:
        raise ValueError("brief has no owner email and BRIEF_IMPORT_FALLBACK_EMAIL is not configured")
    user = get_user_by_email(db, fallback)
    if user is None:
        user = User(email=fallback, name="Creative Flywheel", status=UserStatus.active, email_verified=True)
        db.add(user)
        db.flush()
    return user


def upsert_brief_request(
    db: Session,
    *,
    source_brief_id: str,
    title: str,
    owner_email: Optional[str],
    pdf_bytes: bytes,
    persona_id: Optional[str] = None,
    angle_id: Optional[str] = None,
    brief_id: Optional[str] = None,
    persona_label: Optional[str] = None,
    angle_label: Optional[str] = None,
    problem: Optional[str] = None,
) -> tuple[SubmissionLink, bool]:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", source_brief_id or ""):
        raise ValueError("invalid source_brief_id")
    owner = _resolve_owner(db, owner_email)

    s3_key = f"briefs/{source_brief_id}.pdf"
    s3_service.put_object(s3_key, pdf_bytes, content_type="application/pdf")

    link = (
        db.query(SubmissionLink)
        .filter(
            SubmissionLink.source == SOURCE,
            SubmissionLink.source_brief_id == str(source_brief_id),
            SubmissionLink.deleted_at.is_(None),
        )
        .first()
    )
    created = link is None
    if link is None:
        link = SubmissionLink(
            token=secrets.token_urlsafe(32),
            created_by=owner.id,
            title=title,
            grant_role=ProjectRole.editor,
            source=SOURCE,
            source_brief_id=str(source_brief_id),
            brief_pdf_s3_key=s3_key,
            persona_id=persona_id,
            angle_id=angle_id,
            brief_id=brief_id,
            persona_label=persona_label,
            angle_label=angle_label,
            problem=problem,
        )
        db.add(link)
    else:
        link.title = title
        # Clear any markdown stored by older imports — the PDF is the brief now.
        link.instructions = None
        link.brief_pdf_s3_key = s3_key
        # Refresh CF lineage on re-import so labels/ids track the source.
        link.persona_id = persona_id
        link.angle_id = angle_id
        link.brief_id = brief_id
        link.persona_label = persona_label
        link.angle_label = angle_label
        link.problem = problem
    db.commit()
    db.refresh(link)
    return link, created


def cf_ids_for_project(db: Session, project) -> dict:
    """Return the CF lineage ids to stamp onto an asset created under `project`.

    Walks project.submission_link_id → SubmissionLink. Returns all-None when the
    project isn't under an imported request, so callers can splat unconditionally.
    """
    empty = {"cf_brief_id": None, "cf_persona_id": None, "cf_angle_id": None}
    link_id = getattr(project, "submission_link_id", None)
    if not link_id:
        return empty
    link = db.query(SubmissionLink).filter(SubmissionLink.id == link_id).first()
    if link is None:
        return empty
    return {
        "cf_brief_id": link.brief_id,
        "cf_persona_id": link.persona_id,
        "cf_angle_id": link.angle_id,
    }
