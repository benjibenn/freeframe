"""Celery tasks for Google Drive → Backblaze sync."""
import logging
import re
import tempfile
import uuid as uuid_lib
from datetime import datetime, timezone

from .celery_app import celery_app, send_task_safe
from ..database import SessionLocal
from ..models.drive_sync import DriveSyncConnection, DriveSyncedFile
from ..services.google_drive_service import list_video_files, download_stream
from ..services.s3_service import upload_fileobj
from ..services.import_service import register_s3_object_as_asset

logger = logging.getLogger(__name__)


def _safe_name(name: str) -> str:
    """Sanitize a filename: keep alphanumerics, dots, hyphens, underscores."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


@celery_app.task(name="apps.api.tasks.drive_sync_tasks.sync_one_file")
def sync_one_file(connection_id: str, file_id: str, file_name: str, file_mime: str, file_size: int, target_project_id: str, created_by: str) -> None:
    """Download and register a single Drive file as an asset."""
    db = SessionLocal()
    try:
        conn = (
            db.query(DriveSyncConnection)
            .filter(
                DriveSyncConnection.id == uuid_lib.UUID(connection_id),
                DriveSyncConnection.enabled.is_(True),
                DriveSyncConnection.deleted_at.is_(None),
            )
            .first()
        )
        if not conn:
            logger.info("sync_one_file: connection %s not found / disabled", connection_id)
            return

        already = (
            db.query(DriveSyncedFile)
            .filter(
                DriveSyncedFile.connection_id == conn.id,
                DriveSyncedFile.drive_file_id == file_id,
            )
            .first()
        )
        if already:
            return

        buf = tempfile.SpooledTemporaryFile(max_size=64 * 1024 * 1024)
        try:
            download_stream(file_id, buf)
            buf.seek(0)

            safe = _safe_name(file_name)
            s3_key = f"raw/{target_project_id}/drive/{file_id}/{safe}"
            upload_fileobj(s3_key, buf, file_mime)

            asset = register_s3_object_as_asset(
                db,
                target_project_id,
                s3_key,
                file_name,
                file_size,
                file_mime,
                created_by,
            )

            synced = DriveSyncedFile(
                connection_id=conn.id,
                drive_file_id=file_id,
                asset_id=asset.id,
            )
            db.add(synced)
            db.commit()
        except Exception as exc:
            db.rollback()
            conn.last_error = str(exc)
            db.commit()
            logger.exception(
                "sync_one_file: failed to sync file %s for connection %s: %s",
                file_id,
                connection_id,
                exc,
            )
        finally:
            buf.close()

    finally:
        db.close()


@celery_app.task(name="apps.api.tasks.drive_sync_tasks.sync_one_connection")
def sync_one_connection(connection_id: str) -> None:
    """List Drive files for one connection and enqueue a task per unseen file."""
    db = SessionLocal()
    try:
        conn = (
            db.query(DriveSyncConnection)
            .filter(
                DriveSyncConnection.id == uuid_lib.UUID(connection_id),
                DriveSyncConnection.enabled.is_(True),
                DriveSyncConnection.deleted_at.is_(None),
            )
            .first()
        )
        if not conn:
            logger.info("sync_one_connection: connection %s not found / disabled", connection_id)
            return

        video_files = list_video_files(conn.drive_folder_id)

        seen_rows = (
            db.query(DriveSyncedFile.drive_file_id)
            .filter(DriveSyncedFile.connection_id == conn.id)
            .all()
        )
        seen = {row.drive_file_id for row in seen_rows}

        dispatched = 0
        for file in video_files:
            if file["id"] in seen:
                continue
            send_task_safe(
                sync_one_file,
                str(conn.id),
                file["id"],
                file["name"],
                file["mimeType"],
                int(file.get("size") or 0),
                str(conn.target_project_id),
                str(conn.created_by),
            )
            dispatched += 1

        logger.info("sync_one_connection: dispatched %d file tasks for connection %s", dispatched, connection_id)

        conn.last_synced_at = datetime.now(timezone.utc)
        db.commit()

    finally:
        db.close()


@celery_app.task(name="apps.api.tasks.drive_sync_tasks.sync_drive_connections")
def sync_drive_connections() -> None:
    """Fan out: enqueue sync_one_connection for every enabled connection."""
    db = SessionLocal()
    try:
        conns = (
            db.query(DriveSyncConnection)
            .filter(
                DriveSyncConnection.enabled.is_(True),
                DriveSyncConnection.deleted_at.is_(None),
            )
            .all()
        )
        for conn in conns:
            send_task_safe(sync_one_connection, str(conn.id))
    finally:
        db.close()
