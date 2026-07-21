"""add (user_id, created_at) index to activity_logs

Speeds up per-user activity drill-down (GET /activity?user_id=X ordered by
created_at desc). Does NOT help the 90-day retention sweep — that query filters
on action IN (...) AND created_at < cutoff with no user_id predicate, so this
index's leading column is never usable there.
"""
from alembic import op

revision = "06f7c6e1b1dc"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_activity_logs_user_created",
            "activity_logs",
            ["user_id", "created_at"],
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_activity_logs_user_created",
            table_name="activity_logs",
            postgresql_concurrently=True,
            if_exists=True,
        )
