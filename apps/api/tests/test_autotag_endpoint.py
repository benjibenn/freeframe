import uuid
from unittest.mock import MagicMock, patch


@patch("apps.api.routers.assets.settings")
@patch("apps.api.routers.assets.send_task_safe")
@patch("apps.api.routers.assets._load_editable_asset")
def test_autotag_enqueues_task(load, send, cfg, client, mock_db, auth_headers):
    cfg.gemini_api_key = "k"
    asset_id = uuid.uuid4()
    asset = MagicMock(id=asset_id); load.return_value = asset
    version = MagicMock(id=uuid.uuid4())
    mock_db.first.return_value = version
    resp = client.post(f"/assets/{asset_id}/autotag", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "queued"
    assert send.called


@patch("apps.api.routers.assets.settings")
def test_autotag_returns_503_when_disabled(cfg, client, auth_headers):
    cfg.gemini_api_key = None
    resp = client.post(f"/assets/{uuid.uuid4()}/autotag", headers=auth_headers)
    assert resp.status_code == 503


@patch("apps.api.routers.assets.settings")
@patch("apps.api.routers.assets.send_task_safe")
def test_autotag_batch_enqueues_task(send, cfg, client, auth_headers):
    cfg.gemini_api_key = "k"
    ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    resp = client.post("/assets/autotag-batch", json={"asset_ids": ids}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "queued"
    assert resp.json()["count"] == 2
    assert send.called


@patch("apps.api.routers.assets.settings")
def test_autotag_batch_503_when_disabled(cfg, client, auth_headers):
    cfg.gemini_api_key = None
    ids = [str(uuid.uuid4())]
    resp = client.post("/assets/autotag-batch", json={"asset_ids": ids}, headers=auth_headers)
    assert resp.status_code == 503
