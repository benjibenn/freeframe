"""log_asset_activity collapses repeat (user, asset, action) events inside a
5-minute window. WHY: opening/replaying the same asset fires many client events;
without dedup the admin timeline floods and per-user traceability becomes noise.
The download path relies on the same helper, so the guarantee must hold there too.
"""
import uuid
from unittest.mock import MagicMock

from apps.api.services.activity_service import log_asset_activity
from apps.api.models.activity import ActivityAction


def test_writes_when_no_recent_duplicate():
    db = MagicMock()
    db.query.return_value = db
    db.filter.return_value = db
    db.first.return_value = None  # no recent duplicate
    wrote = log_asset_activity(
        db, user_id=uuid.uuid4(), asset_id=uuid.uuid4(), project_id=uuid.uuid4(),
        action=ActivityAction.asset_viewed.value,
    )
    assert wrote is True
    assert db.add.called


def test_skips_recent_duplicate():
    db = MagicMock()
    db.query.return_value = db
    db.filter.return_value = db
    db.first.return_value = MagicMock()  # a recent duplicate exists
    wrote = log_asset_activity(
        db, user_id=uuid.uuid4(), asset_id=uuid.uuid4(), project_id=uuid.uuid4(),
        action=ActivityAction.asset_viewed.value,
    )
    assert wrote is False
    assert not db.add.called
