"""add is_default to share_links

Marks the auto-created project share link (private view + comment) so the
projects page can surface a single canonical "copy link" per project.

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f6
Create Date: 2026-06-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'share_links',
        sa.Column('is_default', sa.Boolean(), server_default='false', nullable=False),
    )

    # Backfill: every existing project that doesn't already have a project-scoped
    # share link gets one default link (private view + comment enabled), created by
    # the project owner. This guarantees the "by default" promise holds for projects
    # that predate this feature, so the projects-page copy-link button always works.
    op.execute(
        """
        INSERT INTO share_links
            (id, project_id, token, created_by, title, is_enabled, permission,
             visibility, allow_download, show_versions, show_watermark, is_default,
             created_at)
        SELECT
            gen_random_uuid(),
            p.id,
            md5(random()::text || p.id::text || clock_timestamp()::text)
                || md5(p.id::text || random()::text),
            p.created_by,
            p.name,
            true,
            'comment',
            'secure',
            false,
            true,
            false,
            true,
            now()
        FROM projects p
        WHERE p.deleted_at IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM share_links s
              WHERE s.project_id = p.id AND s.deleted_at IS NULL
          )
        """
    )

    # Mark the earliest project-scoped link as the default for projects that
    # already had one or more project shares (so copy-link has a target there too).
    op.execute(
        """
        UPDATE share_links SET is_default = true
        WHERE id IN (
            SELECT DISTINCT ON (project_id) id
            FROM share_links
            WHERE project_id IS NOT NULL AND deleted_at IS NULL
            ORDER BY project_id, created_at ASC
        )
        AND project_id NOT IN (
            SELECT project_id FROM share_links
            WHERE is_default = true AND project_id IS NOT NULL AND deleted_at IS NULL
        )
        """
    )


def downgrade() -> None:
    op.drop_column('share_links', 'is_default')
