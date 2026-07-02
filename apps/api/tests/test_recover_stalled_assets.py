"""Tests for the transcode queue runaway fix.

These encode WHY the recovery task behaves as it does: an earlier version re-queued
every stuck video every 5 minutes with no dedup and no give-up, which flooded the
`transcoding` queue ~5000-deep and starved real uploads. The task must now
(a) re-queue a stuck video at most once per window, (b) give up (mark failed) on
videos stuck longer than any real transcode could run, and (c) never re-transcode a
version that is already `ready` (a stale/duplicate message).
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from apps.api.models.asset import ProcessingStatus, AssetType


def _version(age_minutes: int, status=ProcessingStatus.processing):
    v = MagicMock()
    v.id = uuid.uuid4()
    v.asset_id = uuid.uuid4()
    v.created_at = datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
    v.processing_status = status
    return v


def _video_asset(version):
    a = MagicMock()
    a.id = version.asset_id
    a.asset_type = AssetType.video
    a.project_id = uuid.uuid4()
    return a


def _run_recover(stalled_pairs, redis_set_returns=True):
    """Run recover_stalled_assets with a mocked DB/redis; return the mocks touched."""
    from apps.api.tasks import transcode_tasks as tt

    db = MagicMock()
    query = MagicMock()
    query.join.return_value = query
    query.filter.return_value = query
    query.all.return_value = stalled_pairs
    db.query.return_value = query

    redis_client = MagicMock()
    redis_client.set.return_value = redis_set_returns

    with patch.object(tt, "SessionLocal", return_value=db), \
         patch.object(tt.process_asset, "delay") as mock_delay, \
         patch.object(tt, "_publish_event") as mock_publish, \
         patch("redis.from_url", return_value=redis_client):
        tt.recover_stalled_assets()

    return mock_delay, mock_publish, redis_client, db


def test_stuck_video_requeued_once_with_dedup_lock():
    """A video stuck 45 min is re-queued exactly once, guarded by an NX lock."""
    v = _version(age_minutes=45)
    mock_delay, _publish, redis_client, _db = _run_recover([(v, _video_asset(v))])

    mock_delay.assert_called_once_with(str(v.asset_id), str(v.id))
    # dedup: single-shot NX lock with a TTL so the 5-min sweep can't re-queue it repeatedly
    args, kwargs = redis_client.set.call_args
    assert kwargs.get("nx") is True
    assert kwargs.get("ex") and kwargs["ex"] > 0


def test_dedup_lock_held_skips_requeue():
    """If the dedup lock is already held (set NX -> False), do NOT re-queue again."""
    v = _version(age_minutes=45)
    mock_delay, _publish, _redis, _db = _run_recover(
        [(v, _video_asset(v))], redis_set_returns=False
    )
    mock_delay.assert_not_called()


def test_long_stuck_video_gives_up_and_is_marked_failed():
    """A video stuck 7h is beyond any real transcode — mark failed, never re-queue."""
    v = _version(age_minutes=7 * 60)
    mock_delay, mock_publish, _redis, db = _run_recover([(v, _video_asset(v))])

    mock_delay.assert_not_called()
    assert v.processing_status == ProcessingStatus.failed
    mock_publish.assert_called_once()
    db.commit.assert_called_once()


def test_process_asset_skips_already_ready_version():
    """A stale/duplicate message for an already-ready version must not re-transcode."""
    from apps.api.tasks import transcode_tasks as tt

    v = _version(age_minutes=5, status=ProcessingStatus.ready)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = v

    with patch.object(tt, "SessionLocal", return_value=db), \
         patch.object(tt, "get_s3_client") as mock_s3:
        result = tt.process_asset.apply(args=[str(v.asset_id), str(v.id)]).get()

    assert result is None
    mock_s3.assert_not_called()  # returned before any transcode work
