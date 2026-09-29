"""Tests for the MCP public-share-link tools.

These links are the one thing the MCP server can make that is reachable without
a Freeframe account, so the tests are about what a careless agent must not be
able to do by accident: mint one with a read-only token, hand back a token that
is not a URL anyone can open, turn downloading on without being asked, or echo a
password into a second tool-call log.
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from apps.api.routers import mcp as mcp_router


def _admin():
    u = MagicMock()
    u.id = uuid.uuid4()
    u.is_superadmin = True
    u.is_subadmin = False
    u.deleted_at = None
    return u


@pytest.fixture
def as_admin(mock_db):
    user = _admin()
    user_token = mcp_router._current_user.set(user)
    db_token = mcp_router._current_db.set(mock_db)
    yield user
    mcp_router._current_user.reset(user_token)
    mcp_router._current_db.reset(db_token)


def _share(**over):
    link = MagicMock()
    link.token = over.get("token", "sharetok")
    link.title = over.get("title", "cut-03.mp4")
    link.asset_id = over.get("asset_id")
    link.folder_id = over.get("folder_id")
    link.project_id = over.get("project_id")
    link.permission = over.get("permission", "view")
    link.allow_download = over.get("allow_download", False)
    link.password_hash = over.get("password_hash")
    link.is_enabled = over.get("is_enabled", True)
    link.expires_at = over.get("expires_at")
    return link


# ── The URL is the deliverable ───────────────────────────────────────────────

def test_share_file_returns_a_url_a_recipient_can_open(as_admin):
    """A token is not actionable; the human forwards a URL.

    Same reason create_brief returns submit_url rather than the raw token.
    """
    link = _share(token="abc123", asset_id=uuid.uuid4())
    with patch.object(mcp_router.share_router, "create_share_link", return_value=link):
        with patch("apps.api.routers.mcp.settings") as s:
            s.frontend_url = "https://freeframe.multiadsx.com"
            out = mcp_router.share_file(asset_id=str(uuid.uuid4()))
    assert out["url"] == "https://freeframe.multiadsx.com/share/abc123"
    assert out["shares"] == "file"


def test_share_folder_is_labelled_as_a_folder_link(as_admin):
    """An agent holding two links must be able to tell what each exposes —
    one file, or a folder that keeps growing."""
    link = _share(token="f1", folder_id=uuid.uuid4())
    with patch.object(mcp_router.share_router, "create_folder_share_link", return_value=link):
        with patch("apps.api.routers.mcp.settings") as s:
            s.frontend_url = "https://x.test"
            out = mcp_router.share_folder(folder_id=str(uuid.uuid4()))
    assert out["shares"] == "folder"


def test_share_many_is_labelled_a_selection(as_admin):
    link = _share(token="m1", project_id=uuid.uuid4())
    with patch.object(mcp_router.share_router, "create_multi_share_link", return_value=link) as created:
        with patch("apps.api.routers.mcp.settings") as s:
            s.frontend_url = "https://x.test"
            aid, fid = str(uuid.uuid4()), str(uuid.uuid4())
            out = mcp_router.share_many(
                project_id=str(uuid.uuid4()), asset_ids=[aid], folder_ids=[fid]
            )
    assert out["shares"] == "selection"
    body = created.call_args.kwargs["body"]
    assert [str(a) for a in body.asset_ids] == [aid]
    assert [str(f) for f in body.folder_ids] == [fid]


# ── Safe defaults ────────────────────────────────────────────────────────────

def test_a_link_is_view_only_and_undownloadable_unless_asked(as_admin):
    """The default is the least the recipient needs.

    An agent told "send this to the client" should not silently also grant a
    permanent copy of the file and the right to approve it.
    """
    with patch.object(mcp_router.share_router, "create_share_link", return_value=_share()) as created:
        with patch("apps.api.routers.mcp.settings") as s:
            s.frontend_url = "https://x.test"
            mcp_router.share_file(asset_id=str(uuid.uuid4()))
    body = created.call_args.kwargs["body"]
    assert body.allow_download is False
    assert body.permission.value == "view"
    assert body.expires_at is None
    assert body.password is None


def test_an_unknown_permission_is_refused_before_a_link_exists(as_admin):
    """Rejected here rather than by the enum deeper in: a link created with the
    wrong permission has already been minted by the time anyone notices."""
    with patch.object(mcp_router.share_router, "create_share_link") as created:
        with pytest.raises(ValueError, match="permission must be one of"):
            mcp_router.share_file(asset_id=str(uuid.uuid4()), permission="edit")
    created.assert_not_called()


def test_a_read_only_token_cannot_mint_a_public_link(as_admin):
    """Minting a link is the most consequential write here — it grants access to
    people who have no account at all — so it must sit behind briefs:write."""
    tok = mcp_router._current_scopes.set([mcp_router.SCOPE_READ])
    try:
        with patch.object(mcp_router.share_router, "create_share_link") as created:
            with pytest.raises(ValueError, match="missing the briefs:write scope"):
                mcp_router.share_file(asset_id=str(uuid.uuid4()))
        created.assert_not_called()
    finally:
        mcp_router._current_scopes.reset(tok)


# ── Expiry ───────────────────────────────────────────────────────────────────

def test_expires_in_days_becomes_a_future_timestamp(as_admin):
    """Days-from-now, not an absolute date: an agent asked for "a week" would
    otherwise compute one from whatever it believes today to be."""
    with patch.object(mcp_router.share_router, "create_share_link", return_value=_share()) as created:
        with patch("apps.api.routers.mcp.settings") as s:
            s.frontend_url = "https://x.test"
            mcp_router.share_file(asset_id=str(uuid.uuid4()), expires_in_days=7)
    expires = created.call_args.kwargs["body"].expires_at
    assert expires > datetime.now(timezone.utc) + timedelta(days=6)


def test_a_non_positive_expiry_is_refused(as_admin):
    """A link that expired before it was created fails only when the recipient
    opens it — by which time the sender has already sent it."""
    with patch.object(mcp_router.share_router, "create_share_link") as created:
        with pytest.raises(ValueError, match="1 or more"):
            mcp_router.share_file(asset_id=str(uuid.uuid4()), expires_in_days=0)
    created.assert_not_called()


# ── Secrets ──────────────────────────────────────────────────────────────────

def test_a_password_is_reported_as_set_but_never_echoed(as_admin):
    """The caller already has it. Repeating it copies the secret into a second
    tool-call transcript for nothing — the same reason reset_user_password takes
    no password argument."""
    link = _share(password_hash="$2b$12$hash")
    with patch.object(mcp_router.share_router, "create_share_link", return_value=link) as created:
        with patch("apps.api.routers.mcp.settings") as s:
            s.frontend_url = "https://x.test"
            out = mcp_router.share_file(asset_id=str(uuid.uuid4()), password="hunter2")
    assert created.call_args.kwargs["body"].password == "hunter2"
    assert out["password_protected"] is True
    assert "hunter2" not in str(out)


# ── Listing and revoking ─────────────────────────────────────────────────────

def test_list_shares_needs_exactly_one_target(as_admin):
    """Both would silently answer about one of them; neither would answer about
    everything, which is what list_project_shares is for."""
    with pytest.raises(ValueError, match="exactly one"):
        mcp_router.list_shares()
    with pytest.raises(ValueError, match="exactly one"):
        mcp_router.list_shares(asset_id=str(uuid.uuid4()), folder_id=str(uuid.uuid4()))


def test_list_shares_reports_the_settings_that_decide_exposure(as_admin):
    """Before re-sharing, the question is what the live link already allows."""
    link = _share(token="t1", asset_id=uuid.uuid4(), allow_download=True)
    with patch.object(mcp_router.share_router, "list_share_links", return_value=[link]):
        with patch("apps.api.routers.mcp.settings") as s:
            s.frontend_url = "https://x.test"
            out = mcp_router.list_shares(asset_id=str(uuid.uuid4()))
    assert out[0]["allow_download"] is True
    assert out[0]["url"] == "https://x.test/share/t1"


def test_revoke_share_accepts_the_whole_url_it_handed_out(as_admin):
    """share_file returns a URL, so a URL is what an agent has to revoke with.
    Demanding the bare token would fail on the obvious input."""
    with patch.object(mcp_router.share_router, "revoke_share_link") as revoked:
        out = mcp_router.revoke_share("https://x.test/share/abc123")
    assert revoked.call_args.kwargs["token"] == "abc123"
    assert out == {"token": "abc123", "revoked": True}


def test_revoke_share_still_accepts_a_bare_token(as_admin):
    with patch.object(mcp_router.share_router, "revoke_share_link") as revoked:
        mcp_router.revoke_share("abc123")
    assert revoked.call_args.kwargs["token"] == "abc123"
