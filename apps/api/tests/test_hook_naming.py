"""Auto-numbering of submitter uploads as "Hook N".

The rules these tests pin down are product rules, not implementation details:
a submitter never names their own uploads, each submitter's sequence is private
to their own project, and revising a hook must not burn a new number.
"""
import uuid
from unittest.mock import MagicMock, patch

from apps.api.services.hook_naming import next_hook_name, next_hook_number


# ── The numbering rule ─────────────────────────────────────────────────────────

def test_first_upload_is_hook_1():
    assert next_hook_number([]) == 1


def test_next_number_follows_the_hooks_already_uploaded():
    # Ben's rule: 4 hooks in the project => the next new file is Hook 5.
    assert next_hook_number(["Hook 1", "Hook 2", "Hook 3", "Hook 4"]) == 5


def test_a_deleted_middle_hook_does_not_get_reused():
    # Counting would hand out "Hook 3" again and two different videos would end
    # up sharing a name in the reviewer's list. Max+1 keeps the gap a gap.
    assert next_hook_number(["Hook 1", "Hook 2", "Hook 4"]) == 5


def test_numbering_ignores_assets_that_are_not_hooks():
    # Owners can drop reference material into a request project; it must not
    # push the submitter's hook numbering along.
    assert next_hook_number(["reference cut.mp4", "Hook 1", "brief"]) == 2


def test_hook_prefix_is_matched_case_and_space_insensitively():
    # Hooks renamed by hand (or numbered before this rule existed) still count,
    # otherwise a rename would silently restart the sequence at 1.
    assert next_hook_number(["hook 1", "HOOK  2"]) == 3


def test_hook_like_names_with_a_suffix_do_not_count():
    # "Hook 7 final" is a human-chosen title, not a slot in the sequence.
    assert next_hook_number(["Hook 7 final", "Hook 1"]) == 2


# ── The DB wrapper ─────────────────────────────────────────────────────────────

def test_next_hook_name_only_counts_live_assets_in_that_project():
    db = MagicMock()
    db.query.return_value = db
    db.filter.return_value = db
    db.all.return_value = [("Hook 1",), ("Hook 2",)]

    assert next_hook_name(db, uuid.uuid4()) == "Hook 3"
    # Two predicates: scoped to the project AND excluding soft-deleted assets.
    # Without the project scope one submitter's uploads would number off another's.
    assert len(db.filter.call_args[0]) == 2


# ── The upload endpoint ────────────────────────────────────────────────────────

def _initiate_body(project_id):
    return {
        "project_id": str(project_id),
        "asset_name": "my cool video",
        "original_filename": "clip.jpg",
        "mime_type": "image/jpeg",
        "file_size_bytes": 1024,
    }


def _mock_project(submission_link_id):
    project = MagicMock()
    project.id = uuid.uuid4()
    project.submission_link_id = submission_link_id
    project.deleted_at = None
    return project


def _wire_db(mock_db, added, first_results):
    mock_db.query.return_value = mock_db
    mock_db.filter.return_value = mock_db
    mock_db.order_by.return_value = mock_db
    mock_db.with_for_update.return_value = mock_db
    mock_db.first.side_effect = first_results
    mock_db.add.side_effect = added.append

    def assign_ids():
        # Stand in for the DB-side uuid defaults, which the endpoint reads back
        # after flush() to build the S3 key and the response.
        for obj in added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    mock_db.flush.side_effect = assign_ids


def _created_asset(added):
    from apps.api.models.asset import Asset

    return next(obj for obj in added if isinstance(obj, Asset))


@patch("apps.api.routers.upload.create_multipart_upload", return_value="upload-123")
@patch("apps.api.routers.upload.require_project_role")
@patch("apps.api.services.hook_naming.next_hook_name", return_value="Hook 5")
def test_submission_project_upload_is_renamed_to_the_next_hook(
    mock_next_hook_name, mock_require_role, mock_create_upload, client, mock_db, auth_headers
):
    project = _mock_project(uuid.uuid4())  # provisioned by a request
    added = []
    # project lookup, CF-lineage link lookup, locked project, latest version
    _wire_db(mock_db, added, [project, None, project, None])

    res = client.post("/upload/initiate", json=_initiate_body(project.id), headers=auth_headers)

    assert res.status_code == 200, res.text
    # Naming is server-side: whatever the client sent is discarded, so a
    # submitter can't opt out by posting their own asset_name.
    assert _created_asset(added).name == "Hook 5"
    # The project row is locked first, otherwise a multi-file selection (one
    # concurrent initiate per file) would name every file the same hook.
    mock_db.with_for_update.assert_called_once()


@patch("apps.api.routers.upload.create_multipart_upload", return_value="upload-123")
@patch("apps.api.routers.upload.require_project_role")
@patch("apps.api.services.hook_naming.next_hook_name", return_value="Hook 5")
def test_ordinary_project_upload_keeps_the_client_supplied_name(
    mock_next_hook_name, mock_require_role, mock_create_upload, client, mock_db, auth_headers
):
    project = _mock_project(None)  # standalone project — naming stays the user's
    added = []
    _wire_db(mock_db, added, [project, None])

    res = client.post("/upload/initiate", json=_initiate_body(project.id), headers=auth_headers)

    assert res.status_code == 200, res.text
    assert _created_asset(added).name == "my cool video"
    mock_next_hook_name.assert_not_called()
