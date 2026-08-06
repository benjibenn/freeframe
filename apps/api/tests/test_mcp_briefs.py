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
    """Run a tool body as an authenticated admin on a request-scoped session."""
    user = _admin()
    user_token = mcp_router._current_user.set(user)
    db_token = mcp_router._current_db.set(mock_db)
    yield user
    mcp_router._current_user.reset(user_token)
    mcp_router._current_db.reset(db_token)


def test_tools_use_the_request_session_not_a_new_one(as_admin, mock_db):
    """Regression: the authenticated User is attached to the request's session.

    resolve_api_key_user commits to stamp last_used_at, which expires the User.
    If a tool then opened its own session, that User would be detached and the
    first lazy attribute read inside the route would raise DetachedInstanceError —
    which is exactly what happened against a real database, invisibly to mocks.
    """
    with patch("apps.api.routers.mcp.SessionLocal") as fresh:
        with patch.object(
            mcp_router.submissions_router, "list_submission_links", return_value=[]
        ) as listed:
            mcp_router.list_briefs()
    fresh.assert_not_called()
    assert listed.call_args.kwargs["db"] is mock_db


def test_a_failed_tool_rolls_back_so_the_next_one_is_usable(as_admin, mock_db):
    """One MCP request can carry several tool calls on one session."""
    with patch.object(
        mcp_router.submissions_router,
        "create_submission_link",
        side_effect=HTTPException(status_code=404, detail="Project not found"),
    ):
        with pytest.raises(ValueError):
            mcp_router.create_brief(title="X", home_project_id=str(uuid.uuid4()))
    mock_db.rollback.assert_called_once()


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


# ── Structured briefs ────────────────────────────────────────────────────────

SAMPLE = {
    "title": "Static - iPhone",
    "overview": "Adapt the reference ad into 2 localised statics.",
    "output_languages": ["German", "Swedish"],
    "guidelines": ["Keep the original layout"],
}


def test_create_brief_attaches_the_structured_brief_in_one_call(as_admin):
    """The REST API needs two writes; the agent should not have to know that.

    A forgotten second call leaves a live submit URL on a request with no brief,
    which submitters can already start working against.
    """
    created = _link()
    attached = _link()
    attached.brief_json = SAMPLE
    with patch.object(
        mcp_router.submissions_router, "create_submission_link", return_value=created
    ):
        with patch.object(
            mcp_router.submissions_router,
            "set_submission_brief_json",
            return_value=attached,
        ) as setter:
            out = mcp_router.create_brief(
                title="Static - iPhone",
                home_project_id=str(uuid.uuid4()),
                brief_json=SAMPLE,
            )
    assert setter.call_args.kwargs["link_id"] == created.id
    assert setter.call_args.kwargs["body"].brief == SAMPLE
    assert out["has_brief_json"] is True


def test_create_brief_without_brief_json_makes_only_one_write(as_admin):
    with patch.object(
        mcp_router.submissions_router, "create_submission_link", return_value=_link()
    ):
        with patch.object(
            mcp_router.submissions_router, "set_submission_brief_json"
        ) as setter:
            mcp_router.create_brief(title="X", home_project_id=str(uuid.uuid4()))
    setter.assert_not_called()


def test_an_invalid_brief_is_rejected_before_the_request_exists(as_admin):
    """Validating after create would strand an empty request with a live URL."""
    with patch.object(mcp_router.submissions_router, "create_submission_link") as create:
        with pytest.raises(ValueError, match="must not be empty"):
            mcp_router.create_brief(
                title="X", home_project_id=str(uuid.uuid4()), brief_json={}
            )
    create.assert_not_called()


def test_a_failed_attach_retracts_the_request(as_admin):
    """No half-made request: if the brief cannot be attached, the request goes away."""
    created = _link()
    with patch.object(
        mcp_router.submissions_router, "create_submission_link", return_value=created
    ):
        with patch.object(
            mcp_router.submissions_router,
            "set_submission_brief_json",
            side_effect=HTTPException(status_code=500, detail="boom"),
        ):
            with patch.object(
                mcp_router.submissions_router, "disable_submission_link"
            ) as retract:
                with pytest.raises(ValueError):
                    mcp_router.create_brief(
                        title="X",
                        home_project_id=str(uuid.uuid4()),
                        brief_json=SAMPLE,
                    )
    assert retract.call_args.kwargs["link_id"] == created.id


def test_duplicate_brief_passes_brief_json_through(as_admin):
    """The duplicate endpoint takes brief_json natively — it was simply never wired up."""
    with patch.object(
        mcp_router.submissions_router, "duplicate_submission_link", return_value=_link()
    ) as dup:
        mcp_router.duplicate_brief(link_id=str(uuid.uuid4()), brief_json=SAMPLE)
    assert dup.call_args.kwargs["body"].brief_json == SAMPLE


def test_get_brief_returns_brief_json_that_list_briefs_omits(as_admin):
    link = _link()
    link.instructions = "Deliver by Friday"
    link.brief_json = SAMPLE
    link.has_brief_json = True
    link.has_brief = True
    link.reference_video_count = 2
    link.reference_image_count = 0
    with patch.object(
        mcp_router.submissions_router, "get_submission_link", return_value=link
    ):
        out = mcp_router.get_brief(link_id=str(uuid.uuid4()))
    assert out["brief_json"] == SAMPLE
    # Flagged rather than returned — no MCP tool serves the PDF or media bytes,
    # and silence would read as "this brief has nothing attached".
    assert out["has_brief_pdf"] is True
    assert out["reference_video_count"] == 2


def test_set_brief_json_accepts_null_to_clear(as_admin):
    cleared = _link()
    cleared.brief_json = None
    cleared.has_brief_json = False
    with patch.object(
        mcp_router.submissions_router,
        "set_submission_brief_json",
        return_value=cleared,
    ) as setter:
        out = mcp_router.set_brief_json(link_id=str(uuid.uuid4()), brief_json=None)
    assert setter.call_args.kwargs["body"].brief is None
    assert out["has_brief_json"] is False


def test_set_brief_json_rejects_a_non_object(as_admin):
    with pytest.raises(ValueError, match="must be a JSON object"):
        mcp_router.set_brief_json(link_id=str(uuid.uuid4()), brief_json="just a string")


def test_the_mcp_endpoint_answers_with_or_without_a_trailing_slash():
    """Regression: claude.ai stores the URL exactly as typed.

    Mounting at /mcp made a bare /mcp redirect, and behind Traefik that redirect
    named the internal path over plain http — a client posting to /api/mcp got a
    downgraded URL pointing nowhere, and the connector failed with "couldn't
    connect" before a single request reached the app.
    """
    import os
    from unittest.mock import MagicMock, patch

    for k, v in dict(
        DATABASE_URL="postgresql://u:p@localhost:5432/t", REDIS_URL="redis://localhost:6379/0",
        S3_BUCKET="b", S3_ENDPOINT="http://x", S3_ACCESS_KEY="k", S3_SECRET_KEY="s",
        S3_REGION="r", JWT_SECRET="x" * 32, FRONTEND_URL="https://freeframe.multiadsx.com",
    ).items():
        os.environ.setdefault(k, v)

    with patch("apps.api.services.s3_service.ensure_bucket_exists"), \
         patch("apps.api.services.s3_service.get_s3_client", return_value=MagicMock()):
        from fastapi.testclient import TestClient
        from apps.api.main import app

        body = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                           "clientInfo": {"name": "v", "version": "1"}}}
        headers = {"Accept": "application/json, text/event-stream",
                   "Content-Type": "application/json"}
        with TestClient(app) as c:
            for path in ("/mcp", "/mcp/"):
                r = c.post(path, json=body, headers=headers, follow_redirects=False)
                # 401 is the endpoint answering. A 3xx means it redirected instead.
                assert r.status_code == 401, f"{path} returned {r.status_code}, not the endpoint"
