# Bulk shift-select, bulk run-as-ad, submissions file table — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add shift-click range selection and a bulk "run as ad" action to the asset grid, and give the submissions page a per-submitter file table inside each link card.

**Architecture:** Three independent slices. Backend adds one bulk endpoint (mirrors the existing `PATCH /assets/bulk/status`) and one extra field on the submissions list response. Frontend adds pure range-selection logic (unit-tested) wired into `asset-grid.tsx`, a new menu section in `BulkStatusMenu`, and a table in the submissions `LinkCard`.

**Tech Stack:** FastAPI + SQLAlchemy (Python, `uv`/pytest), Next.js + React + TypeScript (vitest, Radix dropdown, Tailwind design tokens).

## Global Constraints

- Backend tests use the `client`, `mock_db`, `auth_headers`, `test_user` fixtures from `apps/api/tests/conftest.py`. `mock_db.query()/.filter()` return the db itself; set `mock_db.all.return_value` / `mock_db.first.return_value` to control query results.
- `test_user` has `is_superadmin = False` but is a `MagicMock`, so `is_subadmin` is truthy unless explicitly set. In any test that must exercise the non-admin permission branch, set `test_user.is_subadmin = False`.
- Run backend tests from repo root: `uv run pytest <path> -v`.
- Run web unit tests from `apps/web`: `npx vitest run <path>`.
- Follow existing Tailwind design tokens (`text-text-secondary`, `bg-bg-hover`, `border-border`, etc.) — no raw colors.
- Bulk endpoints cap at 200 ids (422 on empty, 413 on over-cap, 404 on missing), matching `bulk_update_asset_status`.
- `run_as_ad` is editor-gated, not admin-gated (matches the single-asset path).
- Commit after each task. No commit attribution lines.

---

### Task 1: Backend — `PATCH /assets/bulk/run-as-ad`

**Files:**
- Modify: `apps/api/routers/assets.py` (add after `bulk_update_asset_status`, ~line 269)
- Test: `apps/api/tests/test_bulk_run_as_ad.py` (create)

**Interfaces:**
- Produces: `PATCH /assets/bulk/run-as-ad` accepting `{ "asset_ids": [uuid...], "run_as_ad": bool }`, returning `{"updated": int}`.

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/test_bulk_run_as_ad.py`:

```python
"""Bulk run-as-ad flag toggle across many assets (multi-select). Mirrors the
bulk status endpoint: editor role enforced per project before any mutation."""
import uuid
from unittest.mock import MagicMock, patch


def _fake_asset():
    a = MagicMock()
    a.id = uuid.uuid4()
    a.project_id = uuid.uuid4()
    a.run_as_ad = False
    a.deleted_at = None
    return a


@patch("apps.api.routers.assets.require_project_role")
def test_bulk_run_as_ad_sets_flag(_role, client, mock_db, auth_headers, test_user):
    test_user.is_subadmin = False  # force the editor-permission branch
    a1, a2 = _fake_asset(), _fake_asset()
    mock_db.all.return_value = [a1, a2]
    resp = client.patch(
        "/assets/bulk/run-as-ad",
        json={"asset_ids": [str(a1.id), str(a2.id)], "run_as_ad": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"updated": 2}
    assert a1.run_as_ad is True and a2.run_as_ad is True
    # Editor role checked on each asset's project before mutating.
    assert _role.call_count == 2


@patch("apps.api.routers.assets.require_project_role")
def test_bulk_run_as_ad_can_unset(_role, client, mock_db, auth_headers, test_user):
    test_user.is_subadmin = False
    a1 = _fake_asset()
    a1.run_as_ad = True
    mock_db.all.return_value = [a1]
    resp = client.patch(
        "/assets/bulk/run-as-ad",
        json={"asset_ids": [str(a1.id)], "run_as_ad": False},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert a1.run_as_ad is False


def test_bulk_run_as_ad_rejects_empty(client, mock_db, auth_headers):
    resp = client.patch(
        "/assets/bulk/run-as-ad",
        json={"asset_ids": [], "run_as_ad": True},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_bulk_run_as_ad_404_on_missing(client, mock_db, auth_headers, test_user):
    test_user.is_subadmin = False
    missing = uuid.uuid4()
    mock_db.all.return_value = []  # nothing found
    resp = client.patch(
        "/assets/bulk/run-as-ad",
        json={"asset_ids": [str(missing)], "run_as_ad": True},
        headers=auth_headers,
    )
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest apps/api/tests/test_bulk_run_as_ad.py -v`
Expected: FAIL (404 route not found → tests error/assert-fail).

- [ ] **Step 3: Implement the endpoint**

In `apps/api/routers/assets.py`, immediately after the `bulk_update_asset_status` function (before `@router.put("/assets/{asset_id}/tags"...)`), add:

```python
class BulkRunAsAdRequest(BaseModel):
    asset_ids: list[uuid.UUID]
    run_as_ad: bool


@router.patch("/assets/bulk/run-as-ad")
def bulk_update_run_as_ad(
    body: BulkRunAsAdRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Toggle the run-as-ad flag on many assets at once (multi-select bulk edit).

    Same permission rule as the single-asset PATCH: platform admins manage every
    project; everyone else needs editor role or higher on each asset's project."""
    if not body.asset_ids:
        raise HTTPException(status_code=422, detail="asset_ids is empty")
    if len(body.asset_ids) > 200:
        raise HTTPException(status_code=413, detail="Too many asset_ids (max 200)")
    assets = db.query(Asset).filter(
        Asset.id.in_(body.asset_ids), Asset.deleted_at.is_(None)
    ).all()
    found = {a.id for a in assets}
    missing = [str(a) for a in body.asset_ids if a not in found]
    if missing:
        raise HTTPException(status_code=404, detail=f"Assets not found: {', '.join(missing)}")
    if not is_platform_admin(current_user):
        for asset in assets:
            require_project_role(db, asset.project_id, current_user, ProjectRole.editor)
    for asset in assets:
        asset.run_as_ad = body.run_as_ad
    db.commit()
    return {"updated": len(assets)}
```

Confirm `BaseModel`, `uuid`, `ProjectRole`, `is_platform_admin`, `require_project_role`, `HTTPException`, `Depends`, `get_db`, `get_current_user`, `Asset`, `User`, `Session` are already imported in this file (they are — used by `bulk_update_asset_status`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest apps/api/tests/test_bulk_run_as_ad.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/api/routers/assets.py apps/api/tests/test_bulk_run_as_ad.py
git commit -m "feat(assets): bulk run-as-ad endpoint for multi-select"
```

---

### Task 2: Backend — submissions list returns each submitter's files

**Files:**
- Modify: `apps/api/schemas/submission.py` (add `SubmissionFile`, extend `SubmissionItem`)
- Modify: `apps/api/routers/submissions.py:414-452` (`list_submissions`)
- Test: `apps/api/tests/test_submission_files.py` (create)

**Interfaces:**
- Produces: `SubmissionItem.files: list[SubmissionFile]`, `SubmissionFile { asset_id: uuid, name: str }`. `GET /submission-links/{id}/submissions` now includes `files` per row.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_submission_files.py`:

```python
"""list_submissions must return each submitter's actual files (not just a count)
so the submissions page can render a per-submitter file table."""
import uuid
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone


def _sub(project_id, user_id):
    s = MagicMock()
    s.id = uuid.uuid4()
    s.submission_link_id = uuid.uuid4()
    s.user_id = user_id
    s.display_name = None
    s.project_id = project_id
    s.created_at = datetime.now(timezone.utc)
    return s


@patch("apps.api.routers.submissions._get_owned_link")
def test_list_submissions_includes_files(_owned, client, mock_db, auth_headers):
    pid = uuid.uuid4()
    uid = uuid.uuid4()
    link = MagicMock()
    link.id = uuid.uuid4()
    _owned.return_value = link
    sub = _sub(pid, uid)
    user = MagicMock(); user.id = uid; user.name = "Ada"; user.email = "ada@x.co"
    aid1, aid2 = uuid.uuid4(), uuid.uuid4()

    # list_submissions runs three queries in order: submissions, asset rows, users.
    # mock_db.query().filter()... returns mock_db; .all() is what varies per call.
    mock_db.all.side_effect = [
        [sub],                                   # submissions
        [(pid, aid1, "a.mp4"), (pid, aid2, "b.mp4")],  # (project_id, id, name) asset rows
        [user],                                  # users
    ]
    resp = client.get(f"/submission-links/{link.id}/submissions", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    row = resp.json()[0]
    assert row["asset_count"] == 2
    names = sorted(f["name"] for f in row["files"])
    assert names == ["a.mp4", "b.mp4"]
    assert {f["asset_id"] for f in row["files"]} == {str(aid1), str(aid2)}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest apps/api/tests/test_submission_files.py -v`
Expected: FAIL — response rows have no `files` key (KeyError) or validation drops it.

- [ ] **Step 3: Extend the schema**

In `apps/api/schemas/submission.py`, add before `class SubmissionItem`:

```python
class SubmissionFile(BaseModel):
    asset_id: uuid.UUID
    name: str
```

Then add to `SubmissionItem` (after `asset_count`):

```python
    files: list[SubmissionFile] = []
```

- [ ] **Step 4: Rewrite the query in `list_submissions`**

In `apps/api/routers/submissions.py`, replace the asset-count block (the `asset_counts = {}` / `if project_ids:` / grouped-count query) and the `out` loop with a per-project file grouping. The full function body from `subs = ...` becomes:

```python
    subs = db.query(Submission).filter(
        Submission.submission_link_id == link.id,
    ).order_by(Submission.created_at.desc()).all()

    project_ids = [s.project_id for s in subs]
    files_by_project: dict[uuid.UUID, list[SubmissionFile]] = {}
    if project_ids:
        rows = (
            db.query(Asset.project_id, Asset.id, Asset.name)
            .filter(Asset.project_id.in_(project_ids), Asset.deleted_at.is_(None))
            .order_by(Asset.created_at.asc())
            .all()
        )
        for pid, aid, name in rows:
            files_by_project.setdefault(pid, []).append(
                SubmissionFile(asset_id=aid, name=name or "")
            )

    user_ids = [s.user_id for s in subs]
    users = {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}

    out = []
    for s in subs:
        u = users.get(s.user_id)
        files = files_by_project.get(s.project_id, [])
        out.append(SubmissionItem(
            id=s.id,
            user_id=s.user_id,
            user_name=(u.name if u else "") or "",
            user_email=(u.email if u else "") or "",
            display_name=s.display_name,
            project_id=s.project_id,
            asset_count=len(files),
            files=files,
            created_at=s.created_at,
        ))
    return out
```

Add `SubmissionFile` to the existing `from ..schemas.submission import (...)` block at the top of the file (find the import that already pulls `SubmissionItem`).

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest apps/api/tests/test_submission_files.py -v`
Expected: 1 passed.

- [ ] **Step 6: Guard against regressions in the existing submissions test**

Run: `uv run pytest apps/api/tests/test_submission_brief_pdf.py -v`
Expected: still passing (no change to those paths).

- [ ] **Step 7: Commit**

```bash
git add apps/api/schemas/submission.py apps/api/routers/submissions.py apps/api/tests/test_submission_files.py
git commit -m "feat(submissions): return per-submitter files from list endpoint"
```

---

### Task 3: Frontend — pure range-selection helper (unit-tested)

**Files:**
- Create: `apps/web/lib/selection.ts`
- Test: `apps/web/lib/__tests__/selection.test.ts`

**Interfaces:**
- Produces: `type SelectableItem = { kind: 'asset' | 'folder'; id: string }` and `rangeBetween(items: SelectableItem[], anchor: SelectableItem, target: SelectableItem): SelectableItem[]` — returns the inclusive slice of `items` between the anchor and target (order-agnostic). Returns `[target]` if either is absent from `items`.

- [ ] **Step 1: Write the failing tests**

Create `apps/web/lib/__tests__/selection.test.ts`:

```typescript
import { describe, it, expect } from 'vitest'
import { rangeBetween, type SelectableItem } from '../selection'

const items: SelectableItem[] = [
  { kind: 'folder', id: 'f1' },
  { kind: 'folder', id: 'f2' },
  { kind: 'asset', id: 'a1' },
  { kind: 'asset', id: 'a2' },
  { kind: 'asset', id: 'a3' },
]

describe('rangeBetween', () => {
  it('returns inclusive slice when anchor precedes target', () => {
    const r = rangeBetween(items, { kind: 'folder', id: 'f2' }, { kind: 'asset', id: 'a2' })
    expect(r.map((i) => i.id)).toEqual(['f2', 'a1', 'a2'])
  })

  it('is order-agnostic (target before anchor)', () => {
    const r = rangeBetween(items, { kind: 'asset', id: 'a3' }, { kind: 'folder', id: 'f1' })
    expect(r.map((i) => i.id)).toEqual(['f1', 'f2', 'a1', 'a2', 'a3'])
  })

  it('spans folders into assets across the boundary', () => {
    const r = rangeBetween(items, { kind: 'folder', id: 'f1' }, { kind: 'asset', id: 'a1' })
    expect(r.map((i) => i.id)).toEqual(['f1', 'f2', 'a1'])
  })

  it('single item when anchor equals target', () => {
    const r = rangeBetween(items, { kind: 'asset', id: 'a2' }, { kind: 'asset', id: 'a2' })
    expect(r.map((i) => i.id)).toEqual(['a2'])
  })

  it('falls back to [target] when anchor is not present', () => {
    const r = rangeBetween(items, { kind: 'asset', id: 'gone' }, { kind: 'asset', id: 'a2' })
    expect(r.map((i) => i.id)).toEqual(['a2'])
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `apps/web`): `npx vitest run lib/__tests__/selection.test.ts`
Expected: FAIL — cannot resolve `../selection`.

- [ ] **Step 3: Implement the helper**

Create `apps/web/lib/selection.ts`:

```typescript
export type SelectableItem = { kind: 'asset' | 'folder'; id: string }

/**
 * Inclusive slice of `items` between `anchor` and `target`, order-agnostic.
 * Used for shift-click range selection over the combined folders+assets list.
 * If either endpoint is missing from `items`, selects just the target.
 */
export function rangeBetween(
  items: SelectableItem[],
  anchor: SelectableItem,
  target: SelectableItem,
): SelectableItem[] {
  const key = (i: SelectableItem) => `${i.kind}:${i.id}`
  const ai = items.findIndex((i) => key(i) === key(anchor))
  const ti = items.findIndex((i) => key(i) === key(target))
  if (ai === -1 || ti === -1) return [target]
  const [lo, hi] = ai <= ti ? [ai, ti] : [ti, ai]
  return items.slice(lo, hi + 1)
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `apps/web`): `npx vitest run lib/__tests__/selection.test.ts`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/web/lib/selection.ts apps/web/lib/__tests__/selection.test.ts
git commit -m "feat(web): pure range-selection helper for shift-click"
```

---

### Task 4: Frontend — wire shift-click into the asset grid

**Files:**
- Modify: `apps/web/components/projects/asset-grid.tsx`

**Interfaces:**
- Consumes: `rangeBetween`, `SelectableItem` from `@/lib/selection` (Task 3).
- Produces: shift-click range selection in both grid and list views, additive.

- [ ] **Step 1: Import the helper and add an anchor ref**

At the top of `asset-grid.tsx` with the other imports:

```typescript
import { rangeBetween, type SelectableItem } from '@/lib/selection'
```

Just after the `selectedFolderIds` state (line ~127), add:

```typescript
  const lastClickedRef = React.useRef<SelectableItem | null>(null)
```

- [ ] **Step 2: Build the combined visible-order list**

The render order is folders first (in `folders` order), then assets (in `filtered` order), identical in grid and list. After the `filtered` useMemo (line ~200), add:

```typescript
  const visibleOrder = React.useMemo<SelectableItem[]>(
    () => [
      ...(folders ?? []).map((f) => ({ kind: 'folder' as const, id: f.id })),
      ...filtered.map((a) => ({ kind: 'asset' as const, id: a.id })),
    ],
    [folders, filtered],
  )
```

- [ ] **Step 3: Add a shared range-apply helper and rewrite the toggles**

Replace `toggleAssetSelect` and `toggleFolderSelect` (lines ~154-170) with event-aware versions plus a shared applier:

```typescript
  const applyRange = (target: SelectableItem) => {
    const anchor = lastClickedRef.current
    const slice = anchor ? rangeBetween(visibleOrder, anchor, target) : [target]
    setSelectedAssetIds((prev) => {
      const next = new Set(prev)
      slice.forEach((i) => i.kind === 'asset' && next.add(i.id))
      return next
    })
    setSelectedFolderIds((prev) => {
      const next = new Set(prev)
      slice.forEach((i) => i.kind === 'folder' && next.add(i.id))
      return next
    })
    // Anchor stays put so a follow-up shift-click re-ranges from the same origin.
  }

  const toggleAssetSelect = (assetId: string, e?: React.MouseEvent) => {
    if (e?.shiftKey) {
      e.preventDefault()
      applyRange({ kind: 'asset', id: assetId })
      return
    }
    setSelectedAssetIds((prev) => {
      const next = new Set(prev)
      if (next.has(assetId)) next.delete(assetId)
      else next.add(assetId)
      return next
    })
    lastClickedRef.current = { kind: 'asset', id: assetId }
  }

  const toggleFolderSelect = (folderId: string, e?: React.MouseEvent) => {
    if (e?.shiftKey) {
      e.preventDefault()
      applyRange({ kind: 'folder', id: folderId })
      return
    }
    setSelectedFolderIds((prev) => {
      const next = new Set(prev)
      if (next.has(folderId)) next.delete(folderId)
      else next.add(folderId)
      return next
    })
    lastClickedRef.current = { kind: 'folder', id: folderId }
  }
```

- [ ] **Step 4: Thread the event through every call site**

Update these handlers to forward the event:
- Grid asset card (line ~357): `onSelect={(e) => toggleAssetSelect(asset.id, e)}`
- List asset row (line ~538): `onClick={(e) => { e.stopPropagation(); toggleAssetSelect(asset.id, e) }}`
- Folder handlers (lines ~291, ~300, ~419): `onClick={(e) => { e.stopPropagation(); toggleFolderSelect(folder.id, e) }}` (line ~291 is `shareMode ? (e) => {...} : undefined` — keep that shape, add `, e` to the call).

- [ ] **Step 5: Suppress text-selection highlight on shift-drag**

On the outermost container `div` (line ~219, `className="flex flex-col gap-3 relative"`), add `select-none`:

```typescript
    <div className="flex flex-col gap-3 relative select-none">
```

- [ ] **Step 6: Typecheck and build**

Run (from `apps/web`): `npx tsc --noEmit`
Expected: no new errors in `asset-grid.tsx`.

- [ ] **Step 7: Browser verification (per UX-fidelity rule)**

Start the app (or use the running dev stack), open a project with ≥3 assets and ≥2 folders. In grid view: click one item, then shift-click another 3 rows away → the whole span selects. Switch to list view, repeat. Confirm no blue text-highlight appears while shift-clicking.

- [ ] **Step 8: Commit**

```bash
git add apps/web/components/projects/asset-grid.tsx
git commit -m "feat(web): shift-click range selection in asset grid"
```

---

### Task 5: Frontend — bulk run-as-ad menu section + page wiring

**Files:**
- Modify: `apps/web/components/projects/bulk-status-menu.tsx`
- Modify: `apps/web/components/projects/asset-grid.tsx` (new prop + action bar wiring)
- Modify: `apps/web/app/(dashboard)/assets/page.tsx`
- Modify: `apps/web/app/(dashboard)/projects/[id]/page.tsx`

**Interfaces:**
- Consumes: `PATCH /assets/bulk/run-as-ad` (Task 1).
- Produces: `AssetGridProps.onBulkRunAsAd?: (assetIds: string[], runAsAd: boolean) => void`; `BulkStatusMenu` gains `onSetRunAsAd?: (runAsAd: boolean) => void`.

- [ ] **Step 1: Add the "Ad" section to `BulkStatusMenu`**

In `bulk-status-menu.tsx`, add `Megaphone` to the lucide import line:

```typescript
import { Tag, ChevronDown, Megaphone } from 'lucide-react'
```

Extend the props:

```typescript
export function BulkStatusMenu({
  onSetStatus,
  onSetStage,
  onSetRunAsAd,
}: {
  onSetStatus: (status: AssetStatus) => void
  onSetStage?: (stageId: string | null) => void
  onSetRunAsAd?: (runAsAd: boolean) => void
}) {
```

Inside `DropdownMenu.Content`, after the `showStages` block and before the closing `</DropdownMenu.Content>`, add:

```typescript
          {onSetRunAsAd && (
            <>
              <DropdownMenu.Separator className="my-1 h-px bg-border mx-1" />
              <div className="px-3 py-1 text-2xs font-medium uppercase tracking-wider text-text-tertiary">
                Ad
              </div>
              <DropdownMenu.Item onSelect={() => onSetRunAsAd(true)} className={itemClass}>
                <Megaphone className="h-3.5 w-3.5" />
                Mark as ad
              </DropdownMenu.Item>
              <DropdownMenu.Item onSelect={() => onSetRunAsAd(false)} className={itemClass}>
                <Megaphone className="h-3.5 w-3.5 opacity-40" />
                Unmark as ad
              </DropdownMenu.Item>
            </>
          )}
```

- [ ] **Step 2: Add the prop and wire the menu in `asset-grid.tsx`**

In the `AssetGridProps` interface (near the other `onBulk*` props, ~line 59), add:

```typescript
  onBulkRunAsAd?: (assetIds: string[], runAsAd: boolean) => void
```

Add `onBulkRunAsAd` to the destructured props of the component. Then in the action bar where `<BulkStatusMenu ...>` is rendered (line ~675), add the third callback:

```typescript
            <BulkStatusMenu
              onSetStatus={(status) => {
                onBulkStatus(Array.from(selectedAssetIds), status)
                clearSelection()
              }}
              onSetStage={
                onBulkStage
                  ? (stageId) => {
                      onBulkStage(Array.from(selectedAssetIds), stageId)
                      clearSelection()
                    }
                  : undefined
              }
              onSetRunAsAd={
                onBulkRunAsAd
                  ? (runAsAd) => {
                      onBulkRunAsAd(Array.from(selectedAssetIds), runAsAd)
                      clearSelection()
                    }
                  : undefined
              }
            />
```

- [ ] **Step 3: Wire the assets page**

In `apps/web/app/(dashboard)/assets/page.tsx`, immediately after the existing `onBulkStage` prop on `<AssetGrid ...>` (line ~127-130), add (this page's refetch is `mutate()`):

```typescript
          onBulkRunAsAd={async (assetIds, runAsAd) => {
            await api.patch(`/assets/bulk/run-as-ad`, { asset_ids: assetIds, run_as_ad: runAsAd })
            mutate()
          }}
```

- [ ] **Step 4: Wire the project page**

In `apps/web/app/(dashboard)/projects/[id]/page.tsx`, immediately after the `onBulkStage` handler on `<AssetGrid ...>` (line ~1012-1015), add (this page's refetch is `mutateAssets()`):

```typescript
              onBulkRunAsAd={async (assetIds, runAsAd) => {
                await api.patch(`/assets/bulk/run-as-ad`, { asset_ids: assetIds, run_as_ad: runAsAd });
                mutateAssets();
              }}
```

- [ ] **Step 5: Typecheck**

Run (from `apps/web`): `npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 6: Browser verification**

As a platform admin, multi-select assets, open "Set status", choose "Mark as ad". Open one asset's review header and confirm the run-as-ad toggle now reads on. Repeat with "Unmark as ad".

- [ ] **Step 7: Commit**

```bash
git add apps/web/components/projects/bulk-status-menu.tsx apps/web/components/projects/asset-grid.tsx "apps/web/app/(dashboard)/assets/page.tsx" "apps/web/app/(dashboard)/projects/[id]/page.tsx"
git commit -m "feat(web): bulk mark/unmark as ad on multi-select"
```

---

### Task 6: Frontend — submissions file table inside the card

**Files:**
- Modify: `apps/web/app/(dashboard)/submissions/page.tsx`

**Interfaces:**
- Consumes: `GET /submission-links/{id}/submissions` now returns `files` (Task 2).

- [ ] **Step 1: Extend the `SubmissionItem` TS interface**

In `submissions/page.tsx`, update the interface (line ~27):

```typescript
interface SubmissionItem {
  id: string
  user_id: string
  user_name: string
  user_email: string
  project_id: string
  asset_count: number
  files: { asset_id: string; name: string }[]
  created_at: string
}
```

- [ ] **Step 2: Replace the submitter `<ul>` with a table**

In `LinkCard`, the expanded block renders `subs.map((s) => <li>...)` (lines ~605-626). Replace that `<ul>...</ul>` with:

```tsx
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-2xs uppercase tracking-wider text-text-tertiary">
                    <th className="px-2 py-1.5 font-medium">Submitter</th>
                    <th className="px-2 py-1.5 font-medium">Files</th>
                    <th className="px-2 py-1.5 font-medium text-right">Date</th>
                  </tr>
                </thead>
                <tbody>
                  {subs.map((s) => (
                    <tr key={s.id} className="border-t border-border align-top">
                      <td className="px-2 py-2">
                        <Link href={`/projects/${s.project_id}`} className="block hover:underline">
                          <span className="block truncate text-text-primary">{s.user_name || s.user_email}</span>
                          {s.user_name && (
                            <span className="block truncate text-xs text-text-tertiary">{s.user_email}</span>
                          )}
                        </Link>
                      </td>
                      <td className="px-2 py-2">
                        {s.files.length === 0 ? (
                          <span className="text-xs text-text-tertiary">No files yet</span>
                        ) : (
                          <div className="flex flex-wrap gap-1">
                            {s.files.slice(0, 6).map((f) => (
                              <Link
                                key={f.asset_id}
                                href={`/projects/${s.project_id}/assets/${f.asset_id}`}
                                className="inline-flex max-w-[160px] items-center gap-1 truncate rounded-md border border-border bg-bg-primary px-2 py-0.5 text-xs text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors"
                                title={f.name}
                              >
                                <Film className="h-3 w-3 shrink-0" />
                                <span className="truncate">{f.name}</span>
                              </Link>
                            ))}
                            {s.files.length > 6 && (
                              <span className="inline-flex items-center px-1 text-xs text-text-tertiary">
                                +{s.files.length - 6} more
                              </span>
                            )}
                          </div>
                        )}
                      </td>
                      <td className="px-2 py-2 text-right text-xs text-text-tertiary whitespace-nowrap">
                        {new Date(s.created_at).toLocaleDateString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
```

`Film` and `Link` are already imported in this file. Leave the "Pre-assign folder to email…" button that follows unchanged.

- [ ] **Step 3: Typecheck**

Run (from `apps/web`): `npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 4: Browser verification**

As a platform admin, open Submissions, expand a link with submissions. Confirm the table shows Submitter / Files / Date, file chips link to the asset page, and empty submitters show "No files yet".

- [ ] **Step 5: Commit**

```bash
git add "apps/web/app/(dashboard)/submissions/page.tsx"
git commit -m "feat(submissions): file table per submitter in link card"
```

---

## Notes for the implementer

- Line numbers are from the state at planning time; if they've drifted, search for the quoted anchor strings instead.
- Backend and frontend for each feature are separate tasks so a reviewer can gate them independently, but Task 5 depends on Task 1 and Task 6 depends on Task 2 (the endpoints must exist first).
- Final gate before merge: `uv run pytest apps/api/tests/test_bulk_run_as_ad.py apps/api/tests/test_submission_files.py -v` and `cd apps/web && npx vitest run && npx tsc --noEmit`.
