"""Tests for the project-role write gate, `require_project_role`.

Intent encoded (why this matters):
- Platform admins (superadmin / sub-admin) can UPLOAD into and EDIT every project —
  including the isolated per-submitter submission projects they can already SEE but were
  never added to as members. This mirrors the read-side bypass in `can_view_project` /
  `can_access_asset`; without it, an admin who didn't create a submission link gets a
  spurious 403 "Not a project member" when uploading into that submission folder.
- A non-member who is NOT an admin is still rejected with 403 "Not a project member".
- A member whose role is below the requirement is rejected naming the required role.
"""
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from apps.api.models.project import ProjectRole
from apps.api.services.permissions import require_project_role


def _user(*, is_superadmin=False, is_subadmin=False):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.is_superadmin = is_superadmin
    u.is_subadmin = is_subadmin
    return u


def _db_returning_member(member):
    """Shape db.query(ProjectMember).filter(...).first() -> member (or None)."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = member
    return db


@pytest.mark.parametrize("admin", [
    _user(is_superadmin=True),
    _user(is_subadmin=True),
])
def test_platform_admin_bypasses_without_membership(admin):
    # No membership row exists for this project, yet the admin must pass — this is the
    # exact submission-folder upload case that was previously a 403.
    db = _db_returning_member(None)
    assert require_project_role(db, uuid.uuid4(), admin, ProjectRole.editor) is None


def test_non_member_non_admin_is_rejected():
    db = _db_returning_member(None)
    with pytest.raises(HTTPException) as exc:
        require_project_role(db, uuid.uuid4(), _user(), ProjectRole.editor)
    assert exc.value.status_code == 403
    assert exc.value.detail == "Not a project member"


def test_member_below_required_role_is_rejected():
    viewer = MagicMock(role=ProjectRole.viewer)
    db = _db_returning_member(viewer)
    with pytest.raises(HTTPException) as exc:
        require_project_role(db, uuid.uuid4(), _user(), ProjectRole.editor)
    assert exc.value.status_code == 403
    assert "editor" in exc.value.detail


def test_member_meeting_role_passes():
    editor = MagicMock(role=ProjectRole.editor)
    db = _db_returning_member(editor)
    assert require_project_role(db, uuid.uuid4(), _user(), ProjectRole.editor) is editor
