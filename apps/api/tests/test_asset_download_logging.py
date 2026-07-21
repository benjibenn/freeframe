"""A successful ?download=true call records asset_downloaded server-side.

WHY: download is the sensitive, auditable event. It must be logged where it can't
be bypassed by a client that skips the /track call — i.e. in the endpoint itself.
"""
import uuid
from unittest.mock import MagicMock, patch

from apps.api.models.asset import AssetType, ProcessingStatus


def _ready_video_asset():
    a = MagicMock()
    a.id = uuid.uuid4()
    a.deleted_at = None
    a.asset_type = AssetType.video
    a.project_id = uuid.uuid4()
    a.name = "Clip"
    return a


def test_download_logs_asset_downloaded(client, auth_headers, mock_db):
    asset = _ready_video_asset()
    version = MagicMock(id=uuid.uuid4(), processing_status=ProcessingStatus.ready)
    media = MagicMock(s3_key_processed="proc/key.m3u8", s3_key_raw="raw/key.mp4",
                      original_filename="clip.mp4", version_id=version.id)
    # asset lookup, version lookup, media lookup in order:
    mock_db.first.side_effect = [asset, version, media]
    with patch("apps.api.services.permissions.can_access_asset", return_value=True), \
         patch("apps.api.routers.assets.generate_presigned_get_url", return_value="https://signed"), \
         patch("apps.api.routers.assets.log_asset_activity") as mock_log:
        resp = client.get(
            f"/assets/{asset.id}/stream?download=true&version_id={version.id}",
            headers=auth_headers,
        )
    assert resp.status_code == 200
    assert mock_log.called
    kwargs = mock_log.call_args.kwargs
    assert kwargs["action"] == "asset_downloaded"
    assert kwargs["asset_id"] == asset.id
