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
        db, source_brief_id="B1", title="Brief: X", instructions="do the thing",
        owner_email="a@b.com", pdf_bytes=b"%PDF-1.4 fake",
    )
    assert created is True
    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.source == "creative-flywheel"
    assert added.source_brief_id == "B1"
    assert added.created_by == "owner-id"
    assert added.instructions == "do the thing"
    assert added.brief_pdf_s3_key == "briefs/B1.pdf"


def test_updates_existing_request(patched):
    existing = MagicMock(); existing.token = "tok"
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = existing
    link, created = svc.upsert_brief_request(
        db, source_brief_id="B1", title="New Title", instructions="updated",
        owner_email="a@b.com", pdf_bytes=b"%PDF",
    )
    assert created is False
    assert existing.title == "New Title"
    assert existing.instructions == "updated"
    db.add.assert_not_called()


def test_falls_back_to_configured_account(patched, monkeypatch):
    monkeypatch.setattr(settings, "brief_import_fallback_email", "cf@team.test", raising=False)
    monkeypatch.setattr(svc, "get_user_by_email", lambda db, email: None)
    db = _db_no_existing()
    link, created = svc.upsert_brief_request(
        db, source_brief_id="B2", title="T", instructions="i", owner_email=None, pdf_bytes=b"%PDF",
    )
    assert created is True
    assert db.add.call_count >= 1


def test_no_owner_no_fallback_raises(patched, monkeypatch):
    monkeypatch.setattr(settings, "brief_import_fallback_email", None, raising=False)
    monkeypatch.setattr(svc, "get_user_by_email", lambda db, email: None)
    db = _db_no_existing()
    with pytest.raises(ValueError):
        svc.upsert_brief_request(db, source_brief_id="B3", title="T", instructions="i", owner_email=None, pdf_bytes=b"%PDF")


def test_rejects_unsafe_source_brief_id(patched):
    db = _db_no_existing()
    with pytest.raises(ValueError):
        svc.upsert_brief_request(db, source_brief_id="../../etc/passwd", title="t", instructions="i", owner_email="a@b.com", pdf_bytes=b"%PDF")
