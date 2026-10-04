"""The paging rules both brief lists share.

Intent:
- an editor's chip counts and filters by THEIR stage, an admin's by the brief's.
  That is the rule lib/brief-stage.ts applies on screen. If the server applied a
  different one, a chip would say 1 and then show an empty list;
- counts are taken before the stage filter, because a chip must count what
  clicking it would show;
- paging past the end is an empty page with the real total, not an error.
"""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from apps.api.services.board_paging import (
    UNASSIGNED, aware, brief_matches, intersect, page_briefs, parse_stage_filter,
    reader_stage, under_prefix,
)

S1, S2 = uuid.uuid4(), uuid.uuid4()


def _row(stage=None, title="Brief", created=None):
    return SimpleNamespace(
        id=uuid.uuid4(), task_stage_id=stage, title=title,
        created_at=created or datetime(2026, 9, 10, 12, tzinfo=timezone.utc),
    )


def test_an_editor_reads_their_own_stage():
    link = uuid.uuid4()
    assert reader_stage(link, S1, {link: S2}) == S2


def test_an_editor_who_has_not_started_reads_none_not_the_briefs_stage():
    """Their own row exists with no stage. Falling back to the brief's stage
    would file a not-started editor under someone else's progress."""
    link = uuid.uuid4()
    assert reader_stage(link, S1, {link: None}) is None


def test_admins_and_owners_read_the_briefs_stage():
    assert reader_stage(uuid.uuid4(), S1, {}) == S1


def test_counts_are_taken_before_the_stage_filter():
    rows = [_row(S1), _row(S2), _row(S2), _row(None)]
    page, total, counts = page_briefs(rows, my_stage_by_link={}, stage_filter=str(S2), offset=0, limit=25)
    assert page == [rows[1].id, rows[2].id]
    assert total == 2
    assert counts == {str(S1): 1, str(S2): 2, UNASSIGNED: 1}


def test_unassigned_filter_keeps_briefs_with_no_stage():
    rows = [_row(S1), _row(None)]
    page, total, _ = page_briefs(rows, my_stage_by_link={}, stage_filter=UNASSIGNED, offset=0, limit=25)
    assert page == [rows[1].id] and total == 1


def test_offset_and_limit_slice_in_order():
    rows = [_row() for _ in range(30)]
    page, total, _ = page_briefs(rows, my_stage_by_link={}, stage_filter=None, offset=25, limit=25)
    assert page == [r.id for r in rows[25:]] and total == 30


def test_paging_past_the_end_is_empty_with_the_real_total():
    rows = [_row(S1) for _ in range(3)]
    page, total, counts = page_briefs(rows, my_stage_by_link={}, stage_filter=None, offset=50, limit=25)
    assert page == [] and total == 3 and counts == {str(S1): 3}


def test_an_editor_is_filtered_by_their_own_stage():
    row = _row(S1)
    page, _, counts = page_briefs([row], my_stage_by_link={row.id: S2}, stage_filter=str(S2), offset=0, limit=25)
    assert page == [row.id] and counts == {str(S2): 1}


def test_search_matches_title_or_path_case_insensitively():
    row = _row(title="Battery hook")
    assert brief_matches(row, None, q="  BATTERY ")
    assert brief_matches(row, "ecom/Phones/Iphone 17", q="iphone 17")
    assert not brief_matches(row, "ecom/Phones", q="camera")


def test_folder_matches_whole_segments_only():
    row = _row()
    assert brief_matches(row, "ecom/Phones/Store 1", folder="ecom/Phones")
    assert brief_matches(row, "ecom/Phones", folder="/ecom/Phones/")
    assert not brief_matches(row, "ecom/Phones2", folder="ecom/Phones")
    assert not brief_matches(row, None, folder="ecom")


def test_created_range_is_start_inclusive_end_exclusive():
    lo = datetime(2026, 9, 10, tzinfo=timezone.utc)
    hi = datetime(2026, 9, 11, tzinfo=timezone.utc)
    assert brief_matches(_row(created=lo), None, created_from=lo, created_to=hi)
    assert not brief_matches(_row(created=hi), None, created_from=lo, created_to=hi)


def test_only_ids_restricts_and_none_means_no_restriction():
    row = _row()
    assert brief_matches(row, None, only_ids=None)
    assert not brief_matches(row, None, only_ids=set())
    assert brief_matches(row, None, only_ids={row.id})


def test_intersect_ignores_unset_restrictions():
    a, b = uuid.uuid4(), uuid.uuid4()
    assert intersect(None, None) is None
    assert intersect({a, b}, None) == {a, b}
    assert intersect({a, b}, {b}) == {b}


def test_stage_filter_parsing():
    assert parse_stage_filter(None) is None
    assert parse_stage_filter("") is None
    assert parse_stage_filter(UNASSIGNED) == UNASSIGNED
    assert parse_stage_filter(str(S1).upper()) == str(S1)
    with pytest.raises(HTTPException) as e:
        parse_stage_filter("review")
    assert e.value.status_code == 422


def test_naive_bounds_are_read_as_utc():
    assert aware(datetime(2026, 9, 10)) == datetime(2026, 9, 10, tzinfo=timezone.utc)
    assert aware(None) is None


def test_under_prefix():
    assert under_prefix("a/b", "a") and not under_prefix("ab", "a") and not under_prefix(None, "a")
