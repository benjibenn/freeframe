from datetime import datetime
from pydantic import BaseModel
import uuid
from typing import Any, Literal, Optional

from ..models.share import SharePermission


# Field types the model (models.metadata.FieldType) actually supports. Keep this in
# sync with that enum — listing types here that the DB enum lacks (e.g. url/boolean)
# turns a create into a 500 and breaks response serialization.
FieldTypeLiteral = Literal["text", "number", "date", "select", "multi_select"]


class MetadataFieldCreate(BaseModel):
    name: str
    field_type: FieldTypeLiteral
    options: Optional[list[str]] = None  # for select/multi_select
    required: bool = False


class MetadataFieldResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    # Plain str: the ORM hands back a FieldType enum member, which serializes to its
    # value cleanly here (a Literal rejects the enum member → ResponseValidationError).
    field_type: str
    options: Optional[list[str]] = None
    required: bool
    model_config = {"from_attributes": True}


class AssetMetadataSet(BaseModel):
    field_id: uuid.UUID
    value: Optional[Any] = None


class AssetMetadataResponse(BaseModel):
    field_id: uuid.UUID
    field_name: str
    field_type: str
    value: Optional[Any] = None


class CollectionCreate(BaseModel):
    name: str
    filter_rules: Optional[dict] = None


class CollectionResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    filter_rules: Optional[dict] = None
    is_smart: bool
    asset_count: int = 0
    model_config = {"from_attributes": True}


class CollectionShareCreate(BaseModel):
    permission: SharePermission = SharePermission.view
    expires_at: Optional[datetime] = None


class CollectionShareResponse(BaseModel):
    id: uuid.UUID
    token: str
    permission: SharePermission
    expires_at: Optional[datetime] = None
    model_config = {"from_attributes": True}
