"""Superadmin write path for the persona and angle labels on briefs.

The playbook view groups and counts briefs by these two labels, so they are
written in batches (tag every brief of one angle at once) and all-or-nothing:
a half-applied batch would make the coverage matrix quietly wrong.

Own module, like brief_overview, so the shared feature stays out of
routers/submissions.py, where the two tenant branches diverge most.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.submission import SubmissionLink
from ..models.user import User
from ..schemas.brief_overview import BriefLabelsUpdate
from .brief_overview import _require_superadmin

router = APIRouter(prefix="/brief-overview", tags=["brief-overview"])


@router.patch("/labels")
def set_brief_labels(
    body: BriefLabelsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_superadmin(current_user)

    if not body.link_ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "link_ids must contain at least one brief id")
    if body.persona_label is None and body.angle_label is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Nothing to set: pass persona_label, angle_label or both")

    wanted = set(body.link_ids)
    links = (
        db.query(SubmissionLink)
        .filter(SubmissionLink.id.in_(list(wanted)), SubmissionLink.deleted_at.is_(None))
        .all()
    )
    missing = wanted - {l.id for l in links}
    if missing:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Unknown or deleted briefs, nothing saved: " + ", ".join(sorted(str(m) for m in missing)),
        )

    for l in links:
        if body.persona_label is not None:
            l.persona_label = body.persona_label.strip() or None
        if body.angle_label is not None:
            l.angle_label = body.angle_label.strip() or None
    db.commit()

    return {"updated": len(links)}
