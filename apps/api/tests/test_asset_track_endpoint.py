"""POST /assets/{id}/track records soft click/view signals for authenticated users.

Intent:
- only someone who can *see* the asset may generate a tracking row (no phantom
  access logged);
- the body's action maps to asset_clicked / asset_viewed (never to a raw
  ActivityLog action a client could spoof);
- download is NOT settable here — it is server-authoritative (Task 4).
"""
import uuid
from unittest.mock import MagicMock, patch

from apps.api.models.asset import AssetType


def _asset():
    a = MagicMock()
    a.id = uuid.uuid4()
    a.deleted_at = None
    a.asset_type = AssetType.video
    a.project_id = uuid.uuid4()
    a.name = "Clip"
    return a


def test_track_view_logs_asset_viewed(client, auth_headers, mock_db):
    asset = _asset()
    mock_db.first.return_value = asset
    with patch("apps.api.services.permissions.can_access_asset", return_value=True), \
         patch("apps.api.routers.assets.log_asset_activity") as mock_log:
        resp = client.post(
            f"/assets/{asset.id}/track", json={"action": "viewed"}, headers=auth_headers
        )
    assert resp.status_code == 204
    assert mock_log.call_args.kwargs["action"] == "asset_viewed"


def test_track_forbidden_without_access(client, auth_headers, mock_db):
    asset = _asset()
    mock_db.first.return_value = asset
    with patch("apps.api.services.permissions.can_access_asset", return_value=False):
        resp = client.post(
            f"/assets/{asset.id}/track", json={"action": "clicked"}, headers=auth_headers
        )
    assert resp.status_code == 403


def test_track_rejects_download_action(client, auth_headers, mock_db):
    asset = _asset()
    mock_db.first.return_value = asset
    with patch("apps.api.services.permissions.can_access_asset", return_value=True):
        resp = client.post(
            f"/assets/{asset.id}/track", json={"action": "downloaded"}, headers=auth_headers
        )
    assert resp.status_code == 422
