"""/task-board pages its briefs.

Intent:
- the first request returns 25 briefs, not every brief. The page used to load
  every asset on the platform to draw its first screen;
- total and stage_counts describe the whole filtered set, so the chips and the
  infinite-scroll sentinel stay right while one page is loaded;
- which briefs another editor is on is what per-submitter isolation withholds,
  so only an admin may filter by editor.

db.all() results are queued in the order get_task_board asks:
[non-admin scope x2] [editor's briefs + stages] light rows, page rows, [assets, owners, editors].
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


def _link(stage_id=None, title="Brief"):
    l = MagicMock()
    l.id = uuid.uuid4()
    l.title = title
    l.token = "tok"
    l.task_stage_id = stage_id
    l.assignee_id = None
    l.brief_pdf_s3_key = None
    l.brief_json = None
    l.created_at = datetime.now(timezone.utc)
    l.deleted_at = None
    l.home_folder_id = None
    l.home_project_id = None
    l.taxonomy_path = None
    return l


def _chain(mock_db):
    mock_db.order_by.return_value = mock_db
    mock_db.join.return_value = mock_db


@patch("apps.api.routers.tasks.link_home_paths", return_value={})
@patch("apps.api.routers.tasks._build_task_items", return_value=[])
@patch("apps.api.routers.tasks.is_platform_admin", return_value=True)
def test_first_page_is_25_briefs_with_the_full_total(_adm, _items, _paths, client, mock_db, auth_headers):
    links = [_link() for _ in range(30)]
    _chain(mock_db)
    mock_db.all.side_effect = [links, links[:25], [], []]

    r = client.get("/task-board", headers=auth_headers)

    assert r.status_code == 200, r.text
    body = r.json()
    assert [b["id"] for b in body["items"]] == [str(l.id) for l in links[:25]]
    assert body["total"] == 30
    assert body["stage_counts"] == {"unassigned": 30}


@patch("apps.api.routers.tasks.link_home_paths", return_value={})
@patch("apps.api.routers.tasks._build_task_items", return_value=[])
@patch("apps.api.routers.tasks.is_platform_admin", return_value=True)
def test_second_page_starts_where_the_first_ended(_adm, _items, _paths, client, mock_db, auth_headers):
    links = [_link() for _ in range(30)]
    _chain(mock_db)
    mock_db.all.side_effect = [links, links[25:], [], []]

    r = client.get("/task-board?offset=25", headers=auth_headers)

    assert [b["id"] for b in r.json()["items"]] == [str(l.id) for l in links[25:]]


@patch("apps.api.routers.tasks.link_home_paths", return_value={})
@patch("apps.api.routers.tasks._build_task_items", return_value=[])
@patch("apps.api.routers.tasks.is_platform_admin", return_value=True)
def test_paging_past_the_end_is_empty_not_an_error(_adm, _items, _paths, client, mock_db, auth_headers):
    links = [_link() for _ in range(30)]
    _chain(mock_db)
    mock_db.all.side_effect = [links]

    r = client.get("/task-board?offset=50", headers=auth_headers)

    assert r.status_code == 200, r.text
    assert r.json() == {"items": [], "total": 30, "stage_counts": {"unassigned": 30}}


@patch("apps.api.routers.tasks.is_platform_admin", return_value=True)
def test_limit_is_capped_at_100(_adm, client, mock_db, auth_headers):
    assert client.get("/task-board?limit=101", headers=auth_headers).status_code == 422


@patch("apps.api.routers.tasks.is_platform_admin", return_value=False)
def test_an_editor_cannot_filter_by_another_editor(_adm, client, mock_db, auth_headers):
    r = client.get(f"/task-board?editor_id={uuid.uuid4()}", headers=auth_headers)
    assert r.status_code == 403


@patch("apps.api.routers.tasks.link_home_paths", return_value={})
@patch("apps.api.routers.tasks._build_task_items", return_value=[])
@patch("apps.api.routers.tasks.is_platform_admin", return_value=False)
def test_an_editor_filters_and_counts_by_their_own_stage(_adm, _items, _paths, client, mock_db, auth_headers):
    mine, briefs = uuid.uuid4(), uuid.uuid4()
    link = _link(stage_id=briefs)
    _chain(mock_db)
    mock_db.all.side_effect = [
        [],                                  # owner scope
        [(link.id, uuid.uuid4(), mine)],     # editor scope: (link, my project, MY stage)
        [link],                              # light rows
        [link],                              # page rows
        [],                                  # assets
        [],                                  # editor rows
    ]

    r = client.get(f"/task-board?stage_id={mine}", headers=auth_headers)

    assert r.status_code == 200, r.text
    assert [b["id"] for b in r.json()["items"]] == [str(link.id)]
    assert r.json()["stage_counts"] == {str(mine): 1}


@patch("apps.api.routers.tasks.link_home_paths", return_value={})
@patch("apps.api.routers.tasks._build_task_items", return_value=[])
@patch("apps.api.routers.tasks.is_platform_admin", return_value=True)
def test_editor_filter_keeps_only_that_editors_briefs(_adm, _items, _paths, client, mock_db, auth_headers):
    on, off = _link(), _link()
    _chain(mock_db)
    mock_db.all.side_effect = [
        [(on.id, None)], # briefs the editor is on, with their own stage
        [on, off],       # light rows
        [on],            # page rows
        [],              # assets
        [],              # editor rows
    ]

    r = client.get(f"/task-board?editor_id={uuid.uuid4()}", headers=auth_headers)

    assert [b["id"] for b in r.json()["items"]] == [str(on.id)]
    assert r.json()["total"] == 1


@patch("apps.api.routers.tasks.link_home_paths", return_value={})
@patch("apps.api.routers.tasks._build_task_items", return_value=[])
@patch("apps.api.routers.tasks.is_platform_admin", return_value=True)
def test_admin_on_one_editors_desk_counts_and_filters_by_that_editors_stage(
    _adm, _items, _paths, client, mock_db, auth_headers
):
    """The web board places each card by the picked editor's own stage
    (stageOf's asEditorId). The chips and column headers come from these counts,
    so counting by the brief's stage would show a column header that disagrees
    with the cards under it."""
    theirs, briefs = uuid.uuid4(), uuid.uuid4()
    link = _link(stage_id=briefs)
    _chain(mock_db)
    mock_db.all.side_effect = [
        [(link.id, theirs)],  # the editor's briefs, with THEIR stage
        [link],               # light rows
        [link],               # page rows
        [],                   # assets
        [],                   # editor rows
    ]

    r = client.get(f"/task-board?editor_id={uuid.uuid4()}&stage_id={theirs}", headers=auth_headers)

    assert r.status_code == 200, r.text
    assert [b["id"] for b in r.json()["items"]] == [str(link.id)]
    assert r.json()["stage_counts"] == {str(theirs): 1}


@patch("apps.api.routers.tasks.link_home_paths", return_value={})
@patch("apps.api.routers.tasks._build_task_items", return_value=[])
@patch("apps.api.routers.tasks.is_platform_admin", return_value=True)
def test_title_search(_adm, _items, _paths, client, mock_db, auth_headers):
    battery, camera = _link(title="Battery hook"), _link(title="Camera hook")
    _chain(mock_db)
    mock_db.all.side_effect = [[battery, camera], [battery], [], []]

    r = client.get("/task-board?q=battery", headers=auth_headers)

    assert [b["id"] for b in r.json()["items"]] == [str(battery.id)]
    assert r.json()["total"] == 1
