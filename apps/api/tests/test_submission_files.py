"""list_submissions must return each submitter's actual files (not just a count)
so the submissions page can render a per-submitter file table."""
import uuid
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone


def _sub(project_id, user_id):
    s = MagicMock()
    s.id = uuid.uuid4()
    s.submission_link_id = uuid.uuid4()
    s.user_id = user_id
    s.display_name = None
    s.project_id = project_id
    s.created_at = datetime.now(timezone.utc)
    return s


@patch("apps.api.routers.submissions._get_owned_link")
def test_list_submissions_includes_files(_owned, client, mock_db, auth_headers):
    pid = uuid.uuid4()
    uid = uuid.uuid4()
    link = MagicMock()
    link.id = uuid.uuid4()
    _owned.return_value = link
    sub = _sub(pid, uid)
    user = MagicMock(); user.id = uid; user.name = "Ada"; user.email = "ada@x.co"
    aid1, aid2 = uuid.uuid4(), uuid.uuid4()

    # list_submissions runs three queries in order: submissions, asset rows, users.
    # mock_db.query().filter()... returns mock_db; .all() is what varies per call.
    mock_db.order_by.return_value = mock_db
    mock_db.all.side_effect = [
        [sub],                                   # submissions
        [(pid, aid1, "a.mp4"), (pid, aid2, "b.mp4")],  # (project_id, id, name) asset rows
        [user],                                  # users
    ]
    resp = client.get(f"/submission-links/{link.id}/submissions", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    row = resp.json()[0]
    assert row["asset_count"] == 2
    names = sorted(f["name"] for f in row["files"])
    assert names == ["a.mp4", "b.mp4"]
    assert {f["asset_id"] for f in row["files"]} == {str(aid1), str(aid2)}
