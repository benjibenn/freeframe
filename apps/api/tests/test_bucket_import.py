"""
Bucket-scan importer service tests.

Tests drive import_service.import_prefix() directly with a mock DB and patched
list_objects_v2 / send_task_safe so no live S3 or Celery is needed.

Intent captured by each case:
  (a) Media files (.mp4 + .png) → each becomes an Asset+AssetVersion+MediaFile,
      transcode task enqueued for every one.
  (b) Non-media extensions (.txt) → skipped; nothing created, no task dispatched.
  (c) A key already present as MediaFile.s3_key_raw in this project → dedupe; skipped,
      not re-imported.  The dedupe query now joins through AssetVersion→Asset to scope
      to project_id.
  (d) Keys ending in "/" (S3 directory markers) → skipped unconditionally.
  (e) Zero-size objects → skipped.
  (f) One poison object (raises mid-loop) is captured in "failed"; others still import.
  (g) When listing returns MAX_IMPORT_OBJECTS items, truncated=True is returned.
"""
import uuid
from unittest.mock import MagicMock, patch, call

import pytest

import apps.api.services.import_service as svc


PROJECT_ID = uuid.uuid4()
CREATED_BY = uuid.uuid4()


def _make_db(hit_key: str | None = None) -> MagicMock:
    """Mock SQLAlchemy Session.

    The dedupe query chain is: query().join().join().filter().first()
    We make join() return the same mock so chaining works, and wire filter()
    to return a hit (non-None) when hit_key is provided.
    """
    db = MagicMock()

    # join() must return something that also has .join() and .filter()
    # We achieve this by making the query mock return itself on join() calls.
    query_mock = MagicMock()
    query_mock.join.return_value = query_mock  # chained .join().join()
    query_mock.filter.return_value = query_mock
    query_mock.first.return_value = None       # default: no dedupe hit
    db.query.return_value = query_mock

    if hit_key:
        # Override filter() to return a hit when the key string appears in args
        def smart_filter(*args, **kwargs):
            result_mock = MagicMock()
            result_mock.join.return_value = result_mock
            result_mock.filter.return_value = result_mock
            # Inspect filter args for the key value
            for a in args:
                if hasattr(a, "right") and hasattr(a.right, "value"):
                    if a.right.value == hit_key:
                        result_mock.first.return_value = MagicMock()  # hit
                        return result_mock
            result_mock.first.return_value = None
            return result_mock

        query_mock.filter = smart_filter

    db.add.return_value = None
    db.flush.return_value = None
    db.commit.return_value = None
    db.rollback.return_value = None
    return db


# ── (a) Two media files imported ────────────────────────────────────────────

def test_imports_mp4_and_png():
    """A .mp4 and a .png under the prefix each become an asset; transcode enqueued twice."""
    objects = [
        {"key": "uploads/proj/clip.mp4", "size": 1_000_000},
        {"key": "uploads/proj/thumb.png", "size": 50_000},
    ]
    db = _make_db()

    with patch.object(svc, "list_objects_v2", return_value=objects) as mock_list, \
         patch("apps.api.services.import_service.send_task_safe") as mock_send:

        result = svc.import_prefix(db, PROJECT_ID, "uploads/proj/", CREATED_BY)

    assert result["imported"] == 2, "Both media files must be imported"
    assert result["skipped"] == 0
    assert result["failed"] == []
    assert result["truncated"] is False
    assert len(result["assets"]) == 2

    # Two transcode tasks dispatched — one per asset
    assert mock_send.call_count == 2, "send_task_safe must fire once per imported asset"

    # DB objects created: 2 × (Asset + AssetVersion + MediaFile) = 6 adds, 4 flushes, 2 commits
    assert db.add.call_count == 6
    assert db.flush.call_count == 4
    assert db.commit.call_count == 2

    # Names reflect basenames
    names = {a["name"] for a in result["assets"]}
    assert names == {"clip.mp4", "thumb.png"}


# ── (b) Non-media extension skipped ─────────────────────────────────────────

def test_skips_non_media_extension():
    """.txt is not in EXT_TO_MIME → skipped; no DB writes, no task dispatched."""
    objects = [{"key": "uploads/proj/readme.txt", "size": 1_234}]
    db = _make_db()

    with patch.object(svc, "list_objects_v2", return_value=objects), \
         patch("apps.api.services.import_service.send_task_safe") as mock_send:

        result = svc.import_prefix(db, PROJECT_ID, "uploads/proj/", CREATED_BY)

    assert result["imported"] == 0
    assert result["skipped"] == 1, ".txt must count as skipped"
    assert result["assets"] == []
    assert result["failed"] == []
    mock_send.assert_not_called()
    db.add.assert_not_called()


# ── (c) Already-registered key deduped ──────────────────────────────────────

def test_dedupes_existing_s3_key():
    """An object whose s3_key_raw is already in MediaFile for this project is skipped."""
    existing_key = "uploads/proj/existing.mp4"
    objects = [{"key": existing_key, "size": 2_000_000}]

    # Build a db whose join().join().filter().first() always returns a hit
    db = MagicMock()
    hit = MagicMock()  # simulates an existing MediaFile row

    chain = MagicMock()
    chain.join.return_value = chain
    chain.filter.return_value = chain
    chain.first.return_value = hit  # always a hit — only one key in this test
    db.query.return_value = chain
    db.add.return_value = None
    db.rollback.return_value = None

    with patch.object(svc, "list_objects_v2", return_value=objects), \
         patch("apps.api.services.import_service.send_task_safe") as mock_send:

        result = svc.import_prefix(db, PROJECT_ID, "uploads/proj/", CREATED_BY)

    assert result["imported"] == 0
    assert result["skipped"] == 1, "Already-registered key must be counted as skipped"
    assert result["assets"] == []
    assert result["failed"] == []
    mock_send.assert_not_called()
    db.add.assert_not_called()


# ── (d) Directory marker (key ending in "/") skipped ────────────────────────

def test_skips_directory_markers():
    """S3 'directory' objects (key ends in '/') must be skipped unconditionally."""
    objects = [
        {"key": "uploads/proj/", "size": 0},
        {"key": "uploads/proj/subfolder/", "size": 0},
    ]
    db = _make_db()

    with patch.object(svc, "list_objects_v2", return_value=objects), \
         patch("apps.api.services.import_service.send_task_safe") as mock_send:

        result = svc.import_prefix(db, PROJECT_ID, "uploads/proj/", CREATED_BY)

    assert result["imported"] == 0
    assert result["skipped"] == 2, "Each directory marker must count as skipped"
    assert result["assets"] == []
    assert result["failed"] == []
    mock_send.assert_not_called()
    db.add.assert_not_called()


# ── (e) Zero-size object skipped ────────────────────────────────────────────

def test_skips_zero_size_objects():
    """Objects with size 0 are placeholders and must be skipped."""
    objects = [{"key": "uploads/proj/empty.mp4", "size": 0}]
    db = _make_db()

    with patch.object(svc, "list_objects_v2", return_value=objects), \
         patch("apps.api.services.import_service.send_task_safe") as mock_send:

        result = svc.import_prefix(db, PROJECT_ID, "uploads/proj/", CREATED_BY)

    assert result["imported"] == 0
    assert result["skipped"] == 1
    assert result["failed"] == []
    mock_send.assert_not_called()


# ── (f) Poison object captured in "failed", others still import ─────────────

def test_poison_object_captured_in_failed():
    """One object that raises mid-loop is captured in failed[]; others import successfully.

    Intent: a single bad key must not abort the whole batch or leave a partial commit.
    The service rolls back the failed object's transaction and continues.
    """
    objects = [
        {"key": "uploads/proj/good1.mp4", "size": 1_000_000},
        {"key": "uploads/proj/poison.mp4", "size": 2_000_000},
        {"key": "uploads/proj/good2.png", "size": 50_000},
    ]
    db = _make_db()

    call_count = {"n": 0}

    original_add = db.add.side_effect

    def add_side_effect(obj):
        # Raise on the Asset add for the second media file (poison)
        from apps.api.models.asset import Asset
        if isinstance(obj, Asset):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("Simulated DB error for poison object")

    db.add.side_effect = add_side_effect

    with patch.object(svc, "list_objects_v2", return_value=objects), \
         patch("apps.api.services.import_service.send_task_safe") as mock_send:

        result = svc.import_prefix(db, PROJECT_ID, "uploads/proj/", CREATED_BY)

    assert result["imported"] == 2, "good1 and good2 must still import"
    assert result["skipped"] == 0
    assert len(result["failed"]) == 1, "exactly one object must be captured in failed"
    assert result["failed"][0]["key"] == "uploads/proj/poison.mp4"
    assert "Simulated DB error" in result["failed"][0]["error"]
    assert mock_send.call_count == 2, "transcode task dispatched only for successful imports"
    # rollback called once for the poison object
    db.rollback.assert_called_once()


# ── (g) Truncation flag when listing hits MAX_IMPORT_OBJECTS ────────────────

def test_truncated_flag_when_listing_hits_limit():
    """When listing returns MAX_IMPORT_OBJECTS items, truncated=True is returned.

    Intent: callers need to know the scan was capped and there may be more objects.
    """
    # Build exactly MAX_IMPORT_OBJECTS objects (all non-media so we don't have to
    # mock DB writes — we only care about the truncated flag here)
    objects = [
        {"key": f"uploads/proj/file_{i}.txt", "size": 100}
        for i in range(svc.MAX_IMPORT_OBJECTS)
    ]
    db = _make_db()

    with patch.object(svc, "list_objects_v2", return_value=objects), \
         patch("apps.api.services.import_service.send_task_safe"):

        result = svc.import_prefix(db, PROJECT_ID, "uploads/proj/", CREATED_BY)

    assert result["truncated"] is True, (
        "truncated must be True when listing returns MAX_IMPORT_OBJECTS items"
    )
    assert result["skipped"] == svc.MAX_IMPORT_OBJECTS
    assert result["imported"] == 0
