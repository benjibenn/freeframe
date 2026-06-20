"""add CF lineage to submission_links and assets

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e8f9
Create Date: 2026-06-20
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, Sequence[str], None] = 'a2b3c4d5e8f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SubmissionLink: CF campaign lineage ids + human labels (all nullable).
    op.add_column('submission_links', sa.Column('persona_id', sa.String(length=255), nullable=True))
    op.add_column('submission_links', sa.Column('angle_id', sa.String(length=255), nullable=True))
    op.add_column('submission_links', sa.Column('brief_id', sa.String(length=255), nullable=True))
    op.add_column('submission_links', sa.Column('persona_label', sa.String(length=255), nullable=True))
    op.add_column('submission_links', sa.Column('angle_label', sa.String(length=255), nullable=True))
    op.add_column('submission_links', sa.Column('problem', sa.String(length=255), nullable=True))

    # Asset: CF lineage stamped at creation, indexed for external filtering.
    op.add_column('assets', sa.Column('cf_brief_id', sa.String(length=255), nullable=True))
    op.add_column('assets', sa.Column('cf_persona_id', sa.String(length=255), nullable=True))
    op.add_column('assets', sa.Column('cf_angle_id', sa.String(length=255), nullable=True))
    op.create_index('ix_assets_cf_brief_id', 'assets', ['cf_brief_id'])
    op.create_index('ix_assets_cf_persona_id', 'assets', ['cf_persona_id'])
    op.create_index('ix_assets_cf_angle_id', 'assets', ['cf_angle_id'])


def downgrade() -> None:
    op.drop_index('ix_assets_cf_angle_id', table_name='assets')
    op.drop_index('ix_assets_cf_persona_id', table_name='assets')
    op.drop_index('ix_assets_cf_brief_id', table_name='assets')
    op.drop_column('assets', 'cf_angle_id')
    op.drop_column('assets', 'cf_persona_id')
    op.drop_column('assets', 'cf_brief_id')

    op.drop_column('submission_links', 'problem')
    op.drop_column('submission_links', 'angle_label')
    op.drop_column('submission_links', 'persona_label')
    op.drop_column('submission_links', 'brief_id')
    op.drop_column('submission_links', 'angle_id')
    op.drop_column('submission_links', 'persona_id')
