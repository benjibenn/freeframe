"""Where submitted work is filed: the caller's own slot, or an editor's.

Intent encoded:
- each submitter on a brief has a private project, and an editor sees only
  theirs. Language variants an admin makes from an editor's file are useless to
  that editor if they land in the admin's slot, so the admin can name the
  editor's submission and file them beside the original.
- that is a write into another user's project, so only platform admins may do
  it; a submission from a different brief is refused, never silently used.
- leaving submission_id out keeps today's behaviour exactly.
"""
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from apps.api.routers import mcp as mcp_router
from apps.api.routers import submissions as submissions_router


def _user(admin=False):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.is_superadmin = admin
    u.is_subadmin = False
    return u


def _link():
    link = MagicMock()
    link.id = uuid.uuid4()
    return link


def _submission(link, owner):
    sub = MagicMock()
    sub.id = uuid.uuid4()
    sub.submission_link_id = link.id
    sub.user_id = owner.id
    sub.project_id = uuid.uuid4()
    return sub


def test_admin_files_variants_into_the_editors_project(mock_db):
    link, editor, admin = _link(), _user(), _user(admin=True)
    sub = _submission(link, editor)
    mock_db.query.return_value.filter.return_value.first.return_value = sub
    with patch.object(submissions_router, "_provision_submission_project") as provision:
        slot = submissions_router.resolve_submission_slot(mock_db, link, admin, sub.id)
    assert slot == sub.project_id
    provision.assert_not_called()  # no admin slot is created on the side


def test_a_non_admin_cannot_write_into_someone_elses_submission(mock_db):
    link, editor, other = _link(), _user(), _user()
    mock_db.query.return_value.filter.return_value.first.return_value = _submission(link, editor)
    with pytest.raises(HTTPException) as err:
        submissions_router.resolve_submission_slot(mock_db, link, other, uuid.uuid4())
    assert err.value.status_code == 403


def test_a_submission_from_another_brief_is_refused(mock_db):
    link, editor, admin = _link(), _user(), _user(admin=True)
    mock_db.query.return_value.filter.return_value.first.return_value = _submission(_link(), editor)
    with pytest.raises(HTTPException) as err:
        submissions_router.resolve_submission_slot(mock_db, link, admin, uuid.uuid4())
    assert err.value.status_code == 404


def test_without_submission_id_work_goes_to_the_callers_own_slot(mock_db):
    link, user = _link(), _user()
    own = uuid.uuid4()
    with patch.object(submissions_router, "_provision_submission_project", return_value=own):
        assert submissions_router.resolve_submission_slot(mock_db, link, user) == own


def test_submit_work_passes_the_target_submission_through(mock_db):
    admin = _user(admin=True)
    admin.deleted_at = None
    u_tok = mcp_router._current_user.set(admin)
    d_tok = mcp_router._current_db.set(mock_db)
    target = uuid.uuid4()
    try:
        with patch.object(
            mcp_router.submissions_router, "submit_work_from_url", return_value=MagicMock()
        ) as submitted:
            mcp_router.submit_work(
                link_id=str(uuid.uuid4()),
                url="https://cdn.example.com/es.png",
                source_url="https://canva.com/design/abc",
                submission_id=str(target),
            )
    finally:
        mcp_router._current_user.reset(u_tok)
        mcp_router._current_db.reset(d_tok)
    assert submitted.call_args.kwargs["body"].submission_id == target


def test_get_file_url_passes_every_route_argument(mock_db):
    """get_file_url calls the stream route as a plain function. Any argument it
    leaves out keeps FastAPI's Query() marker, which the route then put into a SQL
    filter ("can't adapt type 'Query'"), so the tool failed for every file."""
    import inspect
    from apps.api.routers import assets as assets_router
    admin = _user(admin=True)
    admin.deleted_at = None
    u_tok = mcp_router._current_user.set(admin)
    d_tok = mcp_router._current_db.set(mock_db)
    try:
        with patch.object(mcp_router.assets_router, "get_stream_url", return_value=MagicMock()) as route:
            mcp_router.get_file_url(asset_id=str(uuid.uuid4()))
    finally:
        mcp_router._current_user.reset(u_tok)
        mcp_router._current_db.reset(d_tok)
    params = set(inspect.signature(assets_router.get_stream_url).parameters) - {"db", "current_user"}
    assert params <= set(route.call_args.kwargs)


# ── Who is named as uploader ─────────────────────────────────────────────────
# The clone bot files an editor's language variants with the admin's API key.
# The work is the editor's, so the editor must show as uploader, not the admin.

from apps.api.models.activity import ActivityAction, ActivityLog
from apps.api.models.comment import Comment
from apps.api.models.submission import Submission
from apps.api.services import source_link


def _upload(uploader, version_number=1, asset_creator=None):
    asset = MagicMock()
    asset.id, asset.project_id = uuid.uuid4(), uuid.uuid4()
    asset.created_by = (asset_creator or uploader).id
    version = MagicMock()
    version.id, version.version_number, version.created_by = uuid.uuid4(), version_number, uploader.id
    source = MagicMock(author_id=uploader.id, body=f"{source_link.PREFIX}https://canva.com/design/x")
    note = MagicMock(author_id=uploader.id, body="the admin's own note")
    log = MagicMock(user_id=uploader.id, payload={"version_number": version_number})
    return asset, version, source, note, log


def _db_with(sub, comments, logs):
    db = MagicMock()
    rows = {Submission: [sub], Comment: comments, ActivityLog: logs}

    def query(model):
        q = MagicMock()
        q.filter.return_value.first.return_value = rows[model][0]
        q.filter.return_value.all.return_value = rows[model]
        return q
    db.query.side_effect = query
    return db


def test_work_an_admin_files_into_an_editors_slot_is_credited_to_the_editor():
    admin, editor = _user(admin=True), _user()
    asset, version, source, note, log = _upload(admin)
    sub = MagicMock(user_id=editor.id, project_id=asset.project_id)
    submissions_router.credit_slot_owner(_db_with(sub, [source, note], [log]), asset, version, admin)
    assert version.created_by == editor.id
    assert asset.created_by == editor.id
    assert source.author_id == editor.id
    assert log.user_id == editor.id
    assert note.author_id == admin.id  # only the upload's own rows move, never real comments


def test_a_revision_keeps_the_assets_original_creator():
    admin, editor, first = _user(admin=True), _user(), _user()
    asset, version, source, _, log = _upload(admin, version_number=2, asset_creator=first)
    sub = MagicMock(user_id=editor.id, project_id=asset.project_id)
    submissions_router.credit_slot_owner(_db_with(sub, [source], [log]), asset, version, admin)
    assert version.created_by == editor.id
    assert asset.created_by == first.id


def test_uploading_into_your_own_slot_changes_nothing():
    editor = _user()
    asset, version, source, _, log = _upload(editor)
    sub = MagicMock(user_id=editor.id, project_id=asset.project_id)
    submissions_router.credit_slot_owner(_db_with(sub, [source], [log]), asset, version, editor)
    assert version.created_by == editor.id and log.user_id == editor.id
