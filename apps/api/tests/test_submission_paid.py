"""Marking a submission paid is bookkeeping the owner relies on: the paid date
must persist per editor, must not disturb the handle/rename machinery living on
the same PATCH, and must never leak to non-admin task-board viewers."""
import uuid
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch


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
    return [(link_id, date(2026, 8, 1), u1), (link_id, None, u2)]


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
        [(link.id,)],            # owned link ids (assignee scope)
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
