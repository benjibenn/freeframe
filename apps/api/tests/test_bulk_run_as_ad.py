"""Bulk run-as-ad flag toggle across many assets (multi-select). Mirrors the
bulk status endpoint: editor role enforced per project before any mutation."""
import uuid
from unittest.mock import MagicMock, patch


def _fake_asset():
    a = MagicMock()
    a.id = uuid.uuid4()
    a.project_id = uuid.uuid4()
    a.run_as_ad = False
    a.deleted_at = None
    return a


@patch("apps.api.routers.assets.require_project_role")
def test_bulk_run_as_ad_sets_flag(_role, client, mock_db, auth_headers, test_user):
    test_user.is_subadmin = False  # force the editor-permission branch
    a1, a2 = _fake_asset(), _fake_asset()
    mock_db.all.return_value = [a1, a2]
    resp = client.patch(
        "/assets/bulk/run-as-ad",
        json={"asset_ids": [str(a1.id), str(a2.id)], "run_as_ad": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"updated": 2}
    assert a1.run_as_ad is True and a2.run_as_ad is True
    # Editor role checked on each asset's project before mutating.
    assert _role.call_count == 2


@patch("apps.api.routers.assets.require_project_role")
def test_bulk_run_as_ad_can_unset(_role, client, mock_db, auth_headers, test_user):
    test_user.is_subadmin = False
    a1 = _fake_asset()
    a1.run_as_ad = True
    mock_db.all.return_value = [a1]
    resp = client.patch(
        "/assets/bulk/run-as-ad",
        json={"asset_ids": [str(a1.id)], "run_as_ad": False},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert a1.run_as_ad is False


def test_bulk_run_as_ad_rejects_empty(client, mock_db, auth_headers):
    resp = client.patch(
        "/assets/bulk/run-as-ad",
        json={"asset_ids": [], "run_as_ad": True},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_bulk_run_as_ad_404_on_missing(client, mock_db, auth_headers, test_user):
    test_user.is_subadmin = False
    missing = uuid.uuid4()
    mock_db.all.return_value = []  # nothing found
    resp = client.patch(
        "/assets/bulk/run-as-ad",
        json={"asset_ids": [str(missing)], "run_as_ad": True},
        headers=auth_headers,
    )
    assert resp.status_code == 404
