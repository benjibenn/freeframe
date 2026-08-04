"""Tests for the admin-set password and admin-activate endpoints.

These mount the admin router on a standalone FastAPI app (mirroring
test_admin_nickname.py) so each test can pin `get_current_user` to a superadmin or
a normal user independently. The DB is the shared MagicMock from conftest.

`hash_password` is patched out: what matters here is that SOME hash is stored for
the given password, not that bcrypt works (conftest notes the local bcrypt install
may be incompatible with passlib).

Intent encoded:
- setting a password is NOT a verification event — a pending user stays pending, so
  the admin still has to make the explicit call to vouch for them;
- the 8-character minimum is enforced server-side, not just in the browser, and a
  rejected password must leave the stored hash untouched;
- activating burns any outstanding invite token, because /auth/accept-invite checks
  only the token — leaving it live would let its holder overwrite the password the
  admin just set;
- activating sets email_verified: activating by hand is the admin standing in for
  the verification email;
- deactivated users are NOT this endpoint's business (they were already verified);
  /reactivate owns that path, so mixing them up must fail loudly;
- the whole surface is superadmin-only (403 otherwise).
"""
import uuid

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.models.user import UserStatus


# ── Fixtures / helpers ───────────────────────────────────────────────────────────

def _make_user(
    *,
    is_superadmin=False,
    status=UserStatus.active,
    name="Target User",
    invite_token=None,
):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.email = f"{name.replace(' ', '.').lower()}@example.com"
    u.name = name
    u.avatar_url = None
    u.status = status
    u.is_superadmin = is_superadmin
    u.is_subadmin = False
    u.uid = None
    u.nickname = None
    u.password_hash = None
    u.email_verified = False
    u.invite_token = invite_token
    u.invite_token_expires_at = None
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


# ── POST /admin/users/{id}/password ──────────────────────────────────────────────

def test_set_password_stores_hash_without_activating(mock_db):
    """Handing someone a password is not proof of their email: status is untouched."""
    admin = _make_user(is_superadmin=True, name="Admin")
    target = _make_user(status=UserStatus.pending_verification)
    mock_db.first.return_value = target
    client = _admin_client(mock_db, admin)

    with patch("apps.api.routers.admin.hash_password", return_value="hashed!") as h:
        resp = client.post(
            f"/admin/users/{target.id}/password", json={"password": "correct-horse"}
        )

    assert resp.status_code == 200
    h.assert_called_once_with("correct-horse")
    assert target.password_hash == "hashed!"
    assert target.status == UserStatus.pending_verification
    assert target.email_verified is False
    mock_db.commit.assert_called_once()


def test_set_password_too_short_is_rejected_and_stores_nothing(mock_db):
    """The 8-char rule lives on the server too, so the browser check can't be bypassed."""
    admin = _make_user(is_superadmin=True, name="Admin")
    target = _make_user()
    mock_db.first.return_value = target
    client = _admin_client(mock_db, admin)

    resp = client.post(f"/admin/users/{target.id}/password", json={"password": "short7!"})

    assert resp.status_code == 422
    assert "at least 8" in resp.json()["detail"]
    assert target.password_hash is None
    mock_db.commit.assert_not_called()


def test_set_password_requires_superadmin(mock_db):
    """A normal user must not be able to take over another account."""
    actor = _make_user(name="Normal")
    target = _make_user()
    mock_db.first.return_value = target
    client = _admin_client(mock_db, actor)

    resp = client.post(
        f"/admin/users/{target.id}/password", json={"password": "correct-horse"}
    )

    assert resp.status_code == 403
    assert target.password_hash is None


def test_set_password_unknown_user_404s(mock_db):
    admin = _make_user(is_superadmin=True, name="Admin")
    mock_db.first.return_value = None
    client = _admin_client(mock_db, admin)

    resp = client.post(
        f"/admin/users/{uuid.uuid4()}/password", json={"password": "correct-horse"}
    )

    assert resp.status_code == 404


# ── PATCH /admin/users/{id}/activate ─────────────────────────────────────────────

def test_activate_marks_unverified_user_active_and_verified(mock_db):
    """Activating by hand stands in for the verification email the user never used."""
    admin = _make_user(is_superadmin=True, name="Admin")
    target = _make_user(status=UserStatus.pending_verification)
    mock_db.first.return_value = target
    client = _admin_client(mock_db, admin)

    resp = client.patch(f"/admin/users/{target.id}/activate")

    assert resp.status_code == 200
    assert target.status == UserStatus.active
    assert target.email_verified is True
    mock_db.commit.assert_called_once()


def test_activate_burns_outstanding_invite_token(mock_db):
    """/auth/accept-invite checks only the token, so a live link would be a
    password-reset backdoor into the account the admin just activated."""
    admin = _make_user(is_superadmin=True, name="Admin")
    target = _make_user(status=UserStatus.pending_invite, invite_token="live-token")
    mock_db.first.return_value = target
    client = _admin_client(mock_db, admin)

    resp = client.patch(f"/admin/users/{target.id}/activate")

    assert resp.status_code == 200
    assert target.status == UserStatus.active
    assert target.invite_token is None
    assert target.invite_token_expires_at is None


def test_activate_refuses_deactivated_users(mock_db):
    """Deactivated users belong to /reactivate; silently vouching for their email here
    would be a different decision than the admin asked for."""
    admin = _make_user(is_superadmin=True, name="Admin")
    target = _make_user(status=UserStatus.deactivated)
    mock_db.first.return_value = target
    client = _admin_client(mock_db, admin)

    resp = client.patch(f"/admin/users/{target.id}/activate")

    assert resp.status_code == 400
    assert target.status == UserStatus.deactivated
    assert target.email_verified is False
    mock_db.commit.assert_not_called()


def test_activate_requires_superadmin(mock_db):
    actor = _make_user(name="Normal")
    target = _make_user(status=UserStatus.pending_verification)
    mock_db.first.return_value = target
    client = _admin_client(mock_db, actor)

    resp = client.patch(f"/admin/users/{target.id}/activate")

    assert resp.status_code == 403
    assert target.status == UserStatus.pending_verification
