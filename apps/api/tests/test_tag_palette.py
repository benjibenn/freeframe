"""Tests for per-project editable tag palette endpoints.

These tests mount the tag_palette router on a standalone FastAPI app so that
main.py does not need to be modified.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ── App fixture ────────────────────────────────────────────────────────────────

@pytest.fixture
def palette_client(mock_db, test_user):
    """TestClient for a minimal app that only mounts the tag_palette router."""
    import os
    os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/freeframe_test")

    from apps.api.routers.tag_palette import router
    from apps.api.database import get_db
    from apps.api.middleware.auth import get_current_user

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: test_user
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_palette_label(project_id=None, created_by=None, position=1):
    row = MagicMock()
    row.id = uuid.uuid4()
    row.project_id = project_id or uuid.uuid4()
    row.label = "hero"
    row.color = "#ff0000"
    row.position = position
    row.created_by = created_by or uuid.uuid4()
    row.created_at = datetime.now(timezone.utc)
    row.updated_at = datetime.now(timezone.utc)
    row.deleted_at = None
    return row


# ── Tests ──────────────────────────────────────────────────────────────────────

@patch("apps.api.routers.tag_palette.require_project_role")
def test_create_label_201_trims_label(
    mock_require_role,
    palette_client,
    mock_db,
    test_user,
):
    """POST /projects/{id}/tag-palette should trim label and return 201."""
    project_id = uuid.uuid4()
    row = _make_palette_label(project_id=project_id, created_by=test_user.id)
    row.label = "hero"  # trimmed value

    # scalar() for max position query
    mock_db.scalar.return_value = None
    mock_db.first.return_value = row
    mock_require_role.return_value = None

    # After db.refresh, the row attributes are used; mock refresh to set them
    def fake_refresh(obj):
        obj.id = row.id
        obj.project_id = row.project_id
        obj.label = "hero"
        obj.color = None
        obj.position = 1

    mock_db.refresh.side_effect = fake_refresh

    response = palette_client.post(
        f"/projects/{project_id}/tag-palette",
        json={"label": "  hero  "},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["label"] == "hero", "label must be trimmed"


@patch("apps.api.routers.tag_palette.require_project_role")
def test_create_label_empty_label_422(
    mock_require_role,
    palette_client,
    mock_db,
):
    """POST with whitespace-only label must return 422."""
    project_id = uuid.uuid4()
    mock_require_role.return_value = None
    mock_db.scalar.return_value = None

    response = palette_client.post(
        f"/projects/{project_id}/tag-palette",
        json={"label": "   "},
    )

    assert response.status_code == 422, response.text


@patch("apps.api.routers.tag_palette.require_project_role")
def test_create_label_editor_gate_403(
    mock_require_role,
    palette_client,
    mock_db,
    test_user,
):
    """Editor gate must be enforced; non-editors get 403."""
    from fastapi import HTTPException

    test_user.is_superadmin = False
    test_user.is_subadmin = False
    project_id = uuid.uuid4()
    mock_require_role.side_effect = HTTPException(status_code=403, detail="Requires editor role or higher")
    mock_db.scalar.return_value = None

    response = palette_client.post(
        f"/projects/{project_id}/tag-palette",
        json={"label": "hero"},
    )

    assert response.status_code == 403, response.text


@patch("apps.api.routers.tag_palette.can_view_project")
def test_list_labels_ordered_by_position_then_created_at(
    mock_can_view,
    palette_client,
    mock_db,
):
    """GET /projects/{id}/tag-palette returns labels ordered by position then created_at."""
    project_id = uuid.uuid4()
    mock_can_view.return_value = True

    now = datetime.now(timezone.utc)
    label_a = _make_palette_label(project_id=project_id, position=1)
    label_a.created_at = now
    label_a.label = "alpha"
    label_b = _make_palette_label(project_id=project_id, position=2)
    label_b.created_at = now
    label_b.label = "beta"

    # Chain: query().filter().order_by().all()
    # order_by returns a new MagicMock by default; wire it back to mock_db so .all() works.
    mock_db.order_by.return_value = mock_db
    mock_db.all.return_value = [label_a, label_b]

    response = palette_client.get(f"/projects/{project_id}/tag-palette")

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 2
    assert body[0]["label"] == "alpha"
    assert body[1]["label"] == "beta"


@patch("apps.api.routers.tag_palette.require_project_role")
def test_delete_label_soft_deletes_204(
    mock_require_role,
    palette_client,
    mock_db,
    test_user,
):
    """DELETE /tag-palette/{id} must soft-delete (set deleted_at) and return 204."""
    row = _make_palette_label(created_by=test_user.id)
    mock_db.first.return_value = row
    mock_require_role.return_value = None

    response = palette_client.delete(f"/tag-palette/{row.id}")

    assert response.status_code == 204, response.text
    assert row.deleted_at is not None, "deleted_at must be set on soft-delete"
    mock_db.commit.assert_called()
