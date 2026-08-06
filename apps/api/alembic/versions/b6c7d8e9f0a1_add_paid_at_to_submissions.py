"""add paid_at to submissions

Revision ID: b6c7d8e9f0a1
Revises: a5b462ca5336
Create Date: 2026-08-06
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'b6c7d8e9f0a1'
down_revision: Union[str, Sequence[str], None] = 'a5b462ca5336'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('submissions', sa.Column('paid_at', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column('submissions', 'paid_at')
