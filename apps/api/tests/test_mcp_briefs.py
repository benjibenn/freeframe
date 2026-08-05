"""Tests for the MCP brief tools and the API-key-to-user auth they rely on.

The point of these tests is the *why*, not the plumbing: an MCP key must not be
able to act as nobody (bootstrap key) or as someone without admin rights, and a
move must not claim to have relocated work it did not touch.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from apps.api.middleware.api_key import resolve_api_key_user
from apps.api.routers import mcp as mcp_router


# ── resolve_api_key_user ─────────────────────────────────────────────────────

def _admin(user_id=None):
    u = MagicMock()
    u.id = user_id or uuid.uuid4()
    u.is_superadmin = True
    u.is_subadmin = False
    u.deleted_at = None
    return u


def _key_record(created_by):
    rec = MagicMock()
    rec.created_by = created_by
    rec.revoked_at = None
    rec.last_used_at = None
    return rec


def test_missing_key_is_rejected(mock_db):
    with pytest.raises(HTTPException) as exc:
        resolve_api_key_user(mock_db, None)
    assert exc.value.status_code == 401


def test_bootstrap_key_is_rejected(mock_db):
    """The static env key authenticates /public/v1 but has no created_by.

    Accepting it here would leave the tools with no user to act as, so it has to
    fail at the door rather than deeper in with a confusing AttributeError.
    """
    with patch("apps.api.middleware.api_key.settings") as s:
        s.public_api_key = "bootstrap-secret"
        with pytest.raises(HTTPException) as exc:
            resolve_api_key_user(mock_db, "bootstrap-secret")
    assert exc.value.status_code == 401
    assert "no user identity" in str(exc.value.detail)


def test_unknown_or_revoked_key_is_rejected(mock_db):
    mock_db.first.return_value = None  # no matching, unrevoked row
    with patch("apps.api.middleware.api_key.settings") as s:
        s.public_api_key = None
        with pytest.raises(HTTPException) as exc:
            resolve_api_key_user(mock_db, "ffpk_nope")
    assert exc.value.status_code == 401


def test_non_admin_key_is_rejected_at_resolution(mock_db):
    """A non-admin key would otherwise 403 twice, in two unrelated places.

    Every write route calls require_platform_admin, and _resolve_home separately
    falls back to project membership. Failing once here is what makes the error
    reportable by an agent.
    """
    user = _admin()
    user.is_superadmin = False
    user.is_subadmin = False
    mock_db.first.side_effect = [_key_record(user.id), user]
    with patch("apps.api.middleware.api_key.settings") as s:
        s.public_api_key = None
        with pytest.raises(HTTPException) as exc:
            resolve_api_key_user(mock_db, "ffpk_valid")
    assert exc.value.status_code == 403


def test_deleted_creator_is_rejected(mock_db):
    rec = _key_record(uuid.uuid4())
    mock_db.first.side_effect = [rec, None]  # key found, user gone
    with patch("apps.api.middleware.api_key.settings") as s:
        s.public_api_key = None
        with pytest.raises(HTTPException) as exc:
            resolve_api_key_user(mock_db, "ffpk_valid")
    assert exc.value.status_code == 401


def test_valid_admin_key_resolves_to_its_creator(mock_db):
    """The key IS the identity — this is what removes the need for a service account."""
    user = _admin()
    rec = _key_record(user.id)
    mock_db.first.side_effect = [rec, user]
    with patch("apps.api.middleware.api_key.settings") as s:
        s.public_api_key = None
        resolved = resolve_api_key_user(mock_db, "ffpk_valid")
    assert resolved is user
    assert rec.last_used_at is not None  # activity shows up in the admin UI
    mock_db.commit.assert_called_once()


# ── Tools ────────────────────────────────────────────────────────────────────

@pytest.fixture
def as_admin(mock_db):
    """Run a tool body as an authenticated admin against a mocked session."""
    user = _admin()
    token = mcp_router._current_user.set(user)
    with patch("apps.api.routers.mcp.SessionLocal", return_value=mock_db):
        yield user
    mcp_router._current_user.reset(token)


def _link(**over):
    link = MagicMock()
    link.id = over.get("id", uuid.uuid4())
    link.token = over.get("token", "tok123")
    link.title = over.get("title", "Spring campaign")
    link.home_project_id = over.get("home_project_id", uuid.uuid4())
    link.home_folder_id = over.get("home_folder_id")
    link.home_path = over.get("home_path", "ecom/Phones")
    link.submission_count = over.get("submission_count", 0)
    link.is_enabled = True
    link.created_at = datetime.now(timezone.utc)
    return link


def test_create_brief_returns_a_usable_submit_url(as_admin):
    """The token alone is not actionable; the human needs the URL to send out."""
    created = _link(token="abc123")
    with patch.object(mcp_router.submissions_router, "create_submission_link", return_value=created):
        with patch("apps.api.routers.mcp.settings") as s:
            s.frontend_url = "https://freeframe.multiadsx.com"
            out = mcp_router.create_brief(
                title="Spring campaign",
                home_project_id=str(uuid.uuid4()),
            )
    assert out["submit_url"] == "https://freeframe.multiadsx.com/submit/abc123"


def test_create_brief_rejects_a_non_uuid_project(as_admin):
    with pytest.raises(ValueError, match="home_project_id must be a UUID"):
        mcp_router.create_brief(title="X", home_project_id="the ecom one")


def test_duplicate_brief_rejects_a_folder_without_its_project(as_admin):
    """The endpoint drops a lone folder silently; the tool must not.

    DuplicateLinkRequest only applies home_folder_id when home_project_id is also
    given. Passing one alone would look like it worked and file the copy somewhere
    the caller did not choose.
    """
    with pytest.raises(ValueError, match="needs home_project_id"):
        mcp_router.duplicate_brief(
            link_id=str(uuid.uuid4()),
            home_folder_id=str(uuid.uuid4()),
        )


def test_duplicate_brief_passes_overrides_through(as_admin):
    src_id = uuid.uuid4()
    with patch.object(
        mcp_router.submissions_router, "duplicate_submission_link", return_value=_link()
    ) as dup:
        mcp_router.duplicate_brief(link_id=str(src_id), title="Copy for Q3")
    assert dup.call_args.kwargs["link_id"] == src_id
    assert dup.call_args.kwargs["body"].title == "Copy for Q3"


def test_move_brief_states_that_existing_assets_do_not_move(as_admin):
    """Re-filing is scoped to future uploads — assets keep the path stamped at upload.

    Without this in the payload an agent will tell the user their existing work was
    relocated. It was not, and that stamp is deliberate: an asset must keep the path
    it was filed under when it was made.
    """
    result = MagicMock()
    result.updated = 2
    with patch.object(
        mcp_router.submissions_router, "bulk_refile_submission_links", return_value=result
    ):
        out = mcp_router.move_brief(
            link_ids=[str(uuid.uuid4()), str(uuid.uuid4())],
            home_project_id=str(uuid.uuid4()),
        )
    assert out["moved"] == 2
    assert "keep their original stamped path" in out["note"]


def test_move_brief_reports_partial_moves_honestly(as_admin):
    """bulk-refile skips ids it cannot find rather than failing the batch.

    Reporting len(link_ids) would claim work that did not happen.
    """
    result = MagicMock()
    result.updated = 1
    with patch.object(
        mcp_router.submissions_router, "bulk_refile_submission_links", return_value=result
    ):
        out = mcp_router.move_brief(
            link_ids=[str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())],
            home_project_id=str(uuid.uuid4()),
        )
    assert out == {"moved": 1, "requested": 3, "note": out["note"]}


def test_move_brief_rejects_an_empty_selection(as_admin):
    with pytest.raises(ValueError, match="at least one brief id"):
        mcp_router.move_brief(link_ids=[], home_project_id=str(uuid.uuid4()))


def test_http_errors_become_actionable_tool_errors(as_admin):
    """A 403 escaping as a transport failure tells the agent nothing it can use."""
    with patch.object(
        mcp_router.submissions_router,
        "create_submission_link",
        side_effect=HTTPException(status_code=403, detail="Not a member of that project"),
    ):
        with pytest.raises(ValueError, match="Not a member of that project"):
            mcp_router.create_brief(title="X", home_project_id=str(uuid.uuid4()))


def test_list_briefs_filters_by_project(as_admin):
    wanted = uuid.uuid4()
    links = [_link(home_project_id=wanted), _link(home_project_id=uuid.uuid4())]
    with patch.object(mcp_router.submissions_router, "list_submission_links", return_value=links):
        with patch("apps.api.routers.mcp.settings") as s:
            s.frontend_url = "https://x.test"
            out = mcp_router.list_briefs(project_id=str(wanted))
    assert len(out) == 1
    assert out[0]["home_project_id"] == str(wanted)


def test_list_destinations_flattens_folders_to_paths(as_admin):
    """An agent matches on "ecom/Phones"; making it walk nested JSON adds a step it can get wrong."""
    # `name` is reserved by the MagicMock constructor, so it has to be set after.
    child = MagicMock(id=uuid.uuid4(), children=[])
    child.name = "Phones"
    root = MagicMock(id=uuid.uuid4(), children=[child])
    root.name = "ecom"
    with patch.object(mcp_router.folders_router, "get_folder_tree", return_value=[root]):
        out = mcp_router.list_destinations(project_id=str(uuid.uuid4()))
    assert [f["path"] for f in out["folders"]] == ["ecom", "ecom/Phones"]
