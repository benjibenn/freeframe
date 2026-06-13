import uuid
import hashlib
import secrets
from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
try:
    from ..database import Base
except ImportError:
    from database import Base

# Public API keys are shown to the caller exactly once at creation; only a hash
# is stored. Keys are sent in the X-API-Key header by external integrations.
API_KEY_PREFIX = "ffpk_"


def generate_api_key() -> str:
    """Return a new plaintext API key (shown once, never stored)."""
    return API_KEY_PREFIX + secrets.token_urlsafe(32)


def hash_api_key(raw_key: str) -> str:
    """SHA-256 hash of the plaintext key, for storage and lookup."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


class APIKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # First few chars of the key, for display (e.g. "ffpk_Gr366cWq…"). Not a secret.
    key_prefix: Mapped[str] = mapped_column(String(32), nullable=False)
    # SHA-256 hex digest of the full key — what we compare against on each request.
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Soft state: a revoked key keeps its row (audit) but no longer authenticates.
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
