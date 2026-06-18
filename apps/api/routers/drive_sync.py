"""Platform-admin endpoints for Google Drive sync connections."""
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.drive_sync import DriveSyncConnection, DriveSyncedFile
from ..models.project import Project
from ..models.user import User
from ..schemas.drive_sync import (
    DriveSyncConnectionCreate,
    DriveSyncConnectionResponse,
    DriveSyncConnectionUpdate,
)
from ..services.google_drive_service import extract_folder_id, service_account_email
from ..services.permissions import is_platform_admin
from ..tasks.celery_app import send_task_safe

router = APIRouter(prefix="/admin/drive-sync", tags=["drive-sync"])


def _require_admin(current_user: User) -> None:
    if not is_platform_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")


def _get_connection_or_404(db: Session, connection_id: uuid.UUID) -> DriveSyncConnection:
    conn = (
        db.query(DriveSyncConnection)
        .filter(
            DriveSyncConnection.id == connection_id,
            DriveSyncConnection.deleted_at.is_(None),
        )
        .first()
    )
    if not conn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    return conn


def _synced_count(db: Session, connection_id: uuid.UUID) -> int:
    return (
        db.query(DriveSyncedFile)
        .filter(DriveSyncedFile.connection_id == connection_id)
        .count()
    )


def _to_response(db: Session, conn: DriveSyncConnection) -> DriveSyncConnectionResponse:
    return DriveSyncConnectionResponse(
        id=conn.id,
        drive_folder_id=conn.drive_folder_id,
        folder_name=conn.folder_name,
        target_project_id=conn.target_project_id,
        enabled=conn.enabled,
        last_synced_at=conn.last_synced_at,
        last_error=conn.last_error,
        synced_count=_synced_count(db, conn.id),
    )


@router.get("/service-account")
def get_service_account(
    current_user: User = Depends(get_current_user),
):
    """Return the SA email that Drive folders must be shared with."""
    _require_admin(current_user)
    return {"email": service_account_email()}


@router.get("", response_model=list[DriveSyncConnectionResponse])
def list_connections(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all non-deleted drive sync connections."""
    _require_admin(current_user)
    conns = (
        db.query(DriveSyncConnection)
        .filter(DriveSyncConnection.deleted_at.is_(None))
        .all()
    )
    return [_to_response(db, c) for c in conns]


@router.post("", response_model=DriveSyncConnectionResponse, status_code=status.HTTP_201_CREATED)
def create_connection(
    body: DriveSyncConnectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Parse Drive folder link, validate the target project, create a connection."""
    _require_admin(current_user)

    folder_id = extract_folder_id(body.folder_link)

    project = (
        db.query(Project)
        .filter(
            Project.id == body.target_project_id,
            Project.deleted_at.is_(None),
        )
        .first()
    )
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    conn = DriveSyncConnection(
        drive_folder_id=folder_id,
        target_project_id=body.target_project_id,
        created_by=current_user.id,
        enabled=True,
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return _to_response(db, conn)


@router.patch("/{connection_id}", response_model=DriveSyncConnectionResponse)
def update_connection(
    connection_id: uuid.UUID,
    body: DriveSyncConnectionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Enable or disable a connection."""
    _require_admin(current_user)
    conn = _get_connection_or_404(db, connection_id)
    if body.enabled is not None:
        conn.enabled = body.enabled
    db.commit()
    db.refresh(conn)
    return _to_response(db, conn)


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(
    connection_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft-delete a connection."""
    _require_admin(current_user)
    conn = _get_connection_or_404(db, connection_id)
    conn.deleted_at = datetime.now(timezone.utc)
    db.commit()


@router.post("/{connection_id}/sync-now")
def sync_now(
    connection_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Enqueue an immediate sync for one connection."""
    _require_admin(current_user)
    _get_connection_or_404(db, connection_id)

    from ..tasks.drive_sync_tasks import sync_one_connection
    send_task_safe(sync_one_connection, str(connection_id))
    return {"status": "queued"}
