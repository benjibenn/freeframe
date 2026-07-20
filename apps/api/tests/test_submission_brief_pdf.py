"""Tests for has_brief flag on resolve_submission_link and the brief PDF download route."""
from unittest.mock import MagicMock, patch
import pytest


def _make_link(brief_pdf_s3_key=None):
    """Return a mock SubmissionLink that passes _validate_active."""
    link = MagicMock()
    link.deleted_at = None
    link.is_enabled = True
    link.expires_at = None
    link.title = "Test Brief"
    link.instructions = "Do the thing"
    link.brief_pdf_s3_key = brief_pdf_s3_key
    link.brief_json = None
    link.brief_reference_video_s3_key = None
    # Hand-made request: no CF lineage (must be real None, not a MagicMock, so the
    # Optional[str] response fields validate).
    link.persona_label = None
    link.angle_label = None
    link.problem = None
    return link


# ── resolve: has_brief flag ───────────────────────────────────────────────────

def test_resolve_has_brief_true(client, mock_db):
    mock_db.first.return_value = _make_link(brief_pdf_s3_key="briefs/B1.pdf")
    resp = client.get("/submit/sometoken")
    assert resp.status_code == 200
    assert resp.json()["has_brief"] is True


def test_resolve_has_brief_false(client, mock_db):
    mock_db.first.return_value = _make_link(brief_pdf_s3_key=None)
    resp = client.get("/submit/sometoken")
    assert resp.status_code == 200
    assert resp.json()["has_brief"] is False


# ── GET /submit/{token}/brief.pdf ─────────────────────────────────────────────

def test_brief_pdf_redirects(client, mock_db):
    mock_db.first.return_value = _make_link(brief_pdf_s3_key="briefs/B1.pdf")
    with patch("apps.api.routers.submissions.s3_service.generate_presigned_get_url",
               return_value="https://s3.test/brief.pdf"):
        resp = client.get("/submit/sometoken/brief.pdf", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "https://s3.test/brief.pdf"


def test_brief_pdf_404_when_no_key(client, mock_db):
    mock_db.first.return_value = _make_link(brief_pdf_s3_key=None)
    resp = client.get("/submit/sometoken/brief.pdf", follow_redirects=False)
    assert resp.status_code == 404
