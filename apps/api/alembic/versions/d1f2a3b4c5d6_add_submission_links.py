"""add submission_links and submissions tables

Revision ID: d1f2a3b4c5d6
Revises: 8ca3dffea55f
Create Date: 2026-06-11
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ENUM

revision: str = 'd1f2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = '8ca3dffea55f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Reuse the existing projectrole enum type (created by project_members).
    projectrole = ENUM('owner', 'editor', 'reviewer', 'viewer', name='projectrole', create_type=False)

    op.create_table(
        'submission_links',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('token', sa.String(length=255), nullable=False),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('instructions', sa.Text(), nullable=True),
        sa.Column('grant_role', projectrole, server_default='editor', nullable=False),
        sa.Column('is_enabled', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('token', name='uq_submission_links_token'),
    )
    op.create_index('ix_submission_links_token', 'submission_links', ['token'])
    op.create_index('ix_submission_links_created_by', 'submission_links', ['created_by'])

    op.create_table(
        'submissions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('submission_link_id', UUID(as_uuid=True), sa.ForeignKey('submission_links.id'), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('submission_link_id', 'user_id', name='uq_submissions_link_user'),
    )
    op.create_index('ix_submissions_link', 'submissions', ['submission_link_id'])
    op.create_index('ix_submissions_user', 'submissions', ['user_id'])
    op.create_index('ix_submissions_project', 'submissions', ['project_id'])


def downgrade() -> None:
    op.drop_index('ix_submissions_project', 'submissions')
    op.drop_index('ix_submissions_user', 'submissions')
    op.drop_index('ix_submissions_link', 'submissions')
    op.drop_table('submissions')
    op.drop_index('ix_submission_links_created_by', 'submission_links')
    op.drop_index('ix_submission_links_token', 'submission_links')
    op.drop_table('submission_links')
