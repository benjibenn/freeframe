"""Brief reference downloads: forced-attachment presigning, and the audit row.

WHY these four pin what they pin:

* Inline vs attachment is not cosmetic. The reference routes 302 to S3, and an
  anchor's `download` attribute is ignored cross-origin — Content-Disposition on
  the presign is the *only* thing that makes a browser save the file. Equally, the
  default must stay inline or <video> loses Range seeking through the redirect.
* The download is the auditable event, so it is logged in the endpoint where a
  client cannot skip it — and logged once per file, with no dedup window, because
  "Download all" over N references must leave N rows or the trail under-reports.
* /submit is public. A guest download has to log with user_id=None, not blow up.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

from apps.api.routers import submissions as subs


def _link_with_refs():
    link = MagicMock()
    link.id = uuid.uuid4()
    link.token = "tok"
    link.title = "Spring campaign"
    link.deleted_at = None
    link.is_enabled = True
    link.expires_at = None
    link.home_project_id = uuid.uuid4()
    link.brief_reference_image_s3_keys = ["briefs/manual/a.jpg", "briefs/manual/b.png"]
    link.brief_reference_video_s3_keys = ["briefs/manual/c.mp4"]
    return link


def _db_returning(link):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = link
    return db


def test_default_stays_inline_so_video_seeking_survives(monkeypatch):
    """No ?download → no Content-Disposition, or <video> can't Range-seek the redirect."""
    seen = {}

    def fake_presign(key, expires_in=3600, download_filename=None):
        seen["download_filename"] = download_filename
        return "https://s3/inline"

    monkeypatch.setattr(subs.s3_service, "generate_presigned_get_url", fake_presign)
    logged = MagicMock()
    monkeypatch.setattr(subs, "log_activity", logged)

    link = _link_with_refs()
    resp = subs._reference_redirect(_db_returning(link), "tok", 0, "image")

    assert resp.status_code == 307
    assert seen["download_filename"] is None
    assert not logged.called, "a plain view is not a download and must not be logged"


def test_download_flag_presigns_as_attachment_with_indexed_filename(monkeypatch):
    seen = {}

    def fake_presign(key, expires_in=3600, download_filename=None):
        seen["key"] = key
        seen["download_filename"] = download_filename
        return "https://s3/attachment"

    monkeypatch.setattr(subs.s3_service, "generate_presigned_get_url", fake_presign)
    monkeypatch.setattr(subs, "log_activity", MagicMock())

    link = _link_with_refs()
    subs._reference_redirect(_db_returning(link), "tok", 1, "image", download=True)

    assert seen["key"] == "briefs/manual/b.png"
    # Extension carried over from the S3 key so the saved file opens in something.
    assert seen["download_filename"] == "reference-image-2.png"


def test_download_logs_one_row_per_call_with_no_dedup(monkeypatch):
    """Download-all over N files must leave N rows — dedup here would hide exfiltration."""
    monkeypatch.setattr(
        subs.s3_service, "generate_presigned_get_url",
        lambda key, expires_in=3600, download_filename=None: "https://s3/x",
    )
    logged = MagicMock()
    monkeypatch.setattr(subs, "log_activity", logged)

    link = _link_with_refs()
    db = _db_returning(link)
    user = MagicMock(id=uuid.uuid4())

    subs._reference_redirect(db, "tok", 0, "image", download=True, current_user=user)
    subs._reference_redirect(db, "tok", 0, "image", download=True, current_user=user)

    assert logged.call_count == 2

    kwargs = logged.call_args.kwargs
    assert kwargs["action"] == "brief_reference_downloaded"
    assert kwargs["user_id"] == user.id
    assert kwargs["project_id"] == link.home_project_id
    # References are bare S3 keys on the link, not assets — no asset_id to carry.
    assert "asset_id" not in kwargs
    assert kwargs["payload"]["submission_link_id"] == str(link.id)
    assert kwargs["payload"]["kind"] == "image"
    assert kwargs["payload"]["index"] == 0
    assert kwargs["payload"]["filename"] == "reference-image-1.jpg"


def test_guest_download_logs_anonymously(monkeypatch):
    """/submit is public: no signed-in user must still record the event, not 500."""
    monkeypatch.setattr(
        subs.s3_service, "generate_presigned_get_url",
        lambda key, expires_in=3600, download_filename=None: "https://s3/x",
    )
    logged = MagicMock()
    monkeypatch.setattr(subs, "log_activity", logged)

    link = _link_with_refs()
    resp = subs._reference_redirect(
        _db_returning(link), "tok", 0, "video", download=True, current_user=None
    )

    assert resp.status_code == 307
    assert logged.call_args.kwargs["user_id"] is None
    assert logged.call_args.kwargs["payload"]["filename"] == "reference-video-1.mp4"


def test_brief_reference_downloaded_is_tracking_noise():
    """It rides with asset_downloaded for retention pruning and the unread badge —
    an audit row, not a team event worth notifying anyone about."""
    from apps.api.models.activity import ActivityAction, TRACKING_ACTIONS

    assert ActivityAction.brief_reference_downloaded.value in TRACKING_ACTIONS


def test_expired_link_cannot_be_downloaded(monkeypatch):
    """The download flag must not become a way around the link's own gate."""
    import pytest
    from fastapi import HTTPException

    monkeypatch.setattr(subs, "log_activity", MagicMock())
    link = _link_with_refs()
    link.expires_at = datetime(2000, 1, 1, tzinfo=timezone.utc)

    with pytest.raises(HTTPException) as ei:
        subs._reference_redirect(_db_returning(link), "tok", 0, "image", download=True)
    assert ei.value.status_code == 410
