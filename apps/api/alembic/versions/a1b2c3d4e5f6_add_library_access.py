"""add library_access table for per-user cross-project asset permissions

Revision ID: a1b2c3d4e5f6
Revises: c4d5e6f7a8b9
Create Date: 2026-06-23
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'library_access',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False, index=True),
        sa.Column('folder_id', UUID(as_uuid=True), sa.ForeignKey('folders.id'), nullable=True),
        sa.Column('granted_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    # Two partial unique indexes because NULL != NULL in SQL unique constraints.
    op.create_index(
        'uq_library_access_project',
        'library_access',
        ['user_id', 'project_id'],
        unique=True,
        postgresql_where=sa.text('folder_id IS NULL'),
    )
    op.create_index(
        'uq_library_access_folder',
        'library_access',
        ['user_id', 'project_id', 'folder_id'],
        unique=True,
        postgresql_where=sa.text('folder_id IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index('uq_library_access_folder', table_name='library_access')
    op.drop_index('uq_library_access_project', table_name='library_access')
    op.drop_table('library_access')
