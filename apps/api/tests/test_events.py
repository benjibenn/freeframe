import json
from unittest.mock import MagicMock, patch

from apps.api.tasks._events import publish_event


def test_publish_event_publishes_json_to_project_channel():
    fake_redis = MagicMock()
    with patch("apps.api.tasks._events.sync_redis.from_url", return_value=fake_redis):
        publish_event("proj-1", "autotag_complete", {"asset_id": "a1", "applied": ["demo"]})
    channel, message = fake_redis.publish.call_args[0]
    assert channel == "project:proj-1"
    assert '"autotag_complete"' in message
    # Real shape: {"type": ..., "payload": {...}} — NOT **payload spread
    parsed = json.loads(message)
    assert parsed["type"] == "autotag_complete"
    assert parsed["payload"] == {"asset_id": "a1", "applied": ["demo"]}
