from typing import Optional
from pydantic import BaseModel, Field, field_validator


class BucketImportRequest(BaseModel):
    prefix: str = Field(..., min_length=1)
    folder_id: Optional[str] = None

    @field_validator("prefix")
    @classmethod
    def prefix_not_whitespace(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("prefix must not be empty or whitespace")
        return stripped


class BucketImportResponse(BaseModel):
    imported: int
    skipped: int
    failed: list[dict] = []
    truncated: bool = False
    assets: list[dict]
