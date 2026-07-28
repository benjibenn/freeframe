"""Archiving after review status left the product.

Asset.status used to be a user-facing review workflow (draft / in_review /
approved / rejected / archived) that any editor could set. Only `archived` is
still meaningful, and it is now reachable *only* through these two verbs — no
schema accepts or returns the column any more. These tests pin that down:

- archive/unarchive actually move the column, because the Sorter's archive
  action and its undo are the only writers left and a silent no-op would look
  identical to success in the UI;
- unarchive lands on `draft`, not on whatever the asset held before, because the
  other statuses are unreachable and restoring one would resurrect a concept the
  product no longer has;
- both require editor role or higher, matching the tag verbs — archiving hides
  work from the Sorter and from external ad platforms, so it is not a viewer action.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


def _fake_asset():
    asset = MagicMock()
    asset.id = uuid.uuid4()
    asset.project_id = uuid.uuid4()
    asset.deleted_at = None
    return asset


def _fake_response(asset, db):
    # Build a real AssetResponse so response_model validation passes without a DB.
    from apps.api.schemas.asset import AssetResponse
    from apps.api.models.asset import AssetType
    now = datetime.now(timezone.utc)
    return AssetResponse(
        id=asset.id, project_id=asset.project_id, name="demo", description=None,
        asset_type=AssetType.video, rating=None, assignee_id=None, due_date=None,
        keywords=[], created_by=uuid.uuid4(), created_at=now, updated_at=now,
    )


@patch("apps.api.routers.assets._build_asset_response", side_effect=_fake_response)
@patch("apps.api.routers.assets.require_project_role")
def test_archive_sets_archived(_role, _build, client, mock_db, auth_headers):
    from apps.api.models.asset import AssetStatus

    asset = _fake_asset()
    mock_db.first.return_value = asset
    resp = client.post(f"/assets/{asset.id}/archive", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert asset.status == AssetStatus.archived


@patch("apps.api.routers.assets._build_asset_response", side_effect=_fake_response)
@patch("apps.api.routers.assets.require_project_role")
def test_unarchive_restores_draft(_role, _build, client, mock_db, auth_headers):
    from apps.api.models.asset import AssetStatus

    asset = _fake_asset()
    asset.status = AssetStatus.archived
    mock_db.first.return_value = asset
    resp = client.post(f"/assets/{asset.id}/unarchive", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert asset.status == AssetStatus.draft


@patch("apps.api.routers.assets.require_project_role")
def test_archive_404_when_missing(_role, client, mock_db, auth_headers):
    mock_db.first.return_value = None
    resp = client.post(f"/assets/{uuid.uuid4()}/archive", headers=auth_headers)
    assert resp.status_code == 404


@patch("apps.api.routers.assets._build_asset_response", side_effect=_fake_response)
@patch("apps.api.routers.assets.is_platform_admin", return_value=False)
def test_archive_requires_editor_role(_admin, _build, client, mock_db, auth_headers):
    from fastapi import HTTPException

    asset = _fake_asset()
    mock_db.first.return_value = asset
    with patch("apps.api.routers.assets.require_project_role",
               side_effect=HTTPException(status_code=403, detail="Requires editor role")):
        resp = client.post(f"/assets/{asset.id}/archive", headers=auth_headers)
    assert resp.status_code == 403


@patch("apps.api.routers.assets._build_asset_response", side_effect=_fake_response)
@patch("apps.api.routers.assets.is_platform_admin", return_value=False)
def test_unarchive_requires_editor_role(_admin, _build, client, mock_db, auth_headers):
    from fastapi import HTTPException

    asset = _fake_asset()
    mock_db.first.return_value = asset
    with patch("apps.api.routers.assets.require_project_role",
               side_effect=HTTPException(status_code=403, detail="Requires editor role")):
        resp = client.post(f"/assets/{asset.id}/unarchive", headers=auth_headers)
    assert resp.status_code == 403


def test_bulk_status_endpoint_is_gone(client, auth_headers):
    """The multi-select "Set status" bulk write is removed, not just hidden in the
    UI — leaving it live would let a stale tab keep setting unreachable statuses."""
    resp = client.patch(
        "/assets/bulk/status",
        json={"asset_ids": [str(uuid.uuid4())], "status": "approved"},
        headers=auth_headers,
    )
    assert resp.status_code in (404, 405)


def test_asset_update_rejects_status(client, mock_db, auth_headers):
    """PATCH /assets/{id} no longer carries status. Pydantic drops unknown keys, so
    this asserts the field is absent from the schema rather than that the call fails —
    the point is that a stale client's `status` can never reach the column."""
    from apps.api.schemas.asset import AssetUpdate, AssetResponse

    assert "status" not in AssetUpdate.model_fields
    assert "status" not in AssetResponse.model_fields
