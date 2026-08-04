"""Resolve folder ids to full, human-readable taxonomy paths.

Folders nest arbitrarily via `parent_id` (niche > store > product), so turning a
folder id into "Skincare/GlowCo/Serum" means walking to the root. Doing that in
Python costs one query per level per asset, which is why this is a single
recursive CTE shared by every surface that displays a path.

Paths are rooted at the project name so they read the same whether a level of
the taxonomy is modelled as a project or as a folder.
"""
from typing import Optional

from sqlalchemy import Text, and_, cast, func, or_, select
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


def link_home_paths(db: Session, links) -> dict:
    """Map submission link id -> the taxonomy path it is filed under.

    Derived from `home_folder_id` rather than read off the stored string, so
    renaming a folder moves every request beneath it at once. Legacy links filed
    nowhere fall back to whatever was typed into them by hand.

    Resolves through the same `folder_paths` map the assets use, so a request and
    an asset in the same folder produce the identical string — otherwise a folder
    filter would silently split them into two groups.
    """
    links = list(links)
    folder_ids = {l.home_folder_id for l in links if l.home_folder_id}
    paths = folder_paths(db, folder_ids) if folder_ids else {}

    # Filed at a project root: the project name is the whole path.
    root_project_ids = {
        l.home_project_id for l in links if l.home_project_id and not l.home_folder_id
    }
    project_names = (
        dict(
            db.execute(
                select(Project.id, Project.name).where(Project.id.in_(root_project_ids))
            ).all()
        )
        if root_project_ids
        else {}
    )

    out = {}
    for link in links:
        if link.home_folder_id and paths.get(link.home_folder_id):
            out[link.id] = paths[link.home_folder_id]
        elif link.home_project_id and project_names.get(link.home_project_id):
            out[link.id] = project_names[link.home_project_id]
        else:
            out[link.id] = link.taxonomy_path
    return out


def resolve_link_home_path(db: Session, link) -> Optional[str]:
    """Single-link form of `link_home_paths`, for the upload stamp."""
    return link_home_paths(db, [link]).get(link.id)


def resolve_asset_path(asset, folder_path_by_id: dict, project_name: Optional[str]) -> Optional[str]:
    """The single answer to "where does this asset belong?".

    Explicit filing wins: if someone moved the asset into a real folder, that is
    a deliberate act and outranks whatever was stamped at upload. Otherwise the
    stamped path from the submission link, and failing both, the project name —
    so every asset resolves to something.
    """
    if asset.folder_id and folder_path_by_id.get(asset.folder_id):
        return folder_path_by_id[asset.folder_id]
    return getattr(asset, "taxonomy_path", None) or project_name


def asset_path_filter(db: Session, prefix: str):
    """SQLAlchemy clause selecting assets at or beneath `prefix`.

    Covers all three ways an asset can carry a path — a real folder, a stamped
    taxonomy_path, or bare membership of a project the prefix names — because a
    niche filter that silently omits submitted work is worse than no filter.
    """
    from ..models.asset import Asset

    prefix = prefix.strip("/")
    under, loose_projects = ids_under_path(db, prefix)

    clauses = [
        # Stamped path: exact match or anything nested below it. LIKE is escaped
        # so a folder named "50%_off" cannot turn into a wildcard.
        Asset.taxonomy_path == prefix,
        Asset.taxonomy_path.like(
            prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "/%",
            escape="\\",
        ),
    ]
    if under:
        clauses.append(Asset.folder_id.in_(under))
    if loose_projects:
        clauses.append(and_(Asset.project_id.in_(loose_projects), Asset.folder_id.is_(None)))

    return or_(*clauses)


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
