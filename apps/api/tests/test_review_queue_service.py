"""Pure rules behind the /review queue.

Intent:
- the queue is one item per EDITOR on a brief whose own stage is Review. The
  team moves the editor's stage, not the files' (live data: every file sits in
  Pending while 82 editors sit in Review), so a file-stage queue is empty;
- Review/Done/Revision are found by name because admins rename stages. A missing
  one must be named in the error. Guessing would approve into the wrong column;
- two stages with one name resolve to the first in board order, never to
  whichever row the database returned first;
- a deleted brief or project must not stay queued: clicking through would 404;
- the longest-waiting editor comes first, by their newest upload, so work that
  was re-delivered after a revision queues by the re-delivery;
- the Canva link is the upload's own "Source: " comment, the first on that version.
"""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from apps.api.models.asset import AssetType, ProcessingStatus
from apps.api.services import source_link
from apps.api.services.review_queue import (
    MissingStage,
    build_file,
    build_item,
    files_statement,
    is_revision,
    queue_statement,
    resolve_review_stages,
)


def _stage(name):
    return SimpleNamespace(id=uuid.uuid4(), name=name)


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


# ── Stages ───────────────────────────────────────────────────────────────────

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


# ── The queue query ──────────────────────────────────────────────────────────

def test_queue_selects_editors_whose_own_stage_is_review_not_files():
    review = uuid.uuid4()
    sql = _sql(queue_statement(review))
    assert f"submissions.task_stage_id = '{review}'" in sql
    # The file stage is what was empty in production. It must play no part.
    assert "assets.task_stage_id" not in sql


def test_queue_drops_deleted_briefs_and_deleted_projects():
    sql = _sql(queue_statement(uuid.uuid4()))
    assert "submission_links.brief_json" not in sql
    assert "submission_links.deleted_at IS NULL" in sql
    assert "projects.deleted_at IS NULL" in sql


def test_queue_waits_from_the_newest_live_upload_else_from_when_the_editor_joined():
    sql = _sql(queue_statement(uuid.uuid4()))
    assert "coalesce(" in sql and "submissions.created_at" in sql
    assert "max(asset_versions.created_at)" in sql
    # A deleted or archived file, or a deleted version, is not a delivery.
    assert "assets.deleted_at IS NULL" in sql
    assert "asset_versions.deleted_at IS NULL" in sql
    assert "assets.status IS DISTINCT FROM 'archived'" in sql


def test_queue_is_oldest_first_with_a_stable_tiebreak():
    sql = _sql(queue_statement(uuid.uuid4()))
    order_by = sql[sql.index("ORDER BY"):]
    assert order_by.index("waited_since ASC") < order_by.index("submissions.id ASC")


def test_queue_filters_by_editor_only_when_asked():
    editor = uuid.uuid4()
    assert "submissions.user_id =" not in _sql(queue_statement(uuid.uuid4()))
    assert f"submissions.user_id = '{editor}'" in _sql(queue_statement(uuid.uuid4(), editor_id=editor))


def test_files_are_the_live_newest_versions_of_the_pages_projects():
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    sql = _sql(files_statement([p1, p2]))
    assert f"assets.project_id IN ('{p1}', '{p2}')" in sql
    assert "assets.deleted_at IS NULL" in sql
    assert "assets.status IS DISTINCT FROM 'archived'" in sql
    assert "max(asset_versions.version_number)" in sql
    assert "asset_versions.deleted_at IS NULL" in sql


# ── Source links ─────────────────────────────────────────────────────────────

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


# ── One file ─────────────────────────────────────────────────────────────────

def _asset(asset_type=AssetType.image):
    return SimpleNamespace(id=uuid.uuid4(), project_id=uuid.uuid4(), name="hook-3.png", asset_type=asset_type)


def _version(status=ProcessingStatus.ready):
    return SimpleNamespace(id=uuid.uuid4(), processing_status=status)


def _media(processed=None, raw="raw/x.png", thumb="thumbs/x.jpg"):
    return SimpleNamespace(s3_key_processed=processed, s3_key_raw=raw, s3_key_thumbnail=thumb)


def _file(asset, version, media, canva=None):
    return build_file(
        asset, version, media, canva,
        presign=lambda key: f"https://s3/{key}",
        hls_url=lambda key: f"/stream/hls/{key}",
    )


def test_file_carries_preview_thumbnail_and_canva_link():
    a, v = _asset(), _version()
    f = _file(a, v, [_media()], "https://canva.com/d/1")
    assert (f.asset_id, f.version_id, f.file_name, f.asset_type) == (a.id, v.id, "hook-3.png", AssetType.image)
    assert f.preview_url == "https://s3/raw/x.png"
    assert f.thumbnail_url == "https://s3/thumbs/x.jpg"
    assert f.canva_url == "https://canva.com/d/1"


def test_missing_canva_link_is_null_not_omitted():
    a, v = _asset(), _version()
    assert _file(a, v, [_media()]).canva_url is None


def test_a_version_still_processing_has_no_preview():
    """A half-processed file has no playable output; a broken player reads as a broken file."""
    a, v = _asset(), _version(ProcessingStatus.processing)
    f = _file(a, v, [_media()])
    assert f.preview_url is None
    assert f.thumbnail_url == "https://s3/thumbs/x.jpg"


def test_video_previews_through_the_hls_proxy():
    a, v = _asset(AssetType.video), _version()
    assert _file(a, v, [_media(processed="processed/v1")]).preview_url == "/stream/hls/processed/v1"


def test_audio_has_no_thumbnail():
    a, v = _asset(AssetType.audio), _version()
    assert _file(a, v, [_media(thumb="waveforms/a.json")]).thumbnail_url is None


# ── One editor's submission ──────────────────────────────────────────────────

def _sub(display_name=None):
    return SimpleNamespace(
        id=uuid.uuid4(), submission_link_id=uuid.uuid4(), user_id=uuid.uuid4(),
        project_id=uuid.uuid4(), display_name=display_name,
    )


WAITED = datetime(2026, 10, 1, tzinfo=timezone.utc)


def test_item_is_one_editor_on_one_brief_with_their_files():
    sub, review = _sub(), uuid.uuid4()
    a, v = _asset(), _version()
    files = [_file(a, v, [_media()])]
    item = build_item(sub, "Battery brief", "tok-1", SimpleNamespace(display_name="Ada"), WAITED, files, review)
    assert item.submission_id == sub.id
    assert (item.brief_id, item.brief_title, item.brief_token) == (sub.submission_link_id, "Battery brief", "tok-1")
    assert (item.editor_id, item.editor_name) == (sub.user_id, "Ada")
    assert item.project_id == sub.project_id
    # The page sends this back; the server refuses if the editor has moved since.
    assert item.expected_stage_id == review
    assert item.waited_since == WAITED
    assert [f.asset_id for f in item.files] == [a.id]


def test_owner_set_handle_wins_over_account_name():
    sub = _sub(display_name="Ada (contract)")
    item = build_item(sub, "Battery brief", "tok-1", SimpleNamespace(display_name="Ada"), WAITED, [], uuid.uuid4())
    assert item.editor_name == "Ada (contract)"


def test_an_editor_with_nothing_uploaded_still_queues_with_no_files():
    """Someone moved them to Review; the reviewer must see that there is nothing
    to look at rather than the item silently vanishing."""
    sub = _sub()
    item = build_item(sub, "Battery brief", "tok-1", None, WAITED, [], uuid.uuid4())
    assert item.files == []
    assert item.editor_name is None
