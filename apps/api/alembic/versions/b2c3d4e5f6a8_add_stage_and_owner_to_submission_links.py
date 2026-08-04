"""add task_stage_id and assignee_id to submission_links

The task board listed delivered assets, so a brief nobody had uploaded to yet
was invisible on it — which is precisely the row a to-do list exists to show.
Giving a brief its own stage and owner makes it a first-class work item.

task_stage_id points at the same task_stages table the assets use, deliberately:
one pipeline, so "Review" means the same thing at either level.

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
"""
from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a8"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "submission_links",
        sa.Column("task_stage_id", sa.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "submission_links",
        sa.Column("assignee_id", sa.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_submission_links_task_stage", "submission_links", "task_stages",
        ["task_stage_id"], ["id"],
    )
    op.create_foreign_key(
        "fk_submission_links_assignee", "submission_links", "users",
        ["assignee_id"], ["id"],
    )
    op.create_index("ix_submission_links_task_stage_id", "submission_links", ["task_stage_id"])
    op.create_index("ix_submission_links_assignee_id", "submission_links", ["assignee_id"])


def downgrade() -> None:
    op.drop_index("ix_submission_links_assignee_id", table_name="submission_links")
    op.drop_index("ix_submission_links_task_stage_id", table_name="submission_links")
    op.drop_constraint("fk_submission_links_assignee", "submission_links", type_="foreignkey")
    op.drop_constraint("fk_submission_links_task_stage", "submission_links", type_="foreignkey")
    op.drop_column("submission_links", "assignee_id")
    op.drop_column("submission_links", "task_stage_id")
