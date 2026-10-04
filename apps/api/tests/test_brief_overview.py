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

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.models.asset import AssetType
from apps.api.models.user import UserStatus


def _make_user(*, is_superadmin=False, is_subadmin=False, name="User"):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.email = f"{name.replace(' ', '.').lower()}@example.com"
    u.name = name
    u.display_name = name
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


def _sub(link, editor):
    sub = MagicMock()
    sub.id = uuid.uuid4()
    sub.submission_link_id = link.id
    sub.user_id = editor.id
    sub.project_id = uuid.uuid4()
    sub.display_name = None
    sub.paid_at = None
    sub.created_at = datetime(2026, 9, 10, tzinfo=timezone.utc)
    return sub


def _queries(mock_db, *, light, page, subs=None, assets=None, users=None, before=()):
    """query() results in the order the endpoint asks: [editor/has_files filters]
    light rows, page rows, submissions, [assets, users]."""
    q_light = MagicMock()
    q_light.filter.return_value.order_by.return_value.all.return_value = light
    q_page = MagicMock()
    q_page.filter.return_value.all.return_value = page
    seq = list(before) + [q_light, q_page]
    if page:
        q_subs = MagicMock()
        q_subs.filter.return_value.all.return_value = subs or []
        seq.append(q_subs)
    if subs:
        q_assets = MagicMock()
        q_assets.filter.return_value.order_by.return_value.all.return_value = assets or []
        q_users = MagicMock()
        q_users.filter.return_value.all.return_value = users or []
        seq += [q_assets, q_users]
    mock_db.query.side_effect = seq


def test_superadmin_sees_submitter_and_thumbnail_but_not_the_brief_json(mock_db, monkeypatch):
    """The list carries who uploaded and a preview of it. The structured brief
    loads when a row is opened (GET /submission-links/{id}), so 25 rows do not
    carry 25 brief bodies."""
    from apps.api.routers import brief_overview as mod

    link = _link(brief_json={"title": "The test report"})
    editor = _make_user(name="Ada Editor")
    sub = _sub(link, editor)
    asset_id = uuid.uuid4()
    _queries(
        mock_db, light=[link], page=[link], subs=[sub],
        assets=[(asset_id, sub.project_id, "battery-report-v3.png", AssetType.image)],
        users=[editor],
    )
    monkeypatch.setattr(mod, "link_home_paths", lambda db, links: {link.id: link.taxonomy_path})
    monkeypatch.setattr(mod, "thumbnails_for_assets", lambda db, ids: {asset_id: "https://s3/thumb.jpg"})

    r = _client(mock_db, _make_user(is_superadmin=True, name="Boss")).get("/brief-overview")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    row = body["items"][0]
    assert row["title"] == "Static — iPhone 17 Pro Max"
    assert row["home_path"] == "ecom/Phones/Store 1/Iphone 17 Pro Max"
    assert "brief_json" not in row
    assert row["has_brief_json"] is True
    s = row["submissions"][0]
    assert s["user_name"] == "Ada Editor"
    assert s["files"][0]["thumbnail_url"] == "https://s3/thumb.jpg"


def test_first_page_is_25_of_many(mock_db, monkeypatch):
    from apps.api.routers import brief_overview as mod

    links = [_link(title=f"Brief {i}") for i in range(30)]
    _queries(mock_db, light=links, page=links[:25], subs=[])
    monkeypatch.setattr(mod, "link_home_paths", lambda db, ls: {})

    r = _client(mock_db, _make_user(is_superadmin=True)).get("/brief-overview")

    assert r.status_code == 200, r.text
    assert len(r.json()["items"]) == 25
    assert r.json()["total"] == 30


def test_limit_is_capped_at_100(mock_db):
    r = _client(mock_db, _make_user(is_superadmin=True)).get("/brief-overview?limit=101")
    assert r.status_code == 422


def test_audio_uploads_are_not_presigned_as_thumbnails(mock_db, monkeypatch):
    """Audio keeps waveform JSON where an image thumbnail would be."""
    from apps.api.routers import brief_overview as mod

    link = _link()
    editor = _make_user(name="Ada")
    sub = _sub(link, editor)
    audio_id, image_id = uuid.uuid4(), uuid.uuid4()
    _queries(
        mock_db, light=[link], page=[link], subs=[sub],
        assets=[
            (audio_id, sub.project_id, "vo.mp3", AssetType.audio),
            (image_id, sub.project_id, "ad.png", AssetType.image),
        ],
        users=[editor],
    )
    asked: list = []
    monkeypatch.setattr(mod, "link_home_paths", lambda db, ls: {})
    monkeypatch.setattr(mod, "thumbnails_for_assets", lambda db, ids: asked.extend(ids) or {})

    r = _client(mock_db, _make_user(is_superadmin=True)).get("/brief-overview")

    assert r.status_code == 200, r.text
    assert asked == [image_id]


def test_editor_filter_keeps_briefs_they_submitted_to(mock_db, monkeypatch):
    from apps.api.routers import brief_overview as mod

    on, off = _link(title="On"), _link(title="Off")
    q_editor = MagicMock()
    q_editor.filter.return_value.all.return_value = [(on.id,)]
    _queries(mock_db, light=[on, off], page=[on], subs=[], before=[q_editor])
    monkeypatch.setattr(mod, "link_home_paths", lambda db, ls: {})

    r = _client(mock_db, _make_user(is_superadmin=True)).get(f"/brief-overview?editor_id={uuid.uuid4()}")

    assert [row["id"] for row in r.json()["items"]] == [str(on.id)]
    assert r.json()["total"] == 1


def test_has_files_keeps_briefs_with_an_upload(mock_db, monkeypatch):
    from apps.api.routers import brief_overview as mod

    with_files, empty = _link(title="With"), _link(title="Empty")
    q_files = MagicMock()
    q_files.join.return_value.filter.return_value.distinct.return_value.all.return_value = [(with_files.id,)]
    _queries(mock_db, light=[with_files, empty], page=[with_files], subs=[], before=[q_files])
    monkeypatch.setattr(mod, "link_home_paths", lambda db, ls: {})

    r = _client(mock_db, _make_user(is_superadmin=True)).get("/brief-overview?has_files=true")

    assert [row["id"] for row in r.json()["items"]] == [str(with_files.id)]
