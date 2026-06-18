"""Atomic single-tag add/remove on Asset.keywords. These verbs exist (vs PUT /tags
which replaces the whole array) so rapid keyboard tagging can't lose concurrent writes."""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


def _fake_asset(keywords):
    asset = MagicMock()
    asset.id = uuid.uuid4()
    asset.project_id = uuid.uuid4()
    asset.keywords = list(keywords)
    asset.deleted_at = None
    return asset


def _fake_response(asset, db):
    # Build a real AssetResponse so response_model validation passes without a DB.
    from apps.api.schemas.asset import AssetResponse
    from apps.api.models.asset import AssetType, AssetStatus
    now = datetime.now(timezone.utc)
    return AssetResponse(
        id=asset.id, project_id=asset.project_id, name="demo", description=None,
        asset_type=AssetType.video, status=AssetStatus.draft, rating=None,
        assignee_id=None, due_date=None, keywords=asset.keywords,
        created_by=uuid.uuid4(), created_at=now, updated_at=now,
    )


@patch("apps.api.routers.assets._build_asset_response", side_effect=_fake_response)
@patch("apps.api.routers.assets.require_project_role")
def test_add_tag_appends_normalized(_role, _build, client, mock_db, auth_headers):
    asset = _fake_asset(["existing"])
    mock_db.first.return_value = asset
    resp = client.post(f"/assets/{asset.id}/tags/B-Roll%20", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert asset.keywords == ["existing", "b-roll"]  # normalized + appended


@patch("apps.api.routers.assets._build_asset_response", side_effect=_fake_response)
@patch("apps.api.routers.assets.require_project_role")
def test_add_tag_is_idempotent(_role, _build, client, mock_db, auth_headers):
    asset = _fake_asset(["hook"])
    mock_db.first.return_value = asset
    resp = client.post(f"/assets/{asset.id}/tags/hook", headers=auth_headers)
    assert resp.status_code == 200
    assert asset.keywords == ["hook"]  # unchanged, no duplicate


@patch("apps.api.routers.assets._build_asset_response", side_effect=_fake_response)
@patch("apps.api.routers.assets.require_project_role")
def test_remove_tag(_role, _build, client, mock_db, auth_headers):
    asset = _fake_asset(["hook", "b-roll"])
    mock_db.first.return_value = asset
    resp = client.delete(f"/assets/{asset.id}/tags/hook", headers=auth_headers)
    assert resp.status_code == 200
    assert asset.keywords == ["b-roll"]


@patch("apps.api.routers.assets._build_asset_response", side_effect=_fake_response)
@patch("apps.api.routers.assets.require_project_role")
def test_add_tag_rejects_empty(_role, _build, client, mock_db, auth_headers):
    asset = _fake_asset([])
    mock_db.first.return_value = asset
    resp = client.post(f"/assets/{asset.id}/tags/%20", headers=auth_headers)  # whitespace
    assert resp.status_code == 422


@patch("apps.api.routers.assets._build_asset_response", side_effect=_fake_response)
@patch("apps.api.routers.assets.require_project_role")
def test_add_tag_enforces_max(_role, _build, client, mock_db, auth_headers):
    asset = _fake_asset([f"t{i}" for i in range(50)])  # MAX_TAGS
    mock_db.first.return_value = asset
    resp = client.post(f"/assets/{asset.id}/tags/new", headers=auth_headers)
    assert resp.status_code == 409


@patch("apps.api.routers.assets.require_project_role")
def test_add_tag_404_when_missing(_role, client, mock_db, auth_headers):
    mock_db.first.return_value = None
    resp = client.post(f"/assets/{uuid.uuid4()}/tags/x", headers=auth_headers)
    assert resp.status_code == 404


@patch("apps.api.routers.assets._build_asset_response", side_effect=_fake_response)
@patch("apps.api.routers.assets.is_platform_admin", return_value=False)
def test_add_tag_requires_editor_role(_admin, _build, client, mock_db, auth_headers):
    from fastapi import HTTPException
    asset = _fake_asset([])
    mock_db.first.return_value = asset
    with patch("apps.api.routers.assets.require_project_role",
               side_effect=HTTPException(status_code=403, detail="Requires editor role")):
        resp = client.post(f"/assets/{asset.id}/tags/x", headers=auth_headers)
    assert resp.status_code == 403
