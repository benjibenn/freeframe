"""The reference-video confirm endpoint trusts a client-supplied S3 key. The prefix
guard is what stops a caller from pointing their link at an arbitrary object they
don't own — pin that it rejects a foreign key and accepts the presigned one."""
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from apps.api.routers import submissions as subs
from apps.api.schemas.submission import ReferenceVideoConfirm


def test_confirm_rejects_key_outside_this_links_prefix(monkeypatch):
    link = MagicMock(); link.id = uuid.uuid4()
    monkeypatch.setattr(subs, "_get_owned_link", lambda db, lid, u: link)
    other = uuid.uuid4()
    with pytest.raises(HTTPException) as ei:
        subs.confirm_reference_video(
            link.id, ReferenceVideoConfirm(s3_key=f"briefs/manual/{other}-reference.mp4"),
            db=MagicMock(), current_user=MagicMock(),
        )
    assert ei.value.status_code == 400


def _valid_link():
    """A mock link whose attributes pass SubmissionLinkResponse.model_validate."""
    from datetime import datetime, timezone
    link = MagicMock()
    link.id = uuid.uuid4()
    link.token = "tok"
    link.title = "T"
    link.instructions = None
    link.is_enabled = True
    link.expires_at = None
    link.created_at = datetime.now(timezone.utc)
    link.reference_project_id = None
    link.persona_label = link.angle_label = link.problem = None
    link.brief_pdf_s3_key = None
    link.brief_json = None
    return link


def test_confirm_accepts_key_this_link_would_have_presigned(monkeypatch):
    link = _valid_link()
    monkeypatch.setattr(subs, "_get_owned_link", lambda db, lid, u: link)
    monkeypatch.setattr(subs, "_count_map", lambda db, ids: {})
    key = f"{subs._reference_video_prefix(link.id)}.mp4"
    resp = subs.confirm_reference_video(
        link.id, ReferenceVideoConfirm(s3_key=key), db=MagicMock(), current_user=MagicMock(),
    )
    assert link.brief_reference_video_s3_key == key
    assert resp.has_reference_video is True
