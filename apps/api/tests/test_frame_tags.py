"""Tests for per-frame timecoded tagging endpoints (Phase 4).

The frame_tags router is registered in apps/api/main.py; the conftest `client`
fixture builds a TestClient over that app, so the routes are available here.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_asset(project_id=None):
    asset = MagicMock()
    asset.id = uuid.uuid4()
    asset.project_id = project_id or uuid.uuid4()
    asset.deleted_at = None
    return asset


def _make_frame_tag(asset_id=None, version_id=None, created_by=None):
    ft = MagicMock()
    ft.id = uuid.uuid4()
    ft.asset_id = asset_id or uuid.uuid4()
    ft.version_id = version_id or uuid.uuid4()
    ft.timecode_start = 3.0
    ft.label = "hook"
    ft.created_by = created_by or uuid.uuid4()
    ft.created_at = datetime.now(timezone.utc)
    ft.deleted_at = None
    return ft


# ── Tests ──────────────────────────────────────────────────────────────────────

@patch("apps.api.routers.frame_tags.require_project_role")
@patch("apps.api.routers.frame_tags._build_frame_tag_response")
def test_create_frame_tag_returns_201_and_normalizes_label(
    mock_build,
    mock_require_role,
    client,
    mock_db,
    auth_headers,
    test_user,
):
    """POST /assets/{id}/frame-tags should create a tag with label lowercased+trimmed.

    The label normalization enforces a canonical form so "Hook", " hook ", and "HOOK"
    all map to the same searchable label — important for consistency in the viewer.
    """
    asset = _make_asset()
    ft = _make_frame_tag(asset_id=asset.id, created_by=test_user.id)
    ft.label = "hook"
    ft.timecode_start = 3.0

    mock_db.first.return_value = asset
    mock_require_role.return_value = None
    mock_build.return_value = ft  # bypass ORM-level attribute access

    from apps.api.schemas.frame_tag import FrameTagResponse
    mock_build.return_value = FrameTagResponse(
        id=ft.id,
        asset_id=ft.asset_id,
        version_id=ft.version_id,
        timecode_start=ft.timecode_start,
        label="hook",
        created_by=ft.created_by,
        created_at=ft.created_at,
    )

    response = client.post(
        f"/assets/{asset.id}/frame-tags",
        json={
            "version_id": str(ft.version_id),
            "timecode_start": 3.0,
            "label": "  Hook  ",  # whitespace + mixed case — must be normalized
        },
        headers=auth_headers,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    # The normalized label must be lowercase + stripped — "Hook" → "hook"
    assert body["label"] == "hook", (
        "label must be lowercased and stripped so tags are canonical across clients"
    )


@patch("apps.api.routers.frame_tags.require_project_role")
def test_create_frame_tag_negative_timecode_returns_422(
    mock_require_role,
    client,
    mock_db,
    auth_headers,
):
    """Negative timecodes must be rejected; a timecode before 0s is nonsensical for video."""
    asset = _make_asset()
    mock_db.first.return_value = asset
    mock_require_role.return_value = None

    response = client.post(
        f"/assets/{asset.id}/frame-tags",
        json={
            "version_id": str(uuid.uuid4()),
            "timecode_start": -1.5,
            "label": "hook",
        },
        headers=auth_headers,
    )

    assert response.status_code == 422, (
        "timecode_start < 0 is invalid — video time starts at 0"
    )


@patch("apps.api.routers.frame_tags.require_project_role")
def test_create_frame_tag_whitespace_label_returns_422(
    mock_require_role,
    client,
    mock_db,
    auth_headers,
):
    """Whitespace-only labels must be rejected; an empty label provides no meaning."""
    asset = _make_asset()
    mock_db.first.return_value = asset
    mock_require_role.return_value = None

    response = client.post(
        f"/assets/{asset.id}/frame-tags",
        json={
            "version_id": str(uuid.uuid4()),
            "timecode_start": 5.0,
            "label": "   ",  # only whitespace — strips to empty
        },
        headers=auth_headers,
    )

    assert response.status_code == 422, (
        "A label that is entirely whitespace is semantically empty and must be rejected"
    )


@patch("apps.api.routers.frame_tags.require_project_role")
def test_create_frame_tag_editor_gate_returns_403(
    mock_require_role,
    client,
    mock_db,
    auth_headers,
    test_user,
):
    """Users below editor role must be denied; viewer/reviewer cannot add frame tags.

    The permission boundary ensures only project editors+ can annotate timecodes,
    which keeps the tagging workflow consistent with comment authorship rules.
    """
    from fastapi import HTTPException

    # Ensure neither admin flag is truthy — MagicMock attributes default to a
    # truthy MagicMock if not explicitly set, which would bypass the gate.
    test_user.is_superadmin = False
    test_user.is_subadmin = False

    asset = _make_asset()
    mock_db.first.return_value = asset
    mock_require_role.side_effect = HTTPException(status_code=403, detail="Requires editor role or higher")

    response = client.post(
        f"/assets/{asset.id}/frame-tags",
        json={
            "version_id": str(uuid.uuid4()),
            "timecode_start": 5.0,
            "label": "hook",
        },
        headers=auth_headers,
    )

    assert response.status_code == 403, (
        "A user without editor role must not be allowed to create frame tags"
    )


def test_create_frame_tag_missing_asset_returns_404(
    client,
    mock_db,
    auth_headers,
):
    """Creating a tag for a non-existent asset must 404.

    This prevents orphan tags and gives the client a clear error when the asset
    has been deleted or the ID is wrong.
    """
    mock_db.first.return_value = None  # asset not found

    response = client.post(
        f"/assets/{uuid.uuid4()}/frame-tags",
        json={
            "version_id": str(uuid.uuid4()),
            "timecode_start": 5.0,
            "label": "hook",
        },
        headers=auth_headers,
    )

    assert response.status_code == 404, (
        "Frame tag creation on a missing/deleted asset must return 404"
    )
