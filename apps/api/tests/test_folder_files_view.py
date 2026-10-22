"""File view: every file under a folder, with briefs flattened.

The folder view shows containers — subfolders, briefs, files. File view drops the
containers so a whole subtree reads as one grid of files. Two things make this a
server-side query rather than a client-side merge:

  * a brief's files live in each submitter's own project, so the browser cannot
    even name them, and
  * the grid pages, so the two sources have to be unioned before LIMIT.

These tests therefore assert the WHERE clauses, not just the status code: the
mock Session returns itself from .filter() whatever it is handed, so a dropped
scope clause would otherwise leave every assertion passing while the endpoint
returned the whole table.
"""
import uuid
from unittest.mock import MagicMock, patch

# Same two stubs the other asset-scope tests use: `_usable_or_empty` builds
# exists() subqueries the mock Session cannot produce, and the response builder
# needs real versions and media rows. Neither is what these tests are about.
_stub_usable = patch("apps.api.routers.assets._usable_or_empty", return_value=True)
_stub_view = patch("apps.api.routers.assets.can_view_project", return_value=True)


def _chain(mock_db):
    """Make order_by / offset / limit return the session again.

    conftest chains query() and filter() but not these, so without it the final
    `.all()` lands on a throwaway MagicMock and the test cannot see what the
    endpoint asked for.
    """
    mock_db.order_by.return_value = mock_db
    mock_db.offset.return_value = mock_db
    mock_db.limit.return_value = mock_db
    return mock_db


def _clauses(mock_db):
    """Every WHERE clause the endpoint built, as SQL text."""
    return [str(arg) for call in mock_db.filter.call_args_list for arg in call.args]


def _literal_clauses(mock_db):
    """The same clauses with their bound values inlined, so an IN list is visible."""
    out = []
    for call in mock_db.filter.call_args_list:
        for arg in call.args:
            try:
                out.append(str(arg.compile(compile_kwargs={"literal_binds": True})))
            except Exception:
                out.append(str(arg))
    return out


def _asset(project_id=None):
    a = MagicMock()
    a.id = uuid.uuid4()
    a.project_id = project_id or uuid.uuid4()
    return a


@_stub_view
@_stub_usable
@patch("apps.api.routers.assets._build_asset_responses_bulk", return_value=[])
def test_root_flattens_the_whole_project(build, _usable, _view, client, mock_db, auth_headers, test_user):
    # "root" means every folder, not just the top level: descending into the
    # subfolders is the entire point, so there must be no folder clause at all.
    test_user.is_subadmin = True
    project_id = uuid.uuid4()
    a1, a2 = _asset(project_id), _asset(project_id)
    _chain(mock_db)
    mock_db.all.side_effect = [[], [a1, a2]]  # no briefs, then the assets

    resp = client.get(f"/projects/{project_id}/folder-files?folder_id=root", headers=auth_headers)

    assert resp.status_code == 200, resp.text
    assert build.call_args.args[0] == [a1, a2]
    clauses = _clauses(mock_db)
    assert any("assets.project_id" in c for c in clauses), clauses
    assert any("assets.deleted_at IS NULL" in c for c in clauses), clauses
    assert not any("assets.folder_id" in c for c in clauses), clauses


@_stub_view
@_stub_usable
@patch("apps.api.routers.assets._build_asset_responses_bulk", return_value=[])
def test_a_folder_includes_its_subfolders(build, _usable, _view, client, mock_db, auth_headers, test_user):
    # A store folder holds model subfolders. Scoping to the named folder alone
    # would show an empty grid, which is the bug this view exists to avoid.
    test_user.is_subadmin = True
    project_id, folder_id, child_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    _chain(mock_db)
    mock_db.first.return_value = MagicMock()  # the folder exists
    mock_db.all.side_effect = [
        [(child_id,)],  # BFS: the folder has one child
        [],             # BFS: the child has none
        [],             # no briefs filed under it
        [_asset(project_id)],
    ]

    resp = client.get(
        f"/projects/{project_id}/folder-files?folder_id={folder_id}", headers=auth_headers
    )

    assert resp.status_code == 200, resp.text
    folder_clause = next(
        (c for c in _literal_clauses(mock_db) if "assets.folder_id IN" in c), None
    )
    assert folder_clause, _clauses(mock_db)
    # Both the folder and its child, or the subtree is not covered.
    # .hex: psycopg renders a UUID bind without its dashes.
    assert folder_id.hex in folder_clause, folder_clause
    assert child_id.hex in folder_clause, folder_clause


@_stub_view
@_stub_usable
@patch("apps.api.routers.assets._build_asset_responses_bulk", return_value=[])
def test_includes_files_submitted_against_briefs_in_the_subtree(
    build, _usable, _view, client, mock_db, auth_headers, test_user
):
    # The files an editor submits land in that editor's own project, so they can
    # only appear here as a second source OR-ed into the asset query.
    test_user.is_subadmin = True
    project_id, link_id, submitter_project = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    _chain(mock_db)
    mock_db.all.side_effect = [
        [(link_id,)],            # one brief filed in this project
        [(submitter_project,)],  # one editor submitted against it
        [_asset(submitter_project)],
    ]

    resp = client.get(f"/projects/{project_id}/folder-files?folder_id=root", headers=auth_headers)

    assert resp.status_code == 200, resp.text
    or_clause = next((c for c in _clauses(mock_db) if " OR " in c), None)
    assert or_clause, _clauses(mock_db)
    # Two project_id sources: this project's own files, and the submitters'.
    assert or_clause.count("assets.project_id") == 2, or_clause
    assert any("submission_links.home_project_id" in c for c in _clauses(mock_db))


@_stub_view
@_stub_usable
@patch("apps.api.routers.assets._build_asset_responses_bulk", return_value=[])
def test_a_folder_narrows_which_briefs_are_flattened(
    build, _usable, _view, client, mock_db, auth_headers, test_user
):
    # Without the home_folder_id clause, opening one model's folder in file view
    # would pull in every brief in the project.
    test_user.is_subadmin = True
    project_id, folder_id = uuid.uuid4(), uuid.uuid4()
    _chain(mock_db)
    mock_db.first.return_value = MagicMock()
    mock_db.all.side_effect = [[], [], []]  # no children, no briefs, no assets

    resp = client.get(
        f"/projects/{project_id}/folder-files?folder_id={folder_id}", headers=auth_headers
    )

    assert resp.status_code == 200, resp.text
    assert any("submission_links.home_folder_id IN" in c for c in _clauses(mock_db))


@_stub_view
@_stub_usable
@patch("apps.api.routers.assets._build_asset_responses_bulk", return_value=[])
def test_root_does_not_narrow_briefs_by_folder(
    build, _usable, _view, client, mock_db, auth_headers, test_user
):
    # At root every brief in the project counts, including ones filed at the top
    # level with no folder at all.
    test_user.is_subadmin = True
    _chain(mock_db)
    mock_db.all.side_effect = [[], []]

    resp = client.get(f"/projects/{uuid.uuid4()}/folder-files?folder_id=root", headers=auth_headers)

    assert resp.status_code == 200, resp.text
    assert not any("home_folder_id" in c for c in _clauses(mock_db))


@_stub_view
@_stub_usable
@patch("apps.api.routers.assets._build_asset_responses_bulk", return_value=[])
def test_a_non_admin_only_sees_briefs_they_created(
    build, _usable, _view, client, mock_db, auth_headers, test_user
):
    # Same rule as GET /brief-file-counts and GET /submission-links. Dropping it
    # would hand a plain project member every other admin's submitted work.
    test_user.is_superadmin = False
    test_user.is_subadmin = False
    _chain(mock_db)
    mock_db.all.side_effect = [[], []]

    resp = client.get(f"/projects/{uuid.uuid4()}/folder-files?folder_id=root", headers=auth_headers)

    assert resp.status_code == 200, resp.text
    assert any("submission_links.created_by" in c for c in _clauses(mock_db))


@_stub_view
@_stub_usable
@patch("apps.api.routers.assets._build_asset_responses_bulk", return_value=[])
def test_an_admin_sees_every_brief_in_the_project(
    build, _usable, _view, client, mock_db, auth_headers, test_user
):
    # Platform admins share one view of the shared tree, as elsewhere.
    test_user.is_subadmin = True
    _chain(mock_db)
    mock_db.all.side_effect = [[], []]

    resp = client.get(f"/projects/{uuid.uuid4()}/folder-files?folder_id=root", headers=auth_headers)

    assert resp.status_code == 200, resp.text
    assert not any("submission_links.created_by" in c for c in _clauses(mock_db))


@_stub_view
@_stub_usable
def test_rejects_a_folder_id_that_is_not_a_uuid(_usable, _view, client, mock_db, auth_headers):
    resp = client.get(f"/projects/{uuid.uuid4()}/folder-files?folder_id=nope", headers=auth_headers)
    assert resp.status_code == 422, resp.text


@_stub_view
@_stub_usable
def test_404_for_a_folder_in_another_project(_usable, _view, client, mock_db, auth_headers, test_user):
    # The folder lookup is scoped to this project, so a valid id from elsewhere
    # must not silently fall through to "whole project".
    test_user.is_subadmin = True
    mock_db.first.return_value = None
    resp = client.get(
        f"/projects/{uuid.uuid4()}/folder-files?folder_id={uuid.uuid4()}", headers=auth_headers
    )
    assert resp.status_code == 404, resp.text


@_stub_usable
@patch("apps.api.routers.assets.can_view_project", return_value=False)
def test_403_for_someone_who_cannot_view_the_project(_view, _usable, client, mock_db, auth_headers):
    resp = client.get(f"/projects/{uuid.uuid4()}/folder-files?folder_id=root", headers=auth_headers)
    assert resp.status_code == 403, resp.text
