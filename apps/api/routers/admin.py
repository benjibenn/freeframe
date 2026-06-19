"""Admin endpoints for user management."""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
import uuid

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.user import User, UserStatus
from ..models.api_key import APIKey, generate_api_key, hash_api_key, API_KEY_PREFIX
from ..schemas.auth import UserResponse, UpdateUserRoleRequest, UpdateSubadminRequest, UpdateUidRequest, UpdateNicknameRequest
from ..schemas.api_key import APIKeyResponse, APIKeyCreate, APIKeyCreated

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_superadmin(current_user: User) -> None:
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can access this endpoint",
        )


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/users", response_model=list[UserResponse])
def list_all_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all users in the system. Only accessible by admins."""
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can access this endpoint"
        )

    users = db.query(User).filter(User.deleted_at.is_(None)).all()
    return users

@router.patch("/users/{user_id}/deactivate", response_model=UserResponse)
def deactivate_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Deactivate a user. Admins cannot deactivate themselves."""
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can deactivate users"
        )

    # Prevent admin from deactivating themselves
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate yourself"
        )

    user = db.query(User).filter(User.id == user_id, User.deleted_at.is_(None)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.status = UserStatus.deactivated
    db.commit()
    db.refresh(user)
    return user

@router.patch("/users/{user_id}/reactivate", response_model=UserResponse)
def reactivate_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reactivate a deactivated user. Only accessible by admins."""
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can reactivate users"
        )

    user = db.query(User).filter(User.id == user_id, User.deleted_at.is_(None)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.status = UserStatus.active
    db.commit()
    db.refresh(user)
    return user

@router.patch("/users/{user_id}/role", response_model=UserResponse)
def update_user_role(
    user_id: uuid.UUID,
    body: UpdateUserRoleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Promote or demote a user to/from admin role. Only accessible by admins."""
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can change user roles"
        )

    # Prevent admin from removing their own admin role
    if user_id == current_user.id and not body.is_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot remove your own admin role"
        )

    user = db.query(User).filter(User.id == user_id, User.deleted_at.is_(None)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_superadmin = body.is_admin
    db.commit()
    db.refresh(user)
    return user

@router.patch("/users/{user_id}/subadmin", response_model=UserResponse)
def update_user_subadmin(
    user_id: uuid.UUID,
    body: UpdateSubadminRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Assign or revoke the sub-admin role. Only full admins (superadmin) can do this.

    A sub-admin can view all platform activity and comment on any asset, but cannot
    manage users or change roles — so this assignment stays superadmin-only.
    """
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can assign sub-admins"
        )

    user = db.query(User).filter(User.id == user_id, User.deleted_at.is_(None)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_subadmin = body.is_subadmin
    db.commit()
    db.refresh(user)
    return user


# ── User display number (uid) ────────────────────────────────────────────────────

def _lowest_free_uid(db: Session) -> int:
    """Lowest positive integer (>= 1) not present in the ``uid`` column across ALL
    user rows — including deactivated AND soft-deleted — so freed numbers are reused
    but never collide with a retained one."""
    taken = {
        row[0]
        for row in db.query(User.uid).filter(User.uid.isnot(None)).all()
    }
    n = 1
    while n in taken:
        n += 1
    return n


@router.post("/users/{user_id}/uid:grant", response_model=UserResponse)
def grant_user_uid(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Auto-assign the lowest-free display number to a user. Superadmin only.

    Rejects re-grant (409) if the user already has a uid — admin must edit instead.
    On a unique-constraint race, recomputes the lowest-free number once and retries.
    """
    _require_superadmin(current_user)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.uid is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User already has uid {user.uid}; edit it instead of re-granting",
        )

    for attempt in range(2):
        user.uid = _lowest_free_uid(db)
        try:
            db.commit()
            break
        except IntegrityError:
            db.rollback()
            if attempt == 1:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Could not assign a uid due to a concurrent grant; retry",
                )
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

    db.refresh(user)
    return user


@router.patch("/users/{user_id}/uid", response_model=UserResponse)
def update_user_uid(
    user_id: uuid.UUID,
    body: UpdateUidRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Explicitly set, change, or clear (revoke) a user's display number. Superadmin only.

    ``uid=None`` clears it. An integer >= 1 sets it; ``< 1`` -> 422. A value already
    held by another user -> 409 naming the holder. The unique constraint is the
    ultimate source of truth.
    """
    _require_superadmin(current_user)

    if body.uid is not None and body.uid < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="uid must be a positive integer (>= 1)",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if body.uid is not None:
        holder = (
            db.query(User)
            .filter(User.uid == body.uid, User.id != user_id)
            .first()
        )
        if holder is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"uid {body.uid} is already assigned to {holder.name}",
            )

    user.uid = body.uid
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"uid {body.uid} is already assigned to another user",
        )
    db.refresh(user)
    return user


# ── User display nickname ─────────────────────────────────────────────────────────

@router.patch("/users/{user_id}/nickname", response_model=UserResponse)
def update_user_nickname(
    user_id: uuid.UUID,
    body: UpdateNicknameRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Set, change, or clear a user's display nickname. Superadmin only.

    Whitespace is trimmed. An empty/whitespace-only value (or ``null``) clears it.
    A value longer than 50 chars -> 422. A nickname already held (case-insensitively)
    by another user -> 409 naming the holder; case is preserved on store. The
    functional unique index ``uq_users_nickname_lower`` is the ultimate source of truth.
    """
    _require_superadmin(current_user)

    value = body.nickname.strip() if body.nickname is not None else None

    # Structural validation first (mirrors the uid endpoint's < 1 check).
    if value and len(value) > 50:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="nickname must be at most 50 characters",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not value:
        # Empty / whitespace-only / None -> clear.
        user.nickname = None
    else:
        holder = (
            db.query(User)
            .filter(func.lower(User.nickname) == value.lower(), User.id != user_id)
            .first()
        )
        if holder is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"nickname '{value}' is already taken by {holder.name}",
            )
        user.nickname = value

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"nickname '{value}' is already taken by another user",
        )
    db.refresh(user)
    return user


# ── Public API keys ──────────────────────────────────────────────────────────────

def _api_key_to_response(k: APIKey, creator_name: str | None) -> APIKeyResponse:
    return APIKeyResponse(
        id=k.id,
        name=k.name,
        key_prefix=k.key_prefix,
        created_by=k.created_by,
        created_by_name=creator_name,
        last_used_at=k.last_used_at,
        created_at=k.created_at,
        revoked_at=k.revoked_at,
        is_active=k.revoked_at is None,
    )


@router.get("/api-keys", response_model=list[APIKeyResponse])
def list_api_keys(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all public API keys (newest first). Admin only.

    Keys are returned with only their prefix — the full secret is never
    retrievable after creation."""
    _require_superadmin(current_user)

    keys = db.query(APIKey).order_by(APIKey.created_at.desc()).all()
    names = {
        u.id: u.name
        for u in db.query(User).filter(User.id.in_({k.created_by for k in keys})).all()
    } if keys else {}
    return [_api_key_to_response(k, names.get(k.created_by)) for k in keys]


@router.post("/api-keys", response_model=APIKeyCreated, status_code=status.HTTP_201_CREATED)
def create_api_key(
    body: APIKeyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new public API key. The full key is returned ONCE — store it now.
    Admin only."""
    _require_superadmin(current_user)

    raw_key = generate_api_key()
    key = APIKey(
        name=body.name,
        key_prefix=raw_key[:13],  # e.g. "ffpk_Gr366cWq"
        key_hash=hash_api_key(raw_key),
        created_by=current_user.id,
    )
    db.add(key)
    db.commit()
    db.refresh(key)

    resp = _api_key_to_response(key, current_user.name)
    return APIKeyCreated(**resp.model_dump(), key=raw_key)


@router.delete("/api-keys/{key_id}", response_model=APIKeyResponse)
def revoke_api_key(
    key_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Revoke an API key. It immediately stops authenticating; the row is kept
    for audit. Admin only."""
    _require_superadmin(current_user)

    key = db.query(APIKey).filter(APIKey.id == key_id).first()
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    if key.revoked_at is None:
        key.revoked_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(key)

    creator = db.query(User).filter(User.id == key.created_by).first()
    return _api_key_to_response(key, creator.name if creator else None)
