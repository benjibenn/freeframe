"""Tests for the MCP user-management tools (invite, activate, reset password).

The point of these tests is the *why*: invite_user's admin gate lives in a FastAPI
dependency the direct function call bypasses, so the tool must enforce it itself —
that gap is the reason this file exists. reset_user_password never accepts a
password parameter, so a caller-supplied secret can never land in an MCP client's
tool-call log.
"""
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from apps.api.routers import mcp as mcp_router
from apps.api.models.user import UserStatus


def _admin(user_id=None):
    u = MagicMock()
    u.id = user_id or uuid.uuid4()
    u.is_superadmin = True
    u.is_subadmin = False
    u.deleted_at = None
    return u


def _non_admin():
    u = _admin()
    u.is_superadmin = False
    return u


@pytest.fixture
def as_admin(mock_db):
    user = _admin()
    user_token = mcp_router._current_user.set(user)
    db_token = mcp_router._current_db.set(mock_db)
    yield user
    mcp_router._current_user.reset(user_token)
    mcp_router._current_db.reset(db_token)


@pytest.fixture
def as_non_admin(mock_db):
    user = _non_admin()
    user_token = mcp_router._current_user.set(user)
    db_token = mcp_router._current_db.set(mock_db)
    yield user
    mcp_router._current_user.reset(user_token)
    mcp_router._current_db.reset(db_token)


def _target_user(**over):
    u = MagicMock()
    u.id = over.get("id", uuid.uuid4())
    u.email = over.get("email", "new@example.com")
    u.name = over.get("name", "New Person")
    u.status = over.get("status", UserStatus.pending_invite)
    u.email_verified = over.get("email_verified", False)
    u.is_superadmin = over.get("is_superadmin", False)
    return u


# ── invite_user ──────────────────────────────────────────────────────────────

def test_invite_user_rejects_a_non_admin_caller(as_non_admin):
    """invite_user's real gate is Depends(require_admin) — a FastAPI dependency the
    direct function call under _call() never runs. Without an explicit check here,
    any MCP caller could invite a user regardless of their own admin status.
    """
    with patch.object(mcp_router.users_router, "invite_user") as invite:
        with pytest.raises(ValueError, match="Admin"):
            mcp_router.invite_user(email="new@example.com", name="New Person")
    invite.assert_not_called()


def test_invite_user_returns_the_created_user(as_admin):
    created = _target_user(email="new@example.com", name="New Person")
    with patch.object(mcp_router.users_router, "invite_user", return_value=created) as invite:
        out = mcp_router.invite_user(email="new@example.com", name="New Person")
    assert invite.call_args.kwargs["body"].email == "new@example.com"
    assert invite.call_args.kwargs["body"].name == "New Person"
    assert out == {
        "id": str(created.id),
        "email": "new@example.com",
        "name": "New Person",
        "status": "pending_invite",
        "email_verified": False,
    }


def test_invite_user_surfaces_a_duplicate_email(as_admin):
    with patch.object(
        mcp_router.users_router,
        "invite_user",
        side_effect=HTTPException(status_code=400, detail="Email already registered"),
    ):
        with pytest.raises(ValueError, match="Email already registered"):
            mcp_router.invite_user(email="dup@example.com", name="Dup")


# ── activate_user ────────────────────────────────────────────────────────────

def test_activate_user_passes_the_id_through(as_admin):
    target_id = uuid.uuid4()
    activated = _target_user(id=target_id, status=UserStatus.active, email_verified=True)
    with patch.object(mcp_router.admin_router, "activate_user", return_value=activated) as act:
        out = mcp_router.activate_user(user_id=str(target_id))
    assert act.call_args.kwargs["user_id"] == target_id
    assert out["status"] == "active"
    assert out["email_verified"] is True


def test_activate_user_surfaces_the_deactivated_user_error(as_admin):
    """admin.py rejects activating a deactivated user in favour of /reactivate —
    that's an inline check in the endpoint body, so _call()'s translation covers it
    without any extra work here."""
    with patch.object(
        mcp_router.admin_router,
        "activate_user",
        side_effect=HTTPException(status_code=400, detail="Use reactivate for deactivated users"),
    ):
        with pytest.raises(ValueError, match="Use reactivate"):
            mcp_router.activate_user(user_id=str(uuid.uuid4()))


def test_activate_user_rejects_a_non_admin_caller(as_non_admin):
    """Unlike invite_user, admin.py's activate_user checks is_superadmin inline in
    the function body, so this fires through the normal _call() path — this test
    pins that behaviour rather than assuming it."""
    with patch.object(
        mcp_router.admin_router,
        "activate_user",
        side_effect=HTTPException(status_code=403, detail="Only admins can access this endpoint"),
    ):
        with pytest.raises(ValueError, match="Only admins"):
            mcp_router.activate_user(user_id=str(uuid.uuid4()))


# ── reset_user_password ──────────────────────────────────────────────────────

def test_reset_user_password_takes_no_password_argument():
    """A caller-supplied password would sit in plaintext in an MCP client's
    tool-call log. The tool must not accept one — this pins the signature."""
    import inspect

    params = inspect.signature(mcp_router.reset_user_password).parameters
    assert "password" not in params


def test_reset_user_password_generates_and_returns_a_password_once(as_admin):
    target_id = uuid.uuid4()
    updated = _target_user(id=target_id)
    with patch.object(mcp_router.admin_router, "set_user_password", return_value=updated) as reset:
        out = mcp_router.reset_user_password(user_id=str(target_id))
    sent = reset.call_args.kwargs["body"].password
    assert len(sent) >= 8
    assert out["password"] == sent
    assert out["id"] == str(target_id)


def test_reset_user_password_surfaces_the_not_found_error(as_admin):
    with patch.object(
        mcp_router.admin_router,
        "set_user_password",
        side_effect=HTTPException(status_code=404, detail="User not found"),
    ):
        with pytest.raises(ValueError, match="User not found"):
            mcp_router.reset_user_password(user_id=str(uuid.uuid4()))
