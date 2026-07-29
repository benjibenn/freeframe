"""Auto-naming for assets uploaded into a request's per-submitter project.

Submitters don't get to name their uploads: inside a project provisioned by a
submission link every NEW asset is called "Hook N". N is scoped to that one
project, so each submitter's sequence starts at Hook 1 and they never see (or
collide with) another submitter's numbering.

Only brand-new assets consume a number. A re-upload of an existing hook goes
through POST /assets/{id}/versions, which adds a version and never renames, so
revisions don't advance the counter.
"""
import re
import uuid

from sqlalchemy.orm import Session

from ..models.asset import Asset

_HOOK_NAME = re.compile(r"^hook\s+(\d+)$")


def variation_names(brief_json) -> list[str]:
    """Deliverable names a brief prescribes for submitted assets.

    Walks brief_json -> final_deliverable -> hook_variations[] -> variation,
    collecting non-empty strings. Briefs come from a free-form paste flow and
    predate this naming scheme, so any missing or misshapen level yields [] —
    which callers treat as "no prescribed names, fall back to Hook N".
    """
    if not isinstance(brief_json, dict):
        return []
    deliverable = brief_json.get("final_deliverable")
    if not isinstance(deliverable, dict):
        return []
    variations = deliverable.get("hook_variations")
    if not isinstance(variations, list):
        return []
    names = []
    for row in variations:
        if isinstance(row, dict):
            name = row.get("variation")
            if isinstance(name, str) and name.strip():
                names.append(name.strip())
    return names


def next_hook_number(names) -> int:
    """One past the highest "Hook N" in `names` (1 when there are none).

    Uses the max rather than a count so that renaming or deleting a hook can't
    hand the same number to two different assets — a gap in the middle stays a
    gap.
    """
    highest = 0
    for name in names:
        match = _HOOK_NAME.match(" ".join((name or "").strip().lower().split()))
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


def next_hook_name(db: Session, project_id: uuid.UUID) -> str:
    """The name to give the next new asset uploaded to this submission project.

    Callers must hold a lock on the project row (SELECT ... FOR UPDATE): a
    multi-file selection initiates every upload concurrently, and without
    serialization they would all read the same highest number.
    """
    names = db.query(Asset.name).filter(
        Asset.project_id == project_id,
        Asset.deleted_at.is_(None),
    ).all()
    return f"Hook {next_hook_number(name for (name,) in names)}"
