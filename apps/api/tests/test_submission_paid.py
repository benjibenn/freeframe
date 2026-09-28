"""Marking a submission paid is bookkeeping the owner relies on: the paid date
must persist per editor, must not disturb the handle/rename machinery living on
the same PATCH, and must never leak to non-admin task-board viewers."""
import uuid
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

from apps.api.models.asset import AssetType
from apps.api.schemas.task_stage import TaskItem


def _sub(link_id, display_name="Handle"):
    s = MagicMock()
    s.id = uuid.uuid4()
    s.submission_link_id = link_id
    s.user_id = uuid.uuid4()
    s.display_name = display_name
    s.project_id = uuid.uuid4()
    s.paid_at = None
    s.created_at = datetime.now(timezone.utc)
    return s


@patch("apps.api.routers.submissions._get_owned_link")
def test_mark_paid_sets_date_and_keeps_handle(_owned, client, mock_db, auth_headers):
    link = MagicMock(); link.id = uuid.uuid4()
    _owned.return_value = link
    sub = _sub(link.id)
    user = MagicMock(); user.name = "Ada"; user.email = "ada@x.co"
    # Queries: submission, user. No Project query — a paid-only PATCH must not
    # touch the rename path.
    mock_db.first.side_effect = [sub, user]
    mock_db.scalar.return_value = 2

    resp = client.patch(
        f"/submission-links/{link.id}/submissions/{sub.id}",
        json={"paid_at": "2026-08-01"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert sub.paid_at == date(2026, 8, 1)
    # The handle survived: absent-from-body may not mean "clear".
    assert sub.display_name == "Handle"
    assert resp.json()["paid_at"] == "2026-08-01"


@patch("apps.api.routers.submissions._get_owned_link")
def test_explicit_null_unmarks_paid(_owned, client, mock_db, auth_headers):
    link = MagicMock(); link.id = uuid.uuid4()
    _owned.return_value = link
    sub = _sub(link.id)
    sub.paid_at = date(2026, 8, 1)
    user = MagicMock(); user.name = "Ada"; user.email = "ada@x.co"
    mock_db.first.side_effect = [sub, user]
    mock_db.scalar.return_value = 0

    resp = client.patch(
        f"/submission-links/{link.id}/submissions/{sub.id}",
        json={"paid_at": None},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert sub.paid_at is None
    assert resp.json()["paid_at"] is None


@patch("apps.api.routers.submissions._get_owned_link")
def test_rename_alone_does_not_touch_paid(_owned, client, mock_db, auth_headers):
    link = MagicMock(); link.id = uuid.uuid4(); link.title = "Req"
    _owned.return_value = link
    sub = _sub(link.id)
    sub.paid_at = date(2026, 8, 1)
    user = MagicMock(); user.name = "Ada"; user.email = "ada@x.co"
    project = MagicMock()
    mock_db.first.side_effect = [sub, user, project]
    mock_db.scalar.return_value = 0

    with patch("apps.api.routers.submissions._unique_project_name", return_value="Req — Bob"):
        resp = client.patch(
            f"/submission-links/{link.id}/submissions/{sub.id}",
            json={"display_name": "Bob"},
            headers=auth_headers,
        )
    assert resp.status_code == 200, resp.text
    assert sub.display_name == "Bob"
    assert sub.paid_at == date(2026, 8, 1)


@patch("apps.api.routers.submissions._get_owned_link")
def test_list_submissions_returns_paid_at(_owned, client, mock_db, auth_headers):
    link = MagicMock(); link.id = uuid.uuid4()
    _owned.return_value = link
    sub = _sub(link.id)
    sub.paid_at = date(2026, 7, 15)
    user = MagicMock(); user.id = sub.user_id; user.name = "Ada"; user.email = "ada@x.co"

    mock_db.order_by.return_value = mock_db
    mock_db.all.side_effect = [
        [sub],   # submissions
        [],      # asset rows
        [user],  # users
    ]
    resp = client.get(f"/submission-links/{link.id}/submissions", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()[0]["paid_at"] == "2026-07-15"


def _board_link():
    l = MagicMock()
    l.id = uuid.uuid4()
    l.title = "Req"
    l.task_stage_id = None
    l.assignee_id = None
    l.brief_pdf_s3_key = None
    l.brief_json = None
    l.created_at = datetime.now(timezone.utc)
    l.deleted_at = None
    return l


def _editor_rows(link_id):
    u1 = MagicMock(); u1.id = uuid.uuid4(); u1.name = "Ada"; u1.email = "ada@x.co"
    u2 = MagicMock(); u2.id = uuid.uuid4(); u2.name = "Bob"; u2.email = "bob@x.co"
    # (link_id, paid_at, task_stage_id, user) — matches the bulk editors query,
    # which now also selects Submission.task_stage_id.
    return [(link_id, date(2026, 8, 1), None, u1), (link_id, None, None, u2)]


@patch("apps.api.routers.tasks.link_home_paths", return_value={})
@patch("apps.api.routers.tasks._build_task_items", return_value=[])
@patch("apps.api.routers.tasks.is_platform_admin", return_value=True)
def test_task_board_rolls_up_paid_counts_for_admin(_adm, _items, _paths, client, mock_db, auth_headers):
    link = _board_link()
    mock_db.order_by.return_value = mock_db
    mock_db.join.return_value = mock_db
    mock_db.all.side_effect = [
        [],                      # assets
        [link],                  # links
        _editor_rows(link.id),   # (link_id, paid_at, user) editor rows
    ]
    resp = client.get("/task-board", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    brief = resp.json()["briefs"][0]
    assert brief["paid_count"] == 1
    assert brief["submission_count"] == 2


@patch("apps.api.routers.tasks.link_home_paths", return_value={})
@patch("apps.api.routers.tasks._build_task_items", return_value=[])
@patch("apps.api.routers.tasks.is_platform_admin", return_value=False)
def test_task_board_hides_paid_counts_from_non_admin(_adm, _items, _paths, client, mock_db, auth_headers):
    link = _board_link()
    mock_db.order_by.return_value = mock_db
    mock_db.join.return_value = mock_db
    mock_db.all.side_effect = [
        [(link.id,)],            # owned link ids — assignee_id scope
        [],                      # owned link ids — submissions scope (union)
        [],                      # assets
        [link],                  # links
        _editor_rows(link.id),   # editor rows — one of two paid
    ]
    resp = client.get("/task-board", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    brief = resp.json()["briefs"][0]
    # Payment state is the owner's bookkeeping; an editor's board must not carry it.
    assert brief["paid_count"] == 0
    assert brief["submission_count"] == 0


def _editor_rows_including(link_id, viewer_id):
    """Two editors on one brief, one of whom is the person asking."""
    me = MagicMock(); me.id = viewer_id; me.name = "Me"; me.email = "me@x.co"
    other = MagicMock(); other.id = uuid.uuid4(); other.name = "Cleo"; other.email = "cleo@x.co"
    return [(link_id, None, None, me), (link_id, date(2026, 8, 1), None, other)]


@patch("apps.api.routers.tasks.link_home_paths", return_value={})
@patch("apps.api.routers.tasks._build_task_items", return_value=[])
@patch("apps.api.routers.tasks.is_platform_admin", return_value=False)
def test_task_board_reaches_an_editor_who_does_not_own_the_brief(
    _adm, _items, _paths, client, mock_db, auth_headers
):
    """The change that made several editors per brief possible.

    A brief has to reach someone because they were assigned to make it, not only
    because it sits on their desk. If the scope ever narrows back to assignee_id
    alone, the first result below is empty, the board early-returns, and an
    assigned editor is told they have no work.
    """
    link = _board_link()
    mock_db.order_by.return_value = mock_db
    mock_db.join.return_value = mock_db
    mock_db.all.side_effect = [
        [],                                    # assignee_id scope — they do not own this brief
        [(link.id, uuid.uuid4())],             # submissions scope — assigned to make it
        [],                                    # assets
        [link],                                # links
        _editor_rows(link.id),                 # editor rows
    ]
    resp = client.get("/task-board", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert [b["id"] for b in resp.json()["briefs"]] == [str(link.id)]


@patch("apps.api.routers.tasks.link_home_paths", return_value={})
@patch("apps.api.routers.tasks._build_task_items", return_value=[])
@patch("apps.api.routers.tasks.is_platform_admin", return_value=False)
def test_task_board_unions_both_scopes_into_distinct_briefs(
    _adm, _items, _paths, client, mock_db, auth_headers
):
    """Pins each half of the union to a distinct observable outcome.

    The mock harness tells the two scope queries apart only by call order, so a
    test that reuses the same link id for both halves — or drops one entirely —
    can still pass for the wrong reason: a shifted queue, not a noticed absence.
    Returning a *different* link id from each half and requiring both in the
    response is what actually catches one half going missing.
    """
    owned_link = _board_link()
    edited_link = _board_link()
    mock_db.order_by.return_value = mock_db
    mock_db.join.return_value = mock_db
    mock_db.all.side_effect = [
        [(owned_link.id,)],                    # assignee_id scope
        [(edited_link.id, uuid.uuid4())],      # submissions scope
        [],                                     # assets
        [owned_link, edited_link],              # links
        [],                                     # editor rows
    ]
    resp = client.get("/task-board", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    ids = {b["id"] for b in resp.json()["briefs"]}
    assert ids == {str(owned_link.id), str(edited_link.id)}


@patch("apps.api.routers.tasks.link_home_paths", return_value={})
@patch("apps.api.routers.tasks.is_platform_admin", return_value=False)
def test_task_board_hides_a_co_editors_assets_on_a_shared_brief(
    _adm, _paths, client, mock_db, auth_headers
):
    """Two editors on one brief get separate private projects, but both of those
    projects carry the same submission_link_id. Filtering assets by link id
    alone would hand an editor every other editor's filenames, submitter name,
    email and a working presigned thumbnail URL — exactly the exposure
    submission links exist to prevent.
    """
    link = _board_link()
    my_project_id = uuid.uuid4()
    their_project_id = uuid.uuid4()
    mine = TaskItem(
        asset_id=uuid.uuid4(), name="mine.mp4", project_id=my_project_id,
        asset_type=AssetType.video, request_id=link.id,
        created_at=datetime.now(timezone.utc),
    )
    theirs = TaskItem(
        asset_id=uuid.uuid4(), name="hook-v3.mp4", project_id=their_project_id,
        asset_type=AssetType.video, request_id=link.id,
        created_at=datetime.now(timezone.utc),
        submitter_name="Cleo", submitter_email="cleo@x.co",
        thumbnail_url="https://example.com/thumb.jpg",
    )
    mock_db.order_by.return_value = mock_db
    mock_db.join.return_value = mock_db
    mock_db.all.side_effect = [
        [],                            # assignee_id scope — not the owner
        [(link.id, my_project_id)],    # submissions scope — editor on my own project
        [],                            # assets (args discarded; _build_task_items is mocked below)
        [link],                        # links
        _editor_rows(link.id),         # editor rows
    ]
    with patch("apps.api.routers.tasks._build_task_items", return_value=[mine, theirs]):
        resp = client.get("/task-board", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assets = resp.json()["briefs"][0]["assets"]
    assert [a["name"] for a in assets] == ["mine.mp4"]


@patch("apps.api.routers.tasks.link_home_paths", return_value={})
@patch("apps.api.routers.tasks._build_task_items", return_value=[])
@patch("apps.api.routers.tasks.is_platform_admin", return_value=False)
def test_task_board_shows_an_editor_only_their_own_row(
    _adm, _items, _paths, client, mock_db, test_user, auth_headers
):
    """Per-submitter isolation, asserted on the wire rather than in a unit test.

    Two editors work this brief. Returning both would hand each of them the
    other's name and progress — the thing submission links exist to prevent.
    Filtering in the UI would not help; the response would still carry them.
    """
    link = _board_link()
    mock_db.order_by.return_value = mock_db
    mock_db.join.return_value = mock_db
    mock_db.all.side_effect = [
        [(link.id,)],                                   # assignee_id scope
        [],                                             # submissions scope
        [],                                             # assets
        [link],                                         # links
        _editor_rows_including(link.id, test_user.id),  # two editors, one is me
    ]
    resp = client.get("/task-board", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    editors = resp.json()["briefs"][0]["editors"]
    assert [e["id"] for e in editors] == [str(test_user.id)]
