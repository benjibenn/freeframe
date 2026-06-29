"""Tests for comment visibility tiers (public / internal / admin).

WHY these matter: comment visibility is a security boundary, not a UI nicety.
- Guests (share-link viewers) must never receive `internal` or `admin` comments.
- Authenticated team members (editor/reviewer/viewer/owner) must never receive
  `admin` comments.
- Only platform admins (superadmin OR subadmin) may see `admin` comments.

The rule lives in one helper so the read paths cannot drift apart. These tests
encode the rule directly; endpoint tests below prove the write-side guard and
that replies inherit their parent's tier.
"""
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.api.services.permissions import visible_visibilities


def _guest():
    return None


def _team_member():
    # Authenticated, but no elevated platform role.
    return SimpleNamespace(is_superadmin=False, is_subadmin=False)


def _superadmin():
    return SimpleNamespace(is_superadmin=True, is_subadmin=False)


def _subadmin():
    return SimpleNamespace(is_superadmin=False, is_subadmin=True)


def test_guest_sees_only_public():
    assert visible_visibilities(_guest()) == ["public"]


def test_team_member_sees_public_and_internal_but_not_admin():
    allowed = visible_visibilities(_team_member())
    assert "public" in allowed
    assert "internal" in allowed
    assert "admin" not in allowed


def test_superadmin_sees_admin():
    assert "admin" in visible_visibilities(_superadmin())


def test_subadmin_sees_admin():
    # A delegated sub-admin is a platform admin for visibility purposes.
    assert "admin" in visible_visibilities(_subadmin())


# ── Write-side guard: you cannot create a comment you could not see ──────────────


@patch("apps.api.routers.comments._build_comment_response")
@patch("apps.api.routers.comments.require_asset_access")
def test_create_comment_rejects_admin_visibility_for_non_admin(
    mock_access, mock_build, client, mock_db, test_user, auth_headers,
):
    """A team member must not be able to author an admin-only comment — otherwise
    they could plant a comment they themselves are not allowed to read back."""
    test_user.is_superadmin = False
    test_user.is_subadmin = False
    mock_db.first.return_value = MagicMock()  # asset exists

    resp = client.post(
        f"/assets/{uuid.uuid4()}/comments",
        json={"version_id": str(uuid.uuid4()), "body": "secret", "visibility": "admin"},
        headers=auth_headers,
    )

    assert resp.status_code == 403
    mock_build.assert_not_called()  # bailed before doing any work


@patch("apps.api.routers.comments._build_comment_response")
@patch("apps.api.routers.comments._create_mentions")
@patch("apps.api.routers.comments.require_asset_access")
def test_create_comment_allows_internal_for_team_member(
    mock_access, mock_mentions, mock_build, client, mock_db, test_user, auth_headers,
):
    """The guard must not over-block: a team member can still post `internal`."""
    test_user.is_superadmin = False
    test_user.is_subadmin = False
    mock_db.first.return_value = MagicMock()  # asset exists

    resp = client.post(
        f"/assets/{uuid.uuid4()}/comments",
        json={"version_id": str(uuid.uuid4()), "body": "team note", "visibility": "internal"},
        headers=auth_headers,
    )

    # Guard let it through to the build step (response_model serialization of the
    # mock is out of scope here; what matters is we did NOT 403).
    assert resp.status_code != 403
    mock_build.assert_called_once()


@patch("apps.api.routers.comments._build_comment_response")
@patch("apps.api.routers.comments._create_mentions")
@patch("apps.api.routers.comments.require_asset_access")
def test_reply_inherits_parent_visibility(
    mock_access, mock_mentions, mock_build, client, mock_db, test_user, auth_headers,
):
    """A reply to an admin comment must itself be admin-tier — otherwise an
    admin thread leaks through a public-tier reply nested under it."""
    from apps.api.models.comment import Comment

    parent = MagicMock()
    parent.visibility = "admin"
    parent.version_id = uuid.uuid4()
    parent.author_id = uuid.uuid4()
    parent.id = uuid.uuid4()
    # The same lookup serves as both the asset fetch and the parent fetch.
    mock_db.first.return_value = parent

    client.post(
        f"/assets/{uuid.uuid4()}/comments/{uuid.uuid4()}/replies",
        json={"version_id": str(uuid.uuid4()), "body": "ack"},
        headers=auth_headers,
    )

    # Inspect the Comment that was persisted (recorded before response serialization).
    added = [call.args[0] for call in mock_db.add.call_args_list]
    replies = [a for a in added if isinstance(a, Comment)]
    assert len(replies) == 1
    assert replies[0].visibility == "admin"
