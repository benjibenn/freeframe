import asyncio
import uuid
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from .celery_app import celery_app, send_task_safe
from ._events import publish_event
from ..database import SessionLocal
from ..models.asset import Asset, AssetVersion, MediaFile, AssetType
from ..models.tag_palette import TagPaletteLabel
from ..services.s3_service import get_s3_client
from ..services.gemini_service import GeminiClient, Analysis
from ..services.tags import normalize_tags
from ..config import settings

SUPPORTED = (AssetType.video, AssetType.image, AssetType.image_carousel)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _analyze(media_file) -> Analysis:
    """Download raw media from S3, upload to Gemini, and return Analysis."""
    async def _inner():
        s3 = get_s3_client()
        data = s3.get_object(Bucket=settings.s3_bucket, Key=media_file.s3_key_raw)["Body"].read()
        gc = GeminiClient.from_settings()
        try:
            file = await gc.upload_file(data, media_file.mime_type, media_file.original_filename)
            await gc.wait_until_active(file["uri"])
            return await gc.analyze_media(file["uri"], media_file.mime_type)
        finally:
            await gc.aclose()
    return _run_async(_inner())


def _match(summary: str, transcript: str, palette: list[str]) -> list[str]:
    """Ask Gemini to match the asset against the tag palette."""
    async def _inner():
        gc = GeminiClient.from_settings()
        try:
            return await gc.match_tags(summary, transcript, palette)
        finally:
            await gc.aclose()
    return _run_async(_inner())


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60, acks_late=True, reject_on_worker_lost=True)
def autotag_asset(self, asset_id: str, version_id: str, force: bool = False):
    db = SessionLocal()
    try:
        asset = db.query(Asset).filter(Asset.id == uuid.UUID(asset_id), Asset.deleted_at.is_(None)).first()
        if not asset:
            return
        version = db.query(AssetVersion).filter(AssetVersion.id == uuid.UUID(version_id)).first()
        if not version:
            return

        if asset.asset_type not in SUPPORTED:
            publish_event(str(asset.project_id), "autotag_skipped", {"asset_id": asset_id, "reason": "unsupported_type"})
            return

        if not settings.gemini_api_key:
            publish_event(str(asset.project_id), "autotag_skipped", {"asset_id": asset_id, "reason": "gemini_disabled"})
            return

        # Stage 1 — analysis (cached on the version)
        if version.ai_summary is None or force:
            media_file = db.query(MediaFile).filter(MediaFile.version_id == version.id).first()
            if not media_file:
                publish_event(str(asset.project_id), "autotag_skipped", {"asset_id": asset_id, "reason": "no_media_file"})
                return
            try:
                analysis = _analyze(media_file)
            except Exception as exc:
                raise self.retry(exc=exc)
            version.ai_summary = analysis.summary
            version.ai_transcript = analysis.transcript
            version.ai_analyzed_at = datetime.now(timezone.utc)
            db.commit()

        # Stage 2 — match against the project palette
        palette = [
            row.label for row in db.query(TagPaletteLabel).filter(
                TagPaletteLabel.project_id == asset.project_id,
                TagPaletteLabel.deleted_at.is_(None),
            ).all()
        ]
        if not palette:
            publish_event(str(asset.project_id), "autotag_skipped", {"asset_id": asset_id, "reason": "empty_palette"})
            return

        try:
            matched = _match(version.ai_summary, version.ai_transcript or "", palette)
        except Exception as exc:
            raise self.retry(exc=exc)

        # Apply — normalized, idempotent
        current = list(asset.keywords or [])
        applied: list[str] = []
        for label in matched:
            for norm in normalize_tags([label]):
                if norm not in current:
                    current.append(norm)
                    applied.append(norm)
        asset.keywords = current
        db.commit()
        publish_event(str(asset.project_id), "autotag_complete", {"asset_id": asset_id, "applied": applied})
    finally:
        db.close()


@celery_app.task
def autotag_batch(asset_ids: list[str], skip_if_tagged: bool = True):
    db = SessionLocal()
    try:
        for aid in asset_ids:
            asset = db.query(Asset).filter(Asset.id == uuid.UUID(aid), Asset.deleted_at.is_(None)).first()
            if not asset:
                continue
            if skip_if_tagged and asset.keywords:
                continue
            version = db.query(AssetVersion).filter(
                AssetVersion.asset_id == asset.id,
                AssetVersion.deleted_at.is_(None),
            ).order_by(AssetVersion.version_number.desc()).first()
            if version:
                send_task_safe(autotag_asset, aid, str(version.id), False)
    finally:
        db.close()
