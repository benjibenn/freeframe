"""add task_stage_id to submissions

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-09-28

Each editor assigned to a brief carries their own pipeline stage, so two
editors on one brief can be at different points. The brief keeps its own
stage on submission_links; this is the per-editor one.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'c7d8e9f0a1b2'
down_revision: Union[str, Sequence[str], None] = 'b6c7d8e9f0a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'submissions',
        sa.Column('task_stage_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_submissions_task_stage', 'submissions', 'task_stages',
        ['task_stage_id'], ['id'],
    )
    op.create_index('ix_submissions_task_stage_id', 'submissions', ['task_stage_id'])


def downgrade() -> None:
    op.drop_index('ix_submissions_task_stage_id', table_name='submissions')
    op.drop_constraint('fk_submissions_task_stage', 'submissions', type_='foreignkey')
    op.drop_column('submissions', 'task_stage_id')
