from pydantic import BaseModel
import uuid
from datetime import datetime
from typing import Optional


class TagPaletteCreate(BaseModel):
    label: str
    color: Optional[str] = None


class TagPaletteUpdate(BaseModel):
    label: Optional[str] = None
    color: Optional[str] = None
    position: Optional[int] = None


class TagPaletteResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    label: str
    color: Optional[str] = None
    position: int
    model_config = {"from_attributes": True}
