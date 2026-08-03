"""Resolve folder ids to full, human-readable taxonomy paths.

Folders nest arbitrarily via `parent_id` (niche > store > product), so turning a
folder id into "Skincare/GlowCo/Serum" means walking to the root. Doing that in
Python costs one query per level per asset, which is why this is a single
recursive CTE shared by every surface that displays a path.

Paths are rooted at the project name so they read the same whether a level of
the taxonomy is modelled as a project or as a folder.
"""
from typing import Optional

from sqlalchemy import Text, and_, cast, func, select
from sqlalchemy.orm import Session, aliased

from ..models.folder import Folder
from ..models.project import Project


def folder_paths(db: Session, folder_ids: Optional[set] = None) -> dict:
    """Map folder id -> full path rooted at the project name.

    Pass `folder_ids` to resolve just the folders on one page, or None for every
    folder — needed when a prefix filter has to be applied before pagination.
    """
    base_where = [Folder.deleted_at.is_(None)]
    if folder_ids is not None:
        if not folder_ids:
            return {}
        base_where.append(Folder.id.in_(folder_ids))

    base = (
        select(
            Folder.id.label("leaf_id"),
            Folder.parent_id.label("parent_id"),
            Folder.project_id.label("project_id"),
            # Both arms of a recursive CTE must agree on type. folders.name is
            # VARCHAR(255) while concat() below yields unbounded VARCHAR, which
            # Postgres rejects outright — so pin both ends to TEXT.
            cast(Folder.name, Text).label("path"),
        )
        .where(and_(*base_where))
        .cte("folder_path_cte", recursive=True)
    )
    parent = aliased(Folder)
    walk = base.union_all(
        select(
            base.c.leaf_id,
            parent.parent_id,
            base.c.project_id,
            cast(func.concat(parent.name, "/", base.c.path), Text),
        ).where(and_(parent.id == base.c.parent_id, parent.deleted_at.is_(None)))
    )

    # Only rows that reached a root folder (no parent left) carry a complete path.
    rows = db.execute(
        select(walk.c.leaf_id, walk.c.project_id, walk.c.path).where(walk.c.parent_id.is_(None))
    ).all()
    if not rows:
        return {}

    project_names = dict(
        db.execute(
            select(Project.id, Project.name).where(Project.id.in_({r.project_id for r in rows}))
        ).all()
    )
    return {
        r.leaf_id: f"{project_names.get(r.project_id, '')}/{r.path}".lstrip("/")
        for r in rows
    }


def ids_under_path(db: Session, prefix: str) -> tuple[set, set]:
    """Folder ids at or beneath `prefix`, plus projects the prefix names outright.

    The second set exists because an asset filed loose in a project has that
    project's name as its whole path, so a bare project name must still match it.
    """
    prefix = prefix.strip("/")
    under = {
        fid for fid, path in folder_paths(db).items()
        if path == prefix or path.startswith(prefix + "/")
    }
    loose_projects = {
        pid for pid, pname in db.execute(select(Project.id, Project.name)).all()
        if pname == prefix
    }
    return under, loose_projects
