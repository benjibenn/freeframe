import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, Integer, Boolean, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
try:
    from ..database import Base
except ImportError:
    from database import Base


class TaskStage(Base):
    """An admin-configurable stage in the video review pipeline.

    Stages are ordered by `position` (ascending) and define the columns of the
    task list, e.g. Pending → In Progress → Review → Revision → Done. Admins can
    add, rename, recolour, reorder and remove stages without a code change.
    Each video Asset points at its current stage via `Asset.task_stage_id`.
    """
    __tablename__ = "task_stages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Hex colour (e.g. "#3b82f6") used for the stage badge in the UI; optional.
    color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # The stage newly uploaded videos land in. At most one stage is the default.
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false", default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
