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


@celery_app.task(name="apps.api.tasks.drive_sync_tasks.sync_one_connection")
def sync_one_connection(connection_id: str) -> None:
    """Download new Drive files for one connection and register them as assets."""
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

        # Build set of already-seen drive file ids for this connection
        seen_rows = (
            db.query(DriveSyncedFile.drive_file_id)
            .filter(DriveSyncedFile.connection_id == conn.id)
            .all()
        )
        seen = {row.drive_file_id for row in seen_rows}

        had_failure = False

        for file in video_files:
            if file["id"] in seen:
                continue

            buf = tempfile.SpooledTemporaryFile(max_size=64 * 1024 * 1024)
            try:
                download_stream(file["id"], buf)
                buf.seek(0)

                safe = _safe_name(file["name"])
                s3_key = f"raw/{conn.target_project_id}/drive/{file['id']}/{safe}"
                upload_fileobj(s3_key, buf, file["mimeType"])

                asset = register_s3_object_as_asset(
                    db,
                    conn.target_project_id,
                    s3_key,
                    file["name"],
                    int(file.get("size") or 0),
                    file["mimeType"],
                    conn.created_by,
                )

                synced = DriveSyncedFile(
                    connection_id=conn.id,
                    drive_file_id=file["id"],
                    asset_id=asset.id,
                )
                db.add(synced)
                db.commit()
            except Exception as exc:
                db.rollback()
                had_failure = True
                conn.last_error = str(exc)
                db.commit()
                logger.exception(
                    "sync_one_connection: failed to sync file %s for connection %s: %s",
                    file["id"],
                    connection_id,
                    exc,
                )
            finally:
                buf.close()

        conn.last_synced_at = datetime.now(timezone.utc)
        if not had_failure:
            conn.last_error = None
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
