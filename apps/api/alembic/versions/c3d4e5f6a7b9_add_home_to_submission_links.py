"""Give a submission link a home project + folder.

Until now a request had no home at all: it floated free and only acquired
projects later, one auto-provisioned per editor who accepted it. That is why
requests rendered as a homeless flat grid and why their taxonomy path had to be
typed by hand.

`home_folder_id` becomes the source of truth for where a request belongs, so the
path is derived from the folder tree instead of retyped — and it follows folder
renames, which a stamped string never could.

Revision ID: c3d4e5f6a7b9
Revises: b2c3d4e5f6a8
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c3d4e5f6a7b9"
down_revision = "b2c3d4e5f6a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "submission_links",
        sa.Column("home_project_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "submission_links",
        sa.Column("home_folder_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_submission_links_home_project_id", "submission_links", ["home_project_id"]
    )
    op.create_index(
        "ix_submission_links_home_folder_id", "submission_links", ["home_folder_id"]
    )
    op.create_foreign_key(
        "fk_submission_links_home_project",
        "submission_links",
        "projects",
        ["home_project_id"],
        ["id"],
    )
    # A folder can be deleted while requests still point at it. SET NULL demotes
    # those requests to the project root rather than blocking the delete or
    # orphaning the row behind a dangling id.
    op.create_foreign_key(
        "fk_submission_links_home_folder",
        "submission_links",
        "folders",
        ["home_folder_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_submission_links_home_folder", "submission_links", type_="foreignkey")
    op.drop_constraint("fk_submission_links_home_project", "submission_links", type_="foreignkey")
    op.drop_index("ix_submission_links_home_folder_id", table_name="submission_links")
    op.drop_index("ix_submission_links_home_project_id", table_name="submission_links")
    op.drop_column("submission_links", "home_folder_id")
    op.drop_column("submission_links", "home_project_id")
