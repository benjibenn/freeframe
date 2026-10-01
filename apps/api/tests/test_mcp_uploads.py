"""Tests for getting files into Freeframe over MCP: local files and URLs.

Intent encoded:
- the MCP server runs beside the API, not on the caller's machine, so it never
  opens the local path it is given. The bytes go straight to storage through a
  presigned URL; the path is only used to name the file and write the command.
- every step reuses the browser's own routes (initiate, complete, abort), so the
  required source link, naming rules and processing are exactly the web's.
- finishing asks storage for the uploaded part instead of making the caller
  relay an ETag, and it must actually start processing: the route queues that
  as a response background task, which never runs without an HTTP response.
- nothing is created before a request can be refused — a bad type, a missing
  source link or a failed fetch leaves no asset or version behind.
- a deliverable submitted to a brief twice is a revision of the first, the
  same rule submit_work follows, not a second asset beside it.
"""
import uuid
from unittest.mock import MagicMock, patch

import pytest

from apps.api.routers import mcp as mcp_router
from apps.api.services.url_fetch import RemoteFetchError


def _admin():
    u = MagicMock()
    u.id = uuid.uuid4()
    u.is_superadmin = True
    u.is_subadmin = False
    u.deleted_at = None
    return u


@pytest.fixture
def as_admin(mock_db):
    user = _admin()
    user_token = mcp_router._current_user.set(user)
    db_token = mcp_router._current_db.set(mock_db)
    yield user
    mcp_router._current_user.reset(user_token)
    mcp_router._current_db.reset(db_token)


def _init(**over):
    out = MagicMock()
    out.upload_id = over.get("upload_id", "up-1")
    out.s3_key = over.get("s3_key", "raw/p/a/v/original.png")
    out.asset_id = over.get("asset_id", uuid.uuid4())
    out.version_id = over.get("version_id", uuid.uuid4())
    return out


SOURCE = "https://figma.com/file/abc"


# ── Local file into a project ─────────────────────────────────────────────────

def test_start_returns_a_command_that_sends_the_file_straight_to_storage(as_admin):
    init = _init()
    with patch.object(mcp_router.upload_router, "initiate_upload", return_value=init) as initiate, \
         patch.object(mcp_router.s3_service, "presign_upload_part", return_value="https://s3/put?sig=1") as presign:
        out = mcp_router.start_file_upload(
            project_id=str(uuid.uuid4()),
            file_path="/Users/ben/Desktop/Hook 1 final.png",
            source_url=SOURCE,
        )

    body = initiate.call_args.kwargs["body"]
    # Named from the path, typed from its extension, source carried through.
    assert body.original_filename == "Hook 1 final.png"
    assert body.asset_name == "Hook 1 final"
    assert body.mime_type == "image/png"
    assert body.source_url == SOURCE
    presign.assert_called_once_with(init.s3_key, init.upload_id, 1)
    # The path is quoted: a space in it would otherwise split the command.
    assert "'/Users/ben/Desktop/Hook 1 final.png'" in out["curl"]
    assert "https://s3/put?sig=1" in out["curl"]
    assert out["version_id"] == str(init.version_id)
    assert out["upload_id"] == "up-1"


def test_start_never_opens_the_local_path(as_admin):
    """The server cannot see the caller's disk; reading the path would at best
    fail and at worst read a file of the same name on the server."""
    with patch.object(mcp_router.upload_router, "initiate_upload", return_value=_init()), \
         patch.object(mcp_router.s3_service, "presign_upload_part", return_value="u"), \
         patch("builtins.open", side_effect=AssertionError("opened the path")) as opened:
        mcp_router.start_file_upload(
            project_id=str(uuid.uuid4()), file_path="/etc/hosts.png", source_url=SOURCE,
        )
    opened.assert_not_called()


def test_start_refuses_a_file_it_cannot_type_before_anything_exists(as_admin):
    with patch.object(mcp_router.upload_router, "initiate_upload") as initiate:
        with pytest.raises(ValueError, match="mime_type"):
            mcp_router.start_file_upload(
                project_id=str(uuid.uuid4()), file_path="/tmp/notes", source_url=SOURCE,
            )
    initiate.assert_not_called()


def test_start_refuses_a_missing_source_link_before_anything_exists(as_admin):
    with patch.object(mcp_router.upload_router, "initiate_upload") as initiate:
        with pytest.raises(ValueError, match="source_url"):
            mcp_router.start_file_upload(
                project_id=str(uuid.uuid4()), file_path="/tmp/a.png", source_url="  ",
            )
    initiate.assert_not_called()


def test_start_refuses_more_than_one_part_can_carry(as_admin):
    """One presigned part tops out at 5 GB; past that the PUT would fail at
    storage after a long upload, so say so up front."""
    with patch.object(mcp_router.upload_router, "initiate_upload") as initiate:
        with pytest.raises(ValueError, match="5 GB"):
            mcp_router.start_file_upload(
                project_id=str(uuid.uuid4()), file_path="/tmp/a.mp4", source_url=SOURCE,
                size_bytes=6 * 1024**3,
            )
    initiate.assert_not_called()


# ── Finishing ─────────────────────────────────────────────────────────────────

def _version_and_media(mock_db, owner_id, *, s3_key="raw/p/a/v/original.png"):
    version = MagicMock()
    version.asset_id = uuid.uuid4()
    version.created_by = owner_id
    media = MagicMock()
    media.s3_key_raw = s3_key
    mock_db.query.return_value.filter.return_value.first.side_effect = [version, media]
    return version, media


def test_finish_completes_with_the_part_storage_holds_and_starts_processing(as_admin, mock_db):
    version, media = _version_and_media(mock_db, as_admin.id)
    version_id = uuid.uuid4()
    processed = []

    def complete(**kwargs):
        # Stand in for the route queueing _trigger_processing on BackgroundTasks.
        kwargs["background_tasks"].add_task(processed.append, "dispatched")
        return MagicMock(status="ready")

    with patch.object(mcp_router.s3_service, "list_uploaded_parts",
                      return_value=[{"PartNumber": 1, "ETag": '"e1"', "Size": 2048}]), \
         patch.object(mcp_router.upload_router, "complete_upload", side_effect=complete) as done:
        out = mcp_router.finish_file_upload(version_id=str(version_id), upload_id="up-1")

    body = done.call_args.kwargs["body"]
    assert body.s3_key == "raw/p/a/v/original.png"
    assert [p.model_dump() for p in body.parts] == [{"PartNumber": 1, "ETag": '"e1"'}]
    # Without running the queued task the file is stored but never processed:
    # no thumbnail for an image, no HLS for a video.
    assert processed == ["dispatched"]
    # The size given at start was a claim, or absent; storage knows the truth.
    assert media.file_size_bytes == 2048
    assert out["status"] == "ready"


def test_finish_before_the_file_was_sent_says_what_to_do(as_admin, mock_db):
    _version_and_media(mock_db, as_admin.id)
    with patch.object(mcp_router.s3_service, "list_uploaded_parts", return_value=[]), \
         patch.object(mcp_router.upload_router, "complete_upload") as done:
        with pytest.raises(ValueError, match="curl"):
            mcp_router.finish_file_upload(version_id=str(uuid.uuid4()), upload_id="up-1")
    done.assert_not_called()


def test_finish_refuses_someone_elses_upload_without_touching_storage(as_admin, mock_db):
    _version_and_media(mock_db, uuid.uuid4())  # created by another user
    with patch.object(mcp_router.s3_service, "list_uploaded_parts") as listed:
        with pytest.raises(ValueError):
            mcp_router.finish_file_upload(version_id=str(uuid.uuid4()), upload_id="up-1")
    listed.assert_not_called()


# ── Local file into a brief ───────────────────────────────────────────────────

def _link(brief_json=None):
    link = MagicMock()
    link.id = uuid.uuid4()
    link.brief_json = brief_json
    link.deleted_at = None
    link.is_enabled = True
    link.expires_at = None
    return link


def test_submitting_a_file_to_a_brief_uploads_into_the_callers_own_slot(as_admin, mock_db):
    link = _link({"output_languages": ["German", "Swedish"]})
    slot = uuid.uuid4()
    mock_db.query.return_value.filter.return_value.first.side_effect = [link, None]
    with patch.object(mcp_router.submissions_router, "_provision_submission_project", return_value=slot), \
         patch.object(mcp_router.upload_router, "initiate_upload", return_value=_init()) as initiate, \
         patch.object(mcp_router.s3_service, "presign_upload_part", return_value="u"):
        mcp_router.start_file_submission(
            link_id=str(link.id), file_path="/tmp/hook.mp4", source_url=SOURCE, language="German",
        )

    body = initiate.call_args.kwargs["body"]
    assert body.project_id == slot
    assert body.language == "German"
    assert body.asset_id is None


def test_resubmitting_a_deliverable_adds_a_version_not_a_second_asset(as_admin, mock_db):
    """Same rule as submit_work: a revised cut threads under the original."""
    name = "Battery dies by 3pm"
    link = _link({"final_deliverable": {"hook_variations": [{"variation": name}]}})
    existing = MagicMock()
    existing.id = uuid.uuid4()
    mock_db.query.return_value.filter.return_value.first.side_effect = [link, existing]
    with patch.object(mcp_router.submissions_router, "_provision_submission_project", return_value=uuid.uuid4()), \
         patch.object(mcp_router.upload_router, "initiate_upload", return_value=_init()) as initiate, \
         patch.object(mcp_router.s3_service, "presign_upload_part", return_value="u"):
        mcp_router.start_file_submission(
            link_id=str(link.id), file_path="/tmp/v2.png", source_url=SOURCE, asset_name=name,
        )

    assert initiate.call_args.kwargs["body"].asset_id == existing.id


def test_submitting_to_a_disabled_brief_creates_nothing(as_admin, mock_db):
    link = _link()
    link.is_enabled = False
    mock_db.query.return_value.filter.return_value.first.side_effect = [link]
    with patch.object(mcp_router.submissions_router, "_provision_submission_project") as provision, \
         patch.object(mcp_router.upload_router, "initiate_upload") as initiate:
        with pytest.raises(ValueError, match="no longer accepting"):
            mcp_router.start_file_submission(
                link_id=str(link.id), file_path="/tmp/a.png", source_url=SOURCE,
            )
    provision.assert_not_called()
    initiate.assert_not_called()


# ── From a URL ────────────────────────────────────────────────────────────────

def test_upload_from_url_fetches_stores_and_finishes(as_admin):
    init = _init()
    with patch.object(mcp_router, "fetch_remote_file", return_value=(b"PNGDATA", "image/png")) as fetched, \
         patch.object(mcp_router.upload_router, "initiate_upload", return_value=init) as initiate, \
         patch.object(mcp_router.s3_service, "upload_part", return_value='"e1"') as stored, \
         patch.object(mcp_router, "_finish", return_value={"status": "ready"}) as finished:
        out = mcp_router.upload_from_url(
            project_id=str(uuid.uuid4()),
            url="https://cdn.example.com/ads/hook%201.png?w=1080",
            source_url=SOURCE,
        )

    # Images and video only, through the SSRF-guarded fetcher, with a size cap.
    kwargs = fetched.call_args.kwargs
    assert kwargs["allowed_content_types"] == ("image/", "video/")
    assert kwargs["max_bytes"] > 0
    body = initiate.call_args.kwargs["body"]
    assert body.original_filename == "hook 1.png"  # decoded, query string dropped
    assert body.file_size_bytes == len(b"PNGDATA")
    stored.assert_called_once_with(init.s3_key, init.upload_id, 1, b"PNGDATA")
    finished.assert_called_once_with(init.version_id, init.upload_id)
    assert out == {"status": "ready"}


def test_a_failed_fetch_creates_nothing(as_admin):
    with patch.object(mcp_router, "fetch_remote_file", side_effect=RemoteFetchError("blocked address")), \
         patch.object(mcp_router.upload_router, "initiate_upload") as initiate:
        with pytest.raises(ValueError, match="blocked address"):
            mcp_router.upload_from_url(
                project_id=str(uuid.uuid4()), url="http://169.254.169.254/x.png", source_url=SOURCE,
            )
    initiate.assert_not_called()


def test_a_failed_storage_write_aborts_rather_than_strand_an_uploading_version(as_admin):
    init = _init()
    with patch.object(mcp_router, "fetch_remote_file", return_value=(b"x", "image/png")), \
         patch.object(mcp_router.upload_router, "initiate_upload", return_value=init), \
         patch.object(mcp_router.s3_service, "upload_part", side_effect=RuntimeError("storage down")), \
         patch.object(mcp_router.upload_router, "abort_upload") as aborted:
        with pytest.raises(RuntimeError):
            mcp_router.upload_from_url(
                project_id=str(uuid.uuid4()), url="https://cdn.example.com/a.png", source_url=SOURCE,
            )
    body = aborted.call_args.kwargs["body"]
    assert (body.upload_id, body.version_id) == (init.upload_id, init.version_id)


def test_upload_from_url_names_a_bare_url_by_its_type(as_admin):
    """A URL with no filename (an image CDN endpoint) still needs an extension,
    or the stored key and download name come out typeless."""
    with patch.object(mcp_router, "fetch_remote_file", return_value=(b"x", "image/jpeg")), \
         patch.object(mcp_router.upload_router, "initiate_upload", return_value=_init()) as initiate, \
         patch.object(mcp_router.s3_service, "upload_part", return_value='"e"'), \
         patch.object(mcp_router, "_finish", return_value={}):
        mcp_router.upload_from_url(
            project_id=str(uuid.uuid4()), url="https://images.example.com/render/", source_url=SOURCE,
        )
    name = initiate.call_args.kwargs["body"].original_filename
    assert name.endswith((".jpg", ".jpeg"))
