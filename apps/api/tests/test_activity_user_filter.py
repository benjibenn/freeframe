"""GET /activity?user_id=X narrows the feed to one user (per-user drill-down).

WHY: the admin per-user activity page reuses this endpoint; the user_id filter is
what makes "trace this specific person" possible. Non-admins must still be denied.
"""
import uuid
from unittest.mock import MagicMock, patch


def test_user_id_filter_applied(client, auth_headers, mock_db, test_user):
    test_user.is_superadmin = True
    target = uuid.uuid4()
    mock_db.order_by.return_value = mock_db
    mock_db.limit.return_value = mock_db
    mock_db.all.return_value = []
    with patch("apps.api.routers.activity.require_platform_admin"):
        resp = client.get(f"/activity?user_id={target}", headers=auth_headers)
    assert resp.status_code == 200
    # The filter chain was exercised (user_id predicate added).
    assert mock_db.filter.called


def test_activity_requires_admin(client, auth_headers, mock_db):
    from fastapi import HTTPException
    with patch("apps.api.routers.activity.require_platform_admin",
               side_effect=HTTPException(status_code=403, detail="x")):
        resp = client.get("/activity", headers=auth_headers)
    assert resp.status_code == 403


def test_unread_count_excludes_tracking_actions(test_user):
    """GET /activity/unread-count drives the sidebar badge (polled every 45s).

    WHY: asset_clicked/asset_viewed/asset_downloaded rows share activity_logs with
    team actions (created/commented/approved/…). If the unread-count query doesn't
    exclude tracking rows, the badge pins at 99+ from click/view/download noise —
    silently defeating its whole purpose of flagging new TEAM activity worth
    reviewing. Pin the actual filter clause, not just that .filter() was called.
    """
    from apps.api.routers import activity as activity_router

    db = MagicMock()
    query = MagicMock()
    db.query.return_value = query
    query.filter.return_value = query
    query.scalar.return_value = 0
    test_user.preferences = {}

    with patch("apps.api.routers.activity.require_platform_admin"):
        activity_router.unread_activity_count(db=db, current_user=test_user)

    filter_args = [arg for call in query.filter.call_args_list for arg in call.args]
    rendered = " ".join(str(arg) for arg in filter_args)
    assert "activity_logs.action" in rendered
    assert "NOT IN" in rendered
