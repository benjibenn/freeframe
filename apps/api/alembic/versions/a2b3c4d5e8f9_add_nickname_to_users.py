"""add nickname to users

Revision ID: a2b3c4d5e8f9
Revises: f1a2b3c4d5e7
Create Date: 2026-06-19
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a2b3c4d5e8f9'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('nickname', sa.String(length=50), nullable=True))
    op.create_index('uq_users_nickname_lower', 'users', [sa.text('lower(nickname)')], unique=True)


def downgrade() -> None:
    op.drop_index('uq_users_nickname_lower', table_name='users')
    op.drop_column('users', 'nickname')
