"""add GIN index on assets.keywords for tag filtering

Tags are stored in the JSONB array Asset.keywords. The per-project tag filter and
tag autocomplete query with the containment operator (@>), which a GIN index makes
fast. Created CONCURRENTLY-free since the table is small at this stage.

Revision ID: a7b8c9d0e1f2
Revises: f4a5b6c7d8e0
Create Date: 2026-06-14
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'f4a5b6c7d8e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'ix_assets_keywords_gin',
        'assets',
        ['keywords'],
        postgresql_using='gin',
    )


def downgrade() -> None:
    op.drop_index('ix_assets_keywords_gin', table_name='assets')
