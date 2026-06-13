"""add reference_project_id to submission_links

Optional shared "reference" project per request (submission link). When enabled,
every submitter on the request is added as a viewer of this one shared project so
they see a common brief / reference material, while their own submission projects
stay private. Null = no shared folder (strict isolation, the default).

Revision ID: d2e3f4a5b6c7
Revises: c2d3e4f5a6b7
Create Date: 2026-06-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = 'd2e3f4a5b6c7'
down_revision: Union[str, Sequence[str], None] = 'c2d3e4f5a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'submission_links',
        sa.Column('reference_project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('submission_links', 'reference_project_id')
