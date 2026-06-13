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

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware.auth import get_current_user, get_optional_user
from ..models.user import User
from ..models.project import Project, ProjectMember, ProjectRole, ProjectType
from ..models.asset import Asset
from ..models.submission import SubmissionLink, Submission
from ..schemas.submission import (
    SubmissionLinkCreate,
    SubmissionLinkResponse,
    SubmissionLinkPublic,
    SubmissionAcceptResponse,
    SubmissionItem,
    SubmissionUpdate,
    ReferenceResponse,
)
from ..services.share_service import build_default_project_share_link

router = APIRouter(tags=["submissions"])


def _get_owned_link(db: Session, link_id: uuid.UUID, user: User) -> SubmissionLink:
    link = db.query(SubmissionLink).filter(
        SubmissionLink.id == link_id,
        SubmissionLink.deleted_at.is_(None),
    ).first()
    if not link:
        raise HTTPException(status_code=404, detail="Submission link not found")
    if link.created_by != user.id:
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Convert an existing project into a video request: create a submission link
    titled after the project and make the project the request's shared reference
    (its current assets become brief/examples visible to every editor). Editors who
    accept the link still upload into their own private per-editor projects."""
    project = db.query(Project).filter(
        Project.id == project_id, Project.deleted_at.is_(None),
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    owner = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == current_user.id,
        ProjectMember.deleted_at.is_(None),
        ProjectMember.role == ProjectRole.owner,
    ).first()
    if not owner:
        raise HTTPException(status_code=403, detail="Project owner access required")

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
        reference_project_id=project.id,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    resp = SubmissionLinkResponse.model_validate(link)
    resp.submission_count = 0
    return resp


@router.get("/submission-links", response_model=list[SubmissionLinkResponse])
def list_submission_links(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    links = db.query(SubmissionLink).filter(
        SubmissionLink.created_by == current_user.id,
        SubmissionLink.deleted_at.is_(None),
    ).order_by(SubmissionLink.created_at.desc()).all()
    counts = _count_map(db, [l.id for l in links])
    out = []
    for l in links:
        resp = SubmissionLinkResponse.model_validate(l)
        resp.submission_count = counts.get(l.id, 0)
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
            proj.deleted_at = datetime.now(timezone.utc)
        link.reference_project_id = None
        db.commit()


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
    )


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
