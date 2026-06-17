"""POST /public/v1/briefs: API-key gated, multipart, delegates to the service."""
from unittest.mock import MagicMock
import pytest

from apps.api.main import app
from apps.api.services import brief_import_service
from apps.api.config import settings

API_KEY = "test-public-key"


@pytest.fixture
def keyed(monkeypatch):
    monkeypatch.setattr(settings, "public_api_key", API_KEY, raising=False)
    monkeypatch.setattr(settings, "frontend_url", "https://ff.test", raising=False)


def _post(client, **over):
    files = over.get("files", {"pdf": ("b.pdf", b"%PDF-1.4 fake", "application/pdf")})
    data = {"source_brief_id": "B1", "title": "Brief: X", "instructions": "do it", "owner_email": "a@b.com"}
    data.update(over.get("data", {}))
    return client.post("/public/v1/briefs", data=data, files=files,
                       headers={"X-API-Key": over.get("key", API_KEY)})


def test_requires_api_key(client, keyed):
    files = {"pdf": ("b.pdf", b"%PDF", "application/pdf")}
    resp = client.post("/public/v1/briefs", data={"source_brief_id": "B1", "title": "t", "instructions": "i"}, files=files)
    assert resp.status_code == 401


def test_creates_request(client, keyed, monkeypatch):
    link = MagicMock(); link.token = "tok123"
    monkeypatch.setattr(brief_import_service, "upsert_brief_request", lambda db, **k: (link, True))
    resp = _post(client)
    assert resp.status_code == 200
    assert resp.json() == {"request_url": "https://ff.test/submit/tok123", "token": "tok123", "created": True}


def test_empty_pdf_is_400(client, keyed):
    resp = _post(client, files={"pdf": ("b.pdf", b"", "application/pdf")})
    assert resp.status_code == 400


def test_no_owner_no_fallback_is_422(client, keyed, monkeypatch):
    def boom(db, **k):
        raise ValueError("no owner")
    monkeypatch.setattr(brief_import_service, "upsert_brief_request", boom)
    resp = _post(client, data={"owner_email": ""})
    assert resp.status_code == 422
