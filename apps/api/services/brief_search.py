"""Finding briefs in bulk, for agents.

An agent asked to read or count briefs used to list them (ids and titles only,
capped at 200, no paging) and then call get_brief once per brief. Each call is a
model round trip, so 300 briefs took about two hours — none of it server time.
This module is what lets one call carry filters, paging and content instead.

Split in two on purpose:

- SQL does what maps onto a column — project, folder, angle, enabled, dates,
  whether anyone has submitted — and leaves the heavy columns (brief_json,
  instructions) unloaded unless content was asked for.
- Python does what is derived — the folder path (computed from the folder tree,
  so a rename needs no backfill) and the persona (a label, or else the title's
  third slot). The persona's SQL clause is only a prefilter; the exact rule runs
  here, so it cannot drift from what the playbook shows.

Paging happens after both, so a page is never short because Python dropped rows
SQL had already counted.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Optional
import uuid

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Query, Session, defer

from ..models.submission import Submission, SubmissionLink
from .permissions import is_platform_admin

TITLE_SEPARATOR = " - "


@dataclass
class BriefFilters:
    project_id: Optional[uuid.UUID] = None
    folder_id: Optional[uuid.UUID] = None
    query: Optional[str] = None
    persona: Optional[str] = None
    angle: Optional[str] = None
    enabled: Optional[bool] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    has_submissions: Optional[bool] = None


def _like_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def base_query(db: Session, user: Any, f: BriefFilters, *, with_content: bool) -> Query:
    """Every live brief this user may see that passes the column filters, newest first."""
    q = db.query(SubmissionLink).filter(SubmissionLink.deleted_at.is_(None))
    # The same visibility rule as GET /submission-links.
    if not is_platform_admin(user):
        q = q.filter(SubmissionLink.created_by == user.id)
    if not with_content:
        q = q.options(defer(SubmissionLink.brief_json), defer(SubmissionLink.instructions))

    if f.project_id:
        q = q.filter(SubmissionLink.home_project_id == f.project_id)
    if f.folder_id:
        q = q.filter(SubmissionLink.home_folder_id == f.folder_id)
    if f.angle:
        q = q.filter(func.lower(func.trim(SubmissionLink.angle_label)) == f.angle.strip().lower())
    if f.persona:
        # Prefilter only: the label, or the persona slot of a conventional title.
        # matches_persona applies the exact rule to what this lets through.
        needle = f.persona.strip()
        q = q.filter(or_(
            func.lower(func.trim(SubmissionLink.persona_label)) == needle.lower(),
            SubmissionLink.title.ilike(
                f"%{TITLE_SEPARATOR}{_like_escape(needle)}{TITLE_SEPARATOR}%", escape="\\"
            ),
        ))
    if f.enabled is not None:
        q = q.filter(SubmissionLink.is_enabled.is_(f.enabled))
    if f.created_after:
        q = q.filter(SubmissionLink.created_at >= f.created_after)
    if f.created_before:
        q = q.filter(SubmissionLink.created_at < f.created_before)
    if f.has_submissions is not None:
        anyone = db.query(Submission.id).filter(
            Submission.submission_link_id == SubmissionLink.id
        ).exists()
        q = q.filter(anyone if f.has_submissions else ~anyone)

    return q.order_by(SubmissionLink.created_at.desc(), SubmissionLink.id.desc())


def persona_of(title: Optional[str], persona_label: Optional[str]) -> Optional[str]:
    """The brief's persona as the playbook reads it: label first, then the title.

    A title supplies one only when it has all six slots of
    YYYYMMDD - sku - Persona - Lens - Hook - Format, as in parseTitle.
    """
    if persona_label and persona_label.strip():
        return persona_label.strip()
    parts = [p.strip() for p in (title or "").split(TITLE_SEPARATOR)]
    if len(parts) < 6:
        return None
    return parts[2] or None


def matches_persona(title: Optional[str], persona_label: Optional[str], wanted: str) -> bool:
    return (persona_of(title, persona_label) or "").casefold() == wanted.strip().casefold()


def matches_query(title: Optional[str], home_path: Optional[str], needle: str) -> bool:
    """Title or folder path, case-insensitively: "globex" finds the Globex folder."""
    n = needle.casefold().strip()
    return n in (title or "").casefold() or n in (home_path or "").casefold()


def page(rows: list, *, offset: int, limit: int) -> tuple[list, dict[str, Any]]:
    """One page of rows, and what an agent needs to know about the rest.

    truncated stays because an agent handed a cut list without being told reads
    it as the whole set; next_offset is how it asks for the remainder.
    """
    total = len(rows)
    chunk = rows[offset:offset + limit]
    end = offset + len(chunk)
    more = end < total
    return chunk, {
        "total_matched": total,
        "offset": offset,
        "returned": len(chunk),
        "next_offset": end if more else None,
        "truncated": more,
    }


def tally(keys: Iterable[Optional[str]], *, blank: str) -> list[dict[str, Any]]:
    """Counts per key, largest first; a missing key is counted under `blank`."""
    counts: dict[str, int] = {}
    for k in keys:
        name = k if k else blank
        counts[name] = counts.get(name, 0) + 1
    return [
        {"key": k, "count": c}
        for k, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].casefold()))
    ]
