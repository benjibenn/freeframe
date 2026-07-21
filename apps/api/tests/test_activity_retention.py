"""prune_asset_activity deletes ONLY tracking rows older than 90 days.

WHY (the whole point of scoping this job): activity_logs also holds the team audit
trail — comments, approvals, shares. A blanket 90-day purge would destroy that
history. This test fails loudly if the delete ever stops filtering by the three
tracking actions, which is exactly the mistake that would erase the audit trail.
"""
from unittest.mock import MagicMock, patch

from apps.api.tasks import retention_tasks as rt


def test_prune_filters_to_tracking_actions_and_age():
    db = MagicMock()
    query = MagicMock()
    query.filter.return_value = query
    query.delete.return_value = 3
    db.query.return_value = query

    with patch.object(rt, "SessionLocal", return_value=db):
        deleted = rt.prune_asset_activity()

    assert deleted == 3
    assert set(rt.TRACKING_ACTIONS) == {"asset_clicked", "asset_viewed", "asset_downloaded"}
    assert query.delete.called
    db.commit.assert_called_once()

    # Pin the actual filter clauses, not just that .filter()/.delete() were called.
    # Without this, a future refactor to a blanket `db.query(ActivityLog).delete()`
    # (deleting the entire team audit trail — the exact catastrophe this task exists
    # to prevent) would still pass every assertion above. SQLAlchemy clause elements
    # render to SQL-ish text via str(), so inspect what was actually passed to
    # query.filter() to confirm both the action-scoping and age predicates are there.
    filter_args = query.filter.call_args.args
    rendered = " ".join(str(arg) for arg in filter_args)
    assert "activity_logs.action" in rendered
    assert "activity_logs.created_at" in rendered
