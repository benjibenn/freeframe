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
