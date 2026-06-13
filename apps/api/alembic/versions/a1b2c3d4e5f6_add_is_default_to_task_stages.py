"""add is_default to task_stages

Revision ID: a1b2c3d4e5f6
Revises: f0a1b2c3d4e5
Create Date: 2026-06-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f0a1b2c3d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'task_stages',
        sa.Column('is_default', sa.Boolean(), server_default='false', nullable=False),
    )
    # Make the first stage (lowest position, e.g. "Pending") the default landing
    # stage for newly uploaded videos. Guard against an empty table.
    op.execute(
        """
        UPDATE task_stages SET is_default = true
        WHERE id = (
            SELECT id FROM task_stages
            WHERE deleted_at IS NULL
            ORDER BY position ASC, created_at ASC
            LIMIT 1
        )
        """
    )


def downgrade() -> None:
    op.drop_column('task_stages', 'is_default')
