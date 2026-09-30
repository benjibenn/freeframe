"""Tests for the source link an uploader must give with every file.

Intent encoded:
- the link is the only trace back from a delivered file to the artwork it was
  made from, so it is required at initiate — after the upload there is no moment
  that forces it, and a file without one cannot be revised by anyone else.
- it lands as a comment on the VERSION, not the asset: a revision is usually a
  different Figma frame, so v2's source must not be read as v1's.
- internal, not public: share-link guests are the client, and the working file
  is not theirs to see.
"""
import uuid

import pytest

from apps.api.schemas.upload import InitiateUploadRequest
from apps.api.services import source_link


def test_keeps_the_link_as_given():
    assert source_link.normalize("  https://figma.com/file/abc  ") == "https://figma.com/file/abc"


@pytest.mark.parametrize("blank", ["", "   ", "\n\t"])
def test_refuses_a_blank_link(blank):
    with pytest.raises(ValueError, match="source_url"):
        source_link.normalize(blank)


def test_accepts_anything_non_blank():
    # Deliberately unvalidated beyond non-blank: a source may be a Figma or Canva
    # URL, a Drive folder, or a path inside a shared volume, and refusing the odd
    # one out would block an upload for a rule nobody agreed to.
    assert source_link.normalize("canva.com/design/xyz") == "canva.com/design/xyz"


def test_the_comment_is_the_first_thing_on_that_version():
    asset_id, version_id, author_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    comment = source_link.source_comment(
        asset_id=asset_id,
        version_id=version_id,
        author_id=author_id,
        source_url="https://figma.com/file/abc",
    )

    assert comment.asset_id == asset_id
    assert comment.version_id == version_id
    assert comment.author_id == author_id
    assert "https://figma.com/file/abc" in comment.body


def test_the_comment_is_not_visible_to_share_link_guests():
    comment = source_link.source_comment(
        asset_id=uuid.uuid4(), version_id=uuid.uuid4(), author_id=uuid.uuid4(),
        source_url="https://figma.com/file/abc",
    )

    assert comment.visibility == "internal"


# ── The request cannot be made without one ────────────────────────────────────

def _body(**over):
    return dict(
        project_id=uuid.uuid4(),
        asset_name="Hook 1",
        original_filename="hook1.mp4",
        mime_type="video/mp4",
        file_size_bytes=10,
        source_url="https://figma.com/file/abc",
    ) | over


def test_initiate_requires_a_source_url():
    with pytest.raises(ValueError):
        InitiateUploadRequest(**{k: v for k, v in _body().items() if k != "source_url"})


def test_initiate_refuses_a_blank_source_url():
    with pytest.raises(ValueError, match="source_url"):
        InitiateUploadRequest(**_body(source_url="   "))


def test_initiate_stores_the_link_stripped():
    assert InitiateUploadRequest(**_body(source_url=" x ")).source_url == "x"


# ── End to end through /upload/initiate ───────────────────────────────────────
#
# Reuses the harness in test_hook_naming, which is the only place that drives the
# real endpoint. What matters here is the pairing: one upload, one comment, on the
# version that upload created.

from unittest.mock import MagicMock, patch  # noqa: E402

from apps.api.models.asset import AssetType  # noqa: E402
from apps.api.models.comment import Comment  # noqa: E402
from apps.api.tests.test_hook_naming import (  # noqa: E402
    _initiate_body, _mock_project, _wire_db,
)


@patch("apps.api.routers.upload.create_multipart_upload", return_value="upload-123")
@patch("apps.api.routers.upload.require_project_role")
@patch("apps.api.services.hook_naming.next_hook_name", return_value="Hook 1")
def test_an_upload_records_its_source_as_the_versions_first_comment(
    _hook_name, _role, _create, client, mock_db, auth_headers
):
    project = _mock_project(uuid.uuid4())
    added = []
    # Padded: the endpoint's exact query count varies with what else has run
    # (the tests in test_hook_naming are order-dependent for this reason). Extra
    # Nones are never read, a missing one raises StopIteration mid-request.
    _wire_db(mock_db, added, [project, None, None, project, None, None, None, None])

    body = _initiate_body(project.id) | {"source_url": "https://figma.com/file/xyz/Hook-1"}
    res = client.post("/upload/initiate", json=body, headers=auth_headers)

    assert res.status_code == 200, res.text
    comments = [o for o in added if isinstance(o, Comment)]
    assert len(comments) == 1
    assert comments[0].body == "Source: https://figma.com/file/xyz/Hook-1"
    # Bound to the version this upload made, so a later revision's source cannot
    # be mistaken for this one's.
    assert str(comments[0].version_id) == res.json()["version_id"]
    assert str(comments[0].asset_id) == res.json()["asset_id"]


@patch("apps.api.routers.upload.create_multipart_upload", return_value="upload-123")
@patch("apps.api.routers.upload.require_project_role")
def test_an_upload_with_no_source_is_refused_before_anything_is_created(
    _role, _create, client, mock_db, auth_headers
):
    """422 at the schema, so no asset, no version and no S3 multipart exist."""
    project = _mock_project(uuid.uuid4())
    added = []
    _wire_db(mock_db, added, [project, None, None, project, None, None, None, None])

    body = {k: v for k, v in _initiate_body(project.id).items() if k != "source_url"}
    res = client.post("/upload/initiate", json=body, headers=auth_headers)

    assert res.status_code == 422
    assert added == []
    _create.assert_not_called()


@patch("apps.api.routers.assets.create_multipart_upload", return_value="upload-456")
@patch("apps.api.routers.assets.require_project_role")
def test_a_new_version_records_its_own_source(_role, _create, client, mock_db, auth_headers):
    """v2 is usually a different frame — inheriting v1's link would misattribute it."""
    asset = MagicMock()
    asset.id = uuid.uuid4()
    asset.project_id = uuid.uuid4()
    asset.deleted_at = None
    asset.asset_type = AssetType.image
    added = []
    _wire_db(mock_db, added, [asset, None, None, None, None])

    res = client.post(
        f"/assets/{asset.id}/versions",
        json=_initiate_body(asset.project_id) | {"source_url": "https://figma.com/file/xyz/v2"},
        headers=auth_headers,
    )

    assert res.status_code == 200, res.text
    comments = [o for o in added if isinstance(o, Comment)]
    assert len(comments) == 1
    assert comments[0].body == "Source: https://figma.com/file/xyz/v2"
    assert str(comments[0].version_id) == res.json()["version_id"]


def test_submitted_work_cannot_omit_its_source():
    """The from-url path creates an asset and a version like an upload does, so it
    is held to the same rule rather than being a way around it."""
    from apps.api.routers.submissions import SubmitWorkFromUrlRequest

    with pytest.raises(ValueError, match="source_url"):
        SubmitWorkFromUrlRequest(url="https://cdn.example.com/a.png", source_url=" ")
    with pytest.raises(ValueError):
        SubmitWorkFromUrlRequest(url="https://cdn.example.com/a.png")
    assert SubmitWorkFromUrlRequest(
        url="https://cdn.example.com/a.png", source_url=" https://figma.com/x "
    ).source_url == "https://figma.com/x"
