"""GET /reports: the superadmin pipeline read model.

Intent encoded:
- the report spans every owner's briefs and every submitter's uploads, so a
  non-superadmin must be refused outright, not merely shown less;
- a file belongs to a person only via the per-submitter PROJECT (assets carry no
  uploader column), so the join has to resolve through Submission.project_id —
  getting this wrong silently credits work to the wrong editor;
- an asset in a project that is not a submitter project is not submitted work and
  must not reach the payload;
- the endpoint returns FACTS and no counts. The page applies the date window, so
  the page derives every number; a count computed here could not know the window
  and would end up printed beside a filter it does not obey. That is exactly the
  bug this endpoint shipped with and no longer can.
"""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException


NOW = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def _link(title, **kw):
    return SimpleNamespace(
        id=uuid.uuid4(),
        title=title,
        taxonomy_path=kw.get("taxonomy_path"),
        created_at=kw.get("created_at", NOW),
        is_enabled=kw.get("is_enabled", True),
        persona_label=kw.get("persona_label"),
        angle_label=kw.get("angle_label"),
    )


def _sub(link, user_id, created_at=NOW):
    return SimpleNamespace(
        id=uuid.uuid4(),
        submission_link_id=link.id,
        user_id=user_id,
        project_id=uuid.uuid4(),
        created_at=created_at,
    )


def _user(name, email, nickname=None):
    return SimpleNamespace(id=uuid.uuid4(), name=name, email=email, nickname=nickname)


def test_non_superadmin_is_refused(test_user):
    from apps.api.routers.reports import get_reports

    test_user.is_superadmin = False
    with pytest.raises(HTTPException) as exc:
        get_reports(db=MagicMock(), current_user=test_user)
    assert exc.value.status_code == 403


def test_files_resolve_to_a_person_through_the_submitter_project():
    from apps.api.routers.reports import build_report

    alice = _user("Alice A", "alice@example.com", nickname="Ali")
    bob = _user("Bob B", "bob@example.com")
    brief = _link("Hook test")
    a_sub = _sub(brief, alice.id)
    b_sub = _sub(brief, bob.id)

    assets = [
        (uuid.uuid4(), a_sub.project_id, "alice-1.mp4", NOW),
        (uuid.uuid4(), a_sub.project_id, "alice-2.mp4", NOW + timedelta(hours=1)),
        (uuid.uuid4(), b_sub.project_id, "bob-1.mp4", NOW),
        # An asset in some unrelated project: not submitted work.
        (uuid.uuid4(), uuid.uuid4(), "stray.mp4", NOW),
    ]

    r = build_report([brief], [a_sub, b_sub], assets, {alice.id: alice, bob.id: bob}, {})

    assert {f.name for f in r.files} == {"alice-1.mp4", "alice-2.mp4", "bob-1.mp4"}
    by_name = {f.name: f for f in r.files}
    assert by_name["alice-1.mp4"].user_id == alice.id
    # Nickname wins over the account name, so one person reads the same everywhere.
    assert by_name["alice-1.mp4"].user_name == "Ali"
    assert by_name["bob-1.mp4"].user_name == "Bob B"
    assert by_name["alice-1.mp4"].brief_title == "Hook test"


def test_submitters_carry_the_day_they_accepted():
    """Without this date the page cannot tell an accept inside the window from one
    that happened months earlier, which is what left a lifetime number beside a
    two-day filter."""
    from apps.api.routers.reports import build_report

    alice = _user("Alice", "alice@example.com")
    bob = _user("Bob", "bob@example.com")
    brief = _link("Shared")
    early = _sub(brief, alice.id, created_at=NOW)
    late = _sub(brief, bob.id, created_at=NOW + timedelta(days=30))

    r = build_report([brief], [early, late], [], {alice.id: alice, bob.id: bob}, {})

    accepted = {s.name: s.submitted_at for s in r.briefs[0].submitters}
    assert accepted == {"Alice": NOW, "Bob": NOW + timedelta(days=30)}


def test_a_brief_nobody_delivered_on_still_reaches_the_page():
    """The page needs it to answer "awaiting work"; dropping it here would make
    that question unanswerable no matter what the page does."""
    from apps.api.routers.reports import build_report

    carol = _user("Carol", "carol@example.com")
    delivered, accepted_only, untouched = _link("A"), _link("B"), _link("C")
    s1 = _sub(delivered, carol.id)
    s2 = _sub(accepted_only, carol.id)

    r = build_report(
        [delivered, accepted_only, untouched],
        [s1, s2],
        [(uuid.uuid4(), s1.project_id, "done.mp4", NOW)],
        {carol.id: carol},
        {},
    )

    assert {b.title for b in r.briefs} == {"A", "B", "C"}
    assert len(r.files) == 1
    # Carol accepted two briefs and delivered on one; she is in the roster either way.
    assert [u.name for u in r.users] == ["Carol"]
    assert {b.title: len(b.submitters) for b in r.briefs} == {"A": 1, "B": 1, "C": 0}


def test_every_submitter_appears_once_even_across_many_briefs():
    from apps.api.routers.reports import build_report

    dave = _user("Dave", "dave@example.com")
    one, two = _link("One"), _link("Two")

    r = build_report(
        [one, two], [_sub(one, dave.id), _sub(two, dave.id)], [], {dave.id: dave}, {}
    )

    assert [u.user_id for u in r.users] == [dave.id]


def test_home_path_prefers_the_derived_folder_path_over_the_stored_string():
    from apps.api.routers.reports import build_report

    filed = _link("Filed", taxonomy_path="typed/by/hand")
    legacy = _link("Legacy", taxonomy_path="legacy/path")

    r = build_report([filed, legacy], [], [], {}, {filed.id: "ecom/Phones/Store 1"})

    by_title = {b.title: b.home_path for b in r.briefs}
    assert by_title["Filed"] == "ecom/Phones/Store 1"
    assert by_title["Legacy"] == "legacy/path"


def test_missing_user_row_degrades_instead_of_breaking_the_report():
    from apps.api.routers.reports import build_report

    brief = _link("Orphan")
    ghost_id = uuid.uuid4()
    s = _sub(brief, ghost_id)

    r = build_report([brief], [s], [(uuid.uuid4(), s.project_id, "f.mp4", NOW)], {}, {})

    assert r.files[0].user_name == ""
    assert r.users[0].name == ""
    assert r.users[0].email == ""
    assert len(r.files) == 1
