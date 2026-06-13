"""add task_stages table and asset.task_stage_id

Revision ID: f0a1b2c3d4e5
Revises: e3f4a5b6c7d8
Create Date: 2026-06-13
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = 'f0a1b2c3d4e5'
down_revision: Union[str, Sequence[str], None] = 'e3f4a5b6c7d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Default pipeline seeded on first migration. Admins can edit these afterwards.
DEFAULT_STAGES = [
    ("Pending", 1, "#6b7280"),
    ("In Progress", 2, "#3b82f6"),
    ("Review", 3, "#a855f7"),
    ("Revision", 4, "#f59e0b"),
    ("Done", 5, "#22c55e"),
]


def upgrade() -> None:
    task_stages = op.create_table(
        'task_stages',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('color', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.bulk_insert(
        task_stages,
        [
            {"id": uuid.uuid4(), "name": name, "position": pos, "color": color}
            for name, pos, color in DEFAULT_STAGES
        ],
    )

    op.add_column(
        'assets',
        sa.Column('task_stage_id', UUID(as_uuid=True), nullable=True),
    )
    op.create_index('ix_assets_task_stage_id', 'assets', ['task_stage_id'])
    op.create_foreign_key(
        'fk_assets_task_stage_id', 'assets', 'task_stages',
        ['task_stage_id'], ['id'],
    )


def downgrade() -> None:
    op.drop_constraint('fk_assets_task_stage_id', 'assets', type_='foreignkey')
    op.drop_index('ix_assets_task_stage_id', table_name='assets')
    op.drop_column('assets', 'task_stage_id')
    op.drop_table('task_stages')
