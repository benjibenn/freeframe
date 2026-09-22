"""GET /reports: the superadmin pipeline read model.

Intent encoded:
- the report spans every owner's briefs and every submitter's uploads, so a
  non-superadmin must be refused outright, not merely shown less;
- a file belongs to a person only via the per-submitter PROJECT (assets carry no
  uploader column), so the join has to resolve through Submission.project_id —
  getting this wrong silently credits work to the wrong editor;
- "awaiting work" counts on FILES, not on submissions: someone accepting a brief
  and never delivering is precisely the case an admin opens this page to find;
- an asset in a project that is not a submitter project is not submitted work and
  must not inflate any count.
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


def _sub(link, user_id):
    return SimpleNamespace(
        id=uuid.uuid4(),
        submission_link_id=link.id,
        user_id=user_id,
        project_id=uuid.uuid4(),
    )


def _user(name, email, nickname=None):
    return SimpleNamespace(id=uuid.uuid4(), name=name, email=email, nickname=nickname)


def test_non_superadmin_is_refused(test_user):
    from apps.api.routers.reports import get_reports

    test_user.is_superadmin = False
    with pytest.raises(HTTPException) as exc:
        get_reports(db=MagicMock(), current_user=test_user)
    assert exc.value.status_code == 403


def test_counts_resolve_files_through_the_submitter_project():
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

    r = build_report(
        [brief], [a_sub, b_sub], assets, {alice.id: alice, bob.id: bob}, {}
    )

    assert r.totals.file_count == 3
    assert r.totals.submission_count == 2
    assert r.totals.submitter_count == 2
    assert r.briefs[0].file_count == 3
    assert r.briefs[0].submission_count == 2

    by_user = {u.user_id: u for u in r.users}
    assert by_user[alice.id].file_count == 2
    assert by_user[bob.id].file_count == 1
    # Nickname wins over the account name, so one person reads the same everywhere.
    assert by_user[alice.id].name == "Ali"
    assert by_user[bob.id].name == "Bob B"
    assert set(r.briefs[0].submitter_names) == {"Ali", "Bob B"}
    assert {f.name for f in r.files} == {"alice-1.mp4", "alice-2.mp4", "bob-1.mp4"}


def test_accepted_but_undelivered_brief_still_counts_as_awaiting_work():
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

    assert r.totals.brief_count == 3
    # B was accepted but nothing was uploaded — it is still awaiting work.
    assert r.totals.briefs_awaiting_work == 2
    assert {b.title: b.file_count for b in r.briefs} == {"A": 1, "B": 0, "C": 0}
    # One person, two briefs, one file.
    assert len(r.users) == 1
    assert r.users[0].brief_count == 2
    assert r.users[0].file_count == 1


def test_last_upload_tracks_the_newest_file_and_users_sort_busiest_first():
    from apps.api.routers.reports import build_report

    quiet = _user("Quiet", "q@example.com")
    busy = _user("Busy", "b@example.com")
    brief = _link("Shared")
    q_sub, b_sub = _sub(brief, quiet.id), _sub(brief, busy.id)
    latest = NOW + timedelta(days=3)

    r = build_report(
        [brief],
        [q_sub, b_sub],
        [
            (uuid.uuid4(), q_sub.project_id, "q.mp4", NOW),
            (uuid.uuid4(), b_sub.project_id, "b1.mp4", NOW + timedelta(days=1)),
            (uuid.uuid4(), b_sub.project_id, "b2.mp4", latest),
        ],
        {quiet.id: quiet, busy.id: busy},
        {},
    )

    assert r.briefs[0].last_upload_at == latest
    assert [u.name for u in r.users] == ["Busy", "Quiet"]
    assert r.users[0].last_upload_at == latest


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

    r = build_report(
        [brief], [s], [(uuid.uuid4(), s.project_id, "f.mp4", NOW)], {}, {}
    )

    assert r.files[0].user_name == ""
    assert r.users[0].name == ""
    assert r.users[0].email == ""
    assert r.totals.file_count == 1
