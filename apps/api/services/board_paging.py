"""Paging the brief lists (/task-board and /brief-overview) by one set of rules.

Both lists filter on things SQL cannot see cheaply. A brief's path is derived
from its folder (folder_paths.link_home_paths), so renaming a folder moves every
brief beneath it. An editor reads a brief by their OWN stage, not the brief's
(apps/web/lib/brief-stage.ts). So the light columns of every brief in scope are
filtered here, and only the page that is returned has its files, editors and
thumbnails loaded. Briefs number in the hundreds; files do not.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

UNASSIGNED = "unassigned"
DEFAULT_LIMIT = 25
MAX_LIMIT = 100


def parse_stage_filter(stage_id: Optional[str]) -> Optional[str]:
    """None, 'unassigned', or a stage id in its canonical string form."""
    if not stage_id:
        return None
    if stage_id == UNASSIGNED:
        return UNASSIGNED
    try:
        return str(uuid.UUID(stage_id))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"stage_id must be a stage UUID or '{UNASSIGNED}'")


def aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Read a naive bound as UTC. Comparing it with created_at would otherwise raise."""
    if dt is None or dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def reader_stage(link_id, brief_stage_id, my_stage_by_link: dict):
    """The stage a reader files this brief under. Python twin of stageOf().

    An editor on the brief reads their own row, even when it has no stage yet.
    Everyone else (admins, and owners who are not editors on it) reads the
    brief's own stage. For an admin, pass an empty map.
    """
    if link_id in my_stage_by_link:
        return my_stage_by_link[link_id]
    return brief_stage_id


def under_prefix(path: Optional[str], prefix: str) -> bool:
    p = prefix.strip("/")
    return bool(path) and (path == p or path.startswith(p + "/"))


def brief_matches(
    row,
    path: Optional[str],
    *,
    q: Optional[str] = None,
    folder: Optional[str] = None,
    only_ids: Optional[set] = None,
    created_from: Optional[datetime] = None,
    created_to: Optional[datetime] = None,
) -> bool:
    """Whether one brief survives the list's filters.

    `q` matches the title OR the path, because both are on the row: an admin
    searching "Iphone 17" is reading the line they see. `created_to` is
    exclusive, so a client can pass the start of the next day.
    """
    if only_ids is not None and row.id not in only_ids:
        return False
    if folder and not under_prefix(path, folder):
        return False
    if created_from is not None and row.created_at < created_from:
        return False
    if created_to is not None and row.created_at >= created_to:
        return False
    needle = (q or "").strip().casefold()
    if needle and needle not in f"{row.title} {path or ''}".casefold():
        return False
    return True


def intersect(*sets: Optional[set]) -> Optional[set]:
    """None means "no restriction". Intersect only the restrictions that are set."""
    out = None
    for s in sets:
        if s is not None:
            out = set(s) if out is None else out & s
    return out


def page_briefs(rows, *, my_stage_by_link: dict, stage_filter: Optional[str], offset: int, limit: int):
    """(page_ids, total, stage_counts) over rows already in display order.

    stage_counts are counted BEFORE the stage filter. They are what the stage
    chips show, and a chip must count what clicking it would show.
    """
    counts: dict = {}
    kept: list = []
    for r in rows:
        sid = reader_stage(r.id, r.task_stage_id, my_stage_by_link)
        key = str(sid) if sid is not None else UNASSIGNED
        counts[key] = counts.get(key, 0) + 1
        if stage_filter is None or key == stage_filter:
            kept.append(r.id)
    return kept[offset:offset + limit], len(kept), counts
