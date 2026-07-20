from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session
import uuid
from ..models.user import User
from ..models.project import Project, ProjectMember, ProjectRole
from ..models.asset import Asset
from ..models.share import AssetShare, ShareLink, SharePermission
from ..models.library_access import LibraryAccess
from ..services.redis_service import verify_share_session


def has_library_asset_access(db: Session, asset: Asset, user: User) -> bool:
    """True if the user has a library grant covering this asset — a project-wide grant
    (folder_id NULL) or a folder grant matching the asset's folder. Mirrors the library
    browser's _access_filter so anything a user can see in the library they can open."""
    return db.query(LibraryAccess.id).filter(
        LibraryAccess.user_id == user.id,
        LibraryAccess.project_id == asset.project_id,
        or_(
            LibraryAccess.folder_id.is_(None),
            LibraryAccess.folder_id == asset.folder_id,
        ),
    ).first() is not None


def has_project_library_access(db: Session, project_id: uuid.UUID, user: User) -> bool:
    """True if the user has a PROJECT-LEVEL library grant (folder_id NULL), which conveys
    viewing the whole project. Folder-level grants do NOT grant project-wide view — those
    are scoped to their folder's assets via has_library_asset_access — so a folder grantee
    never leaks the rest of the project through can_view_project."""
    return db.query(LibraryAccess.id).filter(
        LibraryAccess.user_id == user.id,
        LibraryAccess.project_id == project_id,
        LibraryAccess.folder_id.is_(None),
    ).first() is not None


# ── Platform-level (superadmin / subadmin) ──────────────────────────────────────

def is_platform_admin(user: User) -> bool:
    """True for full admins (superadmin) and delegated sub-admins.

    Platform admins can view all activity across every project and comment on any
    asset — including the isolated per-submitter projects created by submission links —
    without being an explicit member of each one.
    """
    return bool(getattr(user, "is_superadmin", False) or getattr(user, "is_subadmin", False))


def require_platform_admin(user: User) -> None:
    if not is_platform_admin(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or sub-admin access required",
        )


def visible_visibilities(user: Optional[User]) -> list[str]:
    """Comment visibility tiers a viewer is allowed to see.

    This is the single source of truth for comment visibility. Every read path
    (authenticated list, share-link list, reply assembly) filters against it so
    the tiers cannot drift apart and leak:

    - Guests (no account, via share link): public only.
    - Authenticated team members: public + internal.
    - Platform admins (superadmin / subadmin): public + internal + admin.
    """
    if user is None:
        return ["public"]
    if is_platform_admin(user):
        return ["public", "internal", "admin"]
    return ["public", "internal"]


# ── Project-level ──────────────────────────────────────────────────────────────

def get_project_member(db: Session, project_id: uuid.UUID, user_id: uuid.UUID) -> ProjectMember | None:
    return db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id,
        ProjectMember.deleted_at.is_(None),
    ).first()


def require_project_role(
    db: Session,
    project_id: uuid.UUID,
    user: User,
    minimum_role: ProjectRole,
) -> ProjectMember | None:
    """Require the user to have at least `minimum_role` on the project.

    Role hierarchy (descending): owner > editor > reviewer > viewer

    Platform admins (superadmin / sub-admin) satisfy any role requirement without an
    explicit membership row — mirroring the read-side bypass in `can_view_project` /
    `can_access_asset`. This lets admins upload into and edit the isolated per-submitter
    submission projects they can already see but were never added to as members.
    Returns None for admins (no membership row exists); callers use this purely as a
    guard and never read the return value.
    """
    if is_platform_admin(user):
        return None
    ROLE_RANK = {
        ProjectRole.owner: 4,
        ProjectRole.editor: 3,
        ProjectRole.reviewer: 2,
        ProjectRole.viewer: 1,
    }
    member = get_project_member(db, project_id, user.id)
    if not member:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a project member")
    if ROLE_RANK[member.role] < ROLE_RANK[minimum_role]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Requires {minimum_role.value} role or higher",
        )
    return member


# ── Asset-level ────────────────────────────────────────────────────────────────

def is_public_project(db: Session, project_id: uuid.UUID) -> bool:
    """Check if a project is public."""
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.deleted_at.is_(None),
    ).first()
    return project is not None and project.is_public


def can_view_project(db: Session, project_id: uuid.UUID, user: User) -> bool:
    """True if the user may view a project's folders/assets.

    Platform admins (superadmin / subadmin) can view every project — so all admins
    share the same view regardless of explicit membership. Otherwise the user must be
    a project member or the project must be public.
    """
    if is_platform_admin(user):
        return True
    if get_project_member(db, project_id, user.id):
        return True
    # A project-level library grant conveys viewing the whole project.
    if has_project_library_access(db, project_id, user):
        return True
    return is_public_project(db, project_id)


def can_access_asset(db: Session, asset: Asset, user: User) -> bool:
    """Check if user can access the asset via any path."""
    # 0. Platform admins (superadmin / subadmin) can access every asset so they can
    #    review and comment on the latest revision from the global activity feed.
    if is_platform_admin(user):
        return True

    # 1. Asset creator
    if asset.created_by == user.id:
        return True

    # 2. Project member
    if get_project_member(db, asset.project_id, user.id):
        return True

    # 3. Direct AssetShare with user
    direct = db.query(AssetShare).filter(
        AssetShare.asset_id == asset.id,
        AssetShare.shared_with_user_id == user.id,
        AssetShare.deleted_at.is_(None),
    ).first()
    if direct:
        return True

    # 4. Library grant (project- or folder-level) — anything visible in the library
    #    must be openable. Scoped to the asset's folder for folder-level grants.
    if has_library_asset_access(db, asset, user):
        return True

    # 5. Public project — any authenticated user can view
    if is_public_project(db, asset.project_id):
        return True

    return False


def require_asset_access(db: Session, asset: Asset, user: User) -> None:
    if not can_access_asset(db, asset, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


def get_asset_share_permission(db: Session, asset: Asset, user: User) -> SharePermission:
    """Get the effective share permission for a user on an asset (highest wins)."""
    PERM_RANK = {
        SharePermission.approve: 3,
        SharePermission.comment: 2,
        SharePermission.view: 1,
    }

    best = SharePermission.view

    # Direct share
    direct = db.query(AssetShare).filter(
        AssetShare.asset_id == asset.id,
        AssetShare.shared_with_user_id == user.id,
        AssetShare.deleted_at.is_(None),
    ).first()
    if direct and PERM_RANK[direct.permission] > PERM_RANK[best]:
        best = direct.permission

    return best


# ── Share link validation ──────────────────────────────────────────────────────

def validate_share_link(db: Session, token: str) -> ShareLink:
    """Validate a share link token and return the link. Raises 404/410 on failure."""
    from datetime import datetime, timezone
    link = db.query(ShareLink).filter(
        ShareLink.token == token,
        ShareLink.deleted_at.is_(None),
    ).first()
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found")
    if not link.is_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Share link is disabled")
    if link.expires_at and link.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Share link has expired")
    return link


def validate_share_link_with_session(
    db: Session,
    token: str,
    share_session: "str | None" = None,
    current_user: "User | None" = None,
) -> ShareLink:
    """Validate a share link and verify password session if link is password-protected.
    Skips password check if the caller is the authenticated link creator."""
    link = validate_share_link(db, token)
    if link.password_hash:
        # Skip password for authenticated link creator (e.g. admin settings preview)
        if current_user and link.created_by == current_user.id:
            return link
        if not share_session or not verify_share_session(token, share_session):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Password required",
            )
    return link
