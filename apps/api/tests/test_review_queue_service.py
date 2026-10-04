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
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from apps.api.models.asset import AssetType, ProcessingStatus
from apps.api.services import source_link
from apps.api.services.review_queue import (
    MissingStage,
    QueueContext,
    build_item,
    is_revision,
    resolve_review_stages,
)


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


def _asset(asset_type=AssetType.image):
    return SimpleNamespace(
        id=uuid.uuid4(), project_id=uuid.uuid4(), created_by=uuid.uuid4(),
        name="hook-3.png", asset_type=asset_type,
    )


def _version(status=ProcessingStatus.ready):
    return SimpleNamespace(id=uuid.uuid4(), processing_status=status, created_at=datetime(2026, 10, 1, tzinfo=timezone.utc))


def _file(version, processed=None, raw="raw/x.png", thumb="thumbs/x.jpg", order=1):
    return SimpleNamespace(version_id=version.id, s3_key_processed=processed, s3_key_raw=raw,
                           s3_key_thumbnail=thumb, sequence_order=order)


def _ctx(asset, version, files, **kw):
    project = SimpleNamespace(id=asset.project_id, submission_link_id=uuid.uuid4())
    link = SimpleNamespace(id=project.submission_link_id, title="Battery brief", token="tok-1")
    return QueueContext(
        files_by_version={version.id: files},
        projects={project.id: project},
        links={link.id: link},
        submissions_by_project=kw.get("subs", {}),
        users=kw.get("users", {asset.created_by: SimpleNamespace(display_name="Ada")}),
        source_by_version=kw.get("sources", {}),
        presign=lambda key: f"https://s3/{key}",
        hls_url=lambda key: f"/stream/hls/{key}",
    )


def test_item_carries_brief_editor_preview_and_canva_link():
    a, v = _asset(), _version()
    item = build_item(a, v, _ctx(a, v, [_file(v)], sources={v.id: "https://canva.com/d/1"}))
    assert item.brief_title == "Battery brief" and item.brief_token == "tok-1"
    assert item.editor_name == "Ada"
    assert item.preview_url == "https://s3/raw/x.png"
    assert item.thumbnail_url == "https://s3/thumbs/x.jpg"
    assert item.canva_url == "https://canva.com/d/1"
    assert item.submitted_at == v.created_at


def test_missing_canva_link_is_null_not_omitted():
    a, v = _asset(), _version()
    assert build_item(a, v, _ctx(a, v, [_file(v)])).canva_url is None


def test_owner_set_handle_wins_over_account_name():
    a, v = _asset(), _version()
    subs = {a.project_id: SimpleNamespace(display_name="Ada (contract)")}
    assert build_item(a, v, _ctx(a, v, [_file(v)], subs=subs)).editor_name == "Ada (contract)"


def test_a_version_still_processing_has_no_preview():
    """A half-processed file has no playable output; a broken player reads as a broken file."""
    a, v = _asset(), _version(ProcessingStatus.processing)
    item = build_item(a, v, _ctx(a, v, [_file(v)]))
    assert item.preview_url is None
    assert item.thumbnail_url == "https://s3/thumbs/x.jpg"


def test_video_previews_through_the_hls_proxy():
    a, v = _asset(AssetType.video), _version()
    item = build_item(a, v, _ctx(a, v, [_file(v, processed="processed/v1")]))
    assert item.preview_url == "/stream/hls/processed/v1"


def test_audio_has_no_thumbnail():
    a, v = _asset(AssetType.audio), _version()
    assert build_item(a, v, _ctx(a, v, [_file(v, thumb="waveforms/a.json")])).thumbnail_url is None
