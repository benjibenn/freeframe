"""Brief render template — a singleton, admin-editable config describing how structured
JSON briefs render (ordered sections mapping dot-paths to text/bullets/table). Read
publicly (the submit page renders briefs for guests); written by platform admins only.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.submission import BriefTemplate
from ..models.user import User
from ..schemas.brief_template import BriefTemplateResponse, BriefTemplateUpdate
from ..services.permissions import require_platform_admin

router = APIRouter(tags=["brief_template"])

ALLOWED_RENDER_TYPES = {"text", "bullets", "table"}


def _get_singleton(db: Session) -> BriefTemplate:
    """Return the single template row, creating an empty one if the table is somehow
    empty (the migration seeds a default, so this is just belt-and-suspenders)."""
    row = db.query(BriefTemplate).first()
    if row is None:
        row = BriefTemplate(sections=[])
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _normalize_sections(raw: list[dict]) -> list[dict]:
    """Coerce each section into the {id, title, path, as, columns?} shape and drop
    anything unusable (no path, unknown render type). The renderer is defensive too,
    but normalizing on write keeps stored configs clean."""
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        render_as = str(item.get("as") or "text").strip()
        if not path or render_as not in ALLOWED_RENDER_TYPES:
            continue
        section = {
            "id": str(item.get("id") or uuid.uuid4()),
            "title": str(item.get("title") or ""),
            "path": path,
            "as": render_as,
        }
        if render_as == "table":
            cols = []
            for col in item.get("columns") or []:
                if not isinstance(col, dict):
                    continue
                key = str(col.get("key") or "").strip()
                if not key:
                    continue
                cols.append({"key": key, "header": str(col.get("header") or key)})
            section["columns"] = cols
        out.append(section)
    return out


@router.get("/brief-template", response_model=BriefTemplateResponse)
def get_brief_template(db: Session = Depends(get_db)):
    row = _get_singleton(db)
    return BriefTemplateResponse(sections=row.sections or [])


@router.put("/brief-template", response_model=BriefTemplateResponse)
def update_brief_template(
    body: BriefTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_platform_admin(current_user)
    sections = _normalize_sections(body.sections)
    if not sections:
        raise HTTPException(status_code=400, detail="Template must have at least one valid section")
    row = _get_singleton(db)
    row.sections = sections
    db.commit()
    db.refresh(row)
    return BriefTemplateResponse(sections=row.sections or [])
