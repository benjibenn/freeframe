"""Tests for finding briefs in bulk.

Intent encoded:
- an agent reading 300 briefs one get_brief at a time spent ~2 hours in round
  trips. Filters, paging and content in one call are what make that two calls.
- column filters run in SQL, and brief_json — the heavy column — is not loaded
  unless asked for, because a listing of hundreds otherwise drags every brief's
  full JSON over the wire to show a title.
- persona follows the playbook's rule (lib/playbook.ts): a label set on the
  brief beats what its title says, and a title only says it when it has all
  six slots. Counting by a different rule than the matrix shows would give an
  agent numbers that disagree with the screen.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

from sqlalchemy.dialects import postgresql

from apps.api.services import brief_search
from apps.api.services.brief_search import BriefFilters


def _sql(query) -> str:
    return str(query.statement.compile(dialect=postgresql.dialect())).lower()


def _admin():
    u = MagicMock()
    u.id = uuid.uuid4()
    u.is_superadmin = True
    u.is_subadmin = False
    return u


def _query(filters: BriefFilters, *, with_content=False, user=None):
    from sqlalchemy.orm import Session

    return brief_search.base_query(Session(), user or _admin(), filters, with_content=with_content)


# ── What runs in SQL ──────────────────────────────────────────────────────────

def test_column_filters_are_pushed_into_the_query():
    sql = _sql(_query(BriefFilters(
        project_id=uuid.uuid4(),
        angle="A28",
        enabled=True,
        created_after=datetime(2026, 9, 1, tzinfo=timezone.utc),
        has_submissions=True,
    )))
    assert "submission_links.home_project_id =" in sql
    assert "angle_label" in sql
    assert "submission_links.is_enabled" in sql
    assert "submission_links.created_at >=" in sql
    assert "exists" in sql and "submissions" in sql


def test_brief_json_is_not_loaded_for_a_listing():
    sql = _sql(_query(BriefFilters()))
    select_list = sql.split(" from ")[0]
    assert "brief_json" not in select_list
    assert "submission_links.title" in select_list


def test_brief_json_is_loaded_when_content_is_asked_for():
    select_list = _sql(_query(BriefFilters(), with_content=True)).split(" from ")[0]
    assert "brief_json" in select_list


def test_deleted_briefs_never_match():
    assert "submission_links.deleted_at is null" in _sql(_query(BriefFilters()))


def test_a_non_admin_only_sees_briefs_they_created():
    # The same visibility rule as GET /submission-links.
    user = _admin()
    user.is_superadmin = False
    assert "submission_links.created_by =" in _sql(_query(BriefFilters(), user=user))


# ── What is decided in Python ─────────────────────────────────────────────────

T = "20260910 - iPhone 17 - Frugal Phone Buyer - Fear - Battery - Static"


def test_a_persona_label_beats_the_title():
    assert brief_search.persona_of(T, "Upgrader") == "Upgrader"


def test_the_title_supplies_the_persona_when_no_label_is_set():
    assert brief_search.persona_of(T, None) == "Frugal Phone Buyer"
    assert brief_search.persona_of(T, "   ") == "Frugal Phone Buyer"


def test_a_title_off_the_convention_has_no_persona():
    # Fewer than six slots reads as all-nulls in parseTitle, so it does here too.
    assert brief_search.persona_of("Spring - Frugal - Static", None) is None


def test_query_matches_title_or_folder_path_case_insensitively():
    assert brief_search.matches_query("Stokora hero cut", None, "STOKORA")
    assert brief_search.matches_query("Untitled", "Phones/Stokora", "stokora")
    assert not brief_search.matches_query("Other", "Phones/Other", "stokora")


def test_persona_filter_is_exact_not_a_substring():
    # "Buyer" must not pull in every "... Buyer" persona the SQL prefilter let by.
    assert brief_search.matches_persona(T, None, "frugal phone buyer")
    assert not brief_search.matches_persona(T, None, "Buyer")


def test_page_reports_where_the_next_one_starts():
    rows = list(range(12))
    page, meta = brief_search.page(rows, offset=5, limit=5)
    assert page == [5, 6, 7, 8, 9]
    assert meta == {"total_matched": 12, "offset": 5, "returned": 5, "next_offset": 10, "truncated": True}


def test_the_last_page_says_there_is_no_next_one():
    page, meta = brief_search.page(list(range(12)), offset=10, limit=5)
    assert page == [10, 11]
    assert meta["next_offset"] is None
    assert meta["truncated"] is False


def test_counts_are_grouped_largest_first_with_blanks_named():
    keys = ["Frugal", "Upgrader", "Frugal", None, "Frugal", None]
    assert brief_search.tally(keys, blank="No persona") == [
        {"key": "Frugal", "count": 3},
        {"key": "No persona", "count": 2},
        {"key": "Upgrader", "count": 1},
    ]
