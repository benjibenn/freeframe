"""Approve and send back from the /review page, through the editor-stage endpoint
PATCH /submission-links/{link_id}/editors/{user_id}/task-stage.

Intent:
- /review decides an EDITOR's stage on a brief, the same stage the /tasks board
  moves, so both pages agree on where an editor is;
- an editor sent back cannot act on "rejected" alone, so a reason is required,
  saved on the file it is about (which must be one of theirs) and emailed to
  them, only once the move is committed;
- a decision on an editor someone else already moved is refused (409) before
  anything is written, so two reviewers cannot both decide one editor;
- the /tasks dropdown sends none of this and must keep working unchanged.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.models.asset import AssetType
from apps.api.models.comment import Comment


def _admin():
    u = MagicMock()
    u.id = uuid.uuid4()
    u.name = "Boss"
    u.is_superadmin = True
    u.is_subadmin = False
    return u


def _client(mock_db, user):
    from apps.api.routers.tasks import router
    from apps.api.database import get_db
    from apps.api.middleware.auth import get_current_user

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def _stage(name):
    s = MagicMock()
    s.id = uuid.uuid4()
    s.name = name
    s.deleted_at = None
    return s


REVIEW, DONE, REVISION = _stage("Review"), _stage("Done"), _stage("Revision")


def _link():
    # Every field _brief_item reads must be concrete; see test_brief_editor_endpoints._link.
    l = MagicMock()
    l.id = uuid.uuid4()
    l.token = "tok-abc"
    l.title = "Battery brief"
    l.task_stage_id = None
    l.assignee_id = None
    l.deleted_at = None
    l.brief_pdf_s3_key = None
    l.brief_json = None
    l.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    l.home_folder_id = None
    l.home_project_id = None
    l.taxonomy_path = None
    return l


def _submission(link, stage_id):
    s = MagicMock()
    s.submission_link_id = link.id
    s.user_id = uuid.uuid4()
    s.project_id = uuid.uuid4()
    s.task_stage_id = stage_id
    return s


def _file_in(sub):
    asset = MagicMock()
    asset.id = uuid.uuid4()
    asset.project_id = sub.project_id
    asset.name = "hook-2.png"
    asset.asset_type = AssetType.image
    version = MagicMock()
    version.id = uuid.uuid4()
    return asset, version


def _editor(sub):
    u = MagicMock()
    u.id = sub.user_id
    u.email = "ada@example.com"
    return u


def _db(mock_db, *firsts):
    mock_db.join.return_value = mock_db
    mock_db.first.side_effect = list(firsts)
    mock_db.all.return_value = []
    return mock_db


def _patch(client, link, sub, **body):
    return client.patch(
        f"/submission-links/{link.id}/editors/{sub.user_id}/task-stage",
        json={k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in body.items()},
    )


def _comments(mock_db):
    return [c.args[0] for c in mock_db.add.call_args_list if isinstance(c.args[0], Comment)]


@patch("apps.api.routers.tasks.send_task_safe")
def test_approve_moves_the_editor_to_done_with_no_comment_or_email(send, mock_db):
    link = _link()
    sub = _submission(link, REVIEW.id)
    _db(mock_db, link, DONE, sub)

    r = _patch(_client(mock_db, _admin()), link, sub, task_stage_id=DONE.id, expected_stage_id=REVIEW.id)

    assert r.status_code == 200, r.text
    assert sub.task_stage_id == DONE.id
    assert not _comments(mock_db)
    send.assert_not_called()


@patch("apps.api.routers.tasks.send_task_safe")
def test_an_editor_moved_by_someone_else_is_a_409_and_nothing_is_written(send, mock_db):
    link = _link()
    sub = _submission(link, DONE.id)
    _db(mock_db, link, REVISION, sub)

    r = _patch(_client(mock_db, _admin()), link, sub, task_stage_id=REVISION.id,
               expected_stage_id=REVIEW.id, comment="Fix it", version_id=uuid.uuid4())

    assert r.status_code == 409
    assert r.json()["detail"] == "This editor is no longer in that stage"
    assert sub.task_stage_id == DONE.id
    assert not _comments(mock_db)
    mock_db.commit.assert_not_called()
    send.assert_not_called()


@patch("apps.api.routers.tasks.send_task_safe")
def test_send_back_without_a_reason_is_refused(send, mock_db):
    link = _link()
    sub = _submission(link, REVIEW.id)
    _db(mock_db, link, REVISION, sub)

    r = _patch(_client(mock_db, _admin()), link, sub, task_stage_id=REVISION.id,
               expected_stage_id=REVIEW.id, comment="   ", version_id=uuid.uuid4())

    assert r.status_code == 422
    assert sub.task_stage_id == REVIEW.id
    mock_db.commit.assert_not_called()


@patch("apps.api.routers.tasks.send_task_safe")
def test_send_back_saves_the_reason_on_that_file_and_emails_the_editor_after_commit(send, mock_db):
    from apps.api.tasks.email_tasks import send_approval_email

    link = _link()
    sub = _submission(link, REVIEW.id)
    asset, version = _file_in(sub)
    _db(mock_db, link, REVISION, sub, (version, asset), _editor(sub))
    order = []
    mock_db.commit.side_effect = lambda: order.append("commit")
    send.side_effect = lambda *a, **k: order.append("email")

    r = _patch(_client(mock_db, _admin()), link, sub, task_stage_id=REVISION.id,
               expected_stage_id=REVIEW.id, comment="  Logo is cropped  ", version_id=version.id)

    assert r.status_code == 200, r.text
    assert sub.task_stage_id == REVISION.id
    [c] = _comments(mock_db)
    assert (c.body, c.visibility, c.version_id, c.asset_id) == ("Logo is cropped", "public", version.id, asset.id)
    assert order == ["commit", "email"]
    assert send.call_args.args[0] is send_approval_email
    kw = send.call_args.kwargs
    assert kw["to_email"] == "ada@example.com"
    assert kw["status"] == "rejected"
    assert kw["note"] == "Logo is cropped"
    assert kw["asset_link"].endswith(f"/projects/{sub.project_id}/assets/{asset.id}")


@patch("apps.api.routers.tasks.send_task_safe")
def test_a_reason_about_a_file_outside_this_editors_project_is_refused(send, mock_db):
    """Otherwise a reviewer could pin a comment on, and email about, any file."""
    link = _link()
    sub = _submission(link, REVIEW.id)
    _db(mock_db, link, REVISION, sub, None)  # version lookup scoped to sub.project_id finds nothing

    r = _patch(_client(mock_db, _admin()), link, sub, task_stage_id=REVISION.id,
               expected_stage_id=REVIEW.id, comment="Fix it", version_id=uuid.uuid4())

    assert r.status_code == 422
    assert sub.task_stage_id == REVIEW.id
    assert not _comments(mock_db)
    mock_db.commit.assert_not_called()


@patch("apps.api.routers.tasks.send_task_safe")
def test_a_reason_needs_to_say_which_file_it_is_about(send, mock_db):
    link = _link()
    sub = _submission(link, REVIEW.id)
    _db(mock_db, link, REVISION, sub)

    r = _patch(_client(mock_db, _admin()), link, sub, task_stage_id=REVISION.id,
               expected_stage_id=REVIEW.id, comment="Fix it")

    assert r.status_code == 422
    mock_db.commit.assert_not_called()


@patch("apps.api.routers.tasks.send_task_safe")
def test_a_comment_on_anything_but_revision_is_refused(send, mock_db):
    link = _link()
    sub = _submission(link, REVIEW.id)
    _db(mock_db, link, DONE, sub)

    r = _patch(_client(mock_db, _admin()), link, sub, task_stage_id=DONE.id,
               expected_stage_id=REVIEW.id, comment="nice", version_id=uuid.uuid4())

    assert r.status_code == 422
    mock_db.commit.assert_not_called()


@patch("apps.api.routers.tasks.send_task_safe")
def test_the_tasks_dropdown_still_moves_an_editor_to_revision_without_a_reason(send, mock_db):
    """The /tasks dropdown sends no expected_stage_id. It must not start failing
    because review decisions now require a reason, nor 409 on a stale view."""
    link = _link()
    sub = _submission(link, DONE.id)
    _db(mock_db, link, REVISION, sub)

    r = _patch(_client(mock_db, _admin()), link, sub, task_stage_id=REVISION.id)

    assert r.status_code == 200, r.text
    assert sub.task_stage_id == REVISION.id
    send.assert_not_called()
