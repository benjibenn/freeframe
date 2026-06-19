"""Tests for the admin-granted `uid` display-number endpoints.

These mount the admin router on a standalone FastAPI app (mirroring
test_tag_palette.py) so each test can pin `get_current_user` to a superadmin or
a normal user independently. The DB is the shared MagicMock from conftest; the
router's query chains (`db.query(...).filter(...).first()/.all()`) all resolve to
that same mock, so we drive them with `side_effect`/`return_value` per test.

Intent encoded (per spec):
- a display number must START at 1 and REUSE the lowest freed gap, so numbers
  stay small and human-friendly even after revokes;
- the unique-per-user invariant is enforced with a 409 that NAMES the holder so
  the admin knows who to talk to, and the conflicting write must NOT be applied;
- < 1 is structurally invalid (422), null is a deliberate revoke;
- the whole surface is superadmin-only (403 otherwise).
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.models.user import UserStatus


# ── Fixtures / helpers ───────────────────────────────────────────────────────────

def _make_user(*, is_superadmin=False, uid=None, name="Target User"):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.email = f"{name.replace(' ', '.').lower()}@example.com"
    u.name = name
    u.avatar_url = None
    u.status = UserStatus.active
    u.is_superadmin = is_superadmin
    u.is_subadmin = False
    u.uid = uid
    u.email_verified = True
    u.invite_token = None
    u.preferences = {}
    return u


def _admin_client(mock_db, current_user):
    from apps.api.routers.admin import router
    from apps.api.database import get_db
    from apps.api.middleware.auth import get_current_user

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: current_user
    return TestClient(app, raise_server_exceptions=False)


def _taken_rows(*uids):
    """Shape db.query(User.uid)...all() returns: a list of 1-tuples."""
    return [(n,) for n in uids]


# ── grant ────────────────────────────────────────────────────────────────────────

def test_grant_on_empty_table_assigns_1(mock_db):
    """First grant ever must produce uid 1 — display numbers start at 1, not 0."""
    admin = _make_user(is_superadmin=True, name="Admin")
    target = _make_user(uid=None)
    client = _admin_client(mock_db, admin)

    mock_db.first.return_value = target          # user lookup
    mock_db.all.return_value = _taken_rows()      # no uids taken

    resp = client.post(f"/admin/users/{target.id}/uid:grant")

    assert resp.status_code == 200, resp.text
    assert resp.json()["uid"] == 1
    assert target.uid == 1
    mock_db.commit.assert_called()


def test_grant_fills_lowest_free_gap(mock_db):
    """With 1 and 3 taken, the next grant must reclaim 2 — lowest-free, not max+1."""
    admin = _make_user(is_superadmin=True, name="Admin")
    target = _make_user(uid=None)
    client = _admin_client(mock_db, admin)

    mock_db.first.return_value = target
    mock_db.all.return_value = _taken_rows(1, 3)

    resp = client.post(f"/admin/users/{target.id}/uid:grant")

    assert resp.status_code == 200, resp.text
    assert resp.json()["uid"] == 2
    assert target.uid == 2


def test_grant_when_user_already_has_uid_409(mock_db):
    """Re-granting must be rejected (409) so admins edit explicitly instead."""
    admin = _make_user(is_superadmin=True, name="Admin")
    target = _make_user(uid=5)
    client = _admin_client(mock_db, admin)

    mock_db.first.return_value = target

    resp = client.post(f"/admin/users/{target.id}/uid:grant")

    assert resp.status_code == 409, resp.text
    assert target.uid == 5  # unchanged
    mock_db.commit.assert_not_called()


def test_grant_user_not_found_404(mock_db):
    admin = _make_user(is_superadmin=True, name="Admin")
    client = _admin_client(mock_db, admin)
    mock_db.first.return_value = None

    resp = client.post(f"/admin/users/{uuid.uuid4()}/uid:grant")

    assert resp.status_code == 404, resp.text


def test_grant_non_superadmin_403(mock_db):
    """Granting is a superadmin-only capability."""
    normal = _make_user(is_superadmin=False, name="Normal")
    client = _admin_client(mock_db, normal)

    resp = client.post(f"/admin/users/{uuid.uuid4()}/uid:grant")

    assert resp.status_code == 403, resp.text
    mock_db.commit.assert_not_called()


# ── PATCH (set / revoke) ──────────────────────────────────────────────────────────

def test_patch_duplicate_409_names_holder_and_leaves_value_unchanged(mock_db):
    """Setting a number held by someone else must 409, name the holder, and not write."""
    admin = _make_user(is_superadmin=True, name="Admin")
    target = _make_user(uid=None)
    holder = _make_user(uid=7, name="Grace Hopper")
    client = _admin_client(mock_db, admin)

    # 1st .first() = target lookup; 2nd .first() = duplicate holder lookup.
    mock_db.first.side_effect = [target, holder]

    resp = client.patch(f"/admin/users/{target.id}/uid", json={"uid": 7})

    assert resp.status_code == 409, resp.text
    assert "Grace Hopper" in resp.json()["detail"]
    assert "7" in resp.json()["detail"]
    assert target.uid is None  # unchanged
    mock_db.commit.assert_not_called()


def test_patch_uid_below_one_422(mock_db):
    """0 / negatives are structurally invalid — reject before any DB work."""
    admin = _make_user(is_superadmin=True, name="Admin")
    client = _admin_client(mock_db, admin)

    resp = client.patch(f"/admin/users/{uuid.uuid4()}/uid", json={"uid": 0})

    assert resp.status_code == 422, resp.text
    mock_db.commit.assert_not_called()


def test_patch_null_clears_uid(mock_db):
    """null is the revoke path: the column goes back to None and is persisted."""
    admin = _make_user(is_superadmin=True, name="Admin")
    target = _make_user(uid=9)
    client = _admin_client(mock_db, admin)

    mock_db.first.return_value = target

    resp = client.patch(f"/admin/users/{target.id}/uid", json={"uid": None})

    assert resp.status_code == 200, resp.text
    assert resp.json()["uid"] is None
    assert target.uid is None
    mock_db.commit.assert_called()


def test_patch_set_unique_value_succeeds(mock_db):
    """Setting a free number on a user with no current uid persists it."""
    admin = _make_user(is_superadmin=True, name="Admin")
    target = _make_user(uid=None)
    client = _admin_client(mock_db, admin)

    # target lookup, then holder lookup returns None (free).
    mock_db.first.side_effect = [target, None]

    resp = client.patch(f"/admin/users/{target.id}/uid", json={"uid": 4})

    assert resp.status_code == 200, resp.text
    assert resp.json()["uid"] == 4
    assert target.uid == 4


def test_patch_user_not_found_404(mock_db):
    admin = _make_user(is_superadmin=True, name="Admin")
    client = _admin_client(mock_db, admin)
    mock_db.first.return_value = None

    resp = client.patch(f"/admin/users/{uuid.uuid4()}/uid", json={"uid": 3})

    assert resp.status_code == 404, resp.text


def test_patch_non_superadmin_403(mock_db):
    normal = _make_user(is_superadmin=False, name="Normal")
    client = _admin_client(mock_db, normal)

    resp = client.patch(f"/admin/users/{uuid.uuid4()}/uid", json={"uid": 3})

    assert resp.status_code == 403, resp.text
    mock_db.commit.assert_not_called()
