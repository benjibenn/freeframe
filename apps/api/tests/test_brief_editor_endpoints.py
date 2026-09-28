"""Tests for assigning editors to a brief and moving their individual statuses.

Intent encoded:
- assignment is one-way and provisions an upload project, so it must refuse a
  dead brief rather than leave an orphan project pointing at one;
- an editor's status is theirs — moving it must not disturb the brief's own,
  which is the entire reason there are two;
- a non-participant is told the brief does not exist, not that they lack rights.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.models.user import UserStatus


def _user(*, is_superadmin=False, name="Editor"):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.name = name
    u.email = f"{name.replace(' ', '.').lower()}@example.com"
    u.status = UserStatus.active
    u.is_superadmin = is_superadmin
    u.is_subadmin = False
    u.deleted_at = None
    return u


def _link():
    l = MagicMock()
    l.id = uuid.uuid4()
    l.token = "tok-abc"
    l.title = "Static — iPhone 17 Pro Max"
    l.task_stage_id = uuid.uuid4()
    l.assignee_id = None
    l.brief_pdf_s3_key = None
    l.brief_json = None
    # BriefTaskItem.created_at is a required (non-Optional) datetime field, so
    # unlike the fields above this cannot be None: _brief_item's response-model
    # serialization would raise a pydantic ValidationError on any 200-path test.
    l.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # These three MUST be None, not left as auto-created MagicMock attributes.
    # _brief_item resolves the brief's path through folder_paths, which builds a
    # recursive CTE and iterates db.execute(...).all(). A truthy folder id sends
    # it down that road against a mock session and the request 500s. None makes
    # link_home_paths short-circuit with no DB work at all.
    l.home_folder_id = None
    l.home_project_id = None
    l.taxonomy_path = None
    return l


def _client(mock_db, current_user):
    from apps.api.routers.tasks import router
    from apps.api.database import get_db
    from apps.api.middleware.auth import get_current_user

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: current_user
    return TestClient(app, raise_server_exceptions=False)


# ── Assigning ────────────────────────────────────────────────────────────────

def test_a_plain_editor_cannot_assign_anyone(mock_db):
    """Assignment hands out work and provisions a project. Not self-service."""
    link = _link()
    client = _client(mock_db, _user())
    r = client.post(f"/submission-links/{link.id}/editors", json={"user_id": str(uuid.uuid4())})
    assert r.status_code == 403


def test_assigning_to_a_deleted_brief_is_refused_before_provisioning(mock_db):
    """Otherwise a private project is created pointing at a brief that is gone."""
    # side_effect (not return_value) pins this to the link lookup specifically,
    # so a later query cannot silently satisfy it too.
    mock_db.first.side_effect = [None]  # the deleted-aware lookup finds nothing
    client = _client(mock_db, _user(is_superadmin=True, name="Admin"))
    with patch("apps.api.routers.submissions._provision_submission_project") as prov:
        r = client.post(
            f"/submission-links/{uuid.uuid4()}/editors", json={"user_id": str(uuid.uuid4())}
        )
    assert r.status_code == 404
    prov.assert_not_called()


def test_assigning_an_unknown_user_is_refused(mock_db):
    link = _link()
    editor_id = uuid.uuid4()
    # First lookup finds the link; the user lookup finds nobody.
    mock_db.first.side_effect = [link, None]
    client = _client(mock_db, _user(is_superadmin=True, name="Admin"))
    with patch("apps.api.routers.submissions._provision_submission_project") as prov:
        r = client.post(f"/submission-links/{link.id}/editors", json={"user_id": str(editor_id)})
    assert r.status_code == 404
    prov.assert_not_called()


def test_assigning_the_briefs_own_creator_is_allowed(mock_db):
    """An owner testing their own brief is a real case the provisioner already
    handles (it skips the duplicate membership). It must not blow up here."""
    link = _link()
    admin = _user(is_superadmin=True, name="Admin")
    mock_db.first.side_effect = [link, admin]
    mock_db.all.return_value = []
    client = _client(mock_db, admin)
    with patch(
        "apps.api.routers.submissions._provision_submission_project",
        return_value=uuid.uuid4(),
    ) as prov:
        r = client.post(f"/submission-links/{link.id}/editors", json={"user_id": str(admin.id)})
    assert r.status_code == 200
    prov.assert_called_once()


# ── Moving an editor's status ────────────────────────────────────────────────

def test_an_editor_cannot_move_a_co_editors_status(mock_db):
    """404, not 403 — a co-editor's participation is not theirs to discover."""
    link = _link()
    mock_db.first.return_value = link
    client = _client(mock_db, _user())
    r = client.patch(
        f"/submission-links/{link.id}/editors/{uuid.uuid4()}/task-stage",
        json={"task_stage_id": None},
    )
    assert r.status_code == 404


def test_moving_an_editors_status_leaves_the_briefs_own_status_alone(mock_db):
    """The entire reason there are two statuses. If this fuses them, the feature
    is pointless: one editor finishing would mark the whole brief done."""
    link = _link()
    brief_stage_before = link.task_stage_id
    me = _user()
    submission = MagicMock()
    submission.task_stage_id = None
    stage = MagicMock()
    stage.id = uuid.uuid4()
    stage.deleted_at = None
    # link lookup, stage validation, submission lookup — _brief_item's owner
    # lookup is short-circuited because _link() sets assignee_id to None.
    mock_db.first.side_effect = [link, stage, submission]
    mock_db.all.return_value = []
    client = _client(mock_db, me)
    r = client.patch(
        f"/submission-links/{link.id}/editors/{me.id}/task-stage",
        json={"task_stage_id": str(stage.id)},
    )
    assert r.status_code == 200
    assert submission.task_stage_id == stage.id
    assert link.task_stage_id == brief_stage_before


def test_moving_to_a_deleted_stage_is_refused(mock_db):
    """_get_stage filters on deleted_at; a dangling reference would render as a
    status that is not in the picker."""
    link = _link()
    me = _user()
    mock_db.first.side_effect = [link, None]  # link found, stage not found
    client = _client(mock_db, me)
    r = client.patch(
        f"/submission-links/{link.id}/editors/{me.id}/task-stage",
        json={"task_stage_id": str(uuid.uuid4())},
    )
    assert r.status_code == 404
    # Distinguishes this 404 (raised by _get_stage) from the generic "Request
    # not found" 404s elsewhere on this path — without it, deleting the
    # _get_stage call entirely would still pass this test via the submission
    # lookup's own bare 404.
    assert r.json()["detail"] == "Task stage not found"


def test_an_editor_with_no_row_on_this_brief_gets_a_404(mock_db):
    """Being signed in is not participation."""
    link = _link()
    me = _user()
    stage = MagicMock()
    stage.deleted_at = None
    mock_db.first.side_effect = [link, stage, None]  # no submission row
    client = _client(mock_db, me)
    r = client.patch(
        f"/submission-links/{link.id}/editors/{me.id}/task-stage",
        json={"task_stage_id": str(uuid.uuid4())},
    )
    assert r.status_code == 404


def test_deleting_a_stage_releases_the_editors_sitting_in_it(mock_db):
    """A soft-deleted stage would otherwise keep showing as an editor's status
    while being absent from the picker — a status nobody can clear."""
    from apps.api.models.submission import Submission

    stage = MagicMock()
    stage.id = uuid.uuid4()
    stage.deleted_at = None
    mock_db.first.return_value = stage

    client = _client(mock_db, _user(is_superadmin=True, name="Admin"))
    assert client.delete(f"/task-stages/{stage.id}").status_code == 204

    detached = [
        c.args[0] for c in mock_db.update.call_args_list
        if c.args and isinstance(c.args[0], dict)
    ]
    assert any(Submission.task_stage_id in d for d in detached), (
        "submissions in the deleted stage were not detached"
    )
