"""A carousel slide must stream ITS file, not the version's first one.

/assets/{id}/stream ignored media_file_id, so every slide of a carousel got the
first image's URL. The file page now asks for one slide at a time, which only
works if the endpoint honours the id it is given.
"""
import uuid
from unittest.mock import MagicMock, patch


def _image_carousel(mock_db):
    from apps.api.models.asset import AssetType, ProcessingStatus

    mock_db.order_by.return_value = mock_db
    asset = MagicMock()
    asset.id = uuid.uuid4()
    asset.project_id = uuid.uuid4()
    asset.asset_type = AssetType.image_carousel
    asset.name = "carousel"
    asset.deleted_at = None
    version = MagicMock()
    version.id = uuid.uuid4()
    version.processing_status = ProcessingStatus.ready
    slide = MagicMock()
    slide.id = uuid.uuid4()
    slide.version_id = version.id
    slide.s3_key_processed = None
    slide.s3_key_raw = "raw/slide-3.png"
    slide.original_filename = "slide-3.png"
    mock_db.first.side_effect = [asset, version, slide]
    return asset, version, slide


def _filters(mock_db):
    return [str(c.args[0]) for c in mock_db.filter.call_args_list if c.args]


@patch("apps.api.routers.assets.generate_presigned_get_url", side_effect=lambda key, **_: f"https://s3/{key}")
@patch("apps.api.routers.assets.require_asset_access")
def test_stream_narrows_to_the_requested_slide(_access, _presign, client, mock_db, auth_headers):
    asset, version, slide = _image_carousel(mock_db)

    r = client.get(
        f"/assets/{asset.id}/stream?version_id={version.id}&media_file_id={slide.id}",
        headers=auth_headers,
    )

    assert r.status_code == 200, r.text
    assert r.json()["url"] == "https://s3/raw/slide-3.png"
    assert any(f.startswith("media_files.id =") for f in _filters(mock_db))


@patch("apps.api.routers.assets.generate_presigned_get_url", side_effect=lambda key, **_: f"https://s3/{key}")
@patch("apps.api.routers.assets.require_asset_access")
def test_stream_without_a_slide_keeps_the_old_behaviour(_access, _presign, client, mock_db, auth_headers):
    asset, version, _ = _image_carousel(mock_db)

    r = client.get(f"/assets/{asset.id}/stream?version_id={version.id}", headers=auth_headers)

    assert r.status_code == 200, r.text
    assert not any(f.startswith("media_files.id =") for f in _filters(mock_db))
