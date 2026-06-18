# Google Drive → Backblaze auto-sync

A platform admin connects Google Drive folder links; an hourly job syncs **new videos**
from those folders into Backblaze and registers them as freeframe assets (transcoded,
ready to review/sort/tag). One-way and additive — removing a file from Drive never
deletes it in freeframe.

## One-time setup (operator)

1. **Create a Google service account**
   - In Google Cloud Console, create (or pick) a project.
   - Enable the **Google Drive API** for that project.
   - Create a **Service Account**, then create a **JSON key** for it and download it.

2. **Give freeframe the credentials**
   - Put the JSON key's *contents* in `.env.prod` as a single value:
     ```
     GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account", ... }'
     ```
   - Redeploy (push to `main`, or restart the stack) so the api/worker/beat containers pick it up.

3. **Share your Drive folders with the service account**
   - In freeframe: **Settings → Admin → Google Drive Sync** shows the service-account email.
   - In Google Drive, share each folder you want synced with that email (**Viewer** is enough).
     Sharing a parent folder covers its subfolders (sync recurses).

## Using it

- **Settings → Admin → Google Drive Sync**:
  - **Add connection** — paste a Drive folder link and pick the target freeframe **project**.
  - Each connection shows: enabled toggle, last sync time, last error (if any), and how many
    files have synced.
  - **Sync now** triggers an immediate sync for that connection; otherwise it runs hourly.

## Behavior

- **New only**: each file is tracked by its Drive file id per connection, so nothing imports twice.
- **First sync** imports everything currently in the folder; later syncs import only new files.
- **Videos only** (by MIME type); subfolders are included.
- **Large files** stream Drive → Backblaze (spooled to disk, not buffered in memory).
- A file that fails to import is recorded in the connection's `last error` and does not stop the rest.

## How it fits the codebase

- Auth/Drive client: `apps/api/services/google_drive_service.py` (service-account, read-only scope).
- Sync job: `apps/api/tasks/drive_sync_tasks.py` (`sync_drive_connections` on Celery Beat hourly →
  `sync_one_connection` per folder). Reuses `s3_service.upload_fileobj`,
  `import_service.register_s3_object_as_asset`, and the existing `process_asset` transcode.
- Admin API: `apps/api/routers/drive_sync.py` (`/admin/drive-sync*`, platform-admin only).
- Data: `drive_sync_connections` + `drive_synced_files` (migration `e1f2a3b4c5d6`).
