from datetime import datetime, timedelta, timezone

from .celery_app import celery_app
from ..database import SessionLocal
from ..models.activity import ActivityLog, ActivityAction

RETENTION_DAYS = 90

# ONLY these actions are pruned. Team-action rows (created/commented/approved/…)
# are retained indefinitely — never add them here.
TRACKING_ACTIONS = (
    ActivityAction.asset_clicked.value,
    ActivityAction.asset_viewed.value,
    ActivityAction.asset_downloaded.value,
)


@celery_app.task(name="prune_asset_activity")
def prune_asset_activity() -> int:
    """Delete tracking-action activity rows older than RETENTION_DAYS. Returns count."""
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
        deleted = (
            db.query(ActivityLog)
            .filter(
                ActivityLog.action.in_(TRACKING_ACTIONS),
                ActivityLog.created_at < cutoff,
            )
            .delete(synchronize_session=False)
        )
        db.commit()
        return int(deleted)
    finally:
        db.close()
