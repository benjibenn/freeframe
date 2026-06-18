"""
Brief import service (data spine: Brief → FreeFrame).

Creates/updates a FreeFrame submission request from an external brief. The
request is owned by the brief's owner (by email, find-or-create) or a
configured fallback account. The brief PDF is stored in object storage and a
(refreshed) link is appended to the request instructions. Upsert is keyed by
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
    instructions: str,
    owner_email: Optional[str],
    pdf_bytes: bytes,
) -> tuple[SubmissionLink, bool]:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", source_brief_id or ""):
        raise ValueError("invalid source_brief_id")
    owner = _resolve_owner(db, owner_email)

    s3_key = f"briefs/{source_brief_id}.pdf"
    s3_service.put_object(s3_key, pdf_bytes, content_type="application/pdf")
    full_instructions = instructions

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
            instructions=full_instructions,
            grant_role=ProjectRole.editor,
            source=SOURCE,
            source_brief_id=str(source_brief_id),
            brief_pdf_s3_key=s3_key,
        )
        db.add(link)
    else:
        link.title = title
        link.instructions = full_instructions
        link.brief_pdf_s3_key = s3_key
    db.commit()
    db.refresh(link)
    return link, created
