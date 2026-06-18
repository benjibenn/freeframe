"""add brief source tracking columns to submission_links

Revision ID: b2c3d4e5f6a7
Revises: a7b8c9d0e1f2
Create Date: 2026-06-18
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('submission_links', sa.Column('source', sa.String(length=50), nullable=True))
    op.add_column('submission_links', sa.Column('source_brief_id', sa.String(length=255), nullable=True))
    op.add_column('submission_links', sa.Column('brief_pdf_s3_key', sa.String(length=1024), nullable=True))
    op.create_index('ix_submission_links_source', 'submission_links', ['source'])
    # Partial unique index: only active rows (deleted_at IS NULL) are constrained,
    # so a soft-deleted row doesn't block a fresh import of the same brief.
    op.create_index(
        'uq_submission_links_source_brief',
        'submission_links',
        ['source', 'source_brief_id'],
        unique=True,
        postgresql_where=sa.text('deleted_at IS NULL'),
    )


def downgrade() -> None:
    op.drop_index('uq_submission_links_source_brief', table_name='submission_links')
    op.drop_index('ix_submission_links_source', table_name='submission_links')
    op.drop_column('submission_links', 'brief_pdf_s3_key')
    op.drop_column('submission_links', 'source_brief_id')
    op.drop_column('submission_links', 'source')
