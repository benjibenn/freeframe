"""add uid display number to users

Revision ID: f1a2b3c4d5e7
Revises: e1f2a3b4c5d6
Create Date: 2026-06-19
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'f1a2b3c4d5e7'
down_revision: Union[str, Sequence[str], None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('uid', sa.Integer(), nullable=True))
    op.create_unique_constraint('uq_users_uid', 'users', ['uid'])


def downgrade() -> None:
    op.drop_constraint('uq_users_uid', 'users', type_='unique')
    op.drop_column('users', 'uid')
