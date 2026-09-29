"""Tests for tagging briefs with persona and angle labels.

Intent encoded:
- the playbook matrix counts briefs by these labels, so a batch is all-or-nothing:
  one bad id must not leave half the batch tagged and the matrix quietly wrong.
- None keeps a label and "" clears it, so tagging angles never wipes a persona
  someone fixed by hand.
- tagging spans every owner's briefs, so it stays superadmin-only like the overview.
"""
import uuid
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.routers import mcp as mcp_router


def _user(*, is_superadmin=True):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.is_superadmin = is_superadmin
    u.is_subadmin = not is_superadmin
    u.deleted_at = None
    return u


def _client(mock_db, user):
    from apps.api.routers.brief_labels import router
    from apps.api.database import get_db
    from apps.api.middleware.auth import get_current_user

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def _link(persona="Frugal Phone Buyer", angle=None):
    l = MagicMock()
    l.id = uuid.uuid4()
    l.persona_label = persona
    l.angle_label = angle
    return l


def test_sets_angle_and_keeps_the_hand_fixed_persona(mock_db):
    a, b = _link(), _link()
    mock_db.all.return_value = [a, b]

    r = _client(mock_db, _user()).patch("/brief-overview/labels", json={
        "link_ids": [str(a.id), str(b.id)], "angle_label": " A2 ",
    })

    assert r.status_code == 200 and r.json() == {"updated": 2}
    assert (a.angle_label, b.angle_label) == ("A2", "A2")
    assert a.persona_label == "Frugal Phone Buyer"
    mock_db.commit.assert_called_once()


def test_empty_string_clears_a_label(mock_db):
    a = _link(angle="A2")
    mock_db.all.return_value = [a]

    _client(mock_db, _user()).patch("/brief-overview/labels", json={"link_ids": [str(a.id)], "angle_label": ""})

    assert a.angle_label is None


def test_one_unknown_id_saves_nothing(mock_db):
    a = _link()
    mock_db.all.return_value = [a]
    ghost = uuid.uuid4()

    r = _client(mock_db, _user()).patch("/brief-overview/labels", json={
        "link_ids": [str(a.id), str(ghost)], "angle_label": "A2",
    })

    assert r.status_code == 404 and str(ghost) in r.json()["detail"]
    assert a.angle_label is None
    mock_db.commit.assert_not_called()


def test_a_call_that_sets_nothing_is_rejected(mock_db):
    r = _client(mock_db, _user()).patch("/brief-overview/labels", json={"link_ids": [str(uuid.uuid4())]})
    assert r.status_code == 422


def test_subadmin_cannot_tag(mock_db):
    r = _client(mock_db, _user(is_superadmin=False)).patch("/brief-overview/labels", json={
        "link_ids": [str(uuid.uuid4())], "angle_label": "A2",
    })
    assert r.status_code == 403
    mock_db.commit.assert_not_called()


def test_mcp_tool_passes_keep_and_clear_through(mock_db):
    user = _user()
    tokens = mcp_router._current_user.set(user), mcp_router._current_db.set(mock_db)
    try:
        with patch.object(mcp_router.brief_labels_router, "set_brief_labels", return_value={"updated": 1}) as fn:
            out = mcp_router.set_brief_labels(link_ids=[str(uuid.uuid4())], angle_label="")
    finally:
        mcp_router._current_user.reset(tokens[0])
        mcp_router._current_db.reset(tokens[1])

    body = fn.call_args.kwargs["body"]
    assert out == {"updated": 1}
    assert body.persona_label is None and body.angle_label == ""
