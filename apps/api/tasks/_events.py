import json
import redis as sync_redis

try:
    from ..config import settings
except ImportError:
    from config import settings


def publish_event(project_id: str, event_type: str, payload: dict) -> None:
    """Publish an SSE event to the project's Redis channel. Best-effort."""
    try:
        r = sync_redis.from_url(settings.redis_url, decode_responses=True)
        message = json.dumps({"type": event_type, "payload": payload})
        r.publish(f"project:{project_id}", message)
        r.close()
    except Exception:
        pass  # SSE publish is best-effort
