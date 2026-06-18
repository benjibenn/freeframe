"""add frame_tags table for per-frame timecoded tagging

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-18
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'frame_tags',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('asset_id', UUID(as_uuid=True), sa.ForeignKey('assets.id'), nullable=False),
        sa.Column('version_id', UUID(as_uuid=True), sa.ForeignKey('asset_versions.id'), nullable=False),
        sa.Column('timecode_start', sa.Float(), nullable=False),
        sa.Column('label', sa.String(length=255), nullable=False),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_frame_tags_asset_id', 'frame_tags', ['asset_id'])
    op.create_index('ix_frame_tags_version_id', 'frame_tags', ['version_id'])


def downgrade() -> None:
    op.drop_index('ix_frame_tags_version_id', table_name='frame_tags')
    op.drop_index('ix_frame_tags_asset_id', table_name='frame_tags')
    op.drop_table('frame_tags')
