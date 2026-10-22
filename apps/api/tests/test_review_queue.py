"""GET /review-queue.

Intent:
- the queue is an admin tool: it spans every editor's submissions;
- it lists the EDITORS in the stage NAMED Review, one item per editor per brief,
  each with the files they delivered. A renamed-away stage is a 409 that names
  it, so the page can say what to fix instead of showing an empty queue;
- the editor filter reaches the query, and paging is capped like the lists.
"""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.models.asset import AssetType
from apps.api.routers.review_queue import router
from apps.api.database import get_db
from apps.api.middleware.auth import get_current_user
from apps.api.schemas.review_queue import ReviewFile


def _user(*, superadmin=False, subadmin=False):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.is_superadmin = superadmin
    u.is_subadmin = subadmin
    return u


def _client(mock_db, user):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def _stage(name):
    s = MagicMock()
    s.id = uuid.uuid4()
    s.name = name
    return s


def _stages(mock_db, names=("Review", "Done", "Revision")):
    stages = [_stage(n) for n in names]
    mock_db.order_by.return_value = mock_db
    mock_db.all.return_value = stages
    return stages


def test_a_plain_user_is_refused(mock_db):
    assert _client(mock_db, _user()).get("/review-queue").status_code == 403


def test_a_missing_stage_is_a_409_that_names_it(mock_db):
    _stages(mock_db, names=("Review", "Done"))
    r = _client(mock_db, _user(superadmin=True)).get("/review-queue")
    assert r.status_code == 409
    assert r.json()["detail"] == "Missing task stage: Revision"


@patch("apps.api.routers.review_queue._queue_page", return_value=([], 0))
def test_a_sub_admin_may_review_and_the_editor_filter_reaches_the_query(queue_page, mock_db):
    review, done, revision = _stages(mock_db)
    editor = uuid.uuid4()

    r = _client(mock_db, _user(subadmin=True)).get(f"/review-queue?editor_id={editor}&limit=10&offset=5")

    assert r.status_code == 200, r.text
    queue_page.assert_called_once_with(mock_db, review.id, editor_id=editor, limit=10, offset=5)
    assert r.json() == {
        "items": [],
        "total": 0,
        "stages": {"review": str(review.id), "done": str(done.id), "revision": str(revision.id)},
    }


def test_limit_is_capped_at_100_and_offset_cannot_be_negative(mock_db):
    _stages(mock_db)
    client = _client(mock_db, _user(superadmin=True))
    assert client.get("/review-queue?limit=101").status_code == 422
    assert client.get("/review-queue?offset=-1").status_code == 422


def test_one_item_per_editor_carrying_that_editors_files(mock_db):
    review, done, revision = (_stage(n) for n in ("Review", "Done", "Revision"))
    sub = SimpleNamespace(id=uuid.uuid4(), submission_link_id=uuid.uuid4(), user_id=uuid.uuid4(),
                          project_id=uuid.uuid4(), display_name=None)
    editor = SimpleNamespace(id=sub.user_id, display_name="Ada")
    mock_db.order_by.return_value = mock_db
    # stages, then the page's users in one query
    mock_db.all.side_effect = [[review, done, revision], [editor]]
    waited = datetime(2026, 10, 1, tzinfo=timezone.utc)
    f = ReviewFile(asset_id=uuid.uuid4(), version_id=uuid.uuid4(), file_name="hook-1.png",
                   asset_type=AssetType.image)

    with patch("apps.api.routers.review_queue._queue_page",
               return_value=([(sub, "Battery brief", "tok", waited)], 7)), \
         patch("apps.api.routers.review_queue._files_by_project",
               return_value={sub.project_id: [f]}) as files:
        r = _client(mock_db, _user(superadmin=True)).get("/review-queue")

    assert r.status_code == 200, r.text
    files.assert_called_once_with(mock_db, [sub.project_id])
    body = r.json()
    assert body["total"] == 7
    [item] = body["items"]
    assert item["submission_id"] == str(sub.id)
    assert item["editor_id"] == str(sub.user_id)
    assert item["editor_name"] == "Ada"
    assert item["expected_stage_id"] == str(review.id)
    assert [x["asset_id"] for x in item["files"]] == [str(f.asset_id)]
