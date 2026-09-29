"""Tests for submitting finished work against a brief over the from-url path.

The rule under test is the one that keeps review legible: when a brief lists its
deliverables, work must claim one of those names. Free-named work would arrive in
review with nothing tying it to the variation it answers, which is what naming the
variations was for.
"""
import pytest
from fastapi import HTTPException

from apps.api.routers.submissions import (
    resolve_submitted_asset_name,
    resolve_submitted_language,
)


def _brief(*variations):
    return {
        "final_deliverable": {
            "hook_variations": [{"variation": v} for v in variations]
        }
    }


def test_prescribed_name_is_accepted():
    brief = _brief("A. before i click buy", "B. convincing mum")
    assert resolve_submitted_asset_name(brief, "B. convincing mum") == "B. convincing mum"


def test_work_cannot_invent_its_own_name_when_the_brief_lists_them():
    """The point of the rule: an unlisted name breaks the tie to a variation.

    Review shows deliverables by name, so "Final v3" against a brief asking for
    A and B leaves a human guessing which argument it tested.
    """
    brief = _brief("A. before i click buy", "B. convincing mum")
    with pytest.raises(HTTPException) as exc:
        resolve_submitted_asset_name(brief, "Final v3")
    assert exc.value.status_code == 400
    # The caller is usually an agent — it can only retry if told the valid set.
    assert "A. before i click buy" in str(exc.value.detail)


def test_missing_name_is_rejected_rather_than_auto_numbered():
    """Auto-numbering here would silently file work as "Hook 1" against a brief
    that asked for a named variation, hiding the mistake instead of surfacing it."""
    brief = _brief("A. before i click buy")
    with pytest.raises(HTTPException) as exc:
        resolve_submitted_asset_name(brief, None)
    assert exc.value.status_code == 400


def test_brief_without_deliverable_names_auto_numbers():
    """Briefs predate the naming scheme; those must keep accepting work."""
    assert resolve_submitted_asset_name({"overview": "no deliverables here"}, None) is None
    assert resolve_submitted_asset_name(None, None) is None


def test_brief_without_deliverable_names_honours_a_requested_name():
    assert resolve_submitted_asset_name({}, "Founder cut") == "Founder cut"


# ── Multi-language briefs ──────────────────────────────────────────────────────

def test_a_language_is_demanded_when_the_brief_asks_for_several():
    """Same rule as the deliverable name, for the same reason.

    Without it, the German and Swedish cuts of one deliverable both resolve to
    the same name, and the second call threads under the first as a revision —
    silently losing a deliverable the brief explicitly asked for.
    """
    brief = {"output_languages": ["German", "Swedish"]}
    with pytest.raises(HTTPException) as exc:
        resolve_submitted_language(brief, None)
    assert exc.value.status_code == 400
    # The caller is usually an agent; it can only retry if told the valid set.
    assert "German" in str(exc.value.detail)


def test_an_unlisted_language_is_rejected():
    brief = {"output_languages": ["German", "Swedish"]}
    with pytest.raises(HTTPException) as exc:
        resolve_submitted_language(brief, "Dutch")
    assert exc.value.status_code == 400


def test_a_listed_language_is_accepted():
    brief = {"output_languages": ["German", "Swedish"]}
    assert resolve_submitted_language(brief, "Swedish") == "Swedish"


def test_a_single_language_brief_asks_for_nothing_and_ignores_what_it_gets():
    """One language is no choice, so the stored name carries no prefix.

    Returning None rather than rejecting a sent language keeps older agents and
    briefs predating the field working instead of failing on a field that would
    not change the name anyway.
    """
    assert resolve_submitted_language({"output_languages": ["German"]}, None) is None
    assert resolve_submitted_language({"output_languages": ["German"]}, "German") is None
    assert resolve_submitted_language({}, "German") is None
