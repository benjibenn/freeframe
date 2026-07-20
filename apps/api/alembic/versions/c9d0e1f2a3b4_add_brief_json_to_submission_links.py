"""add structured JSON brief column to submission_links

A non-flywheel, non-PDF brief: a structured JSON document (title, overview,
script/storyboard, guidelines, final deliverable) that renders inline on the
submit page and the editor's project page. Independent of brief_pdf_s3_key —
a link may carry both.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-07-20
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, Sequence[str], None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('submission_links', sa.Column('brief_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('submission_links', 'brief_json')
