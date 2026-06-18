"""
Tests for the Drive-sync router and Celery task.

Intent per test:
  ROUTER
  (a) non-admin → 403 on every admin endpoint (gate blocks unauthorized access)
  (b) admin create → 201 with extracted folder id (URL parsed correctly)
  (c) sync-now → queues task via send_task_safe, returns {"status": "queued"}
  (d) delete → 204, soft-deletes the connection

  TASK (sync_one_connection)
  (e) only NEW files are imported — already-seen drive_file_ids are skipped
  (f) a failing file does NOT abort the batch; last_error is set on connection
      and the other file is still imported
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(is_admin: bool = False) -> MagicMock:
    u = MagicMock()
    u.id = uuid.uuid4()
    u.is_superadmin = is_admin
    u.is_subadmin = False
    return u


def _make_connection(conn_id=None, folder_id="FOLDER123", project_id=None) -> MagicMock:
    conn = MagicMock()
    conn.id = conn_id or uuid.uuid4()
    conn.drive_folder_id = folder_id
    conn.target_project_id = project_id or uuid.uuid4()
    conn.enabled = True
    conn.deleted_at = None
    conn.created_by = uuid.uuid4()
    conn.folder_name = None
    conn.last_synced_at = None
    conn.last_error = None
    return conn


# ---------------------------------------------------------------------------
# Router tests — use the FastAPI test client
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_user():
    return _make_user(is_admin=True)


@pytest.fixture
def non_admin_user():
    return _make_user(is_admin=False)


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.query.return_value = db
    db.filter.return_value = db
    db.first.return_value = None
    db.all.return_value = []
    db.count.return_value = 0
    db.add.return_value = None
    db.flush.return_value = None
    db.commit.return_value = None
    db.refresh.return_value = None
    db.close.return_value = None
    return db


@pytest.fixture
def client(mock_db):
    with patch("apps.api.services.s3_service.ensure_bucket_exists"):
        with patch("apps.api.services.s3_service.get_s3_client", return_value=MagicMock()):
            from fastapi.testclient import TestClient
            from apps.api.main import app
            from apps.api.database import get_db
            from apps.api.routers import drive_sync as drive_sync_router_mod

            # Register the drive-sync router if not already registered
            # (main.py is not modified per spec; tests mount it directly)
            _route_paths = {r.path for r in app.routes}
            if "/admin/drive-sync/service-account" not in _route_paths:
                app.include_router(drive_sync_router_mod.router)

            app.dependency_overrides[get_db] = lambda: mock_db
            yield TestClient(app, raise_server_exceptions=False)
            app.dependency_overrides.clear()


def _inject_user(client_fixture, user):
    """Override get_current_user dependency for the duration of a test."""
    from apps.api.main import app
    from apps.api.middleware.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: user


# (a) non-admin → 403
def test_non_admin_blocked(client, mock_db, non_admin_user):
    """Non-admin users must be rejected with 403 on all drive-sync endpoints."""
    _inject_user(client, non_admin_user)
    with patch("apps.api.routers.drive_sync.is_platform_admin", return_value=False):
        r = client.get("/admin/drive-sync/service-account")
        assert r.status_code == 403, "gate must block non-admin on service-account"

        r = client.get("/admin/drive-sync")
        assert r.status_code == 403, "gate must block non-admin on list"

        r = client.post("/admin/drive-sync", json={"folder_link": "https://x.com", "target_project_id": str(uuid.uuid4())})
        assert r.status_code == 403, "gate must block non-admin on create"


# (b) admin create → 201 with extracted folder id
def test_admin_create_connection(client, mock_db, admin_user):
    """POST /admin/drive-sync must parse the folder link and return 201."""
    _inject_user(client, admin_user)

    project_id = uuid.uuid4()
    conn_id = uuid.uuid4()

    # Mock project lookup
    mock_project = MagicMock()
    mock_project.id = project_id
    mock_project.deleted_at = None

    # Mock the connection returned after refresh
    mock_conn = _make_connection(conn_id=conn_id, folder_id="FOLDERABC123", project_id=project_id)
    mock_conn.synced_count = 0

    # db.query().filter().first() for project → returns mock_project
    # db.query().filter().count() for synced_count → returns 0
    db_query = MagicMock()
    db_query.filter.return_value = db_query
    db_query.first.return_value = mock_project
    db_query.count.return_value = 0
    db_query.all.return_value = []

    # After refresh, conn should be returned by the db chain
    def side_effect_refresh(obj):
        # simulate refresh setting attributes from mock_conn
        obj.id = mock_conn.id
        obj.drive_folder_id = mock_conn.drive_folder_id
        obj.target_project_id = mock_conn.target_project_id
        obj.enabled = mock_conn.enabled
        obj.folder_name = mock_conn.folder_name
        obj.last_synced_at = mock_conn.last_synced_at
        obj.last_error = mock_conn.last_error

    mock_db.query.return_value = db_query
    mock_db.refresh.side_effect = side_effect_refresh

    with patch("apps.api.routers.drive_sync.is_platform_admin", return_value=True):
        with patch("apps.api.routers.drive_sync.extract_folder_id", return_value="FOLDERABC123") as mock_extract:
            folder_url = "https://drive.google.com/drive/folders/FOLDERABC123"
            r = client.post(
                "/admin/drive-sync",
                json={"folder_link": folder_url, "target_project_id": str(project_id)},
            )
            assert r.status_code == 201, f"expected 201, got {r.status_code}: {r.text}"
            # folder link was parsed
            mock_extract.assert_called_once_with(folder_url)
            data = r.json()
            assert data["drive_folder_id"] == "FOLDERABC123"


# (c) sync-now → queued
def test_sync_now_enqueues(client, mock_db, admin_user):
    """POST /admin/drive-sync/{id}/sync-now must call send_task_safe and return queued."""
    _inject_user(client, admin_user)

    conn_id = uuid.uuid4()
    mock_conn = _make_connection(conn_id=conn_id)

    db_query = MagicMock()
    db_query.filter.return_value = db_query
    db_query.first.return_value = mock_conn
    db_query.count.return_value = 0
    mock_db.query.return_value = db_query

    with patch("apps.api.routers.drive_sync.is_platform_admin", return_value=True):
        with patch("apps.api.routers.drive_sync.send_task_safe") as mock_send:
            r = client.post(f"/admin/drive-sync/{conn_id}/sync-now")
            assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
            assert r.json()["status"] == "queued", "response must confirm task is queued"
            # send_task_safe must have been called (task dispatch is the side-effect)
            mock_send.assert_called_once()


# (d) delete → 204
def test_delete_soft_deletes(client, mock_db, admin_user):
    """DELETE /admin/drive-sync/{id} must soft-delete (set deleted_at) and return 204."""
    _inject_user(client, admin_user)

    conn_id = uuid.uuid4()
    mock_conn = _make_connection(conn_id=conn_id)

    db_query = MagicMock()
    db_query.filter.return_value = db_query
    db_query.first.return_value = mock_conn
    mock_db.query.return_value = db_query

    with patch("apps.api.routers.drive_sync.is_platform_admin", return_value=True):
        r = client.delete(f"/admin/drive-sync/{conn_id}")
        assert r.status_code == 204, f"expected 204, got {r.status_code}: {r.text}"
        # deleted_at was set (not still None)
        assert mock_conn.deleted_at is not None, "deleted_at must be set after soft-delete"


# ---------------------------------------------------------------------------
# Task tests — call sync_one_connection directly with mocked dependencies
# ---------------------------------------------------------------------------

def _make_task_db(conn, seen_file_ids: list[str]):
    """Build a mock DB session wired to return conn and the seen file rows."""
    db = MagicMock()

    seen_rows = [MagicMock(drive_file_id=fid) for fid in seen_file_ids]

    def query_side_effect(model_cls):
        q = MagicMock()
        q.filter.return_value = q
        q.first.return_value = conn
        q.all.return_value = seen_rows
        return q

    db.query.side_effect = query_side_effect
    db.add.return_value = None
    db.commit.return_value = None
    db.rollback.return_value = None
    db.close.return_value = None
    return db


TWO_FILES = [
    {"id": "FILE_A", "name": "video_a.mp4", "mimeType": "video/mp4", "size": 1000},
    {"id": "FILE_B", "name": "video b.mp4", "mimeType": "video/mp4", "size": 2000},
]


# (e) only NEW files are imported
def test_sync_skips_already_seen_files():
    """sync_one_connection must skip files already recorded in DriveSyncedFile.

    FILE_A is already seen → only FILE_B should be downloaded and registered.
    """
    conn = _make_connection()
    db = _make_task_db(conn, seen_file_ids=["FILE_A"])

    mock_asset = MagicMock()
    mock_asset.id = uuid.uuid4()

    with patch("apps.api.tasks.drive_sync_tasks.SessionLocal", return_value=db):
        with patch("apps.api.tasks.drive_sync_tasks.list_video_files", return_value=TWO_FILES) as mock_list:
            with patch("apps.api.tasks.drive_sync_tasks.download_stream") as mock_dl:
                with patch("apps.api.tasks.drive_sync_tasks.upload_fileobj") as mock_upload:
                    with patch("apps.api.tasks.drive_sync_tasks.register_s3_object_as_asset", return_value=mock_asset) as mock_reg:
                        sync_one_connection(str(conn.id))

        mock_list.assert_called_once_with(conn.drive_folder_id)
        # only FILE_B triggered download (FILE_A was already seen)
        assert mock_dl.call_count == 1, "must download only unseen files"
        call_args = mock_dl.call_args[0]
        assert call_args[0] == "FILE_B", "must download FILE_B, not the already-seen FILE_A"
        assert mock_reg.call_count == 1, "must register only the new file"
        # last_synced_at was updated
        assert conn.last_synced_at is not None, "last_synced_at must be set after sync"
        # no failure → last_error cleared
        assert conn.last_error is None, "last_error must be cleared on successful sync"


# (f) failure isolation: one bad file → last_error set; other file still imports
def test_sync_failure_isolation():
    """When one file fails, sync_one_connection must:
      - record last_error on the connection
      - continue to import the remaining files
    FILE_A raises on register; FILE_B must still be imported.
    """
    conn = _make_connection()
    db = _make_task_db(conn, seen_file_ids=[])  # no files seen yet

    asset_b = MagicMock()
    asset_b.id = uuid.uuid4()

    def register_side_effect(db, project_id, s3_key, name, *args, **kwargs):
        if "FILE_A" in s3_key:
            raise RuntimeError("simulated Drive download failure")
        return asset_b

    with patch("apps.api.tasks.drive_sync_tasks.SessionLocal", return_value=db):
        with patch("apps.api.tasks.drive_sync_tasks.list_video_files", return_value=TWO_FILES):
            with patch("apps.api.tasks.drive_sync_tasks.download_stream"):
                with patch("apps.api.tasks.drive_sync_tasks.upload_fileobj"):
                    with patch("apps.api.tasks.drive_sync_tasks.register_s3_object_as_asset", side_effect=register_side_effect) as mock_reg:
                        sync_one_connection(str(conn.id))

    # Both files were attempted
    assert mock_reg.call_count == 2, "both files must be attempted even when first fails"
    # last_error was set due to FILE_A's failure
    assert conn.last_error is not None, "last_error must be set when any file fails"
    assert "simulated" in conn.last_error, "last_error should contain the exception message"
    # last_synced_at still updated
    assert conn.last_synced_at is not None, "last_synced_at must be updated even when failures occurred"


# needed so the import at test-collection time works without a real task decorator issue
from apps.api.tasks.drive_sync_tasks import sync_one_connection
