"""The authenticated download endpoint must gate on asset access.

Intent: there is no separate "downloadable" flag for logged-in users — being
able to *access* an asset is what grants download. This test pins that gate so a
future change to get_stream_url can't silently let a user without access pull the
raw file via ?download=true.
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
    return a


def test_download_forbidden_without_asset_access(client, auth_headers, mock_db):
    asset = _asset()
    mock_db.first.return_value = asset  # asset lookup succeeds
    with patch("apps.api.services.permissions.can_access_asset", return_value=False):
        resp = client.get(
            f"/assets/{asset.id}/stream?download=true", headers=auth_headers
        )
    assert resp.status_code == 403
