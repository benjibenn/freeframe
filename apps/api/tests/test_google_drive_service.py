"""Tests for google_drive_service — pure-logic and mocked-client, no real Google calls."""
import json
import os
import sys
import pytest
from unittest.mock import MagicMock, patch, call

# Env vars required before any app import
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-secret")

from apps.api.services.google_drive_service import (
    extract_folder_id,
    list_video_files,
    service_account_email,
)

# ---------------------------------------------------------------------------
# extract_folder_id
# ---------------------------------------------------------------------------

class TestExtractFolderId:
    def test_folders_url(self):
        url = "https://drive.google.com/drive/folders/ABC123?usp=sharing"
        assert extract_folder_id(url) == "ABC123"

    def test_folders_url_no_query(self):
        url = "https://drive.google.com/drive/folders/XYZ_789-abc"
        assert extract_folder_id(url) == "XYZ_789-abc"

    def test_open_id_url(self):
        url = "https://drive.google.com/open?id=ABC123"
        assert extract_folder_id(url) == "ABC123"

    def test_raw_id(self):
        assert extract_folder_id("ABC123") == "ABC123"

    def test_raw_id_with_dashes_and_underscores(self):
        assert extract_folder_id("abc-123_XYZ") == "abc-123_XYZ"

    def test_garbage_raises(self):
        with pytest.raises(ValueError, match="Cannot extract"):
            extract_folder_id("not a url or id!!!")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            extract_folder_id("")

    def test_strips_whitespace(self):
        assert extract_folder_id("  ABC123  ") == "ABC123"


# ---------------------------------------------------------------------------
# service_account_email
# ---------------------------------------------------------------------------

_FAKE_SA_JSON = json.dumps({
    "type": "service_account",
    "client_email": "test-sa@my-project.iam.gserviceaccount.com",
    "private_key": "fake-key",
    "project_id": "my-project",
})


class TestServiceAccountEmail:
    def test_returns_email_when_set(self, monkeypatch):
        from apps.api import config
        monkeypatch.setattr(config.settings, "google_service_account_json", _FAKE_SA_JSON)
        assert service_account_email() == "test-sa@my-project.iam.gserviceaccount.com"

    def test_returns_none_when_unset(self, monkeypatch):
        from apps.api import config
        monkeypatch.setattr(config.settings, "google_service_account_json", None)
        assert service_account_email() is None


# ---------------------------------------------------------------------------
# list_video_files
# ---------------------------------------------------------------------------

def _make_drive_mock(pages_by_folder: dict):
    """Build a mock drive client where files().list().execute() returns pages_by_folder[folder_id].

    pages_by_folder: { folder_id: {"files": [...], "nextPageToken": ...} }
    """
    drive_mock = MagicMock()

    def list_side_effect(**kwargs):
        # Extract folder_id from the q string: "'<id>' in parents ..."
        import re
        q = kwargs.get("q", "")
        m = re.search(r"'([^']+)' in parents", q)
        folder_id = m.group(1) if m else "__unknown__"
        page_data = pages_by_folder.get(folder_id, {"files": []})
        list_call = MagicMock()
        list_call.execute.return_value = page_data
        return list_call

    drive_mock.files.return_value.list.side_effect = list_side_effect
    return drive_mock


class TestListVideoFiles:
    def test_returns_video_files_from_single_page(self, monkeypatch):
        video = {"id": "vid1", "name": "clip.mp4", "mimeType": "video/mp4", "size": "1024"}
        drive_mock = _make_drive_mock({
            "folder-root": {"files": [video]},
        })

        with patch("apps.api.services.google_drive_service._drive", return_value=drive_mock):
            result = list_video_files("folder-root", recurse=False)

        assert result == [{"id": "vid1", "name": "clip.mp4", "mimeType": "video/mp4", "size": 1024}]

    def test_recurses_into_subfolders(self, monkeypatch):
        subfolder = {
            "id": "sub1",
            "name": "Subfolder",
            "mimeType": "application/vnd.google-apps.folder",
        }
        video_in_sub = {
            "id": "vid2", "name": "deep.mp4", "mimeType": "video/mp4", "size": "2048",
        }
        drive_mock = _make_drive_mock({
            "folder-root": {"files": [subfolder]},
            "sub1": {"files": [video_in_sub]},
        })

        with patch("apps.api.services.google_drive_service._drive", return_value=drive_mock):
            result = list_video_files("folder-root", recurse=True)

        assert result == [{"id": "vid2", "name": "deep.mp4", "mimeType": "video/mp4", "size": 2048}]

    def test_skips_subfolders_when_recurse_false(self, monkeypatch):
        subfolder = {
            "id": "sub1",
            "name": "Subfolder",
            "mimeType": "application/vnd.google-apps.folder",
        }
        drive_mock = _make_drive_mock({
            "folder-root": {"files": [subfolder]},
        })

        with patch("apps.api.services.google_drive_service._drive", return_value=drive_mock):
            result = list_video_files("folder-root", recurse=False)

        assert result == []

    def test_mixed_folder_and_video(self, monkeypatch):
        video = {"id": "vid1", "name": "top.mp4", "mimeType": "video/mp4", "size": "512"}
        subfolder = {
            "id": "sub1",
            "name": "Sub",
            "mimeType": "application/vnd.google-apps.folder",
        }
        video_in_sub = {
            "id": "vid2", "name": "nested.mov", "mimeType": "video/quicktime", "size": "999",
        }
        drive_mock = _make_drive_mock({
            "root": {"files": [video, subfolder]},
            "sub1": {"files": [video_in_sub]},
        })

        with patch("apps.api.services.google_drive_service._drive", return_value=drive_mock):
            result = list_video_files("root", recurse=True)

        ids = {r["id"] for r in result}
        assert ids == {"vid1", "vid2"}

    def test_uses_correct_query(self, monkeypatch):
        """list() must be called with the right q, supportsAllDrives, includeItemsFromAllDrives."""
        drive_mock = _make_drive_mock({"folder-x": {"files": []}})

        with patch("apps.api.services.google_drive_service._drive", return_value=drive_mock):
            list_video_files("folder-x", recurse=False)

        call_kwargs = drive_mock.files.return_value.list.call_args_list[0][1]
        assert "'folder-x' in parents" in call_kwargs["q"]
        assert "trashed=false" in call_kwargs["q"]
        assert call_kwargs["supportsAllDrives"] is True
        assert call_kwargs["includeItemsFromAllDrives"] is True

    def test_size_defaults_to_zero_when_missing(self, monkeypatch):
        video = {"id": "vid1", "name": "clip.mp4", "mimeType": "video/mp4"}  # no size key
        drive_mock = _make_drive_mock({"f": {"files": [video]}})

        with patch("apps.api.services.google_drive_service._drive", return_value=drive_mock):
            result = list_video_files("f", recurse=False)

        assert result[0]["size"] == 0
