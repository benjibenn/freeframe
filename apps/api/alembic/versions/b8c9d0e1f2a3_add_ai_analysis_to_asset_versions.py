"""add ai analysis cache to asset_versions

Revision ID: b8c9d0e1f2a3
Revises: f7a1b2c3d4e5
Create Date: 2026-07-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, Sequence[str], None] = "f7a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("asset_versions", sa.Column("ai_summary", sa.Text(), nullable=True))
    op.add_column("asset_versions", sa.Column("ai_transcript", sa.Text(), nullable=True))
    op.add_column("asset_versions", sa.Column("ai_analyzed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("asset_versions", "ai_analyzed_at")
    op.drop_column("asset_versions", "ai_transcript")
    op.drop_column("asset_versions", "ai_summary")
