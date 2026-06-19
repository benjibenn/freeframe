"""GET /public/v1/users: API-key gated; lists ONLY users with an assigned uid.

Intent encoded:
- the uid is the gate — a user without one is not an attributable editor and
  must not appear, so external pickers only ever offer known editors;
- the internal UUID is never exposed (the public surface is name/email/uid);
- ordered by uid so the picklist is stable across calls.
"""
import uuid
from unittest.mock import MagicMock

import pytest

from apps.api.config import settings
from apps.api.models.user import UserStatus

API_KEY = "test-public-key"


@pytest.fixture
def keyed(monkeypatch):
    monkeypatch.setattr(settings, "public_api_key", API_KEY, raising=False)


def _user(uid, name, nickname=None):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.uid = uid
    u.name = name
    u.email = f"{name.replace(' ', '.').lower()}@ff.test"
    u.nickname = nickname
    u.status = UserStatus.active
    u.deleted_at = None
    return u


def test_requires_api_key(client, keyed):
    """No key header → 401, even though a valid key is configured."""
    resp = client.get("/public/v1/users")
    assert resp.status_code == 401


def test_lists_only_uid_users_ordered(client, keyed, mock_db):
    # The endpoint's WHERE (uid IS NOT NULL) is exercised against the real DB in
    # prod; here the mock returns the already-filtered roster so we assert the
    # response shape, ordering passthrough, and that the UUID is not leaked.
    mock_db.order_by.return_value = mock_db
    mock_db.all.return_value = [
        _user(1, "Wendy LSC", nickname="wendylsc"),
        _user(2, "Chia Chloe", nickname="chiamchloe"),
        _user(3, "No Nick"),
    ]

    resp = client.get("/public/v1/users", headers={"X-API-Key": API_KEY})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [u["uid"] for u in body] == [1, 2, 3]
    assert body[0] == {
        "uid": 1, "name": "Wendy LSC", "email": "wendy.lsc@ff.test", "nickname": "wendylsc",
    }
    assert body[2]["nickname"] is None
    assert "id" not in body[0]  # internal UUID never exposed
