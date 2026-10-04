"""Prev/next on the file page.

Intent: the file page used to download every asset in the project just to find
the two either side of the open one. The neighbours endpoint answers from an id
list, and must agree with the grid on order and on which assets count, or the
arrow keys would skip files, or land on ones the grid hides.
"""
import uuid
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.services.asset_neighbors import neighbors_of

A, B, C = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def test_middle_asset_has_both_neighbours():
    assert neighbors_of([A, B, C], B) == {"prev_id": A, "next_id": C, "position": 2, "total": 3}


def test_first_asset_has_no_prev():
    assert neighbors_of([A, B, C], A) == {"prev_id": None, "next_id": B, "position": 1, "total": 3}


def test_last_asset_has_no_next():
    assert neighbors_of([A, B, C], C) == {"prev_id": B, "next_id": None, "position": 3, "total": 3}


def test_only_asset_has_neither():
    assert neighbors_of([A], A) == {"prev_id": None, "next_id": None, "position": 1, "total": 1}


def test_asset_the_grid_hides_gets_no_neighbours():
    """A failed upload opened by URL is not in the grid's list. Inventing
    neighbours for it would send the arrow keys somewhere the grid never shows."""
    assert neighbors_of([A, B], C) == {"prev_id": None, "next_id": None, "position": 0, "total": 2}


def _user():
    u = MagicMock()
    u.id = uuid.uuid4()
    u.is_superadmin = False
    u.is_subadmin = False
    return u


def _client(mock_db, user):
    from apps.api.routers.assets import router
    from apps.api.database import get_db
    from apps.api.middleware.auth import get_current_user

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def _asset(asset_id):
    a = MagicMock()
    a.id = asset_id
    a.project_id = uuid.uuid4()
    a.deleted_at = None
    return a


def test_missing_asset_is_404(mock_db):
    mock_db.first.return_value = None
    assert _client(mock_db, _user()).get(f"/assets/{uuid.uuid4()}/neighbors").status_code == 404


@patch("apps.api.routers.assets._usable_or_empty", return_value=True)
@patch("apps.api.routers.assets.can_view_project", return_value=True)
@patch("apps.api.routers.assets.require_asset_access")
def test_returns_neighbours_in_grid_order(_access, _view, _usable, mock_db):
    mock_db.order_by.return_value = mock_db
    mock_db.first.return_value = _asset(B)
    mock_db.all.return_value = [(A,), (B,), (C,)]

    r = _client(mock_db, _user()).get(f"/assets/{B}/neighbors")

    assert r.status_code == 200, r.text
    assert r.json() == {"prev_id": str(A), "next_id": str(C), "position": 2, "total": 3}
    # Newest first like the grid, with a stable tie-break: two uploads in the
    # same second must not swap places between the grid and the arrows.
    assert [str(a) for a in mock_db.order_by.call_args.args] == [
        "assets.created_at DESC",
        "assets.id DESC",
    ]


@patch("apps.api.routers.assets._usable_or_empty", return_value=True)
@patch("apps.api.routers.assets.can_view_project", return_value=False)
@patch("apps.api.routers.assets.require_asset_access")
def test_someone_who_cannot_see_the_project_gets_no_neighbours(_access, _view, _usable, mock_db):
    """A file shared on its own must not leak the ids of the rest of the project.
    The old page asked /projects/{id}/assets, which refused them, so they had no
    arrows either."""
    mock_db.first.return_value = _asset(B)
    mock_db.all.return_value = [(A,), (B,), (C,)]

    r = _client(mock_db, _user()).get(f"/assets/{B}/neighbors")

    assert r.status_code == 200
    assert r.json() == {"prev_id": None, "next_id": None, "position": 0, "total": 0}
