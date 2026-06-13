"""add display_name to submissions

Owner-set handle override for a submission. When set, the per-submitter project is
named "{request title} — {display_name}" instead of using the submitter's account
name — the invite-link equivalent of assigning each editor a unique name.

Revision ID: e3f4a5b6c7d9
Revises: d2e3f4a5b6c7
Create Date: 2026-06-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e3f4a5b6c7d9'
down_revision: Union[str, Sequence[str], None] = 'd2e3f4a5b6c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('submissions', sa.Column('display_name', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('submissions', 'display_name')
