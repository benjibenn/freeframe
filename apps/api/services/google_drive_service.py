"""Google Drive service — read-only access via a service account."""
import json
import re
from typing import Optional
from urllib.parse import urlparse, parse_qs

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.service_account import Credentials

from ..config import settings

_DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
_FOLDER_MIME = "application/vnd.google-apps.folder"


def _creds() -> Credentials:
    raw = settings.google_service_account_json
    if not raw:
        raise ValueError(
            "google_service_account_json is not set. "
            "Add the service account key JSON contents to GOOGLE_SERVICE_ACCOUNT_JSON."
        )
    info = json.loads(raw)
    return Credentials.from_service_account_info(info, scopes=[_DRIVE_SCOPE])


def _drive():
    return build("drive", "v3", credentials=_creds(), cache_discovery=False)


def service_account_email() -> Optional[str]:
    """Return the client_email from the SA JSON, or None if the setting is unset."""
    raw = settings.google_service_account_json
    if not raw:
        return None
    info = json.loads(raw)
    return info.get("client_email")


def extract_folder_id(link_or_id: str) -> str:
    """Parse a Drive folder URL or accept a raw folder id.

    Supported forms:
      - https://drive.google.com/drive/folders/ABC123
      - https://drive.google.com/drive/folders/ABC123?usp=sharing
      - https://drive.google.com/open?id=ABC123
      - ABC123  (raw id, alphanumeric + hyphens + underscores)
    """
    link_or_id = link_or_id.strip()

    # /folders/<id> pattern
    m = re.search(r"/folders/([A-Za-z0-9_-]+)", link_or_id)
    if m:
        return m.group(1)

    # ?id=<id> query param
    parsed = urlparse(link_or_id)
    qs = parse_qs(parsed.query)
    if "id" in qs:
        return qs["id"][0]

    # raw id — must look like a Drive id (only alphanumeric, dash, underscore)
    if re.fullmatch(r"[A-Za-z0-9_-]+", link_or_id):
        return link_or_id

    raise ValueError(f"Cannot extract a Drive folder id from: {link_or_id!r}")


def list_video_files(folder_id: str, recurse: bool = True) -> list[dict]:
    """Return all video files in *folder_id* (and optionally its subfolders).

    Each item is: {id: str, name: str, mimeType: str, size: int}
    """
    drive = _drive()
    return _list_video_files_inner(drive, folder_id, recurse)


def _list_video_files_inner(drive, folder_id: str, recurse: bool) -> list[dict]:
    q = (
        f"'{folder_id}' in parents and trashed=false "
        f"and (mimeType contains 'video/' or mimeType = '{_FOLDER_MIME}')"
    )
    fields = "files(id,name,mimeType,size),nextPageToken"
    results: list[dict] = []
    page_token = None

    while True:
        kwargs = dict(
            q=q,
            fields=fields,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        if page_token:
            kwargs["pageToken"] = page_token
        resp = drive.files().list(**kwargs).execute()
        for f in resp.get("files", []):
            if f["mimeType"] == _FOLDER_MIME:
                if recurse:
                    results.extend(_list_video_files_inner(drive, f["id"], recurse))
            else:
                results.append({
                    "id": f["id"],
                    "name": f["name"],
                    "mimeType": f["mimeType"],
                    "size": int(f.get("size", 0) or 0),
                })
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return results


def download_stream(file_id: str, dest_fileobj) -> None:
    """Download a Drive file into *dest_fileobj* using MediaIoBaseDownload."""
    drive = _drive()
    request = drive.files().get_media(fileId=file_id, supportsAllDrives=True)
    downloader = MediaIoBaseDownload(dest_fileobj, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
