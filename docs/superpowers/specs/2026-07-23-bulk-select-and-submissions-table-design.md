# Bulk shift-select, bulk run-as-ad, submissions file table

Date: 2026-07-23

Three independent UI features, each extending an existing pattern from commit
`1c754f5` (bulk status/stage + run-as-ad toggle).

## 1. Shift-click range selection

**Where:** `apps/web/components/projects/asset-grid.tsx` — the component owns
`selectedAssetIds` and `selectedFolderIds` for both grid and list views.

**Visible order:** The render sequence is folders first (in `folders` array
order), then assets (in `filtered` order), identical in grid and list. Range
selection walks a single combined list:
`[...folders.map(f => ({kind:'folder', id})), ...filtered.map(a => ({kind:'asset', id}))]`.

**Behavior:**
- Add `lastClickedRef = React.useRef<{ kind: 'asset' | 'folder'; id: string } | null>(null)`.
- Both `toggleAssetSelect` and `toggleFolderSelect` gain an optional
  `MouseEvent`. Signatures become
  `toggleAssetSelect(assetId, e?)` / `toggleFolderSelect(folderId, e?)`.
- Plain click (no shift): current toggle behavior, then set the anchor to this
  item.
- Shift-click: compute the index of the anchor and the clicked item in the
  combined visible list; select every item between them (inclusive), additively
  (union with the current selection — does not clear). Anchor is left unchanged
  so a subsequent shift-click re-ranges from the same origin (standard
  file-manager behavior). If there is no anchor yet, treat as a plain click.
- Suppress native text selection: on the click handlers, when `e.shiftKey`, call
  `e.preventDefault()`. Also apply `select-none` to the grid/list containers so
  drag-with-shift doesn't highlight text.

**Call sites to thread the event through:** `asset-card.tsx` already types
`onSelect?: (e: React.MouseEvent) => void` and forwards the event — only the
grid wiring drops it. Change `onSelect={() => toggleAssetSelect(asset.id)}` to
`onSelect={(e) => toggleAssetSelect(asset.id, e)}` (grid ~357, list ~538) and
the folder `onClick` handlers (~291, ~300, ~419) to pass `e`. No card change.

**No backend change.**

## 2. Bulk run-as-ad

**Backend:** new `PATCH /assets/bulk/run-as-ad` in `apps/api/routers/assets.py`,
mirroring `bulk_update_asset_status` exactly:
- `BulkRunAsAdRequest { asset_ids: list[UUID]; run_as_ad: bool }`.
- Same guards: empty → 422, >200 → 413, missing ids → 404, per-project editor
  role enforced before any mutation (`run_as_ad` is not admin-gated on the
  single-asset path, so bulk matches — editor role suffices).
- Sets `asset.run_as_ad = body.run_as_ad` for each; returns `{"updated": n}`.

**Frontend:**
- `asset-grid.tsx` gains an optional prop
  `onBulkRunAsAd?: (assetIds: string[], runAsAd: boolean) => void`.
- Extend `BulkStatusMenu` (rename intent stays "Set status") with a new section,
  OR add two small buttons to the action bar. Decision: add a **new menu
  section** "Ad" inside `BulkStatusMenu` with "Mark as ad" / "Unmark as ad"
  entries, shown only when `onBulkRunAsAd` is provided. Keeps the action bar
  uncluttered and matches the existing "Review status / Pipeline stage"
  sectioned pattern. Pass a third callback `onSetRunAsAd(runAsAd: boolean)`.
- Wire in `apps/web/app/(dashboard)/assets/page.tsx` and
  `apps/web/app/(dashboard)/projects/[id]/page.tsx`:
  `onBulkRunAsAd={async (ids, runAsAd) => { await api.patch('/assets/bulk/run-as-ad', { asset_ids: ids, run_as_ad: runAsAd }); <refetch> }}`.

## 3. Submissions: file table inside the card

**Backend:** `SubmissionItem` (`apps/api/schemas/submission.py`) gains
`files: list[SubmissionFile]` where
`SubmissionFile { asset_id: UUID; name: str }`.
In `list_submissions` (`apps/api/routers/submissions.py`), replace the
count-only query with one grouped query fetching `(project_id, id, name)` for
all non-deleted assets across the submissions' `project_ids`, bucketed per
project in Python. `asset_count` stays (derive from `len(files)`). No N+1 —
submissions per link are small and this is one query.

**Frontend** (`submissions/page.tsx`, `LinkCard` expanded section): replace the
`<ul>` of submitter rows with a compact table:

| Submitter | Files | Date |
|-----------|-------|------|

- Submitter column: name over email (as today), links to the submitter's
  project.
- Files column: each file name as a chip/link to the dedicated per-asset route
  `/projects/{project_id}/assets/{asset_id}` (confirmed to exist). Show
  "No files yet" when empty. Cap visible chips (first 6) with a "+N more"
  affordance to avoid unbounded rows.
- Date column: `created_at`, short format.
- Keep the "Pre-assign folder to email…" button below the table.
- `SubmissionItem` TS interface gains `files: { asset_id: string; name: string }[]`.

## Testing

- **pytest:** new `bulk_run_as_ad` endpoint (happy path, empty→422, missing→404,
  permission enforcement); `list_submissions` returns `files` correctly grouped
  per submission and excludes deleted assets.
- **tsc:** `npm run build` / typecheck for web.
- **Browser (per UX-fidelity rule):** shift-select a range in both grid and list;
  bulk mark/unmark as ad and confirm the review header reflects it; expand a
  submission card and click through a file to its asset.

## Out of scope

- Page-level table/card toggle on submissions (chose table-inside-cards only).
- Keyboard-only range selection (shift+arrow); shift-click only.
