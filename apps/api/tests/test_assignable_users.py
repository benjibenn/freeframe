"""GET /users/assignable: the owner dropdown on the task board.

Intent encoded:
- a deactivated user can no longer log in (auth.py blocks them), so offering
  them as a brief owner assigns work into a void — the filter must exclude
  them even though their row is kept (not soft-deleted) for history;
- soft-deleted rows stay hidden as everywhere else.

Pin the actual filter clauses, not just that .filter() was called — the mock
DB can't run SQL, so the clause text is the behavior under test.
"""
from unittest.mock import MagicMock


def test_assignable_excludes_deactivated_and_deleted(test_user):
    from apps.api.routers.users import list_assignable_users

    db = MagicMock()
    sub_query = MagicMock()
    sub_query.distinct.return_value = sub_query
    sub_query.all.return_value = []
    user_query = MagicMock()
    user_query.filter.return_value = user_query
    user_query.order_by.return_value = user_query
    user_query.all.return_value = []
    db.query = MagicMock(side_effect=[sub_query, user_query])

    list_assignable_users(db=db, current_user=test_user)

    filter_args = [arg for call in user_query.filter.call_args_list for arg in call.args]
    rendered = " ".join(str(arg) for arg in filter_args)
    assert "users.deleted_at IS NULL" in rendered
    assert "users.status !=" in rendered
