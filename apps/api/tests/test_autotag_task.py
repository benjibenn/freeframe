import uuid
from unittest.mock import MagicMock, patch
import apps.api.tasks.autotag_tasks as at
from apps.api.models.asset import AssetType
from apps.api.services.gemini_service import Analysis
from apps.api.tasks.autotag_tasks import MAX_AUTOTAG_BYTES


def _asset(keywords=None, atype=AssetType.video):
    a = MagicMock()
    a.id = uuid.uuid4()
    a.project_id = uuid.uuid4()
    a.asset_type = atype
    a.keywords = list(keywords or [])
    a.deleted_at = None
    return a


def _version(summary=None):
    v = MagicMock()
    v.id = uuid.uuid4()
    v.ai_summary = summary
    v.ai_transcript = "" if summary else None
    return v


def _db_returning(asset, version, palette_labels):
    """A fake db whose .query(...).filter(...).first()/.all() walk returns our objects in order."""
    db = MagicMock()
    # asset first, version first, then palette .all()
    first_side = [asset, version]
    query = MagicMock()
    db.query.return_value = query
    query.filter.return_value = query
    query.order_by.return_value = query
    query.first.side_effect = first_side
    query.all.return_value = [MagicMock(label=l) for l in palette_labels]
    return db


@patch("apps.api.tasks.autotag_tasks.settings")
@patch("apps.api.tasks.autotag_tasks.publish_event")
@patch("apps.api.tasks.autotag_tasks._match", return_value=["Unboxing"])
@patch("apps.api.tasks.autotag_tasks._analyze")
def test_cached_analysis_is_reused_and_tags_applied(analyze, match, pub, cfg):
    cfg.gemini_api_key = "k"
    asset, version = _asset(keywords=["existing"]), _version(summary="a cat unboxing")
    db = _db_returning(asset, version, ["Unboxing", "Demo"])
    with patch("apps.api.tasks.autotag_tasks.SessionLocal", return_value=db):
        at.autotag_asset(str(asset.id), str(version.id))
    analyze.assert_not_called()                      # WHY: cached summary must not re-upload the video
    assert asset.keywords == ["existing", "unboxing"]  # normalized + appended
    pub.assert_called_with(str(asset.project_id), "autotag_complete", {"asset_id": str(asset.id), "applied": ["unboxing"]})


@patch("apps.api.tasks.autotag_tasks.settings")
@patch("apps.api.tasks.autotag_tasks.publish_event")
@patch("apps.api.tasks.autotag_tasks._match", return_value=[])
@patch("apps.api.tasks.autotag_tasks._analyze", return_value=Analysis("fresh summary", "words"))
def test_fresh_asset_runs_analysis_and_caches(analyze, match, pub, cfg):
    cfg.gemini_api_key = "k"
    asset, version = _asset(), _version(summary=None)
    # extra .first() for the MediaFile lookup between asset and palette
    db = MagicMock()
    q = MagicMock(); db.query.return_value = q
    q.filter.return_value = q; q.order_by.return_value = q
    q.first.side_effect = [asset, version, MagicMock(s3_key_raw="raw/1", mime_type="video/mp4", original_filename="c.mp4", file_size_bytes=1024)]
    # Track call order: stage-1 cache committed BEFORE stage-2 palette query
    calls = []
    db.commit.side_effect = lambda: calls.append("commit")
    q.all.side_effect = lambda: (calls.append("palette_query"), [MagicMock(label="Demo")])[1]
    with patch("apps.api.tasks.autotag_tasks.SessionLocal", return_value=db):
        at.autotag_asset(str(asset.id), str(version.id))
    analyze.assert_called_once()
    assert version.ai_summary == "fresh summary"      # WHY: analysis cached for future re-tags
    assert calls.index("commit") < calls.index("palette_query")  # stage-1 cache committed before stage-2 palette query


@patch("apps.api.tasks.autotag_tasks.settings")
@patch("apps.api.tasks.autotag_tasks.publish_event")
def test_unsupported_type_skips(pub, cfg):
    cfg.gemini_api_key = "k"
    asset, version = _asset(atype=AssetType.audio), _version(summary="x")
    db = _db_returning(asset, version, ["Demo"])
    with patch("apps.api.tasks.autotag_tasks.SessionLocal", return_value=db):
        at.autotag_asset(str(asset.id), str(version.id))
    assert pub.call_args[0][1] == "autotag_skipped"
    assert pub.call_args[0][2]["reason"] == "unsupported_type"


@patch("apps.api.tasks.autotag_tasks.settings")
@patch("apps.api.tasks.autotag_tasks.publish_event")
@patch("apps.api.tasks.autotag_tasks._match")
def test_empty_palette_skips_match(match, pub, cfg):
    cfg.gemini_api_key = "k"
    asset, version = _asset(), _version(summary="x")
    db = _db_returning(asset, version, [])
    with patch("apps.api.tasks.autotag_tasks.SessionLocal", return_value=db):
        at.autotag_asset(str(asset.id), str(version.id))
    match.assert_not_called()
    assert pub.call_args[0][1] == "autotag_skipped"
    assert pub.call_args[0][2]["reason"] == "empty_palette"


@patch("apps.api.tasks.autotag_tasks.settings")
@patch("apps.api.tasks.autotag_tasks.publish_event")
@patch("apps.api.tasks.autotag_tasks._analyze")
def test_oversized_file_skips(analyze, pub, cfg):
    cfg.gemini_api_key = "k"
    asset, version = _asset(), _version(summary=None)
    # fresh version (ai_summary=None) so stage-1 is entered; media_file exceeds 1 GB cap
    media_file = MagicMock()
    media_file.file_size_bytes = MAX_AUTOTAG_BYTES + 1
    db = MagicMock()
    q = MagicMock(); db.query.return_value = q
    q.filter.return_value = q; q.order_by.return_value = q
    q.first.side_effect = [asset, version, media_file]
    with patch("apps.api.tasks.autotag_tasks.SessionLocal", return_value=db):
        at.autotag_asset(str(asset.id), str(version.id))
    analyze.assert_not_called()                        # WHY: OOM guard must block S3 read for large files
    assert pub.call_args[0][1] == "autotag_skipped"
    assert pub.call_args[0][2]["reason"] == "file_too_large"
