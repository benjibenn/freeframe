"""add drive_sync_connections and drive_synced_files tables

Revision ID: e1f2a3b4c5d6
Revises: d4e5f6a7b8c9
Create Date: 2026-06-18
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'drive_sync_connections',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('drive_folder_id', sa.String(), nullable=False),
        sa.Column('folder_name', sa.String(length=500), nullable=True),
        sa.Column('target_project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_drive_sync_connections_target_project_id', 'drive_sync_connections', ['target_project_id'])

    op.create_table(
        'drive_synced_files',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('connection_id', UUID(as_uuid=True), sa.ForeignKey('drive_sync_connections.id'), nullable=False),
        sa.Column('drive_file_id', sa.String(), nullable=False),
        sa.Column('asset_id', UUID(as_uuid=True), sa.ForeignKey('assets.id'), nullable=True),
        sa.Column('synced_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.UniqueConstraint('connection_id', 'drive_file_id', name='uq_drive_synced_files_connection_file'),
    )
    op.create_index('ix_drive_synced_files_connection_id', 'drive_synced_files', ['connection_id'])
    op.create_index('ix_drive_synced_files_drive_file_id', 'drive_synced_files', ['drive_file_id'])


def downgrade() -> None:
    op.drop_index('ix_drive_synced_files_drive_file_id', table_name='drive_synced_files')
    op.drop_index('ix_drive_synced_files_connection_id', table_name='drive_synced_files')
    op.drop_table('drive_synced_files')
    op.drop_index('ix_drive_sync_connections_target_project_id', table_name='drive_sync_connections')
    op.drop_table('drive_sync_connections')
