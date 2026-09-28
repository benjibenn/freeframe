"""Tests for who may see, and who may move, another editor's work on a brief.

Intent encoded: per-submitter isolation is the whole reason submission links
exist. An editor learning who else is on a brief, and how far along they are,
is the leak this module prevents — so the tests are written against the leak,
not against the filter.
"""
import uuid
from types import SimpleNamespace

from apps.api.services.brief_editors import may_move_editor_stage, visible_editors


def _editor(user_id=None):
    return SimpleNamespace(id=user_id or uuid.uuid4())


def test_an_editor_sees_only_their_own_row():
    """The leak this exists to stop: co-editor names and progress in the body.

    Filtering in the UI would not do — the response would still carry them.
    """
    me, them = _editor(), _editor()
    assert visible_editors([me, them], me.id, is_admin=False) == [me]


def test_an_admin_sees_every_editor():
    """Admins are who the roll-up is for; hiding rows would make it useless."""
    a, b = _editor(), _editor()
    assert visible_editors([a, b], a.id, is_admin=True) == [a, b]


def test_a_viewer_with_no_row_sees_nothing():
    """An internal owner who is not an editor sees the brief but not the people."""
    assert visible_editors([_editor(), _editor()], uuid.uuid4(), is_admin=False) == []


def test_a_missing_viewer_id_hides_everyone_rather_than_everyone_being_shown():
    """Fail closed. A null id is the case where a leak would be silent."""
    assert visible_editors([_editor(), _editor()], None, is_admin=False) == []


def test_an_editor_may_move_their_own_status():
    me = uuid.uuid4()
    assert may_move_editor_stage(me, me, is_admin=False) is True


def test_an_editor_may_not_move_a_co_editors_status():
    """Two editors on one brief are doing separate work; neither reports for the
    other. Allowing it would also disclose that the other row exists."""
    assert may_move_editor_stage(uuid.uuid4(), uuid.uuid4(), is_admin=False) is False


def test_an_admin_may_move_anyones_status():
    assert may_move_editor_stage(uuid.uuid4(), uuid.uuid4(), is_admin=True) is True
