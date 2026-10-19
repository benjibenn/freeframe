"""Downloads from a brief must be named after the brief, so a folder of files
saved from many briefs still says which brief and language each file is.
"<brief title> - <language>.<ext>", the language read off "French — French · EUR"."""
import io
import uuid
import zipfile
from unittest.mock import MagicMock, patch

from apps.api.routers.brief_files import _download_name

TITLE = "20261016 - p16 - Nervous First-Time Buyer - Fear - Tabloid headline static"


def _asset(name):
    a = MagicMock()
    a.id = uuid.uuid4()
    a.name = name
    return a


def _link():
    link = MagicMock()
    link.id = uuid.uuid4()
    link.title = TITLE
    return link


def test_name_is_brief_title_plus_language_with_real_extension():
    assert _download_name(TITLE, "French — French · EUR", "upload/abc.png") == f"{TITLE} - French.png"


def test_name_without_language_marker_keeps_the_whole_file_name():
    assert _download_name("Brief", "hero shot", "x.mp4") == "Brief - hero shot.mp4"


def test_name_drops_characters_a_file_system_rejects():
    assert _download_name('A/B: "C"', "French — x", "k.jpg") == "AB C - French.jpg"


@patch("apps.api.routers.brief_files.s3_service.generate_presigned_get_url", return_value="https://s3/signed")
@patch("apps.api.routers.brief_files._media", return_value=("key/f.png", "f.png"))
@patch("apps.api.routers.brief_files._brief_assets")
@patch("apps.api.routers.brief_files._get_owned_link")
def test_single_download_signs_url_with_brief_name(owned, assets, _media, signed, client, auth_headers):
    link, fr = _link(), _asset("French — French · EUR")
    owned.return_value, assets.return_value = link, [fr]
    resp = client.get(f"/submission-links/{link.id}/files/{fr.id}/download", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["filename"] == f"{TITLE} - French.png"
    signed.assert_called_once_with("key/f.png", download_filename=f"{TITLE} - French.png")


@patch("apps.api.routers.brief_files._brief_assets")
@patch("apps.api.routers.brief_files._get_owned_link")
def test_single_download_refuses_a_file_from_another_brief(owned, assets, client, auth_headers):
    link = _link()
    owned.return_value, assets.return_value = link, [_asset("French — x")]
    resp = client.get(f"/submission-links/{link.id}/files/{uuid.uuid4()}/download", headers=auth_headers)
    assert resp.status_code == 404


@patch("apps.api.routers.brief_files.s3_service.get_s3_client")
@patch("apps.api.routers.brief_files._media", return_value=("key/f.png", "f.png"))
@patch("apps.api.routers.brief_files._brief_assets")
@patch("apps.api.routers.brief_files._get_owned_link")
def test_zip_holds_every_file_named_after_the_brief(owned, assets, _media, s3, client, auth_headers):
    link = _link()
    owned.return_value = link
    # Two editors both submitted French: the second must not overwrite the first.
    assets.return_value = [_asset("French — a"), _asset("Swedish — b"), _asset("French — c")]
    s3.return_value.get_object.side_effect = lambda **_: {"Body": io.BytesIO(b"img")}
    resp = client.get(f"/submission-links/{link.id}/download-all", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    names = zipfile.ZipFile(io.BytesIO(resp.content)).namelist()
    assert names == [f"{TITLE} - French.png", f"{TITLE} - Swedish.png", f"{TITLE} - French (2).png"]
