"""One-off backfill: synthesize `created` activity-log rows for uploads that
predate activity logging, so the platform-wide activity feed shows every
existing submission / uploaded version (by everyone), not just events captured
after the feature shipped.

Idempotent: skips any (asset, version_number) that already has a `created` log,
so it is safe to re-run. Original upload timestamps are preserved.

Run inside the api container:
    docker compose -f docker-compose.prod.yml exec -T api \
        python -m apps.api.scripts.backfill_activity
"""
try:
    from ..database import SessionLocal
    from ..models.asset import Asset, AssetVersion, MediaFile
    from ..models.activity import ActivityLog, ActivityAction
except ImportError:  # allow `python apps/api/scripts/backfill_activity.py`
    from apps.api.database import SessionLocal
    from apps.api.models.asset import Asset, AssetVersion, MediaFile
    from apps.api.models.activity import ActivityLog, ActivityAction


def main() -> None:
    db = SessionLocal()
    try:
        # (asset_id, version_number) pairs already represented as a `created` log.
        existing: set[tuple[str, object]] = set()
        for log in db.query(ActivityLog).filter(ActivityLog.action == ActivityAction.created).all():
            if log.asset_id is not None:
                existing.add((str(log.asset_id), (log.payload or {}).get("version_number")))

        versions = db.query(AssetVersion).filter(AssetVersion.deleted_at.is_(None)).all()
        assets = {a.id: a for a in db.query(Asset).all()}

        created = 0
        for v in versions:
            asset = assets.get(v.asset_id)
            if not asset:
                continue
            if (str(asset.id), v.version_number) in existing:
                continue
            mf = db.query(MediaFile).filter(MediaFile.version_id == v.id).first()
            db.add(ActivityLog(
                user_id=v.created_by,
                asset_id=asset.id,
                project_id=asset.project_id,
                action=ActivityAction.created,
                payload={
                    "version_number": v.version_number,
                    "is_new_asset": v.version_number == 1,
                    "filename": mf.original_filename if mf else None,
                    "backfilled": True,
                },
                created_at=v.created_at,  # preserve real upload time for ordering
            ))
            created += 1

        db.commit()
        print(f"Backfilled {created} upload activities ({len(versions)} versions scanned).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
