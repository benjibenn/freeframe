"""The file page header names the uploader. It used to make its own /users call
for that one name. GET /assets/{id} now carries it."""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


def _response(asset):
    from apps.api.models.asset import AssetType
    from apps.api.schemas.asset import AssetResponse

    now = datetime.now(timezone.utc)
    return AssetResponse(
        id=asset.id, project_id=uuid.uuid4(), name="hook.mp4", description=None,
        asset_type=AssetType.video, rating=None, assignee_id=None, due_date=None,
        keywords=[], created_by=asset.created_by, created_at=now, updated_at=now,
    )


def _asset():
    a = MagicMock()
    a.id = uuid.uuid4()
    a.created_by = uuid.uuid4()
    a.deleted_at = None
    return a


@patch("apps.api.routers.assets.require_asset_access")
@patch("apps.api.routers.assets._build_asset_response")
def test_get_asset_carries_the_uploader_name(build, _access, client, mock_db, auth_headers):
    asset = _asset()
    build.return_value = _response(asset)
    mock_db.first.side_effect = [asset, ("Ada Editor",)]

    r = client.get(f"/assets/{asset.id}", headers=auth_headers)

    assert r.status_code == 200, r.text
    assert r.json()["uploader_name"] == "Ada Editor"


@patch("apps.api.routers.assets.require_asset_access")
@patch("apps.api.routers.assets._build_asset_response")
def test_uploader_name_is_null_when_the_account_is_gone(build, _access, client, mock_db, auth_headers):
    asset = _asset()
    build.return_value = _response(asset)
    mock_db.first.side_effect = [asset, None]

    r = client.get(f"/assets/{asset.id}", headers=auth_headers)

    assert r.status_code == 200, r.text
    assert r.json()["uploader_name"] is None
