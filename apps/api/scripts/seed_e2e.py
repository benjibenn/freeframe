"""E2E seed — an admin account plus enough projects/assets to exercise the
infinite-scroll surfaces (library, my-assets, project detail, projects list).

Run from the repo root with the project on PYTHONPATH:

    PYTHONPATH=. uv run python apps/api/scripts/seed_e2e.py

Idempotent-ish: it upserts the admin user and always appends a fresh batch of
demo projects/assets. Safe for a throwaway local DB only.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from apps.api.database import SessionLocal
# Register every mapped table so cross-table FKs (e.g. projects.submission_link_id
# → submission_links) resolve at flush time. models/__init__ omits submission.
import apps.api.models  # noqa: F401
import apps.api.models.submission  # noqa: F401
from apps.api.models.user import User, UserStatus
from apps.api.models.project import Project, ProjectMember, ProjectType, ProjectRole
from apps.api.models.asset import (
    Asset, AssetVersion, MediaFile, AssetType, AssetStatus, ProcessingStatus, FileType,
)
from apps.api.services.auth_service import hash_password

ADMIN_EMAIL = "admin@demo.com"
ADMIN_PASSWORD = "password123"
ASSETS_IN_BIG_PROJECT = 30  # > page size (24) so infinite scroll actually triggers
EMPTY_PROJECTS = 22         # > reveal step (18) so the projects list reveals on scroll


def get_or_create_admin(db) -> User:
    admin = db.query(User).filter(User.email == ADMIN_EMAIL).first()
    if admin:
        admin.password_hash = hash_password(ADMIN_PASSWORD)
        admin.is_superadmin = True
        admin.status = UserStatus.active
        db.flush()
        return admin
    admin = User(
        email=ADMIN_EMAIL,
        name="Demo Admin",
        password_hash=hash_password(ADMIN_PASSWORD),
        status=UserStatus.active,
        is_superadmin=True,
        email_verified=True,
    )
    db.add(admin)
    db.flush()
    return admin


def make_asset(db, project_id, admin_id, n: int):
    asset = Asset(
        project_id=project_id,
        name=f"Demo asset {n:03d}",
        asset_type=AssetType.image,
        status=AssetStatus.in_review,
        created_by=admin_id,
        keywords=[],
    )
    db.add(asset)
    db.flush()
    version = AssetVersion(
        asset_id=asset.id,
        version_number=1,
        processing_status=ProcessingStatus.ready,  # non-failed → shows in the grid
        created_by=admin_id,
    )
    db.add(version)
    db.flush()
    db.add(MediaFile(
        version_id=version.id,
        file_type=FileType.image,
        original_filename=f"demo-{n:03d}.jpg",
        mime_type="image/jpeg",
        file_size_bytes=123_456,
        s3_key_raw=f"demo/{asset.id}/raw.jpg",
        s3_key_thumbnail=f"demo/{asset.id}/thumb.jpg",
        width=1200,
        height=800,
    ))


def seed():
    db = SessionLocal()
    try:
        admin = get_or_create_admin(db)

        # One asset-heavy project (project detail + library + my-assets tests).
        big = Project(name="E2E Big Project", project_type=ProjectType.personal, created_by=admin.id)
        db.add(big)
        db.flush()
        # Admin must be a member for /me/assets ("all") to include these.
        db.add(ProjectMember(project_id=big.id, user_id=admin.id, role=ProjectRole.owner))
        for i in range(ASSETS_IN_BIG_PROJECT):
            make_asset(db, big.id, admin.id, i)

        # Many small projects (projects-list reveal-on-scroll test).
        for i in range(EMPTY_PROJECTS):
            p = Project(name=f"E2E Project {i:02d}", project_type=ProjectType.personal, created_by=admin.id)
            db.add(p)
            db.flush()
            db.add(ProjectMember(project_id=p.id, user_id=admin.id, role=ProjectRole.owner))

        db.commit()
        print(
            f"Seeded admin={ADMIN_EMAIL} / {ADMIN_PASSWORD}; "
            f"big project '{big.name}' ({big.id}) with {ASSETS_IN_BIG_PROJECT} assets; "
            f"+{EMPTY_PROJECTS} more projects."
        )
    finally:
        db.close()


if __name__ == "__main__":
    seed()
