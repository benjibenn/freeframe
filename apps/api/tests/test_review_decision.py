"""Approve and reject from the /review page, through PATCH /assets/{id}/task-stage.

Intent:
- a rejected file goes back to its editor, who cannot act on "rejected" alone,
  so a reason is required, saved where they will see it and emailed to them;
- a decision on a file someone else already moved is refused (409), so two
  reviewers cannot both decide one file;
- the tasks board moves files without any of this and must keep working.
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


def _asset(stage_id, created_by=None):
    a = MagicMock()
    a.id = uuid.uuid4()
    a.project_id = uuid.uuid4()
    a.name = "hook-3.png"
    a.asset_type = AssetType.image
    a.task_stage_id = stage_id
    a.created_by = created_by or uuid.uuid4()
    a.run_as_ad = False
    a.created_at = datetime.now(timezone.utc)
    a.deleted_at = None
    return a


def _uploader(asset):
    u = MagicMock()
    u.id = asset.created_by
    u.email = "ada@example.com"
    u.display_name = "Ada"
    return u


def _project():
    p = MagicMock()
    p.name = "Battery brief — Ada"
    p.submission_link_id = None
    return p


def _patch(client, asset, **body):
    return client.patch(f"/assets/{asset.id}/task-stage", json={k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in body.items()})


@patch("apps.api.routers.tasks.send_task_safe")
def test_reject_without_a_comment_is_refused_and_changes_nothing(send, mock_db):
    asset = _asset(REVIEW.id)
    mock_db.first.side_effect = [asset, REVISION]

    r = _patch(_client(mock_db, _admin()), asset, task_stage_id=REVISION.id, expected_stage_id=REVIEW.id, comment="   ")

    assert r.status_code == 422
    assert asset.task_stage_id == REVIEW.id
    mock_db.commit.assert_not_called()
    send.assert_not_called()


@patch("apps.api.routers.tasks.send_task_safe")
def test_a_file_moved_by_someone_else_is_a_409(send, mock_db):
    asset = _asset(DONE.id)
    mock_db.first.side_effect = [asset, DONE]

    r = _patch(_client(mock_db, _admin()), asset, task_stage_id=DONE.id, expected_stage_id=REVIEW.id)

    assert r.status_code == 409
    assert r.json()["detail"] == "This file is no longer in that stage"
    mock_db.commit.assert_not_called()


@patch("apps.api.routers.tasks.send_task_safe")
def test_reject_saves_the_comment_on_that_version_and_emails_the_uploader(send, mock_db):
    from apps.api.tasks.email_tasks import send_approval_email

    asset = _asset(REVIEW.id)
    version = MagicMock()
    version.id = uuid.uuid4()
    mock_db.first.side_effect = [asset, REVISION, version, _uploader(asset), _project()]

    r = _patch(
        _client(mock_db, _admin()), asset,
        task_stage_id=REVISION.id, expected_stage_id=REVIEW.id,
        comment="  Logo is cropped  ", version_id=version.id,
    )

    assert r.status_code == 200, r.text
    assert asset.task_stage_id == REVISION.id
    comments = [c.args[0] for c in mock_db.add.call_args_list if isinstance(c.args[0], Comment)]
    assert len(comments) == 1
    assert comments[0].body == "Logo is cropped"
    assert comments[0].visibility == "public"
    assert comments[0].version_id == version.id
    send.assert_called_once()
    assert send.call_args.args[0] is send_approval_email
    kw = send.call_args.kwargs
    assert kw["to_email"] == "ada@example.com"
    assert kw["status"] == "rejected"
    assert kw["note"] == "Logo is cropped"
    assert kw["asset_link"].endswith(f"/projects/{asset.project_id}/assets/{asset.id}")


@patch("apps.api.routers.tasks.send_task_safe")
def test_approve_needs_no_comment_and_sends_nothing(send, mock_db):
    asset = _asset(REVIEW.id)
    mock_db.first.side_effect = [asset, DONE, _uploader(asset), _project()]

    r = _patch(_client(mock_db, _admin()), asset, task_stage_id=DONE.id, expected_stage_id=REVIEW.id)

    assert r.status_code == 200, r.text
    assert r.json()["asset_type"] == "image"
    assert asset.task_stage_id == DONE.id
    assert not [c for c in mock_db.add.call_args_list if isinstance(c.args[0], Comment)]
    send.assert_not_called()


@patch("apps.api.routers.tasks.send_task_safe")
def test_a_comment_on_anything_but_revision_is_refused(send, mock_db):
    asset = _asset(REVIEW.id)
    mock_db.first.side_effect = [asset, DONE]

    r = _patch(_client(mock_db, _admin()), asset, task_stage_id=DONE.id, expected_stage_id=REVIEW.id, comment="nice")

    assert r.status_code == 422
    mock_db.commit.assert_not_called()


@patch("apps.api.routers.tasks.send_task_safe")
def test_no_email_when_the_reviewer_uploaded_it_themselves(send, mock_db):
    admin = _admin()
    asset = _asset(REVIEW.id, created_by=admin.id)
    version = MagicMock()
    version.id = uuid.uuid4()
    mock_db.order_by.return_value = mock_db
    mock_db.first.side_effect = [asset, REVISION, version, _uploader(asset), _project()]

    r = _patch(_client(mock_db, admin), asset, task_stage_id=REVISION.id, expected_stage_id=REVIEW.id, comment="Fix it")

    assert r.status_code == 200, r.text
    send.assert_not_called()


@patch("apps.api.routers.tasks.send_task_safe")
def test_a_board_move_to_revision_still_needs_no_comment(send, mock_db):
    """The tasks board's stage dropdown sends no expected_stage_id. It must not
    start failing because review decisions now require a reason."""
    asset = _asset(REVIEW.id)
    mock_db.first.side_effect = [asset, REVISION, _uploader(asset), _project()]

    r = _patch(_client(mock_db, _admin()), asset, task_stage_id=REVISION.id)

    assert r.status_code == 200, r.text
    assert asset.task_stage_id == REVISION.id
