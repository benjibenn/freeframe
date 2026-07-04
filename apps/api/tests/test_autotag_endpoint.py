import uuid
from unittest.mock import MagicMock, patch


@patch("apps.api.routers.assets.settings")
@patch("apps.api.routers.assets.send_task_safe")
@patch("apps.api.routers.assets._load_editable_asset")
def test_autotag_enqueues_task(load, send, cfg, client, mock_db, auth_headers):
    cfg.gemini_api_key = "k"
    asset_id = uuid.uuid4()
    asset = MagicMock(id=asset_id); load.return_value = asset
    # Note: the version query requires processing_status==ready (mock_db doesn't evaluate filters)
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
@patch("apps.api.routers.assets._load_editable_asset")
def test_autotag_batch_enqueues_task(load, send, cfg, client, auth_headers):
    cfg.gemini_api_key = "k"
    load.return_value = MagicMock()
    ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    resp = client.post("/assets/autotag-batch", json={"asset_ids": ids}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "queued"
    assert resp.json()["count"] == 2
    assert send.called


@patch("apps.api.routers.assets.settings")
@patch("apps.api.routers.assets.send_task_safe")
@patch("apps.api.routers.assets._load_editable_asset")
def test_batch_authorizes_every_asset(load, send, cfg, client, auth_headers):
    from fastapi import HTTPException as FastAPIHTTPException
    cfg.gemini_api_key = "k"
    ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    # First call succeeds, second raises 403
    load.side_effect = [MagicMock(), FastAPIHTTPException(status_code=403, detail="Forbidden")]
    resp = client.post("/assets/autotag-batch", json={"asset_ids": ids}, headers=auth_headers)
    assert resp.status_code == 403
    assert not send.called


@patch("apps.api.routers.assets.settings")
@patch("apps.api.routers.assets.send_task_safe")
def test_batch_rejects_empty_list(send, cfg, client, auth_headers):
    cfg.gemini_api_key = "k"
    resp = client.post("/assets/autotag-batch", json={"asset_ids": []}, headers=auth_headers)
    assert resp.status_code == 422
    assert not send.called


@patch("apps.api.routers.assets.settings")
def test_autotag_batch_503_when_disabled(cfg, client, auth_headers):
    cfg.gemini_api_key = None
    ids = [str(uuid.uuid4())]
    resp = client.post("/assets/autotag-batch", json={"asset_ids": ids}, headers=auth_headers)
    assert resp.status_code == 503


@patch("apps.api.routers.assets.settings")
@patch("apps.api.routers.assets.send_task_safe")
def test_batch_rejects_oversized_list(send, cfg, client, auth_headers):
    cfg.gemini_api_key = "k"
    ids = [str(uuid.uuid4()) for _ in range(201)]
    resp = client.post("/assets/autotag-batch", json={"asset_ids": ids}, headers=auth_headers)
    assert resp.status_code == 413
    assert not send.called


@patch("apps.api.routers.assets.settings")
@patch("apps.api.routers.assets.send_task_safe")
def test_autotag_403_for_non_admin(send, cfg, client, auth_headers, test_user):
    """WHY: AI tagging spends Gemini quota — platform admins/subadmins only."""
    cfg.gemini_api_key = "k"
    test_user.is_superadmin = False
    test_user.is_subadmin = False
    resp = client.post(f"/assets/{uuid.uuid4()}/autotag", headers=auth_headers)
    assert resp.status_code == 403
    assert not send.called


@patch("apps.api.routers.assets.settings")
@patch("apps.api.routers.assets.send_task_safe")
def test_batch_403_for_non_admin(send, cfg, client, auth_headers, test_user):
    cfg.gemini_api_key = "k"
    test_user.is_superadmin = False
    test_user.is_subadmin = False
    resp = client.post("/assets/autotag-batch", json={"asset_ids": [str(uuid.uuid4())]}, headers=auth_headers)
    assert resp.status_code == 403
    assert not send.called


@patch("apps.api.routers.assets.settings")
@patch("apps.api.routers.assets.send_task_safe")
@patch("apps.api.routers.assets._load_editable_asset")
def test_autotag_allows_subadmin(load, send, cfg, client, mock_db, auth_headers, test_user):
    cfg.gemini_api_key = "k"
    test_user.is_superadmin = False
    test_user.is_subadmin = True
    asset_id = uuid.uuid4()
    load.return_value = MagicMock(id=asset_id)
    mock_db.first.return_value = MagicMock(id=uuid.uuid4())
    resp = client.post(f"/assets/{asset_id}/autotag", headers=auth_headers)
    assert resp.status_code == 200
    assert send.called


@patch("apps.api.routers.assets.settings")
@patch("apps.api.routers.assets.send_task_safe")
def test_project_autotag_403_for_non_admin(send, cfg, client, auth_headers, test_user):
    cfg.gemini_api_key = "k"
    test_user.is_superadmin = False
    test_user.is_subadmin = False
    resp = client.post(f"/projects/{uuid.uuid4()}/autotag", headers=auth_headers)
    assert resp.status_code == 403
    assert not send.called


@patch("apps.api.routers.assets.settings")
@patch("apps.api.routers.assets.send_task_safe")
def test_project_autotag_queues_all_project_assets(send, cfg, client, mock_db, auth_headers, test_user):
    """WHY: the bulk button must cover the WHOLE project server-side, not just
    the pages the browser happened to load; skip_if_tagged guards re-tag cost."""
    cfg.gemini_api_key = "k"
    test_user.is_superadmin = True
    ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    mock_db.first.return_value = MagicMock(id=uuid.uuid4(), deleted_at=None)  # project exists
    mock_db.all.return_value = [(i,) for i in ids]
    resp = client.post(f"/projects/{uuid.uuid4()}/autotag", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "queued", "count": 3}
    args = send.call_args[0]
    assert args[1] == [str(i) for i in ids]   # all asset ids, stringified
    assert args[2] is True                    # skip_if_tagged always on for bulk


@patch("apps.api.routers.assets.settings")
@patch("apps.api.routers.assets.send_task_safe")
def test_project_autotag_404_when_project_missing(send, cfg, client, mock_db, auth_headers, test_user):
    cfg.gemini_api_key = "k"
    test_user.is_superadmin = True
    mock_db.first.return_value = None
    resp = client.post(f"/projects/{uuid.uuid4()}/autotag", headers=auth_headers)
    assert resp.status_code == 404
    assert not send.called
