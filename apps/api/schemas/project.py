from pydantic import BaseModel
import uuid
from datetime import datetime
from ..models.project import ProjectType, ProjectRole

class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    project_type: ProjectType = ProjectType.personal

class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_public: bool | None = None

class ProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    project_type: ProjectType
    created_by: uuid.UUID
    created_at: datetime
    poster_url: str | None = None
    is_public: bool = False
    asset_count: int = 0
    storage_bytes: int = 0
    member_count: int = 0
    role: ProjectRole | None = None
    share_token: str | None = None  # Token of the default (private view+comment) share link
    # Request grouping: if this project was provisioned by a submission link (a "video
    # request"), these identify it so the projects page can nest it under the request
    # instead of listing it flat. Null for ordinary projects.
    submission_link_id: uuid.UUID | None = None
    request_title: str | None = None
    brief_pdf_url: str | None = None
    # Structured JSON brief from the request, rendered on the project page. Populated
    # on the single-project GET only (kept out of the projects-list payload).
    brief_json: dict | None = None
    model_config = {"from_attributes": True}

class ProjectMemberResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    user_id: uuid.UUID
    role: ProjectRole
    model_config = {"from_attributes": True}

class AddProjectMemberRequest(BaseModel):
    user_id: uuid.UUID
    role: ProjectRole = ProjectRole.viewer

class UpdateProjectMemberRequest(BaseModel):
    role: ProjectRole
