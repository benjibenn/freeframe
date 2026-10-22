"""Folder-wide pipeline-stage restamp (the project toolbar's "Bulk status").

Covers what the multi-select bulk endpoint cannot: the caller names a folder, not
a list of ids, so a folder with more assets than the grid has loaded — or more
than the 200-id cap — still gets restamped in one call. Platform-admin only,
matching every other write to task_stage_id.
"""
import uuid
from unittest.mock import MagicMock, patch

# The "has a usable version" filter builds `exists()` subqueries off the live
# session, which the mock Session cannot produce. Stubbing it to a constant is
# the convention test_asset_neighbors.py uses; the filter itself is covered by
# the list_assets tests.
_stub_usable = patch("apps.api.routers.assets._usable_or_empty", return_value=True)


def _fake_asset():
    a = MagicMock()
    a.id = uuid.uuid4()
    a.task_stage_id = None
    a.deleted_at = None
    return a


def _asset_filters(mock_db):
    """The WHERE clauses the endpoint built, as SQL text.

    The mock Session returns itself from .filter() whatever it is handed, so a
    dropped scope clause would otherwise leave every assertion passing while the
    endpoint restamped the whole table. Reading the clauses back is the only way
    these tests can fail when the scope breaks. Clauses naming `folders.` or
    `task_stages.` belong to the two existence lookups, not the asset query.
    """
    return [
        str(arg)
        for call in mock_db.filter.call_args_list
        for arg in call.args
        if "folders." not in str(arg) and "task_stages." not in str(arg)
    ]


@_stub_usable
def test_sets_stage_on_every_asset_at_root(_usable, client, mock_db, auth_headers, test_user):
    test_user.is_subadmin = True
    project_id, stage_id = uuid.uuid4(), uuid.uuid4()
    a1, a2 = _fake_asset(), _fake_asset()
    mock_db.first.return_value = MagicMock()  # the stage exists
    mock_db.all.return_value = [a1, a2]

    resp = client.patch(
        f"/projects/{project_id}/assets/stage",
        json={"folder_id": "root", "task_stage_id": str(stage_id)},
        headers=auth_headers,
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"updated": 2}
    assert a1.task_stage_id == stage_id and a2.task_stage_id == stage_id
    # Scope: this project, this folder level only. Without both clauses the call
    # would restamp every asset in the database.
    clauses = _asset_filters(mock_db)
    assert any("assets.project_id" in c for c in clauses), clauses
    assert any("assets.folder_id IS NULL" in c for c in clauses), clauses
    assert any("assets.deleted_at IS NULL" in c for c in clauses), clauses


@_stub_usable
def test_scopes_to_the_named_subfolder(_usable, client, mock_db, auth_headers, test_user):
    # A folder UUID must narrow to that folder, not fall through to "whole project".
    test_user.is_subadmin = True
    folder_id = uuid.uuid4()
    mock_db.first.return_value = MagicMock()  # folder and stage both exist
    mock_db.all.return_value = [_fake_asset()]

    resp = client.patch(
        f"/projects/{uuid.uuid4()}/assets/stage",
        json={"folder_id": str(folder_id), "task_stage_id": None},
        headers=auth_headers,
    )

    assert resp.status_code == 200, resp.text
    clauses = _asset_filters(mock_db)
    assert any("assets.folder_id =" in c for c in clauses), clauses
    assert not any("assets.folder_id IS NULL" in c for c in clauses), clauses


@_stub_usable
def test_null_stage_clears_to_unassigned(_usable, client, mock_db, auth_headers, test_user):
    # "Unassigned" is a real choice in the menu, so a null stage must be accepted
    # rather than rejected as a missing field.
    test_user.is_subadmin = True
    a1 = _fake_asset()
    a1.task_stage_id = uuid.uuid4()
    mock_db.all.return_value = [a1]

    resp = client.patch(
        f"/projects/{uuid.uuid4()}/assets/stage",
        json={"folder_id": "root", "task_stage_id": None},
        headers=auth_headers,
    )

    assert resp.status_code == 200, resp.text
    assert a1.task_stage_id is None


@_stub_usable
def test_empty_folder_reports_zero(_usable, client, mock_db, auth_headers, test_user):
    # The UI turns this into "No files in this folder" instead of a false success.
    test_user.is_subadmin = True
    mock_db.all.return_value = []

    resp = client.patch(
        f"/projects/{uuid.uuid4()}/assets/stage",
        json={"folder_id": "root", "task_stage_id": None},
        headers=auth_headers,
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"updated": 0}


@_stub_usable
def test_rejects_non_admin(_usable, client, mock_db, auth_headers, test_user):
    # Project editors may tag assets but never move the pipeline stage, so the
    # folder-wide version must not be the hole in that rule.
    test_user.is_superadmin = False
    test_user.is_subadmin = False
    a1 = _fake_asset()
    mock_db.all.return_value = [a1]

    resp = client.patch(
        f"/projects/{uuid.uuid4()}/assets/stage",
        json={"folder_id": "root", "task_stage_id": str(uuid.uuid4())},
        headers=auth_headers,
    )

    assert resp.status_code == 403
    assert a1.task_stage_id is None  # never mutated


@_stub_usable
def test_rejects_unparseable_folder_id(_usable, client, mock_db, auth_headers, test_user):
    # Anything but "root" must be a UUID; a bad value is a client bug, not a
    # silent project-wide restamp.
    test_user.is_subadmin = True
    a1 = _fake_asset()
    mock_db.all.return_value = [a1]

    resp = client.patch(
        f"/projects/{uuid.uuid4()}/assets/stage",
        json={"folder_id": "not-a-uuid", "task_stage_id": None},
        headers=auth_headers,
    )

    assert resp.status_code == 422
    assert a1.task_stage_id is None


@_stub_usable
def test_404_when_folder_not_in_project(_usable, client, mock_db, auth_headers, test_user):
    # The folder filter is scoped to the project, so a folder id from another
    # project must fail rather than restamp nothing and report success.
    test_user.is_subadmin = True
    mock_db.first.return_value = None  # folder lookup misses
    a1 = _fake_asset()
    mock_db.all.return_value = [a1]

    resp = client.patch(
        f"/projects/{uuid.uuid4()}/assets/stage",
        json={"folder_id": str(uuid.uuid4()), "task_stage_id": None},
        headers=auth_headers,
    )

    assert resp.status_code == 404
    assert a1.task_stage_id is None


@_stub_usable
def test_404_when_stage_missing(_usable, client, mock_db, auth_headers, test_user):
    test_user.is_subadmin = True
    mock_db.first.return_value = None  # stage lookup misses
    a1 = _fake_asset()
    mock_db.all.return_value = [a1]

    resp = client.patch(
        f"/projects/{uuid.uuid4()}/assets/stage",
        json={"folder_id": "root", "task_stage_id": str(uuid.uuid4())},
        headers=auth_headers,
    )

    assert resp.status_code == 404
    assert a1.task_stage_id is None
