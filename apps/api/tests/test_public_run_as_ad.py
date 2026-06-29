"""GET /public/v1/videos: the `run_as_ad` filter is wired and typed as a bool.

Intent encoded:
- external platforms can ask for only ad-ready videos (`run_as_ad=true`);
- the flag is a real boolean query param (a non-bool value is rejected), so
  callers get a clear 422 rather than a silently-ignored filter.

The list query itself runs against PostgreSQL in prod; the mock DB here returns
an empty page, so these assert the param contract rather than row filtering.
"""
import pytest

from apps.api.config import settings

API_KEY = "test-public-key"


@pytest.fixture
def keyed(monkeypatch):
    monkeypatch.setattr(settings, "public_api_key", API_KEY, raising=False)


def test_accepts_run_as_ad_filter(client, keyed, mock_db):
    mock_db.count.return_value = 0
    mock_db.all.return_value = []

    resp = client.get(
        "/public/v1/videos",
        params={"run_as_ad": "true"},
        headers={"X-API-Key": API_KEY},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {"items": [], "total": 0, "page": 1, "per_page": 50}


def test_rejects_non_boolean_run_as_ad(client, keyed):
    resp = client.get(
        "/public/v1/videos",
        params={"run_as_ad": "maybe"},
        headers={"X-API-Key": API_KEY},
    )

    assert resp.status_code == 422
