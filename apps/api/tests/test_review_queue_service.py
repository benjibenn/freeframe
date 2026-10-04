"""Pure rules behind the /review queue.

Intent:
- Review/Done/Revision are found by name because admins rename stages. A missing
  one must be named in the error. Guessing would approve files into the wrong
  column;
- two stages with one name resolve to the first in board order, never to
  whichever row the database returned first;
- the Canva link is the upload's own "Source: " comment, the first on that version.
"""
import uuid
from types import SimpleNamespace

import pytest

from apps.api.services import source_link
from apps.api.services.review_queue import MissingStage, is_revision, resolve_review_stages


def _stage(name):
    return SimpleNamespace(id=uuid.uuid4(), name=name)


def test_resolves_the_three_stages_by_name_case_insensitively():
    review, done, revision = _stage(" review "), _stage("DONE"), _stage("Revision")
    out = resolve_review_stages([_stage("Pending"), review, revision, done])
    assert out == {"review": review.id, "done": done.id, "revision": revision.id}


def test_a_missing_stage_is_named():
    with pytest.raises(MissingStage) as e:
        resolve_review_stages([_stage("Review"), _stage("Done")])
    assert e.value.name == "Revision"
    assert str(e.value) == "Missing task stage: Revision"


def test_duplicate_names_resolve_to_the_first_in_board_order():
    first, second = _stage("Review"), _stage("review")
    out = resolve_review_stages([first, second, _stage("Done"), _stage("Revision")])
    assert out["review"] == first.id


def test_is_revision():
    assert is_revision(_stage(" revision "))
    assert not is_revision(_stage("Done"))


def test_parse_reads_the_link_out_of_a_source_comment():
    assert source_link.parse("Source: https://www.canva.com/design/abc/edit") == "https://www.canva.com/design/abc/edit"


def test_parse_ignores_other_comments_and_blank_links():
    assert source_link.parse("Looks great") is None
    assert source_link.parse("Source:   ") is None
    assert source_link.parse(None) is None


def test_the_first_source_comment_on_a_version_wins():
    v1, v2 = uuid.uuid4(), uuid.uuid4()
    rows = [
        (v1, "Source: https://canva.com/first"),
        (v1, "Source: https://canva.com/later"),
        (v1, "Nice"),
        (v2, "Not a source"),
    ]
    assert source_link.links_by_version(rows) == {v1: "https://canva.com/first"}
