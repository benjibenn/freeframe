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
    assert out["total_matched"] == 1
    assert out["truncated"] is False
    assert out["briefs"][0]["home_project_id"] == str(wanted)


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


# ── Editing and closing ──────────────────────────────────────────────────────

def _filed(**over):
    """A brief as get_submission_link hands it back.

    MagicMock invents any attribute asked of it, so the fields update_brief merges
    from have to carry real values or a test passes on a mock comparing equal to
    itself.
    """
    link = _link(**over)
    link.instructions = over.get("instructions", "Deliver by Friday")
    link.expires_at = over.get("expires_at")
    return link


def test_update_brief_keeps_every_field_you_did_not_pass(as_admin):
    """The endpoint behind this assigns the whole record from the body it is given.

    So a rename that sent nothing but a title would null the instructions, drop the
    expiry and strip the brief out of the tree — data loss the caller never asked
    for and would not see until they went looking for the brief.
    """
    folder = uuid.uuid4()
    current = _filed(home_folder_id=folder)
    current.expires_at = datetime(2026, 12, 1, tzinfo=timezone.utc)
    with patch.object(
        mcp_router.submissions_router, "get_submission_link", return_value=current
    ):
        with patch.object(
            mcp_router.submissions_router, "update_submission_link", return_value=_link()
        ) as upd:
            mcp_router.update_brief(link_id=str(current.id), title="Renamed")
    body = upd.call_args.kwargs["body"]
    assert body.title == "Renamed"
    assert body.instructions == "Deliver by Friday"
    assert body.home_project_id == current.home_project_id
    assert body.home_folder_id == folder
    assert body.expires_at == current.expires_at


def test_update_brief_does_not_carry_a_folder_into_a_new_project(as_admin):
    """A folder lives inside exactly one project, so it cannot follow a brief out.

    Keeping the old id would file the brief under a folder its new project does not
    own — the one outcome a caller asking for a move definitely did not want.
    """
    current = _filed(home_folder_id=uuid.uuid4())
    destination = uuid.uuid4()
    with patch.object(
        mcp_router.submissions_router, "get_submission_link", return_value=current
    ):
        with patch.object(
            mcp_router.submissions_router, "update_submission_link", return_value=_link()
        ) as upd:
            mcp_router.update_brief(
                link_id=str(current.id), home_project_id=str(destination)
            )
    body = upd.call_args.kwargs["body"]
    assert body.home_project_id == destination
    assert body.home_folder_id is None


def test_update_brief_clears_instructions_with_an_empty_string(as_admin):
    """Omitting a field has to mean "leave it alone", so removing needs its own signal."""
    current = _filed()
    with patch.object(
        mcp_router.submissions_router, "get_submission_link", return_value=current
    ):
        with patch.object(
            mcp_router.submissions_router, "update_submission_link", return_value=_link()
        ) as upd:
            mcp_router.update_brief(link_id=str(current.id), instructions="")
    assert upd.call_args.kwargs["body"].instructions is None


def test_update_brief_on_an_unfiled_brief_says_what_to_do(as_admin):
    """Legacy links can be filed nowhere.

    Letting that reach pydantic produces "home_project_id: field required", which
    reads as a bug in the tool rather than something the caller can fix.
    """
    current = _filed()
    current.home_project_id = None
    with patch.object(
        mcp_router.submissions_router, "get_submission_link", return_value=current
    ):
        with pytest.raises(ValueError, match="pass home_project_id"):
            mcp_router.update_brief(link_id=str(current.id), title="Renamed")


def test_delete_brief_says_the_submitted_work_survives(as_admin):
    """Closing a brief is a soft delete; the uploads outlive it.

    An agent that reports a bare "deleted" leaves the user believing the editors'
    files went with it, which is the sort of thing people restore from backups over.
    """
    result = MagicMock()
    result.updated = 2
    with patch.object(
        mcp_router.submissions_router, "bulk_delete_submission_links", return_value=result
    ):
        out = mcp_router.delete_brief(link_ids=[str(uuid.uuid4()), str(uuid.uuid4())])
    assert out["deleted"] == 2
    assert "retained" in out["note"]


def test_delete_brief_reports_partial_deletes_honestly(as_admin):
    """Already-closed ids are skipped, not failed — same as bulk-refile.

    Echoing len(link_ids) would claim to have closed briefs that were never open.
    """
    result = MagicMock()
    result.updated = 1
    with patch.object(
        mcp_router.submissions_router, "bulk_delete_submission_links", return_value=result
    ):
        out = mcp_router.delete_brief(
            link_ids=[str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())]
        )
    assert out["deleted"] == 1
    assert out["requested"] == 3


def test_delete_brief_rejects_an_empty_selection(as_admin):
    with pytest.raises(ValueError, match="at least one brief id"):
        mcp_router.delete_brief(link_ids=[])


# ── Folders ──────────────────────────────────────────────────────────────────

def _node(name, children=None, folder_id=None):
    """A FolderTreeNode stand-in. `name` is reserved by MagicMock, so set it after."""
    n = MagicMock(id=folder_id or uuid.uuid4(), children=children or [])
    n.name = name
    return n


def _folder(name, folder_id=None, parent_id=None, project_id=None):
    f = MagicMock(
        id=folder_id or uuid.uuid4(),
        project_id=project_id or uuid.uuid4(),
        parent_id=parent_id,
        item_count=0,
    )
    f.name = name
    return f


def test_create_folder_reuses_the_part_of_the_path_that_exists(as_admin):
    """Re-running the same path must not fork a second "Stokora" beside the first.

    An agent filing a batch of briefs calls this once per destination and cannot
    be trusted to remember which folders it already made.
    """
    stokora = _node("Stokora")
    tree = [_node("Phones", children=[stokora])]
    made = _folder("iPhone 17e")
    with patch.object(mcp_router.folders_router, "get_folder_tree", return_value=tree), \
         patch.object(mcp_router.folders_router, "create_folder", return_value=made) as create:
        out = mcp_router.create_folder(
            project_id=str(uuid.uuid4()), path="Phones/Stokora/iPhone 17e"
        )

    assert create.call_count == 1
    assert create.call_args.kwargs["body"].parent_id == stokora.id
    assert out["created"] == ["iPhone 17e"]
    assert out["id"] == str(made.id)


def test_create_folder_chains_each_new_folder_under_the_last(as_admin):
    """Only the first missing segment has a parent in the tree we read.

    The rest are parented to folders that did not exist when that tree was
    fetched, so re-reading it would find nothing and file them all at the root.
    """
    first = _folder("Stokora")
    second = _folder("iPhone 17e")
    phones = _node("Phones")
    with patch.object(mcp_router.folders_router, "get_folder_tree", return_value=[phones]), \
         patch.object(
             mcp_router.folders_router, "create_folder", side_effect=[first, second]
         ) as create:
        out = mcp_router.create_folder(
            project_id=str(uuid.uuid4()), path="Phones/Stokora/iPhone 17e"
        )

    parents = [c.kwargs["body"].parent_id for c in create.call_args_list]
    assert parents == [phones.id, first.id]
    assert out["created"] == ["Stokora", "iPhone 17e"]


def test_create_folder_refuses_an_ambiguous_segment(as_admin):
    """Nothing stops two siblings sharing a name, and picking one silently
    would file briefs into a tree the caller never looked at."""
    tree = [_node("Phones"), _node("phones")]
    with patch.object(mcp_router.folders_router, "get_folder_tree", return_value=tree):
        with pytest.raises(ValueError, match="parent_folder_id"):
            mcp_router.create_folder(project_id=str(uuid.uuid4()), path="Phones/Stokora")


def test_create_folder_resolves_the_path_under_a_given_parent(as_admin):
    """parent_folder_id is how a caller disambiguates; the path must start there."""
    stokora = _node("Stokora")
    phones = _node("Phones", children=[stokora])
    made = _folder("iPhone 17e")
    with patch.object(mcp_router.folders_router, "get_folder_tree", return_value=[phones]), \
         patch.object(mcp_router.folders_router, "create_folder", return_value=made) as create:
        mcp_router.create_folder(
            project_id=str(uuid.uuid4()),
            path="Stokora/iPhone 17e",
            parent_folder_id=str(phones.id),
        )
    assert create.call_count == 1
    assert create.call_args.kwargs["body"].parent_id == stokora.id


def test_create_folder_rejects_an_empty_path(as_admin):
    with pytest.raises(ValueError, match="at least one folder"):
        mcp_router.create_folder(project_id=str(uuid.uuid4()), path="  /  ")


def test_update_folder_leaves_the_parent_alone_when_only_renaming(as_admin):
    """The endpoint reads model_fields_set, so a parent_id we did not mean to send
    would move the folder to the project root as a side effect of a rename."""
    with patch.object(
        mcp_router.folders_router, "update_folder", return_value=_folder("Renamed")
    ) as update:
        mcp_router.update_folder(folder_id=str(uuid.uuid4()), name="Renamed")
    assert "parent_id" not in update.call_args.kwargs["body"].model_fields_set


def test_update_folder_moves_to_the_root_on_an_empty_string(as_admin):
    """"" is the only way to say "no parent"; omitting it means "don't touch"."""
    with patch.object(
        mcp_router.folders_router, "update_folder", return_value=_folder("Stokora")
    ) as update:
        mcp_router.update_folder(folder_id=str(uuid.uuid4()), parent_folder_id="")
    body = update.call_args.kwargs["body"]
    assert "parent_id" in body.model_fields_set and body.parent_id is None


def test_update_folder_rejects_a_call_that_changes_nothing(as_admin):
    with pytest.raises(ValueError, match="nothing to change"):
        mcp_router.update_folder(folder_id=str(uuid.uuid4()))


def test_delete_folder_reports_how_to_undo_itself(as_admin):
    """The delete cascades over subfolders and assets, so the caller has to know
    it is reversible — and needs the id to reverse it with."""
    fid = uuid.uuid4()
    with patch.object(mcp_router.folders_router, "delete_folder", return_value=None):
        out = mcp_router.delete_folder(folder_id=str(fid))
    assert out["deleted"] == str(fid)
    assert "restore_folder" in out["note"]


def test_restore_folder_undoes_a_delete(as_admin):
    fid = uuid.uuid4()
    with patch.object(
        mcp_router.folders_router, "restore_folder", return_value={"ok": True}
    ) as restore:
        out = mcp_router.restore_folder(folder_id=str(fid))
    assert restore.call_args.kwargs["folder_id"] == fid
    assert out == {"restored": str(fid)}


def test_list_deleted_folders_omits_deleted_assets(as_admin):
    """Trash carries assets too, and MCP exposes no asset tools — listing them
    would spend the caller's context on ids no tool here can act on."""
    trash = {
        "folders": [{"id": str(uuid.uuid4()), "name": "Stokora"}],
        "assets": [{"id": str(uuid.uuid4()), "name": "hook.mp4"}],
    }
    with patch.object(mcp_router.folders_router, "list_trash", return_value=trash):
        out = mcp_router.list_deleted_folders(project_id=str(uuid.uuid4()))
    assert out == trash["folders"]


def test_list_deleted_folders_rejects_a_limit_the_endpoint_would_reject(as_admin):
    """The Query(le=100) bound is not enforced when the function is called directly."""
    with pytest.raises(ValueError, match="between 1 and 100"):
        mcp_router.list_deleted_folders(project_id=str(uuid.uuid4()), limit=500)


# ── Submitted files ──────────────────────────────────────────────────────────

def _submission(files, display_name=None, user_name="Ed", user_email="ed@x.io"):
    s = MagicMock(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        display_name=display_name,
        user_name=user_name,
        user_email=user_email,
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        files=files,
    )
    return s


def _sub_file(name):
    f = MagicMock(asset_id=uuid.uuid4())
    f.name = name
    return f


def _asset(name, folder_id=None, project_id=None):
    a = MagicMock(
        id=uuid.uuid4(),
        project_id=project_id or uuid.uuid4(),
        folder_id=folder_id,
        asset_type=MagicMock(value="video"),
    )
    a.name = name
    return a


def test_list_submitted_files_exposes_the_asset_id_every_file_tool_needs(as_admin):
    """rename/move/delete/review all key off asset_id.

    If this tool reported only filenames, an agent asked to rename a file would
    have nothing to address it by and would have to guess.
    """
    one, two = _sub_file("cut_a.mp4"), _sub_file("cut_b.mp4")
    with patch.object(
        mcp_router.submissions_router, "list_submissions",
        return_value=[_submission([one, two])],
    ):
        out = mcp_router.list_submitted_files(brief_id=str(uuid.uuid4()))

    assert [f["asset_id"] for f in out[0]["files"]] == [str(one.asset_id), str(two.asset_id)]
    assert [f["name"] for f in out[0]["files"]] == ["cut_a.mp4", "cut_b.mp4"]


def test_rename_file_sends_only_the_name(as_admin):
    """update_asset applies model_dump(exclude_unset=True).

    Passing a fully-populated AssetUpdate would blank the description, rating and
    due date of a file whose name is the only thing being changed.
    """
    with patch.object(
        mcp_router.assets_router, "update_asset", return_value=_asset("final.mp4"),
    ) as update:
        mcp_router.rename_file(asset_id=str(uuid.uuid4()), name="  final.mp4  ")

    body = update.call_args.kwargs["body"]
    assert body.model_fields_set == {"name"}
    assert body.name == "final.mp4"


def test_rename_file_rejects_a_blank_name(as_admin):
    """A whitespace-only rename would leave an unclickable, unnameable row."""
    with pytest.raises(ValueError, match="must not be blank"):
        mcp_router.rename_file(asset_id=str(uuid.uuid4()), name="   ")


def test_move_file_treats_an_empty_destination_as_the_project_root(as_admin):
    """The root is not a folder and has no id, so "" is how a caller names it."""
    with patch.object(mcp_router.folders_router, "move_asset") as move:
        out = mcp_router.move_file(asset_id=str(uuid.uuid4()), folder_id="")

    assert move.call_args.kwargs["body"].folder_id is None
    assert out["folder_id"] is None


def test_review_file_reviews_the_newest_version(as_admin):
    """Versions come back newest-first.

    Approving anything but the head would sign off a cut the editor has already
    replaced, and the uploader would be emailed about the wrong one.
    """
    newest, older = MagicMock(id=uuid.uuid4()), MagicMock(id=uuid.uuid4())
    with patch.object(
        mcp_router.assets_router, "list_asset_versions", return_value=[newest, older],
    ), patch.object(mcp_router.approvals_router, "approve_asset") as approve:
        out = mcp_router.review_file(
            asset_id=str(uuid.uuid4()), decision="Approve", note="ship it"
        )

    assert approve.call_args.kwargs["body"].version_id == newest.id
    assert approve.call_args.kwargs["body"].note == "ship it"
    assert out["decision"] == "approve"


def test_review_file_refuses_an_unknown_decision(as_admin):
    """Anything other than approve/reject must not fall through to one of them —
    a review is emailed to the uploader and cannot be taken back."""
    with pytest.raises(ValueError, match="approve"):
        mcp_router.review_file(asset_id=str(uuid.uuid4()), decision="maybe")


def test_review_file_refuses_a_file_with_no_uploaded_version(as_admin):
    """ApprovalCreate requires a version_id; there is nothing to review yet."""
    with patch.object(
        mcp_router.assets_router, "list_asset_versions", return_value=[],
    ):
        with pytest.raises(ValueError, match="no uploaded version"):
            mcp_router.review_file(asset_id=str(uuid.uuid4()), decision="reject")


def test_delete_file_reports_how_to_undo(as_admin):
    """The delete is soft, so the caller is told rather than left to assume
    the file is gone."""
    with patch.object(mcp_router.assets_router, "delete_asset"):
        out = mcp_router.delete_file(asset_id=str(uuid.uuid4()))

    assert "restore_file" in out["note"]


def test_list_folder_contents_passes_every_list_assets_default_explicitly(as_admin):
    """list_assets declares its options as Query(...) objects.

    Called directly rather than through FastAPI, an omitted argument stays a
    Query instance — which is truthy, so include_failed would silently switch on
    and the folder would show broken uploads.
    """
    pid = uuid.uuid4()
    with patch.object(mcp_router.folders_router, "get_folder_tree", return_value=[]), \
         patch.object(mcp_router.assets_router, "list_assets", return_value=[]) as listing, \
         patch.object(mcp_router.submissions_router, "list_submission_links", return_value=[]):
        mcp_router.list_folder_contents(project_id=str(pid))

    kwargs = listing.call_args.kwargs
    assert kwargs["include_failed"] is False
    assert kwargs["exclude_archived"] is False
    assert kwargs["tag"] is None and kwargs["frame_label"] is None
    assert kwargs["folder_id"] == "root"


def test_list_folder_contents_only_returns_briefs_filed_in_that_folder(as_admin):
    """A brief's home folder is what files it; listing the project's briefs in
    every folder would make the folder view meaningless."""
    pid, fid = uuid.uuid4(), uuid.uuid4()
    node = _node("Stokora", folder_id=fid)
    here = _link(title="In here", home_project_id=pid, home_folder_id=fid)
    elsewhere = _link(title="Elsewhere", home_project_id=pid, home_folder_id=uuid.uuid4())
    with patch.object(mcp_router.folders_router, "get_folder_tree", return_value=[node]), \
         patch.object(mcp_router.assets_router, "list_assets", return_value=[]), \
         patch.object(
             mcp_router.submissions_router, "list_submission_links",
             return_value=[here, elsewhere],
         ):
        out = mcp_router.list_folder_contents(project_id=str(pid), folder_id=str(fid))

    assert [b["title"] for b in out["briefs"]] == ["In here"]


def test_list_briefs_says_so_when_it_truncates(as_admin):
    """A silently cut list reads as the whole set.

    A tenant holds hundreds of briefs; an agent told it saw 50 of 550 narrows its
    search, one handed 50 rows concludes the rest do not exist.
    """
    links = [_link(title=f"Brief {i}") for i in range(12)]
    with patch.object(
        mcp_router.submissions_router, "list_submission_links", return_value=links,
    ):
        out = mcp_router.list_briefs(limit=5)

    assert out["total_matched"] == 12
    assert out["returned"] == 5
    assert out["truncated"] is True
    assert len(out["briefs"]) == 5


def test_list_briefs_matches_title_or_folder_path_case_insensitively(as_admin):
    """Ben types "stokora"; the folder is "Stokora". Matching the path as well as
    the title is what makes "show me the Stokora briefs" work."""
    by_title = _link(title="Stokora hero cut")
    by_path = _link(title="Untitled", home_path="Phones/Stokora")
    miss = _link(title="Something else", home_path="Phones/Other")
    with patch.object(
        mcp_router.submissions_router, "list_submission_links",
        return_value=[by_title, by_path, miss],
    ):
        out = mcp_router.list_briefs(query="STOKORA")

    assert out["total_matched"] == 2
    assert {b["title"] for b in out["briefs"]} == {"Stokora hero cut", "Untitled"}


def test_list_deleted_briefs_rejects_an_out_of_range_limit(as_admin):
    """The endpoint's Query(le=100) never runs on a direct call, so the bound is
    enforced here or not at all."""
    with pytest.raises(ValueError, match="between 1 and 100"):
        mcp_router.list_deleted_briefs(limit=500)


# ── Task pipeline ────────────────────────────────────────────────────────────

def _stage(**over):
    s = MagicMock()
    s.id = over.get("id", uuid.uuid4())
    s.name = over.get("name", "In Progress")
    s.position = over.get("position", 1)
    s.color = over.get("color", "#00ff00")
    s.is_default = over.get("is_default", False)
    return s


def _owner(**over):
    u = MagicMock()
    u.id = over.get("id", uuid.uuid4())
    u.name = over.get("name", "Jamie Cho")
    u.email = over.get("email", "jamie@example.com")
    return u


def _brief_task(**over):
    item = MagicMock()
    item.id = over.get("id", uuid.uuid4())
    item.title = over.get("title", "Spring campaign")
    item.taxonomy_path = over.get("taxonomy_path", "ecom/Phones")
    item.task_stage_id = over.get("task_stage_id")
    item.assignee_id = over.get("assignee_id")
    item.assignee_name = over.get("assignee_name")
    item.submit_url = over.get("submit_url", "https://x.test/submit/tok")
    item.created_at = over.get("created_at", datetime.now(timezone.utc))
    return item


def test_list_task_stages_reports_board_order(as_admin):
    stages = [_stage(name="Pending", position=1), _stage(name="Done", position=2)]
    with patch.object(mcp_router.tasks_router, "list_task_stages", return_value=stages):
        out = mcp_router.list_task_stages()
    assert [s["name"] for s in out] == ["Pending", "Done"]


def test_list_assignable_users_reports_id_name_email(as_admin):
    owner = _owner(name="Jamie Cho", email="jamie@example.com")
    with patch.object(mcp_router.users_router, "list_assignable_users", return_value=[owner]):
        out = mcp_router.list_assignable_users()
    assert out == [{"id": str(owner.id), "name": "Jamie Cho", "email": "jamie@example.com"}]


def test_set_brief_task_stage_passes_the_stage_id_through(as_admin):
    stage_id = uuid.uuid4()
    link_id = uuid.uuid4()
    with patch.object(
        mcp_router.tasks_router,
        "set_brief_task_stage",
        return_value=_brief_task(id=link_id, task_stage_id=stage_id),
    ) as moved:
        out = mcp_router.set_brief_task_stage(link_id=str(link_id), task_stage_id=str(stage_id))
    assert moved.call_args.kwargs["link_id"] == link_id
    assert moved.call_args.kwargs["body"].task_stage_id == stage_id
    assert out["task_stage_id"] == str(stage_id)


def test_set_brief_task_stage_null_clears_the_stage(as_admin):
    """Passing null must reach the endpoint as None, not the string "None"."""
    link_id = uuid.uuid4()
    with patch.object(
        mcp_router.tasks_router,
        "set_brief_task_stage",
        return_value=_brief_task(id=link_id, task_stage_id=None),
    ) as moved:
        mcp_router.set_brief_task_stage(link_id=str(link_id), task_stage_id=None)
    assert moved.call_args.kwargs["body"].task_stage_id is None


def test_set_brief_task_stage_surfaces_the_owned_brief_check(as_admin):
    """_owned_brief_or_403 backs this endpoint — a non-owner must see why, not a bare 500."""
    with patch.object(
        mcp_router.tasks_router,
        "set_brief_task_stage",
        side_effect=HTTPException(status_code=404, detail="Request not found"),
    ):
        with pytest.raises(ValueError, match="Request not found"):
            mcp_router.set_brief_task_stage(link_id=str(uuid.uuid4()), task_stage_id=str(uuid.uuid4()))


def test_assign_brief_owner_passes_the_assignee_id_through(as_admin):
    link_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    with patch.object(
        mcp_router.tasks_router,
        "set_brief_assignee",
        return_value=_brief_task(id=link_id, assignee_id=owner_id, assignee_name="Jamie Cho"),
    ) as assigned:
        out = mcp_router.assign_brief_owner(link_id=str(link_id), assignee_id=str(owner_id))
    assert assigned.call_args.kwargs["link_id"] == link_id
    assert assigned.call_args.kwargs["body"].assignee_id == owner_id
    assert out["assignee_name"] == "Jamie Cho"


def test_assign_brief_owner_null_unassigns(as_admin):
    link_id = uuid.uuid4()
    with patch.object(
        mcp_router.tasks_router,
        "set_brief_assignee",
        return_value=_brief_task(id=link_id, assignee_id=None),
    ) as assigned:
        mcp_router.assign_brief_owner(link_id=str(link_id), assignee_id=None)
    assert assigned.call_args.kwargs["body"].assignee_id is None


def test_assign_brief_owner_is_platform_admin_only(as_admin):
    """set_brief_assignee itself calls require_platform_admin — assigning ownership,
    unlike moving a stage, has no self-service path. This asserts the 403 reaches
    the caller as an actionable message, same guarantee as every other write tool."""
    with patch.object(
        mcp_router.tasks_router,
        "set_brief_assignee",
        side_effect=HTTPException(status_code=403, detail="Platform admin required"),
    ):
        with pytest.raises(ValueError, match="Platform admin required"):
            mcp_router.assign_brief_owner(link_id=str(uuid.uuid4()), assignee_id=str(uuid.uuid4()))


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


# ── Titles built from parts ───────────────────────────────────────────────────
#
# The playbook reads persona, lens, hook and format out of a brief's title by
# position (parseTitle, apps/web/lib/playbook.ts). A hand-typed title that misses
# a slot makes all four read as null, so the brief sits in the coverage matrix
# with no persona and no lens. These tests pin that an agent cannot create one.

def _created(as_admin):
    """Patch the create route and hand back the mock so the body can be read."""
    return patch.object(
        mcp_router.submissions_router, "create_submission_link", return_value=_link()
    )


def test_create_brief_assembles_the_title_from_its_parts(as_admin):
    with _created(as_admin) as create:
        mcp_router.create_brief(
            home_project_id=str(uuid.uuid4()),
            sku="iPhone 17 Pro Max",
            persona="Frugal Phone Buyer",
            lens="Fear",
            hook="Battery dies by 3pm",
            ad_format="Static",
            date="20260910",
        )
    assert create.call_args.kwargs["body"].title == (
        "20260910 - iPhone 17 Pro Max - Frugal Phone Buyer - Fear - Battery dies by 3pm - Static"
    )


def test_create_brief_tags_the_persona_and_angle_it_was_given(as_admin):
    """Angle appears nowhere in the title, so without this the brief lands in the
    matrix's "—" angle column however well it is titled."""
    with _created(as_admin) as create:
        mcp_router.create_brief(
            home_project_id=str(uuid.uuid4()),
            sku="x", persona="Frugal Phone Buyer", lens="Fear", hook="Battery",
            ad_format="Static", angle="A28 Battery anxiety",
        )
    body = create.call_args.kwargs["body"]
    assert body.persona_label == "Frugal Phone Buyer"
    assert body.angle_label == "A28 Battery anxiety"


def test_create_brief_still_takes_a_whole_title(as_admin):
    """The escape hatch stays: not every brief follows the convention."""
    with _created(as_admin) as create:
        mcp_router.create_brief(home_project_id=str(uuid.uuid4()), title="Spring campaign")
    assert create.call_args.kwargs["body"].title == "Spring campaign"


def test_create_brief_refuses_a_title_and_its_parts_together(as_admin):
    """Silently ignoring the parts would create a brief whose title and labels
    disagree about what it is."""
    with _created(as_admin) as create:
        with pytest.raises(ValueError, match="hook"):
            mcp_router.create_brief(
                home_project_id=str(uuid.uuid4()), title="Spring campaign", hook="Battery",
            )
    create.assert_not_called()


def test_create_brief_refuses_an_incomplete_set_of_parts(as_admin):
    """Named refusal before anything exists — a half-built title would otherwise
    strand a live submit URL that no one was told about."""
    with _created(as_admin) as create:
        with pytest.raises(ValueError, match="lens"):
            mcp_router.create_brief(
                home_project_id=str(uuid.uuid4()), sku="x", persona="P", hook="H", ad_format="Static",
            )
    create.assert_not_called()


def test_create_brief_says_what_it_needs_when_given_nothing(as_admin):
    with pytest.raises(ValueError, match="title"):
        mcp_router.create_brief(home_project_id=str(uuid.uuid4()))


def test_create_brief_refuses_a_separator_inside_a_part(as_admin):
    """" - " in a part shifts every later slot, so lens would be read as the hook."""
    with _created(as_admin) as create:
        with pytest.raises(ValueError, match="persona"):
            mcp_router.create_brief(
                home_project_id=str(uuid.uuid4()),
                sku="x", persona="Frugal - Buyer", lens="Fear", hook="Battery", ad_format="Static",
            )
    create.assert_not_called()


# ── Source links on submitted work ────────────────────────────────────────────

def test_submit_work_carries_the_source_link(as_admin):
    """An agent's submission records its source like a browser upload does.

    submit-work/from-url is the browser's initiate → presign → complete collapsed
    into one call, so it must not be the one way in that leaves a version with no
    trace of what it was made from.
    """
    with patch.object(
        mcp_router.submissions_router, "submit_work_from_url", return_value=MagicMock()
    ) as submitted:
        mcp_router.submit_work(
            link_id=str(uuid.uuid4()),
            url="https://cdn.example.com/hook1.png",
            source_url="https://canva.com/design/abc",
        )
    assert submitted.call_args.kwargs["body"].source_url == "https://canva.com/design/abc"


def test_submit_work_refuses_a_blank_source_link(as_admin):
    with patch.object(mcp_router.submissions_router, "submit_work_from_url") as submitted:
        with pytest.raises(ValueError, match="source_url"):
            mcp_router.submit_work(
                link_id=str(uuid.uuid4()),
                url="https://cdn.example.com/hook1.png",
                source_url="   ",
            )
    submitted.assert_not_called()
