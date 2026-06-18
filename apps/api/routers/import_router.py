import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.user import User
from ..models.project import Project, ProjectRole
from ..models.folder import Folder
from ..services.permissions import is_platform_admin, require_project_role
from ..services import import_service
from ..schemas.import_schema import BucketImportRequest, BucketImportResponse

router = APIRouter(tags=["import"])


@router.post("/projects/{project_id}/import/bucket", response_model=BucketImportResponse)
def bucket_import(
    project_id: uuid.UUID,
    body: BucketImportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Scan an S3 prefix and register each media file as a freeframe asset.

    Requires editor role or higher (or platform admin). Each discovered object
    is registered with its existing S3 key (no copy/move) and enqueued for
    transcoding. Re-posting the same prefix is idempotent — already-registered
    keys are skipped.
    """
    # Project must exist (regardless of admin status)
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.deleted_at.is_(None),
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not is_platform_admin(current_user):
        require_project_role(db, project_id, current_user, ProjectRole.editor)

    folder_id: Optional[uuid.UUID] = None
    if body.folder_id:
        try:
            folder_id = uuid.UUID(body.folder_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="folder_id is not a valid UUID")

        # Verify folder belongs to this project and is not deleted
        folder = db.query(Folder).filter(
            Folder.id == folder_id,
            Folder.project_id == project_id,
            Folder.deleted_at.is_(None),
        ).first()
        if not folder:
            raise HTTPException(status_code=422, detail="folder_id not found in this project")

    result = import_service.import_prefix(
        db=db,
        project_id=project_id,
        prefix=body.prefix,
        created_by=current_user.id,
        folder_id=folder_id,
    )
    return BucketImportResponse(**result)
