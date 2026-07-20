import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Enum, DateTime, ForeignKey, Boolean, func, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
try:
    from ..database import Base
    from .project import ProjectRole
except ImportError:
    from database import Base
    from models.project import ProjectRole


class SubmissionLink(Base):
    """A reusable link an owner shares with many people (e.g. interview candidates).

    Each authenticated visitor who accepts the link gets their OWN private project
    (the owner is added as project owner, the visitor as `grant_role`). Because
    project membership is per-user, submitters never see each other's uploads, while
    the owner is a member of every per-submitter project and can review/comment.
    """
    __tablename__ = "submission_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Role granted to each submitter on their per-submitter project (editor => can upload).
    grant_role: Mapped[ProjectRole] = mapped_column(
        Enum(ProjectRole, name="projectrole", create_type=False),
        nullable=False,
        server_default=ProjectRole.editor.value,
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    # Optional shared "reference" project all submitters can view (a common brief /
    # examples). Null = strict isolation (the default). See accept_submission_link /
    # the reference endpoints in routers/submissions.py.
    reference_project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Provenance for requests auto-created from an external source (the data
    # spine). NULL for normal hand-made requests. unique among ACTIVE rows
    # (partial index where deleted_at IS NULL), so re-importing a brief upserts
    # and a soft-deleted request doesn't block a fresh import.
    source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    source_brief_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    brief_pdf_s3_key: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    # A hand-authored structured brief (title/overview/script+storyboard/guidelines/
    # deliverable) rendered inline on the submit + project pages. Independent of the
    # PDF brief — a link may carry both, neither, or one.
    brief_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # External (CF) lineage ids + human labels for the campaign this request came
    # from (the data spine). NULL for hand-made requests. The ids are stamped onto
    # every asset created under this request; the labels surface in the UI.
    persona_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    angle_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    brief_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    persona_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    angle_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    problem: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Submission(Base):
    """One record per (link, submitter). Maps a submitter to the private project
    that was provisioned for them, making `accept` idempotent and letting the owner
    enumerate all submissions for a link."""
    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint("submission_link_id", "user_id", name="uq_submissions_link_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_link_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("submission_links.id"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True)
    # Owner-set handle override. When set, the per-submitter project is named
    # "{request title} — {display_name}". Null => use the submitter's account name.
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
