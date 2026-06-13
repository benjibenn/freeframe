"""add submission_link_id to projects

Direct project -> request (submission link) membership. Lets ANY project be a child
of a request — not just auto-provisioned per-editor projects — so an owner can attach
an existing project to an existing request. Backfills from the submissions table so
existing per-editor projects keep nesting under their request.

Revision ID: f4a5b6c7d8e0
Revises: e3f4a5b6c7d9
Create Date: 2026-06-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = 'f4a5b6c7d8e0'
down_revision: Union[str, Sequence[str], None] = 'e3f4a5b6c7d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'projects',
        sa.Column('submission_link_id', UUID(as_uuid=True), sa.ForeignKey('submission_links.id'), nullable=True),
    )
    op.create_index('ix_projects_submission_link_id', 'projects', ['submission_link_id'])
    # Backfill from existing per-editor submissions.
    op.execute(
        """
        UPDATE projects
        SET submission_link_id = s.submission_link_id
        FROM submissions s
        WHERE s.project_id = projects.id
        """
    )


def downgrade() -> None:
    op.drop_index('ix_projects_submission_link_id', table_name='projects')
    op.drop_column('projects', 'submission_link_id')
