"""Tests for assembling a brief title from its parts.

Intent encoded:
- the playbook reads persona, lens, hook and format out of the title by
  splitting on " - " (apps/web/lib/playbook.ts), so the order here is not
  cosmetic: get it wrong and every column shows another column's value.
- the hook is the ONLY part allowed to contain " - ", because parseTitle
  recovers it by joining the middle slots. A separator anywhere else shifts
  every field after it, which is why those are refused rather than escaped.
- a missing part is refused by name: a five-slot title makes parseTitle return
  all-nulls, so the brief would land in the matrix with no persona and no lens
  at all rather than with one wrong value.
"""
import re
from datetime import date

import pytest

from apps.api.services.brief_title import build_title


def _parts(title: str) -> dict:
    """The playbook's own reading of a title, mirrored from parseTitle."""
    slots = [s.strip() for s in title.split(" - ")]
    assert len(slots) >= 6, title
    return {
        "date": slots[0],
        "sku": slots[1],
        "persona": slots[2],
        "lens": slots[3],
        "hook": " - ".join(slots[4:-1]),
        "ad_format": slots[-1],
    }


def test_builds_a_title_the_playbook_reads_back_unchanged():
    title = build_title(
        sku="iPhone 17",
        persona="Frugal Phone Buyer",
        lens="Fear",
        hook="Battery dies by 3pm",
        ad_format="Static",
        date_str="20260910",
    )

    assert title == "20260910 - iPhone 17 - Frugal Phone Buyer - Fear - Battery dies by 3pm - Static"
    assert _parts(title) == {
        "date": "20260910",
        "sku": "iPhone 17",
        "persona": "Frugal Phone Buyer",
        "lens": "Fear",
        "hook": "Battery dies by 3pm",
        "ad_format": "Static",
    }


def test_defaults_the_date_to_today():
    title = build_title(sku="x", persona="p", lens="l", hook="h", ad_format="Static")

    assert _parts(title)["date"] == date.today().strftime("%Y%m%d")


def test_keeps_a_hook_that_contains_the_separator():
    title = build_title(
        sku="x", persona="p", lens="Fear", hook="Cracked screen - again", ad_format="Static",
        date_str="20260910",
    )

    assert _parts(title)["hook"] == "Cracked screen - again"
    assert _parts(title)["lens"] == "Fear"


@pytest.mark.parametrize("part", ["sku", "persona", "lens", "ad_format"])
def test_refuses_a_separator_in_any_other_part(part):
    kwargs = dict(sku="x", persona="p", lens="l", hook="h", ad_format="Static", date_str="20260910")
    kwargs[part] = "one - two"

    with pytest.raises(ValueError, match=part):
        build_title(**kwargs)


@pytest.mark.parametrize("part", ["sku", "persona", "lens", "hook", "ad_format"])
def test_refuses_a_missing_part_by_name(part):
    kwargs = dict(sku="x", persona="p", lens="l", hook="h", ad_format="Static")
    kwargs[part] = "   "

    with pytest.raises(ValueError, match=part):
        build_title(**kwargs)


def test_strips_surrounding_whitespace():
    title = build_title(
        sku="  iPhone 17 ", persona=" Frugal ", lens=" Fear ", hook="  Battery  ",
        ad_format=" Static ", date_str="20260910",
    )

    assert title == "20260910 - iPhone 17 - Frugal - Fear - Battery - Static"


@pytest.mark.parametrize("bad", ["2026-09-10", "10092026", "not a date", "20261340"])
def test_refuses_a_date_that_is_not_a_real_yyyymmdd(bad):
    with pytest.raises(ValueError, match="date"):
        build_title(sku="x", persona="p", lens="l", hook="h", ad_format="Static", date_str=bad)


def test_the_date_slot_is_always_eight_digits():
    title = build_title(sku="x", persona="p", lens="l", hook="h", ad_format="Static")

    assert re.match(r"^\d{8} - ", title)
