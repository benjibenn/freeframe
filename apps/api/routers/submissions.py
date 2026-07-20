"""Submission links — a single shareable link that lets many people each upload
into their own private project.

Use case: an owner sends one link to N interview candidates. Each candidate logs
in (or signs up) and uploads their video. Per-submitter project isolation means no
candidate can see another's submission, while the owner — added as owner of every
provisioned project — can review and comment on all of them.

Two surfaces:
  * Owner-facing (auth required): create / list / inspect / disable links.
  * Visitor-facing: GET /submit/{token} (resolve), POST /submit/{token}/accept
    (auth required — provisions the per-submitter project).
"""
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware.auth import get_current_user, get_optional_user
from ..models.user import User, UserStatus
from ..services.auth_service import get_user_by_email
from ..models.project import Project, ProjectMember, ProjectRole, ProjectType
from ..models.asset import Asset
from ..models.submission import SubmissionLink, Submission
from ..schemas.submission import (
    SubmissionLinkCreate,
    BriefJsonUpdate,
    SubmissionLinkResponse,
    SubmissionLinkPublic,
    SubmissionAcceptResponse,
    SubmissionItem,
    SubmissionUpdate,
    ReferenceResponse,
    AttachProjectRequest,
    ChildProjectItem,
    MySubmissionItem,
)
from ..services.share_service import build_default_project_share_link
from ..services import s3_service
from ..services import brief_import_service
from ..services.permissions import require_platform_admin, is_platform_admin

router = APIRouter(tags=["submissions"])


def _get_owned_link(db: Session, link_id: uuid.UUID, user: User) -> SubmissionLink:
    link = db.query(SubmissionLink).filter(
        SubmissionLink.id == link_id,
        SubmissionLink.deleted_at.is_(None),
    ).first()
    if not link:
        raise HTTPException(status_code=404, detail="Submission link not found")
    # Platform admins (superadmin / sub-admin) co-manage every request, so any admin
    # may inspect/manage a link regardless of which admin created it.
    if link.created_by != user.id and not is_platform_admin(user):
        raise HTTPException(status_code=403, detail="Not your submission link")
    return link


def _validate_active(link: SubmissionLink | None) -> SubmissionLink:
    if not link or link.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Submission link not found")
    if not link.is_enabled:
        raise HTTPException(status_code=403, detail="This submission link is no longer accepting submissions")
    if link.expires_at and link.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="This submission link has expired")
    return link


def _unique_project_name(
    db: Session,
    link: SubmissionLink,
    base_name: str,
    exclude_project_id: uuid.UUID | None = None,
) -> str:
    """Guarantee the per-submitter project name is unique within a request, so two
    editors with the same display name don't both become "{title} — Anna". On a
    collision, append " (2)", " (3)", … `exclude_project_id` skips the project being
    renamed so re-saving its current name doesn't add a suffix."""
    q = (
        db.query(Project.name)
        .join(Submission, Submission.project_id == Project.id)
        .filter(Submission.submission_link_id == link.id, Project.deleted_at.is_(None))
    )
    if exclude_project_id is not None:
        q = q.filter(Project.id != exclude_project_id)
    existing = {n for (n,) in q.all()}
    if base_name not in existing:
        return base_name
    i = 2
    while f"{base_name} ({i})" in existing:
        i += 1
    return f"{base_name} ({i})"


def _count_map(db: Session, link_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not link_ids:
        return {}
    rows = (
        db.query(Submission.submission_link_id, func.count(Submission.id))
        .filter(Submission.submission_link_id.in_(link_ids))
        .group_by(Submission.submission_link_id)
        .all()
    )
    return {lid: int(c) for lid, c in rows}


# ── Owner-facing ─────────────────────────────────────────────────────────────

@router.post("/submission-links", response_model=SubmissionLinkResponse, status_code=status.HTTP_201_CREATED)
def create_submission_link(
    body: SubmissionLinkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Creating a video request (which provisions per-editor projects) is an admin
    # action; non-admins can only join an existing request via its submission link.
    require_platform_admin(current_user)
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")
    link = SubmissionLink(
        token=secrets.token_urlsafe(32),
        created_by=current_user.id,
        title=title,
        instructions=body.instructions,
        grant_role=ProjectRole.editor,
        expires_at=body.expires_at,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    resp = SubmissionLinkResponse.model_validate(link)
    resp.submission_count = 0
    return resp


@router.post("/submission-links/from-project/{project_id}", response_model=SubmissionLinkResponse, status_code=status.HTTP_201_CREATED)
def create_request_from_project(
    project_id: uuid.UUID,
    body: AttachProjectRequest = AttachProjectRequest(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Convert an existing project into a NEW video request titled after the project.
    By default the project becomes the request's shared reference (its assets become
    brief/examples for every editor); pass as_reference=false to add it as a plain
    child folder instead. Either way, editors who accept the link upload into their
    own private per-editor projects."""
    require_platform_admin(current_user)
    project = db.query(Project).filter(
        Project.id == project_id, Project.deleted_at.is_(None),
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    _require_project_owner(db, project_id, current_user)

    # A per-editor submission project can't itself become a request.
    if db.query(Submission).filter(Submission.project_id == project_id).first():
        raise HTTPException(status_code=400, detail="This project is an editor submission and can't be converted")
    # Already the shared reference of another request.
    if db.query(SubmissionLink).filter(
        SubmissionLink.reference_project_id == project_id,
        SubmissionLink.deleted_at.is_(None),
    ).first():
        raise HTTPException(status_code=400, detail="This project is already a request's shared reference")

    link = SubmissionLink(
        token=secrets.token_urlsafe(32),
        created_by=current_user.id,
        title=project.name,
        instructions=project.description,
        grant_role=ProjectRole.editor,
        reference_project_id=project.id if body.as_reference else None,
    )
    db.add(link)
    db.flush()
    if not body.as_reference:
        project.submission_link_id = link.id
    db.commit()
    db.refresh(link)
    resp = SubmissionLinkResponse.model_validate(link)
    resp.submission_count = 0
    return resp


@router.get("/my-submissions", response_model=list[MySubmissionItem])
def get_my_submissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns submission links the current user has submitted to, with asset counts."""
    subs = db.query(Submission).filter(Submission.user_id == current_user.id).all()
    if not subs:
        return []

    link_ids = list({s.submission_link_id for s in subs})
    project_ids = list({s.project_id for s in subs})

    links = {l.id: l for l in db.query(SubmissionLink).filter(SubmissionLink.id.in_(link_ids)).all()}
    projects = {p.id: p for p in db.query(Project).filter(Project.id.in_(project_ids)).all()}
    asset_counts = {
        r[0]: r[1]
        for r in db.query(Asset.project_id, func.count(Asset.id))
        .filter(Asset.project_id.in_(project_ids), Asset.deleted_at.is_(None))
        .group_by(Asset.project_id)
        .all()
    }

    result = []
    for s in sorted(subs, key=lambda x: x.created_at, reverse=True):
        link = links.get(s.submission_link_id)
        project = projects.get(s.project_id)
        if not link or not project:
            continue
        result.append(MySubmissionItem(
            submission_id=s.id,
            project_id=s.project_id,
            project_name=project.name,
            link_id=link.id,
            link_title=link.title,
            link_token=link.token,
            asset_count=asset_counts.get(s.project_id, 0),
            created_at=s.created_at,
        ))
    return result


@router.get("/submission-links", response_model=list[SubmissionLinkResponse])
def list_submission_links(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Platform admins (superadmin / sub-admin) all share the same submissions section,
    # so they see every request regardless of which admin created it. Non-admins only
    # ever see links they created (though creation itself is admin-gated).
    query = db.query(SubmissionLink).filter(SubmissionLink.deleted_at.is_(None))
    if not is_platform_admin(current_user):
        query = query.filter(SubmissionLink.created_by == current_user.id)
    links = query.order_by(SubmissionLink.created_at.desc()).all()
    counts = _count_map(db, [l.id for l in links])
    out = []
    for l in links:
        resp = SubmissionLinkResponse.model_validate(l)
        resp.submission_count = counts.get(l.id, 0)
        resp.has_brief = bool(l.brief_pdf_s3_key)
        resp.has_brief_json = bool(l.brief_json)  # flag only; full brief_json omitted from lists
        out.append(resp)
    return out


@router.get("/submission-links/{link_id}", response_model=SubmissionLinkResponse)
def get_submission_link(
    link_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    link = _get_owned_link(db, link_id, current_user)
    resp = SubmissionLinkResponse.model_validate(link)
    resp.submission_count = _count_map(db, [link.id]).get(link.id, 0)
    resp.has_brief = bool(link.brief_pdf_s3_key)
    resp.has_brief_json = bool(link.brief_json)
    resp.brief_json = link.brief_json  # full brief for the detail/edit view
    return resp


@router.put("/submission-links/{link_id}/brief-json", response_model=SubmissionLinkResponse)
def set_submission_brief_json(
    link_id: uuid.UUID,
    body: BriefJsonUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Set (or clear) a request's structured JSON brief. Owner/admin only. Pass
    brief=null to remove it. Independent of the PDF brief — a link may carry both."""
    link = _get_owned_link(db, link_id, current_user)
    if body.brief is not None and not body.brief:
        raise HTTPException(status_code=400, detail="Brief JSON must be a non-empty object")
    link.brief_json = body.brief
    db.commit()
    db.refresh(link)
    resp = SubmissionLinkResponse.model_validate(link)
    resp.submission_count = _count_map(db, [link.id]).get(link.id, 0)
    resp.has_brief = bool(link.brief_pdf_s3_key)
    resp.has_brief_json = bool(link.brief_json)
    resp.brief_json = link.brief_json
    return resp


@router.post("/submission-links/{link_id}/brief", response_model=SubmissionLinkResponse)
async def upload_submission_brief(
    link_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Attach (or replace) a hand-uploaded PDF brief on a request — the non-flywheel
    path. Owner/admin only (via _get_owned_link). The stored PDF is then served to
    submitters through the existing public GET /submit/{token}/brief.pdf route."""
    link = _get_owned_link(db, link_id, current_user)
    if (file.content_type or "").lower() != "application/pdf":
        raise HTTPException(status_code=400, detail="Brief must be a PDF")
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="The uploaded PDF is empty")
    if len(pdf_bytes) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Brief PDF must be 25 MB or smaller")
    try:
        brief_import_service.attach_manual_brief(db, link, pdf_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    resp = SubmissionLinkResponse.model_validate(link)
    resp.submission_count = _count_map(db, [link.id]).get(link.id, 0)
    resp.has_brief = True
    resp.has_brief_json = bool(link.brief_json)
    return resp


@router.get("/submission-links/{link_id}/submissions", response_model=list[SubmissionItem])
def list_submissions(
    link_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    link = _get_owned_link(db, link_id, current_user)
    subs = db.query(Submission).filter(
        Submission.submission_link_id == link.id,
    ).order_by(Submission.created_at.desc()).all()

    project_ids = [s.project_id for s in subs]
    asset_counts = {}
    if project_ids:
        rows = (
            db.query(Asset.project_id, func.count(Asset.id))
            .filter(Asset.project_id.in_(project_ids), Asset.deleted_at.is_(None))
            .group_by(Asset.project_id)
            .all()
        )
        asset_counts = {pid: int(c) for pid, c in rows}

    user_ids = [s.user_id for s in subs]
    users = {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}

    out = []
    for s in subs:
        u = users.get(s.user_id)
        out.append(SubmissionItem(
            id=s.id,
            user_id=s.user_id,
            user_name=(u.name if u else "") or "",
            user_email=(u.email if u else "") or "",
            display_name=s.display_name,
            project_id=s.project_id,
            asset_count=asset_counts.get(s.project_id, 0),
            created_at=s.created_at,
        ))
    return out


@router.patch("/submission-links/{link_id}/submissions/{submission_id}", response_model=SubmissionItem)
def update_submission(
    link_id: uuid.UUID,
    submission_id: uuid.UUID,
    body: SubmissionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Owner sets/clears a submission's handle override, renaming the per-submitter
    project to "{request title} — {handle}". Blank handle reverts to the account name."""
    link = _get_owned_link(db, link_id, current_user)
    sub = db.query(Submission).filter(
        Submission.id == submission_id,
        Submission.submission_link_id == link.id,
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")

    handle = (body.display_name or "").strip()
    sub.display_name = handle or None

    u = db.query(User).filter(User.id == sub.user_id).first()
    label = handle or (u.name if u else "") or (u.email if u else "") or "Submission"
    project = db.query(Project).filter(Project.id == sub.project_id).first()
    if project:
        project.name = _unique_project_name(
            db, link, f"{link.title} — {label}", exclude_project_id=project.id
        )
    db.commit()
    db.refresh(sub)

    asset_count = db.query(func.count(Asset.id)).filter(
        Asset.project_id == sub.project_id, Asset.deleted_at.is_(None),
    ).scalar() or 0
    return SubmissionItem(
        id=sub.id,
        user_id=sub.user_id,
        user_name=(u.name if u else "") or "",
        user_email=(u.email if u else "") or "",
        display_name=sub.display_name,
        project_id=sub.project_id,
        asset_count=int(asset_count),
        created_at=sub.created_at,
    )


@router.patch("/submission-links/{link_id}", response_model=SubmissionLinkResponse)
def update_submission_link(
    link_id: uuid.UUID,
    body: SubmissionLinkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    link = _get_owned_link(db, link_id, current_user)
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")
    link.title = title
    link.instructions = body.instructions
    link.expires_at = body.expires_at
    db.commit()
    db.refresh(link)
    resp = SubmissionLinkResponse.model_validate(link)
    resp.submission_count = _count_map(db, [link.id]).get(link.id, 0)
    resp.has_brief = bool(link.brief_pdf_s3_key)
    resp.has_brief_json = bool(link.brief_json)
    return resp


@router.delete("/submission-links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def disable_submission_link(
    link_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft-delete the link. Already-provisioned submitter projects are untouched."""
    link = _get_owned_link(db, link_id, current_user)
    link.deleted_at = datetime.now(timezone.utc)
    link.is_enabled = False
    db.commit()


@router.post("/submission-links/{link_id}/dissolve", status_code=status.HTTP_204_NO_CONTENT)
def dissolve_submission_link(
    link_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Undo a request: return every project it grouped (children, per-editor
    submissions, and the shared reference) to standalone — they reappear in /projects
    with their files intact — then soft-delete the request. Nothing is deleted; this
    only unlinks. Use this to reverse a 'convert to request'."""
    link = _get_owned_link(db, link_id, current_user)
    # Detach all child projects (incl. auto-provisioned per-editor ones).
    db.query(Project).filter(Project.submission_link_id == link.id).update(
        {Project.submission_link_id: None}, synchronize_session=False
    )
    # Unlink the shared reference without deleting it.
    link.reference_project_id = None
    link.deleted_at = datetime.now(timezone.utc)
    link.is_enabled = False
    db.commit()


# ── Shared reference folder ──────────────────────────────────────────────────

@router.post("/submission-links/{link_id}/reference", response_model=ReferenceResponse)
def enable_reference(
    link_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Enable a shared reference project for this request: one project all submitters
    can view. Idempotent — returns the existing one if already enabled."""
    link = _get_owned_link(db, link_id, current_user)

    if link.reference_project_id:
        existing_proj = db.query(Project).filter(
            Project.id == link.reference_project_id,
            Project.deleted_at.is_(None),
        ).first()
        if existing_proj:
            return ReferenceResponse(reference_project_id=existing_proj.id)
        # FK pointed at a since-deleted project — fall through and recreate.

    project = Project(
        name=f"{link.title} — Shared reference",
        description=f"Shared reference for “{link.title}”. Visible to every submitter.",
        project_type=ProjectType.team,
        created_by=link.created_by,
    )
    db.add(project)
    db.flush()
    db.add(ProjectMember(
        project_id=project.id,
        user_id=link.created_by,
        role=ProjectRole.owner,
        invited_by=link.created_by,
    ))
    db.add(build_default_project_share_link(project.id, link.created_by, project.name))
    # Enroll every current submitter (except the owner) as a viewer.
    subs = db.query(Submission).filter(Submission.submission_link_id == link.id).all()
    for s in subs:
        if s.user_id == link.created_by:
            continue
        db.add(ProjectMember(
            project_id=project.id,
            user_id=s.user_id,
            role=ProjectRole.viewer,
            invited_by=link.created_by,
        ))
    link.reference_project_id = project.id
    db.commit()
    return ReferenceResponse(reference_project_id=project.id)


@router.delete("/submission-links/{link_id}/reference", status_code=status.HTTP_204_NO_CONTENT)
def disable_reference(
    link_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Disable the shared reference: soft-delete its project (which drops it from every
    submitter's view) and unlink it. Submitters' own projects are untouched."""
    link = _get_owned_link(db, link_id, current_user)
    if link.reference_project_id:
        proj = db.query(Project).filter(Project.id == link.reference_project_id).first()
        if proj and proj.deleted_at is None:
            # Only clean up an empty purpose-built shell. A reference that has content
            # (e.g. an existing project attached as reference) is preserved — just
            # unlinked — so disabling never destroys real work.
            asset_count = db.query(func.count(Asset.id)).filter(
                Asset.project_id == proj.id, Asset.deleted_at.is_(None),
            ).scalar() or 0
            if asset_count == 0:
                proj.deleted_at = datetime.now(timezone.utc)
        link.reference_project_id = None
        db.commit()


# ── Attach existing projects to a request ────────────────────────────────────

def _require_project_owner(db: Session, project_id: uuid.UUID, user: User) -> None:
    owner = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user.id,
        ProjectMember.deleted_at.is_(None),
        ProjectMember.role == ProjectRole.owner,
    ).first()
    if not owner:
        raise HTTPException(status_code=403, detail="Project owner access required")


def _enroll_submitters_as_viewers(db: Session, link: SubmissionLink, project_id: uuid.UUID) -> None:
    """Give every submitter on `link` viewer access to `project_id` (the shared
    reference). Idempotent; skips the owner, who already owns it."""
    subs = db.query(Submission).filter(Submission.submission_link_id == link.id).all()
    for s in subs:
        if s.user_id == link.created_by:
            continue
        existing = db.query(ProjectMember).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == s.user_id,
        ).first()
        if existing:
            if existing.deleted_at is not None:
                existing.deleted_at = None
                existing.role = ProjectRole.viewer
        else:
            db.add(ProjectMember(
                project_id=project_id,
                user_id=s.user_id,
                role=ProjectRole.viewer,
                invited_by=link.created_by,
            ))


@router.post("/submission-links/{link_id}/attach-project/{project_id}", response_model=ReferenceResponse)
def attach_project(
    link_id: uuid.UUID,
    project_id: uuid.UUID,
    body: AttachProjectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add an existing project to an existing request — as a child folder (default)
    or as the request's shared reference. Requires owning both the request and the
    project."""
    link = _get_owned_link(db, link_id, current_user)
    project = db.query(Project).filter(
        Project.id == project_id, Project.deleted_at.is_(None),
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    _require_project_owner(db, project_id, current_user)

    # A per-editor submission project can't be re-homed.
    if db.query(Submission).filter(Submission.project_id == project_id).first():
        raise HTTPException(status_code=400, detail="This project is an editor submission and can't be attached")

    if body.as_reference:
        link.reference_project_id = project.id
        _enroll_submitters_as_viewers(db, link, project.id)
    else:
        # A project that's already a shared reference can't double as a child folder.
        if db.query(SubmissionLink).filter(
            SubmissionLink.reference_project_id == project_id,
            SubmissionLink.deleted_at.is_(None),
        ).first():
            raise HTTPException(status_code=400, detail="This project is a shared reference and can't be added as a folder")
        project.submission_link_id = link.id
    db.commit()
    return ReferenceResponse(reference_project_id=link.reference_project_id)


@router.post("/submission-links/{link_id}/detach-project/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def detach_project(
    link_id: uuid.UUID,
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a manually-attached project (child folder or shared reference) from a
    request. Per-editor submission projects are left in place."""
    link = _get_owned_link(db, link_id, current_user)
    changed = False
    if link.reference_project_id == project_id:
        link.reference_project_id = None
        changed = True
    project = db.query(Project).filter(Project.id == project_id).first()
    if project and project.submission_link_id == link.id:
        is_submission = db.query(Submission).filter(Submission.project_id == project_id).first()
        if not is_submission:
            project.submission_link_id = None
            changed = True
    if changed:
        db.commit()


@router.get("/submission-links/{link_id}/projects", response_model=list[ChildProjectItem])
def list_request_projects(
    link_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually-attached child projects for a request (excludes per-editor submissions,
    which the /submissions endpoint returns). Includes the shared reference, flagged."""
    link = _get_owned_link(db, link_id, current_user)

    submission_pids = {
        pid for (pid,) in db.query(Submission.project_id)
        .filter(Submission.submission_link_id == link.id).all()
    }
    projects = db.query(Project).filter(
        Project.submission_link_id == link.id,
        Project.deleted_at.is_(None),
    ).all()
    attached = [p for p in projects if p.id not in submission_pids]

    # The shared reference isn't a child (no submission_link_id) — append it, flagged.
    ref_project = None
    if link.reference_project_id:
        ref_project = db.query(Project).filter(
            Project.id == link.reference_project_id,
            Project.deleted_at.is_(None),
        ).first()

    pids = [p.id for p in attached] + ([ref_project.id] if ref_project else [])
    asset_counts = {}
    if pids:
        rows = (
            db.query(Asset.project_id, func.count(Asset.id))
            .filter(Asset.project_id.in_(pids), Asset.deleted_at.is_(None))
            .group_by(Asset.project_id)
            .all()
        )
        asset_counts = {pid: int(c) for pid, c in rows}

    out = [
        ChildProjectItem(
            project_id=p.id, name=p.name,
            asset_count=asset_counts.get(p.id, 0), is_reference=False,
        )
        for p in attached
    ]
    if ref_project:
        out.append(ChildProjectItem(
            project_id=ref_project.id, name=ref_project.name,
            asset_count=asset_counts.get(ref_project.id, 0), is_reference=True,
        ))
    return out


# ── Admin: pre-create a submission slot for an email ─────────────────────────

class PreCreateSubmissionRequest(BaseModel):
    email: str
    display_name: str | None = None


@router.post(
    "/submission-links/{link_id}/pre-create",
    response_model=SubmissionItem,
    status_code=status.HTTP_201_CREATED,
)
def pre_create_submission(
    link_id: uuid.UUID,
    body: PreCreateSubmissionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Admin: pre-provision a per-submitter project for an email address.

    Mirrors POST /submit/{token}/accept but runs on behalf of an email the
    person hasn't signed in with yet. Idempotent — returns the existing slot
    if that email already has one. When they sign in later the submission is
    already there and they land straight into their project.
    """
    require_platform_admin(current_user)
    link = _get_owned_link(db, link_id, current_user)

    email = body.email.lower().strip()
    user = get_user_by_email(db, email)
    if user is None:
        user = User(
            email=email,
            name=body.display_name or email.split("@")[0],
            status=UserStatus.pending_invite,
            email_verified=False,
        )
        db.add(user)
        db.flush()

    # Idempotent: already provisioned → return the existing slot.
    existing = db.query(Submission).filter(
        Submission.submission_link_id == link.id,
        Submission.user_id == user.id,
    ).first()
    if existing:
        asset_count = db.query(func.count(Asset.id)).filter(
            Asset.project_id == existing.project_id,
            Asset.deleted_at.is_(None),
        ).scalar() or 0
        return SubmissionItem(
            id=existing.id,
            user_id=existing.user_id,
            user_name=user.name or "",
            user_email=user.email,
            display_name=existing.display_name,
            project_id=existing.project_id,
            asset_count=int(asset_count),
            created_at=existing.created_at,
        )

    submitter_label = (body.display_name or user.name or email.split("@")[0]).strip()
    project = Project(
        name=_unique_project_name(db, link, f"{link.title} — {submitter_label}"),
        description=f"Submission for \"{link.title}\".",
        project_type=ProjectType.team,
        created_by=link.created_by,
        submission_link_id=link.id,
    )
    db.add(project)
    db.flush()

    db.add(ProjectMember(
        project_id=project.id,
        user_id=link.created_by,
        role=ProjectRole.owner,
        invited_by=link.created_by,
    ))
    if user.id != link.created_by:
        db.add(ProjectMember(
            project_id=project.id,
            user_id=user.id,
            role=link.grant_role,
            invited_by=link.created_by,
        ))

    submission = Submission(
        submission_link_id=link.id,
        user_id=user.id,
        project_id=project.id,
        display_name=body.display_name,
    )
    db.add(submission)

    if link.reference_project_id and user.id != link.created_by:
        db.add(ProjectMember(
            project_id=link.reference_project_id,
            user_id=user.id,
            role=ProjectRole.viewer,
            invited_by=link.created_by,
        ))

    db.add(build_default_project_share_link(project.id, link.created_by, project.name))

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(Submission).filter(
            Submission.submission_link_id == link.id,
            Submission.user_id == user.id,
        ).first()
        if existing:
            return SubmissionItem(
                id=existing.id,
                user_id=existing.user_id,
                user_name=user.name or "",
                user_email=user.email,
                display_name=existing.display_name,
                project_id=existing.project_id,
                asset_count=0,
                created_at=existing.created_at,
            )
        raise

    return SubmissionItem(
        id=submission.id,
        user_id=user.id,
        user_name=user.name or "",
        user_email=user.email,
        display_name=submission.display_name,
        project_id=project.id,
        asset_count=0,
        created_at=submission.created_at,
    )


# ── Visitor-facing ───────────────────────────────────────────────────────────

@router.get("/submit/{token}", response_model=SubmissionLinkPublic)
def resolve_submission_link(
    token: str,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    link = _validate_active(
        db.query(SubmissionLink).filter(SubmissionLink.token == token).first()
    )
    return SubmissionLinkPublic(
        title=link.title,
        instructions=link.instructions,
        requires_auth=current_user is None,
        has_brief=bool(link.brief_pdf_s3_key),
        brief_json=link.brief_json,
        persona_label=link.persona_label,
        angle_label=link.angle_label,
        problem=link.problem,
    )


@router.get("/submit/{token}/brief.pdf")
def get_submission_brief_pdf(token: str, db: Session = Depends(get_db)):
    """Public: redirect to the brief PDF for a submission request, if it has one.

    Token-gated like the submit page (no API key). Redirects to a fresh
    short-lived presigned URL so the link never goes stale.
    """
    link = _validate_active(
        db.query(SubmissionLink).filter(SubmissionLink.token == token).first()
    )
    if not link.brief_pdf_s3_key:
        raise HTTPException(status_code=404, detail="No brief PDF for this request")
    url = s3_service.generate_presigned_get_url(link.brief_pdf_s3_key, expires_in=3600, download_filename="brief.pdf")
    return RedirectResponse(url)


@router.post("/submit/{token}/accept", response_model=SubmissionAcceptResponse)
def accept_submission_link(
    token: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Provision (or return) the current user's private project for this link."""
    link = _validate_active(
        db.query(SubmissionLink).filter(SubmissionLink.token == token).first()
    )

    # Idempotent: already accepted → return the existing project.
    existing = db.query(Submission).filter(
        Submission.submission_link_id == link.id,
        Submission.user_id == current_user.id,
    ).first()
    if existing:
        return SubmissionAcceptResponse(project_id=existing.project_id)

    submitter_label = (current_user.name or current_user.email or "Submission").strip()
    project = Project(
        name=_unique_project_name(db, link, f"{link.title} — {submitter_label}"),
        description=f"Submission for “{link.title}”.",
        project_type=ProjectType.team,
        created_by=link.created_by,
        submission_link_id=link.id,
    )
    db.add(project)
    db.flush()

    # Owner (the link creator) is owner of every per-submitter project.
    db.add(ProjectMember(
        project_id=project.id,
        user_id=link.created_by,
        role=ProjectRole.owner,
        invited_by=link.created_by,
    ))
    # The submitter gets the granted role (editor => can upload), unless they ARE
    # the owner (owner testing their own link) — the unique constraint forbids dupes.
    if current_user.id != link.created_by:
        db.add(ProjectMember(
            project_id=project.id,
            user_id=current_user.id,
            role=link.grant_role,
            invited_by=link.created_by,
        ))

    submission = Submission(
        submission_link_id=link.id,
        user_id=current_user.id,
        project_id=project.id,
    )
    db.add(submission)
    # If this request has a shared reference folder enabled, enroll the new submitter
    # as a viewer of it (the owner is already its owner; skip them).
    if link.reference_project_id and current_user.id != link.created_by:
        db.add(ProjectMember(
            project_id=link.reference_project_id,
            user_id=current_user.id,
            role=ProjectRole.viewer,
            invited_by=link.created_by,
        ))
    # Default share link for the submitter's project: private (login required) view +
    # comment. Owned by the link creator (the reviewer), matching project ownership.
    db.add(build_default_project_share_link(project.id, link.created_by, project.name))
    try:
        db.commit()
    except IntegrityError:
        # Lost a race with a concurrent accept — return the winner's project.
        db.rollback()
        existing = db.query(Submission).filter(
            Submission.submission_link_id == link.id,
            Submission.user_id == current_user.id,
        ).first()
        if existing:
            return SubmissionAcceptResponse(project_id=existing.project_id)
        raise
    return SubmissionAcceptResponse(project_id=project.id)
