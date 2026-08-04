"""Add a static image reference to submission links.

Briefs could already carry a reference video, but most static-ad requests are
"adapt this image" — the reference itself is a picture. Mirrors the video
column: an S3 key on the link, served to submitters through a token-gated
redirect so the bucket stays private.

Revision ID: d5e6f7a8b9c1
Revises: c3d4e5f6a7b9
"""
from alembic import op
import sqlalchemy as sa

revision = "d5e6f7a8b9c1"
down_revision = "c3d4e5f6a7b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "submission_links",
        sa.Column("brief_reference_image_s3_key", sa.String(length=1024), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("submission_links", "brief_reference_image_s3_key")
