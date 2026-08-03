"""add taxonomy_path to submission_links and assets

Submitted work is born in a per-submitter project with no folder, and folders
are scoped per project, so a submission link cannot point at a folder in the
main tree. The link therefore carries the taxonomy path as text and stamps it
onto every asset created under it, decoupling "where this belongs" from "where
this physically lives".

Revision ID: a1b2c3d4e5f7
Revises: e5f6a7b8c9d0
"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f7"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("submission_links", sa.Column("taxonomy_path", sa.String(1024), nullable=True))
    op.add_column("assets", sa.Column("taxonomy_path", sa.String(1024), nullable=True))
    # Filtering by a niche has to reach stamped assets too, and that is a prefix
    # match over every asset in the system.
    op.create_index("ix_assets_taxonomy_path", "assets", ["taxonomy_path"])


def downgrade() -> None:
    op.drop_index("ix_assets_taxonomy_path", table_name="assets")
    op.drop_column("assets", "taxonomy_path")
    op.drop_column("submission_links", "taxonomy_path")
