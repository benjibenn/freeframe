"""Reference images and videos become lists.

One "adapt this ad" picture (or clip) per brief turned out to be too few —
briefs often reference several ads. Both single S3-key columns become JSONB
arrays of keys (existing single attachments are carried over as one-element
arrays); the brief page shows images as a carousel and videos stacked.

Revision ID: e6f7a8b9c0d2
Revises: d5e6f7a8b9c1
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e6f7a8b9c0d2"
down_revision = "d5e6f7a8b9c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "submission_links",
        sa.Column(
            "brief_reference_image_s3_keys",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
    )
    op.execute(
        """
        UPDATE submission_links
        SET brief_reference_image_s3_keys = jsonb_build_array(brief_reference_image_s3_key)
        WHERE brief_reference_image_s3_key IS NOT NULL
        """
    )
    op.drop_column("submission_links", "brief_reference_image_s3_key")

    op.add_column(
        "submission_links",
        sa.Column(
            "brief_reference_video_s3_keys",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
    )
    op.execute(
        """
        UPDATE submission_links
        SET brief_reference_video_s3_keys = jsonb_build_array(brief_reference_video_s3_key)
        WHERE brief_reference_video_s3_key IS NOT NULL
        """
    )
    op.drop_column("submission_links", "brief_reference_video_s3_key")


def downgrade() -> None:
    op.add_column(
        "submission_links",
        sa.Column("brief_reference_video_s3_key", sa.String(length=1024), nullable=True),
    )
    op.execute(
        """
        UPDATE submission_links
        SET brief_reference_video_s3_key = brief_reference_video_s3_keys->>0
        WHERE jsonb_array_length(brief_reference_video_s3_keys) > 0
        """
    )
    op.drop_column("submission_links", "brief_reference_video_s3_keys")
    op.add_column(
        "submission_links",
        sa.Column("brief_reference_image_s3_key", sa.String(length=1024), nullable=True),
    )
    op.execute(
        """
        UPDATE submission_links
        SET brief_reference_image_s3_key = brief_reference_image_s3_keys->>0
        WHERE jsonb_array_length(brief_reference_image_s3_keys) > 0
        """
    )
    op.drop_column("submission_links", "brief_reference_image_s3_keys")
