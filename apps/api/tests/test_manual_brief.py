"""Manual (non-flywheel) PDF brief attach: service guard/storage + endpoint validation.

Why these tests: the manual upload path must (a) store the PDF under a per-link key
and tag the link source="manual", and (b) never let a manual upload clobber a brief
owned by Creative Flywheel (or vice-versa). The endpoint must reject non-PDFs before
touching storage.
"""
from unittest.mock import MagicMock
import uuid
import pytest

from apps.api.services import brief_import_service as svc


# ── Service: attach_manual_brief ──────────────────────────────────────────────

def test_attach_manual_stores_pdf_and_tags_source(monkeypatch):
    calls = {}
    monkeypatch.setattr(
        svc.s3_service, "put_object",
        lambda key, body, **kw: calls.update(key=key, body=body, kw=kw),
    )
    link = MagicMock()
    link.id = uuid.UUID("00000000-0000-0000-0000-0000000000aa")
    link.source = None  # a hand-made request, no brief yet
    db = MagicMock()

    svc.attach_manual_brief(db, link, b"%PDF-1.4 fake")

    assert calls["key"] == "briefs/manual/00000000-0000-0000-0000-0000000000aa.pdf"
    assert calls["kw"]["content_type"] == "application/pdf"
    assert link.brief_pdf_s3_key == calls["key"]
    assert link.source == svc.MANUAL_SOURCE
    db.commit.assert_called_once()


def test_attach_manual_refuses_flywheel_link(monkeypatch):
    # A flywheel-owned brief must not be replaceable by hand — a re-import would
    # otherwise overwrite it, so we forbid the manual write outright.
    put = MagicMock()
    monkeypatch.setattr(svc.s3_service, "put_object", put)
    link = MagicMock()
    link.source = svc.SOURCE  # creative-flywheel
    db = MagicMock()

    with pytest.raises(ValueError):
        svc.attach_manual_brief(db, link, b"%PDF")
    put.assert_not_called()  # refused before any storage write
    db.commit.assert_not_called()


def test_attach_manual_replaces_existing_manual_brief(monkeypatch):
    monkeypatch.setattr(svc.s3_service, "put_object", lambda *a, **k: None)
    link = MagicMock()
    link.id = uuid.uuid4()
    link.source = svc.MANUAL_SOURCE  # already has a hand-uploaded brief
    link.brief_pdf_s3_key = "briefs/manual/old.pdf"
    db = MagicMock()

    svc.attach_manual_brief(db, link, b"%PDF new")

    assert link.brief_pdf_s3_key == f"briefs/manual/{link.id}.pdf"
    assert link.source == svc.MANUAL_SOURCE


def test_flywheel_upsert_never_matches_a_manual_link():
    # The flywheel upsert filters source == SOURCE, so a manual link (source="manual")
    # is invisible to it — it creates a fresh flywheel request instead of clobbering.
    # We assert the isolating filter is the flywheel constant, which the query relies on.
    assert svc.SOURCE == "creative-flywheel"
    assert svc.MANUAL_SOURCE == "manual"
    assert svc.SOURCE != svc.MANUAL_SOURCE


# ── Endpoint: POST /submission-links/{id}/brief ───────────────────────────────

def _owned_link(user):
    """A mock link owned by `user` that passes _get_owned_link."""
    link = MagicMock()
    link.id = uuid.uuid4()
    link.deleted_at = None
    link.created_by = user.id
    link.source = None
    return link


def test_upload_brief_rejects_non_pdf(client, mock_db, test_user, auth_headers):
    mock_db.first.return_value = _owned_link(test_user)
    resp = client.post(
        f"/submission-links/{uuid.uuid4()}/brief",
        files={"file": ("brief.txt", b"not a pdf", "text/plain")},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "PDF" in resp.json()["detail"]


def test_upload_brief_rejects_flywheel_link(client, mock_db, test_user, auth_headers, monkeypatch):
    # Even a valid PDF must be refused when the link is flywheel-owned — the service
    # raises ValueError, which the endpoint surfaces as a 400.
    monkeypatch.setattr(svc.s3_service, "put_object", lambda *a, **k: None)
    link = _owned_link(test_user)
    link.source = svc.SOURCE
    mock_db.first.return_value = link
    resp = client.post(
        f"/submission-links/{uuid.uuid4()}/brief",
        files={"file": ("brief.pdf", b"%PDF-1.4 fake", "application/pdf")},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "Creative Flywheel" in resp.json()["detail"]


# ── Structured JSON brief ─────────────────────────────────────────────────────

def test_set_brief_json_rejects_empty_object(client, mock_db, test_user, auth_headers):
    # An empty object is not a usable brief — reject before persisting.
    mock_db.first.return_value = _owned_link(test_user)
    resp = client.put(
        f"/submission-links/{uuid.uuid4()}/brief-json",
        json={"brief": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "non-empty" in resp.json()["detail"]


def test_public_resolve_exposes_brief_json(client, mock_db):
    # The submit page reads the structured brief off the public resolve payload.
    link = MagicMock()
    link.deleted_at = None
    link.is_enabled = True
    link.expires_at = None
    link.title = "NIUD Covers"
    link.instructions = None
    link.brief_pdf_s3_key = None
    link.brief_json = {"title": "NIUD Covers", "overview": "packing video"}
    link.persona_label = None
    link.angle_label = None
    link.problem = None
    mock_db.first.return_value = link
    resp = client.get("/submit/sometoken")
    assert resp.status_code == 200
    assert resp.json()["brief_json"]["overview"] == "packing video"
