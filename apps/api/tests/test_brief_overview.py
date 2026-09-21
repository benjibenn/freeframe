"""Tests for the superadmin brief-overview endpoint.

Intent encoded:
- the overview exposes EVERY brief and EVERY submitter across the platform, so it
  is superadmin-only ground. Sub-admins are deliberately excluded even though they
  can otherwise see all platform activity — that distinction is the whole point of
  the two flags, so it gets its own test.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.models.user import UserStatus


def _make_user(*, is_superadmin=False, is_subadmin=False, name="User"):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.email = f"{name.replace(' ', '.').lower()}@example.com"
    u.name = name
    u.status = UserStatus.active
    u.is_superadmin = is_superadmin
    u.is_subadmin = is_subadmin
    u.deleted_at = None
    return u


def _client(mock_db, current_user):
    from apps.api.routers.brief_overview import router
    from apps.api.database import get_db
    from apps.api.middleware.auth import get_current_user

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: current_user
    return TestClient(app, raise_server_exceptions=False)


def test_subadmin_is_denied(mock_db):
    """A sub-admin must NOT reach the overview: it spans every owner's briefs."""
    client = _client(mock_db, _make_user(is_subadmin=True, name="Sub Admin"))
    assert client.get("/brief-overview").status_code == 403


def test_plain_user_is_denied(mock_db):
    client = _client(mock_db, _make_user(name="Editor"))
    assert client.get("/brief-overview").status_code == 403


def _link(*, title="Static — iPhone 17 Pro Max", brief_json=None):
    l = MagicMock()
    l.id = uuid.uuid4()
    l.token = "tok-" + str(l.id)[:8]
    l.title = title
    l.instructions = None
    l.is_enabled = True
    l.expires_at = None
    l.created_at = datetime(2026, 9, 10, tzinfo=timezone.utc)
    l.home_project_id = uuid.uuid4()
    l.home_folder_id = uuid.uuid4()
    l.taxonomy_path = "ecom/Phones/Store 1/Iphone 17 Pro Max"
    l.persona_label = "Nervous First-Time Buyer"
    l.angle_label = "Performance"
    l.problem = "Battery health unknown"
    l.brief_pdf_s3_key = None
    l.brief_json = brief_json
    l.brief_reference_image_s3_keys = []
    l.brief_reference_video_s3_keys = []
    l.task_stage_id = None
    l.assignee_id = None
    return l


def test_superadmin_sees_brief_json_submitter_and_upload_thumbnail(mock_db, monkeypatch):
    """The whole point of the page: the structured brief, who uploaded, and a
    preview of what they uploaded — all without opening an edit or project page."""
    from apps.api.routers import brief_overview as mod

    brief = {"title": "The test report", "product": "iPhone 17 Pro Max"}
    link = _link(brief_json=brief)

    editor = _make_user(name="Ada Editor")
    sub = MagicMock()
    sub.id = uuid.uuid4()
    sub.submission_link_id = link.id
    sub.user_id = editor.id
    sub.project_id = uuid.uuid4()
    sub.display_name = None
    sub.paid_at = None
    sub.created_at = datetime(2026, 9, 10, tzinfo=timezone.utc)

    asset_id = uuid.uuid4()
    asset_row = (asset_id, sub.project_id, "battery-report-v3.png")

    q_links = MagicMock()
    q_links.filter.return_value.order_by.return_value.all.return_value = [link]
    q_subs = MagicMock()
    q_subs.filter.return_value.all.return_value = [sub]
    q_assets = MagicMock()
    q_assets.filter.return_value.order_by.return_value.all.return_value = [asset_row]
    q_users = MagicMock()
    q_users.filter.return_value.all.return_value = [editor]
    mock_db.query.side_effect = [q_links, q_subs, q_assets, q_users]

    monkeypatch.setattr(mod, "link_home_paths", lambda db, links: {link.id: link.taxonomy_path})
    monkeypatch.setattr(
        mod, "thumbnails_for_assets", lambda db, ids: {asset_id: "https://s3/thumb.jpg"}
    )

    client = _client(mock_db, _make_user(is_superadmin=True, name="Boss"))
    r = client.get("/brief-overview")
    assert r.status_code == 200, r.text

    rows = r.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["title"] == "Static — iPhone 17 Pro Max"
    assert row["home_path"] == "ecom/Phones/Store 1/Iphone 17 Pro Max"
    assert row["persona_label"] == "Nervous First-Time Buyer"
    assert row["angle_label"] == "Performance"
    assert row["problem"] == "Battery health unknown"
    # The structured brief travels in the list payload — that is what removes the
    # trip to the edit page.
    assert row["brief_json"] == brief
    assert row["submission_count"] == 1
    assert row["asset_count"] == 1

    s = row["submissions"][0]
    assert s["user_name"] == "Ada Editor"
    assert s["user_email"] == "ada.editor@example.com"
    assert s["files"][0]["name"] == "battery-report-v3.png"
    assert s["files"][0]["thumbnail_url"] == "https://s3/thumb.jpg"
