"""Schemas for admin-managed public API keys."""
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator


class APIKeyResponse(BaseModel):
    id: uuid.UUID
    name: str
    key_prefix: str
    created_by: uuid.UUID
    created_by_name: Optional[str] = None
    last_used_at: Optional[datetime] = None
    created_at: datetime
    revoked_at: Optional[datetime] = None
    is_active: bool = True
    model_config = {"from_attributes": True}


class APIKeyCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("Name is required")
        return v


class APIKeyCreated(APIKeyResponse):
    # The full plaintext key — returned ONLY on creation, never again.
    key: str
