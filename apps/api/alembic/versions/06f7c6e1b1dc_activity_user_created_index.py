"""add (user_id, created_at) index to activity_logs

Speeds up per-user activity drill-down (GET /activity?user_id=X ordered by
created_at desc) and the 90-day retention sweep.
"""
from alembic import op

revision = "06f7c6e1b1dc"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_activity_logs_user_created",
        "activity_logs",
        ["user_id", "created_at"],
    )


def downgrade():
    op.drop_index("ix_activity_logs_user_created", table_name="activity_logs")
