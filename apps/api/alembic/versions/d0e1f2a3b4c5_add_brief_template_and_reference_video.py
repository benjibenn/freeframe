"""add brief_templates singleton and reference-video key to submission_links

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-07-20

The seeded default template reproduces the previously-hardcoded BriefView so existing
briefs render unchanged. Admins can then reorder/remap/add sections in Settings.
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'd0e1f2a3b4c5'
down_revision: Union[str, Sequence[str], None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_SECTIONS = [
    {"id": "overview", "title": "Overview", "path": "overview", "as": "text"},
    {"id": "deliverable", "title": "Final deliverable", "path": "final_deliverable.label", "as": "text"},
    {
        "id": "hooks",
        "title": "",  # blank title => renders under the "Final deliverable" heading above
        "path": "final_deliverable.hook_variations",
        "as": "table",
        "columns": [
            {"key": "variation", "header": "Hook variation"},
            {"key": "script", "header": "Script"},
            {"key": "shot", "header": "Shot"},
            {"key": "on_screen_text", "header": "On-screen text"},
        ],
    },
    {
        "id": "storyboard",
        "title": "Script & storyboard",
        "path": "script_with_storyboard",
        "as": "table",
        "columns": [
            {"key": "script", "header": "Script"},
            {"key": "shot", "header": "Shot"},
            {"key": "on_screen_text", "header": "On-screen text"},
        ],
    },
    {"id": "guidelines", "title": "Guidelines", "path": "guidelines", "as": "bullets"},
]


def upgrade() -> None:
    op.add_column(
        'submission_links',
        sa.Column('brief_reference_video_s3_key', sa.String(length=1024), nullable=True),
    )
    op.create_table(
        'brief_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('sections', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    brief_templates = sa.table(
        'brief_templates',
        sa.column('id', postgresql.UUID(as_uuid=True)),
        sa.column('sections', postgresql.JSONB()),
    )
    op.bulk_insert(brief_templates, [{'id': uuid.uuid4(), 'sections': DEFAULT_SECTIONS}])


def downgrade() -> None:
    op.drop_table('brief_templates')
    op.drop_column('submission_links', 'brief_reference_video_s3_key')
