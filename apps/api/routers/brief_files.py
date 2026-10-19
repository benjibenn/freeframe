"""Briefs as folders: file counts per brief, and downloads named after the brief.

Editors submit into their own projects, so a brief's files are every live asset
in its submissions' projects. Downloads are named "<brief title> - <language>",
the language being the part of the file name before " — " ("French — French · EUR").
"""
import os
import re
import tempfile
import uuid
import zipfile
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.asset import Asset, AssetType, AssetVersion, MediaFile
from ..models.submission import Submission, SubmissionLink
from ..models.user import User
from ..services import s3_service
from ..services.permissions import can_view_project, is_platform_admin
from .submissions import _get_owned_link

router = APIRouter(tags=["brief-files"])

_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')


def _download_name(brief_title: str, asset_name: str, source: Optional[str]) -> str:
    language = asset_name.split(" — ", 1)[0].strip() or asset_name
    base = _UNSAFE.sub("", f"{brief_title} - {language}").strip()
    return s3_service.build_download_filename(base, source)


def _media(db: Session, asset: Asset) -> tuple[str, Optional[str]]:
    """The S3 key a download serves, and the name its extension comes from.
    Same choice as GET /assets/{id}/stream?download=true: the original upload for
    videos, the processed file (or raw) for everything else."""
    version = (
        db.query(AssetVersion)
        .filter(AssetVersion.asset_id == asset.id, AssetVersion.deleted_at.is_(None))
        .order_by(AssetVersion.version_number.desc())
        .first()
    )
    media = db.query(MediaFile).filter(MediaFile.version_id == version.id).first() if version else None
    if not media:
        raise HTTPException(status_code=404, detail="Media file not found")
    if asset.asset_type == AssetType.video:
        key = media.s3_key_raw or media.s3_key_processed
    else:
        key = media.s3_key_processed or media.s3_key_raw
    if not key:
        raise HTTPException(status_code=409, detail="File is not stored yet")
    return key, media.original_filename or key


def _brief_assets(db: Session, link: SubmissionLink) -> list[Asset]:
    project_ids = [
        pid for (pid,) in db.query(Submission.project_id)
        .filter(Submission.submission_link_id == link.id)
        .all()
    ]
    if not project_ids:
        return []
    return (
        db.query(Asset)
        .filter(Asset.project_id.in_(project_ids), Asset.deleted_at.is_(None))
        .order_by(Asset.created_at.asc())
        .all()
    )


@router.get("/projects/{project_id}/brief-file-counts", response_model=dict[str, int])
def brief_file_counts(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Live file count for each brief filed in this project (briefs with no
    submissions are left out). Same visibility as GET /submission-links."""
    if not can_view_project(db, project_id, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a project member")
    q = (
        db.query(SubmissionLink.id, func.count(Asset.id))
        .join(Submission, Submission.submission_link_id == SubmissionLink.id)
        .join(Asset, (Asset.project_id == Submission.project_id) & Asset.deleted_at.is_(None))
        .filter(SubmissionLink.home_project_id == project_id, SubmissionLink.deleted_at.is_(None))
    )
    if not is_platform_admin(current_user):
        q = q.filter(SubmissionLink.created_by == current_user.id)
    return {str(link_id): n for link_id, n in q.group_by(SubmissionLink.id).all()}


@router.get("/submission-links/{link_id}/files/{asset_id}/download")
def download_brief_file(
    link_id: uuid.UUID,
    asset_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """A presigned URL for one submitted file, saved as "<brief title> - <language>"."""
    link = _get_owned_link(db, link_id, current_user)
    asset = next((a for a in _brief_assets(db, link) if a.id == asset_id), None)
    if not asset:
        raise HTTPException(status_code=404, detail="File not found in this brief")
    key, source = _media(db, asset)
    name = _download_name(link.title or "Brief", asset.name, source)
    return {"url": s3_service.generate_presigned_get_url(key, download_filename=name), "filename": name}


@router.get("/submission-links/{link_id}/download-all")
def download_brief_zip(
    link_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Every submitted file of a brief in one ZIP, each named like a single download."""
    link = _get_owned_link(db, link_id, current_user)
    assets = _brief_assets(db, link)
    if not assets:
        raise HTTPException(status_code=404, detail="This brief has no files")
    title = link.title or "Brief"
    s3 = s3_service.get_s3_client()
    spool = tempfile.SpooledTemporaryFile(max_size=64 * 1024 * 1024)
    used: set[str] = set()
    with zipfile.ZipFile(spool, "w", zipfile.ZIP_STORED) as zf:
        for asset in assets:
            try:
                key, source = _media(db, asset)
            except HTTPException:
                continue  # still uploading or no media: leave it out
            name = _download_name(title, asset.name, source)
            stem, ext = os.path.splitext(name)
            n = 2
            while name.lower() in used:
                name = f"{stem} ({n}){ext}"
                n += 1
            used.add(name.lower())
            body = s3.get_object(Bucket=settings.s3_bucket, Key=key)["Body"]
            with zf.open(name, "w", force_zip64=True) as out:
                for chunk in iter(lambda: body.read(1024 * 1024), b""):
                    out.write(chunk)
    spool.seek(0)
    zip_name = _UNSAFE.sub("", title).strip() + ".zip"

    def stream():
        try:
            for chunk in iter(lambda: spool.read(1024 * 1024), b""):
                yield chunk
        finally:
            spool.close()

    return StreamingResponse(
        stream(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(zip_name)}"},
    )
