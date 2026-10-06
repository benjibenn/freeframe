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
