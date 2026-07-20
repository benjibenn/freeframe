"""Library grants must convey asset/project read access.

Why: assets visible in the library browser were openable only by project members —
a library-only grantee got 403 on GET /assets/{id} (and the viewer hung forever).
These tests pin that a library grant is an access path in can_access_asset /
can_view_project, and that a folder-level grant does NOT convey project-wide view.
"""
from unittest.mock import MagicMock

from apps.api.services import permissions as perms


def _deny_common(monkeypatch):
    """Neutralize every OTHER access path so only the library path can grant."""
    monkeypatch.setattr(perms, "is_platform_admin", lambda u: False)
    monkeypatch.setattr(perms, "get_project_member", lambda db, p, u: None)
    monkeypatch.setattr(perms, "is_public_project", lambda db, p: False)


def _asset_and_user():
    asset = MagicMock(); asset.created_by = "someone-else"; asset.project_id = "proj"
    user = MagicMock(); user.id = "u1"
    return asset, user


def test_can_access_asset_via_library_grant(monkeypatch):
    _deny_common(monkeypatch)
    monkeypatch.setattr(perms, "has_library_asset_access", lambda db, a, u: True)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None  # no direct AssetShare
    asset, user = _asset_and_user()
    assert perms.can_access_asset(db, asset, user) is True


def test_can_access_asset_denied_without_library_grant(monkeypatch):
    _deny_common(monkeypatch)
    monkeypatch.setattr(perms, "has_library_asset_access", lambda db, a, u: False)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    asset, user = _asset_and_user()
    assert perms.can_access_asset(db, asset, user) is False


def test_can_view_project_via_project_library_grant(monkeypatch):
    _deny_common(monkeypatch)
    monkeypatch.setattr(perms, "has_project_library_access", lambda db, p, u: True)
    assert perms.can_view_project(MagicMock(), "proj", MagicMock()) is True


def test_folder_only_grant_does_not_convey_project_view(monkeypatch):
    # A folder-level grant yields has_project_library_access == False, so the grantee
    # must NOT be able to view the whole project (no leak of other folders' assets).
    _deny_common(monkeypatch)
    monkeypatch.setattr(perms, "has_project_library_access", lambda db, p, u: False)
    assert perms.can_view_project(MagicMock(), "proj", MagicMock()) is False
