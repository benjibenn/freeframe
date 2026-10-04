"""GET /review-queue.

Intent:
- the queue is an admin tool: it spans every editor's submissions;
- it lists what is in the stage NAMED Review. A renamed-away stage is a 409 that
  names it, so the page can say what to fix instead of showing an empty queue;
- editor and project filters reach the query, and paging is capped like the lists.
"""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.models.asset import AssetType, ProcessingStatus
from apps.api.routers.review_queue import router
from apps.api.database import get_db
from apps.api.middleware.auth import get_current_user
from apps.api.services.review_queue import QueueContext


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
def test_a_sub_admin_may_review_and_filters_reach_the_query(queue_page, mock_db):
    review, done, revision = _stages(mock_db)
    editor, project = uuid.uuid4(), uuid.uuid4()

    r = _client(mock_db, _user(subadmin=True)).get(
        f"/review-queue?editor_id={editor}&project_id={project}&limit=10&offset=5"
    )

    assert r.status_code == 200, r.text
    queue_page.assert_called_once_with(
        mock_db, review.id, project_id=project, editor_id=editor, limit=10, offset=5,
    )
    assert r.json() == {
        "items": [],
        "total": 0,
        "stages": {"review": str(review.id), "done": str(done.id), "revision": str(revision.id)},
    }


def test_limit_is_capped_at_100(mock_db):
    _stages(mock_db)
    assert _client(mock_db, _user(superadmin=True)).get("/review-queue?limit=101").status_code == 422


def test_items_are_built_from_the_page(mock_db):
    _stages(mock_db)
    asset = SimpleNamespace(id=uuid.uuid4(), project_id=uuid.uuid4(), created_by=uuid.uuid4(),
                            name="hook-3.png", asset_type=AssetType.image)
    version = SimpleNamespace(id=uuid.uuid4(), processing_status=ProcessingStatus.ready,
                              created_at=datetime(2026, 10, 1, tzinfo=timezone.utc))
    with patch("apps.api.routers.review_queue._queue_page", return_value=([(asset, version)], 7)), \
         patch("apps.api.routers.review_queue._context", return_value=QueueContext()):
        r = _client(mock_db, _user(superadmin=True)).get("/review-queue")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 7
    assert body["items"][0]["asset_id"] == str(asset.id)
    assert body["items"][0]["version_id"] == str(version.id)
    assert body["items"][0]["canva_url"] is None


def test_queue_page_excludes_soft_deleted_projects(mock_db):
    """A deleted brief's project is soft-deleted (Project.deleted_at set), not
    removed. Its files must not stay queued — they would 404 when an admin
    clicks through from the queue into a brief that no longer resolves.
    """
    from apps.api.routers.review_queue import _queue_page

    mock_db.join.return_value = mock_db
    mock_db.group_by.return_value = mock_db
    mock_db.subquery.return_value = mock_db
    mock_db.order_by.return_value = mock_db
    mock_db.offset.return_value = mock_db
    mock_db.limit.return_value = mock_db
    mock_db.count.return_value = 0
    mock_db.all.return_value = []

    _queue_page(mock_db, uuid.uuid4(), project_id=None, editor_id=None, limit=25, offset=0)

    filter_args = [arg for call in mock_db.filter.call_args_list for arg in call.args]
    rendered = " ".join(str(arg) for arg in filter_args)
    assert "projects.deleted_at" in rendered
    assert "IS NULL" in rendered
