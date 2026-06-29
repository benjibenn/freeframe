"""add run_as_ad flag to assets

Revision ID: f1a2b3c4d5e6
Revises: c8d9e2f1a3b4
Create Date: 2026-06-29
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'c8d9e2f1a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # "Run as ad" clearance flag, indexed for external filtering. Existing rows
    # default to false (not cleared).
    op.add_column(
        'assets',
        sa.Column('run_as_ad', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index('ix_assets_run_as_ad', 'assets', ['run_as_ad'])


def downgrade() -> None:
    op.drop_index('ix_assets_run_as_ad', table_name='assets')
    op.drop_column('assets', 'run_as_ad')
