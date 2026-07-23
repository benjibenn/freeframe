"""Bulk run-as-ad flag toggle across many assets (multi-select). Platform-admin
only — run_as_ad is the clearance flag external ad platforms filter by, so
unlike bulk status it is never delegable to project editors."""
import uuid


def _fake_asset():
    from unittest.mock import MagicMock

    a = MagicMock()
    a.id = uuid.uuid4()
    a.project_id = uuid.uuid4()
    a.run_as_ad = False
    a.deleted_at = None
    return a


def test_bulk_run_as_ad_sets_flag(client, mock_db, auth_headers, test_user):
    test_user.is_subadmin = True
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


def test_bulk_run_as_ad_can_unset(client, mock_db, auth_headers, test_user):
    test_user.is_subadmin = True
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


def test_bulk_run_as_ad_rejects_non_admin(client, mock_db, auth_headers, test_user):
    test_user.is_superadmin = False
    test_user.is_subadmin = False
    a1 = _fake_asset()
    mock_db.all.return_value = [a1]
    resp = client.patch(
        "/assets/bulk/run-as-ad",
        json={"asset_ids": [str(a1.id)], "run_as_ad": True},
        headers=auth_headers,
    )
    assert resp.status_code == 403
    assert a1.run_as_ad is False  # never mutated


def test_bulk_run_as_ad_rejects_empty(client, mock_db, auth_headers, test_user):
    # Admin so the 422 path (not the 403 admin gate) is what's under test.
    test_user.is_subadmin = True
    resp = client.patch(
        "/assets/bulk/run-as-ad",
        json={"asset_ids": [], "run_as_ad": True},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_bulk_run_as_ad_404_on_missing(client, mock_db, auth_headers, test_user):
    test_user.is_subadmin = True
    missing = uuid.uuid4()
    mock_db.all.return_value = []  # nothing found
    resp = client.patch(
        "/assets/bulk/run-as-ad",
        json={"asset_ids": [str(missing)], "run_as_ad": True},
        headers=auth_headers,
    )
    assert resp.status_code == 404
