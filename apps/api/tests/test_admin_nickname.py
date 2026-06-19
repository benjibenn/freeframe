"""Tests for the admin-editable `nickname` endpoint.

These mount the admin router on a standalone FastAPI app (mirroring
test_admin_uid.py) so each test can pin `get_current_user` to a superadmin or a
normal user independently. The DB is the shared MagicMock from conftest; the
router's query chains (`db.query(...).filter(...).first()`) all resolve to that
same mock, so we drive them with `side_effect`/`return_value` per test.

Intent encoded (per spec):
- a nickname must be stored with its ORIGINAL CASE preserved (it's a display
  string), even though uniqueness is enforced case-INSENSITIVELY — so "Ben" and
  "ben" are the same name and the second write must 409 NAMING the holder and not
  overwrite the loser's value;
- an empty/whitespace-only string and an explicit null are both deliberate CLEARS
  (back to None), not errors — the admin uses them to remove a nickname;
- > 50 chars is structurally invalid (422);
- the whole surface is superadmin-only (403 otherwise).
"""
import uuid

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.models.user import UserStatus


# ── Fixtures / helpers ───────────────────────────────────────────────────────────

def _make_user(*, is_superadmin=False, nickname=None, name="Target User"):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.email = f"{name.replace(' ', '.').lower()}@example.com"
    u.name = name
    u.avatar_url = None
    u.status = UserStatus.active
    u.is_superadmin = is_superadmin
    u.is_subadmin = False
    u.uid = None
    u.nickname = nickname
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


# ── PATCH (set / clear) ───────────────────────────────────────────────────────────

def test_set_nickname_stores_case_preserved(mock_db):
    """A nickname is a display string: the stored value keeps its original case."""
    admin = _make_user(is_superadmin=True, name="Admin")
    target = _make_user(nickname=None)
    client = _admin_client(mock_db, admin)

    # target lookup, then duplicate-holder lookup returns None (free).
    mock_db.first.side_effect = [target, None]

    resp = client.patch(f"/admin/users/{target.id}/nickname", json={"nickname": "  Ben  "})

    assert resp.status_code == 200, resp.text
    assert resp.json()["nickname"] == "Ben"  # trimmed, case preserved
    assert target.nickname == "Ben"
    mock_db.commit.assert_called()


def test_case_insensitive_duplicate_409_names_holder_and_leaves_value_unchanged(mock_db):
    """'Ben' on A then 'ben' on B is the SAME name: B must 409, name A, and not write."""
    admin = _make_user(is_superadmin=True, name="Admin")
    target = _make_user(nickname=None, name="User B")
    holder = _make_user(nickname="Ben", name="User A")
    client = _admin_client(mock_db, admin)

    # 1st .first() = target (B) lookup; 2nd .first() = case-insensitive holder (A).
    mock_db.first.side_effect = [target, holder]

    resp = client.patch(f"/admin/users/{target.id}/nickname", json={"nickname": "ben"})

    assert resp.status_code == 409, resp.text
    assert "User A" in resp.json()["detail"]  # names the holder
    assert "ben" in resp.json()["detail"]
    assert target.nickname is None  # B unchanged
    mock_db.commit.assert_not_called()


def test_empty_string_clears_nickname(mock_db):
    """An empty/whitespace-only value is a deliberate clear -> None, persisted."""
    admin = _make_user(is_superadmin=True, name="Admin")
    target = _make_user(nickname="Ben")
    client = _admin_client(mock_db, admin)

    mock_db.first.return_value = target

    resp = client.patch(f"/admin/users/{target.id}/nickname", json={"nickname": "   "})

    assert resp.status_code == 200, resp.text
    assert resp.json()["nickname"] is None
    assert target.nickname is None
    mock_db.commit.assert_called()


def test_null_clears_nickname(mock_db):
    """null is also the clear path: the column goes back to None and is persisted."""
    admin = _make_user(is_superadmin=True, name="Admin")
    target = _make_user(nickname="Ben")
    client = _admin_client(mock_db, admin)

    mock_db.first.return_value = target

    resp = client.patch(f"/admin/users/{target.id}/nickname", json={"nickname": None})

    assert resp.status_code == 200, resp.text
    assert resp.json()["nickname"] is None
    assert target.nickname is None
    mock_db.commit.assert_called()


def test_nickname_too_long_422(mock_db):
    """> 50 chars is structurally invalid — reject before any write."""
    admin = _make_user(is_superadmin=True, name="Admin")
    client = _admin_client(mock_db, admin)

    resp = client.patch(
        f"/admin/users/{uuid.uuid4()}/nickname",
        json={"nickname": "x" * 51},
    )

    assert resp.status_code == 422, resp.text
    mock_db.commit.assert_not_called()


def test_user_not_found_404(mock_db):
    admin = _make_user(is_superadmin=True, name="Admin")
    client = _admin_client(mock_db, admin)
    mock_db.first.return_value = None

    resp = client.patch(f"/admin/users/{uuid.uuid4()}/nickname", json={"nickname": "Ben"})

    assert resp.status_code == 404, resp.text


def test_non_superadmin_403(mock_db):
    """Editing nicknames is a superadmin-only capability."""
    normal = _make_user(is_superadmin=False, name="Normal")
    client = _admin_client(mock_db, normal)

    resp = client.patch(f"/admin/users/{uuid.uuid4()}/nickname", json={"nickname": "Ben"})

    assert resp.status_code == 403, resp.text
    mock_db.commit.assert_not_called()
