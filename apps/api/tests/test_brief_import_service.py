"""brief_import_service: resolve owner, store PDF, upsert request by source_brief_id."""
from unittest.mock import MagicMock
import pytest

from apps.api.services import brief_import_service as svc
from apps.api.config import settings


@pytest.fixture
def patched(monkeypatch):
    monkeypatch.setattr(svc.s3_service, "put_object", lambda *a, **k: None)
    monkeypatch.setattr(svc.s3_service, "generate_presigned_get_url", lambda *a, **k: "https://pdf.test/x")
    user = MagicMock(); user.id = "owner-id"
    monkeypatch.setattr(svc, "get_user_by_email", lambda db, email: user)
    return user, {}


def _db_no_existing():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    return db


def test_creates_new_request(patched):
    db = _db_no_existing()
    link, created = svc.upsert_brief_request(
        db, source_brief_id="B1", title="Brief: X",
        owner_email="a@b.com", pdf_bytes=b"%PDF-1.4 fake",
    )
    assert created is True
    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.source == "creative-flywheel"
    assert added.source_brief_id == "B1"
    assert added.created_by == "owner-id"
    # The brief body lives only in the PDF — never copied into instructions.
    assert added.instructions is None
    assert added.brief_pdf_s3_key == "briefs/B1.pdf"


def test_updates_existing_request(patched):
    existing = MagicMock(); existing.token = "tok"
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = existing
    link, created = svc.upsert_brief_request(
        db, source_brief_id="B1", title="New Title",
        owner_email="a@b.com", pdf_bytes=b"%PDF",
    )
    assert created is False
    assert existing.title == "New Title"
    # Re-import clears any markdown stored by older imports.
    assert existing.instructions is None
    db.add.assert_not_called()


def test_falls_back_to_configured_account(patched, monkeypatch):
    monkeypatch.setattr(settings, "brief_import_fallback_email", "cf@team.test", raising=False)
    monkeypatch.setattr(svc, "get_user_by_email", lambda db, email: None)
    db = _db_no_existing()
    link, created = svc.upsert_brief_request(
        db, source_brief_id="B2", title="T", owner_email=None, pdf_bytes=b"%PDF",
    )
    assert created is True
    assert db.add.call_count >= 1


def test_no_owner_no_fallback_raises(patched, monkeypatch):
    monkeypatch.setattr(settings, "brief_import_fallback_email", None, raising=False)
    monkeypatch.setattr(svc, "get_user_by_email", lambda db, email: None)
    db = _db_no_existing()
    with pytest.raises(ValueError):
        svc.upsert_brief_request(db, source_brief_id="B3", title="T", owner_email=None, pdf_bytes=b"%PDF")


def test_rejects_unsafe_source_brief_id(patched):
    db = _db_no_existing()
    with pytest.raises(ValueError):
        svc.upsert_brief_request(db, source_brief_id="../../etc/passwd", title="t", owner_email="a@b.com", pdf_bytes=b"%PDF")


def test_create_stamps_cf_lineage(patched):
    # CF ids + labels must be stored on the new request so they can be stamped
    # onto assets and surfaced in the UI later.
    db = _db_no_existing()
    svc.upsert_brief_request(
        db, source_brief_id="B4", title="T", owner_email="a@b.com", pdf_bytes=b"%PDF",
        persona_id="p1", angle_id="a1", brief_id="br1",
        persona_label="Busy Parent", angle_label="Time-saving", problem="Cooking takes too long",
    )
    added = db.add.call_args[0][0]
    assert added.persona_id == "p1"
    assert added.angle_id == "a1"
    assert added.brief_id == "br1"
    assert added.persona_label == "Busy Parent"
    assert added.angle_label == "Time-saving"
    assert added.problem == "Cooking takes too long"


def test_update_refreshes_cf_lineage(patched):
    # Re-import must refresh the CF lineage on the existing request.
    existing = MagicMock(); existing.token = "tok"
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = existing
    svc.upsert_brief_request(
        db, source_brief_id="B4", title="T2", owner_email="a@b.com", pdf_bytes=b"%PDF",
        persona_id="p2", angle_id="a2", brief_id="br2",
        persona_label="New Persona", angle_label="New Angle", problem="New Problem",
    )
    assert existing.persona_id == "p2"
    assert existing.angle_id == "a2"
    assert existing.brief_id == "br2"
    assert existing.persona_label == "New Persona"
    assert existing.angle_label == "New Angle"
    assert existing.problem == "New Problem"


def test_cf_ids_for_project_no_link_returns_nulls():
    # A project not under an imported request yields all-None (safe to splat).
    db = MagicMock()
    project = MagicMock(); project.submission_link_id = None
    assert svc.cf_ids_for_project(db, project) == {
        "cf_brief_id": None, "cf_persona_id": None, "cf_angle_id": None,
    }


def test_cf_ids_for_project_maps_link_fields():
    # Lineage is read off the project's SubmissionLink (brief/persona/angle ids).
    link = MagicMock(); link.brief_id = "br1"; link.persona_id = "p1"; link.angle_id = "a1"
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = link
    project = MagicMock(); project.submission_link_id = "link-id"
    assert svc.cf_ids_for_project(db, project) == {
        "cf_brief_id": "br1", "cf_persona_id": "p1", "cf_angle_id": "a1",
    }
