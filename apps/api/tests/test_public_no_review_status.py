"""GET /public/v1/videos no longer exposes review status.

This is a deliberate breaking change for external consumers (UploadUnicorn →
Meta). Two halves, and the second is the one that actually changes results:

- the `status` field is gone from each item, so nothing downstream can branch on
  a workflow concept the product no longer has;
- `?status=` is gone as a filter, and archived assets are excluded
  unconditionally instead. Callers previously used `?status=` to skip archived
  videos themselves; without the param, leaving them in would silently start
  shipping archived work to ad platforms.

The list query runs against PostgreSQL in prod and the DB is mocked here, so
these assert the API contract rather than row filtering.
"""
import pytest

from apps.api.config import settings

API_KEY = "test-public-key"


@pytest.fixture
def keyed(monkeypatch):
    monkeypatch.setattr(settings, "public_api_key", API_KEY, raising=False)


def test_item_schema_has_no_status():
    from apps.api.schemas.public_api import PublicVideoItem

    assert "status" not in PublicVideoItem.model_fields


def test_status_is_not_a_declared_query_param(client):
    """A removed param must not linger in the OpenAPI contract — external callers
    read it to discover the filters they are allowed to send."""
    schema = client.get("/openapi.json").json()
    params = schema["paths"]["/public/v1/videos"]["get"].get("parameters", [])
    names = {p["name"] for p in params}
    assert "status" not in names
    # The filters that survived, so this test fails loudly if the route is gutted
    # rather than passing vacuously on an empty parameter list.
    assert {"search", "author", "run_as_ad"} <= names


def test_stale_status_param_is_ignored_not_rejected(client, keyed, mock_db):
    """An external caller still sending ?status=approved gets a normal page rather
    than a 422 — the filter stops applying, but their integration keeps working."""
    mock_db.count.return_value = 0
    mock_db.all.return_value = []

    resp = client.get(
        "/public/v1/videos",
        params={"status": "approved"},
        headers={"X-API-Key": API_KEY},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["items"] == []
