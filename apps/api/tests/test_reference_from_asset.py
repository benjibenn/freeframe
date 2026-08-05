"""Attaching a References-library asset to a brief.

Two properties matter more than the happy path, because getting either wrong
destroys data rather than merely erroring:

  * The object is COPIED. Detaching a reference calls delete_object on its key,
    so if a brief stored the library's own key, removing that reference from one
    brief would delete the library asset out from under every other brief.
  * Attach is permission-checked. Brief tokens are handed to external
    submitters, and the public /submit/{token}/reference-* route redirects to a
    presigned URL for whatever key the brief holds — so attaching an asset the
    caller cannot read would turn any brief into an arbitrary-object read.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from apps.api.models.asset import AssetType
from apps.api.routers import submissions as subs


def _valid_link():
    """A mock link whose attributes pass SubmissionLinkResponse.model_validate."""
    link = MagicMock()
    link.id = uuid.uuid4()
    link.token = "tok"
    link.title = "T"
    link.instructions = None
    link.is_enabled = True
    link.expires_at = None
    link.created_at = datetime.now(timezone.utc)
    link.reference_project_id = None
    link.persona_label = link.angle_label = link.problem = None
    link.brief_pdf_s3_key = None
    link.brief_json = None
    link.brief_reference_video_s3_keys = []
    link.brief_reference_image_s3_keys = []
    link.home_project_id = None
    link.home_folder_id = None
    link.home_path = None
    link.taxonomy_path = None
    return link


def _db_returning(asset, version, media):
    """A db whose .query(Model) chain yields the right row per model."""
    from apps.api.models.asset import Asset, AssetVersion, MediaFile

    def query(model):
        q = MagicMock()
        result = {Asset: asset, AssetVersion: version, MediaFile: media}.get(model)
        q.filter.return_value = q
        q.order_by.return_value = q
        q.first.return_value = result
        return q

    db = MagicMock()
    db.query.side_effect = query
    return db


def _asset(project_id, asset_type=AssetType.video):
    a = MagicMock()
    a.id = uuid.uuid4()
    a.project_id = project_id
    a.asset_type = asset_type
    return a


def _setup(monkeypatch, link):
    monkeypatch.setattr(subs, "_get_owned_link", lambda db, lid, u: link)
    monkeypatch.setattr(subs, "_count_map", lambda db, ids: {})
    monkeypatch.setattr(subs, "require_asset_access", lambda db, a, u: None)


def test_copies_the_object_instead_of_reusing_the_library_key(monkeypatch):
    """The brief must end up owning a distinct object under its own prefix.

    If this regresses to storing media.s3_key_raw, detaching the reference from
    any one brief deletes the library asset for everyone.
    """
    project_id = uuid.uuid4()
    link = _valid_link()
    _setup(monkeypatch, link)

    asset = _asset(project_id, AssetType.video)
    version = MagicMock(id=uuid.uuid4())
    library_key = f"raw/{project_id}/{asset.id}/{version.id}/original.mp4"
    media = MagicMock(s3_key_raw=library_key)

    copied = {}
    monkeypatch.setattr(
        subs.s3_service, "copy_object",
        lambda src, dest: copied.update(src=src, dest=dest),
    )

    resp = subs.add_reference_from_asset(
        link.id,
        subs.ReferenceFromAssetRequest(asset_id=asset.id),
        db=_db_returning(asset, version, media),
        current_user=MagicMock(),
    )

    assert copied["src"] == library_key
    assert copied["dest"] != library_key
    # Must satisfy confirm_reference_video's prefix guard, or the same key could
    # never be re-attached through the normal path.
    assert copied["dest"].startswith(subs._reference_video_prefix(link.id))
    assert link.brief_reference_video_s3_keys == [copied["dest"]]
    assert resp.has_reference_video is True


def test_rejects_an_asset_the_caller_cannot_read(monkeypatch):
    """Attach is permission-checked, not project-restricted.

    Letting a caller attach anything they can already read is not a widening —
    they could download and re-upload it as a file. Naming an asset id they
    CANNOT read is the real hazard, because /submit/{token}/reference-* is
    public: an unchecked attach turns any brief into an arbitrary-object read.
    """
    link = _valid_link()
    _setup(monkeypatch, link)

    asset = _asset(uuid.uuid4())

    def deny(db, a, user):
        raise HTTPException(status_code=403, detail="Access denied")

    monkeypatch.setattr(subs, "require_asset_access", deny)
    monkeypatch.setattr(subs.s3_service, "copy_object", lambda src, dest: pytest.fail("copied"))

    with pytest.raises(HTTPException) as ei:
        subs.add_reference_from_asset(
            link.id,
            subs.ReferenceFromAssetRequest(asset_id=asset.id),
            db=_db_returning(asset, MagicMock(), MagicMock()),
            current_user=MagicMock(),
        )
    assert ei.value.status_code == 403


def test_attaches_from_any_project_the_caller_can_read(monkeypatch):
    """Briefs pull references from ordinary projects, not just one library."""
    link = _valid_link()
    _setup(monkeypatch, link)

    asset = _asset(uuid.uuid4(), AssetType.video)  # any project
    version = MagicMock(id=uuid.uuid4())
    media = MagicMock(s3_key_raw=f"raw/p/{asset.id}/{version.id}/original.mp4")
    monkeypatch.setattr(subs.s3_service, "copy_object", lambda src, dest: None)

    subs.add_reference_from_asset(
        link.id,
        subs.ReferenceFromAssetRequest(asset_id=asset.id),
        db=_db_returning(asset, version, media),
        current_user=MagicMock(),
    )
    assert len(link.brief_reference_video_s3_keys) == 1


def test_images_land_in_the_image_list(monkeypatch):
    """The two arrays render in different places on the brief page, and the image
    key prefix must not collide with the video one."""
    project_id = uuid.uuid4()
    link = _valid_link()
    _setup(monkeypatch, link)

    asset = _asset(project_id, AssetType.image)
    version = MagicMock(id=uuid.uuid4())
    media = MagicMock(s3_key_raw=f"raw/{project_id}/{asset.id}/{version.id}/original.jpg")
    monkeypatch.setattr(subs.s3_service, "copy_object", lambda src, dest: None)

    subs.add_reference_from_asset(
        link.id,
        subs.ReferenceFromAssetRequest(asset_id=asset.id),
        db=_db_returning(asset, version, media),
        current_user=MagicMock(),
    )

    assert link.brief_reference_video_s3_keys == []
    assert len(link.brief_reference_image_s3_keys) == 1
    assert "-reference-image-" in link.brief_reference_image_s3_keys[0]
    assert link.brief_reference_image_s3_keys[0].endswith(".jpg")
