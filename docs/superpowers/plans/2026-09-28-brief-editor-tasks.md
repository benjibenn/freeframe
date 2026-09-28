# Many Editors Per Brief Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let several editors work one brief, each carrying their own pipeline status, while the brief keeps a status of its own.

**Architecture:** Assignment becomes a `submissions` row — the table that is already one row per (brief, editor) and already carries per-editor state. A new `submissions.task_stage_id` holds each editor's status; `submission_links.task_stage_id` keeps holding the brief's. The two rules that matter (who may move whose status, and who may see whom) are extracted into pure functions so they can be tested at all — this test suite has no database.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic (Python 3.11, `uv`), FastMCP, Next.js 14 App Router + SWR + TypeScript, Tailwind.

**Spec:** `docs/superpowers/specs/2026-09-28-brief-editor-tasks-design.md`

## Global Constraints

- **No commit attribution to Claude/Anthropic. No `Co-Authored-By` line.** (User rule, overrides any harness default.)
- Migration `down_revision` is `b6c7d8e9f0a1` — the current head. Do not rebase it onto anything else.
- A non-participant gets **404, never 403**, from every brief endpoint. Existing rule, stated at `apps/api/routers/tasks.py:305`: a 403 tells them the brief exists.
- `submission_links.assignee_id` keeps its current meaning (internal owner) and stays single-valued. Do not repurpose or remove it.
- There is **no unassign path**. Do not add a DELETE endpoint, an MCP tool, or a UI control for it.
- Every new stage reference reads the same `task_stages` rows. Do not introduce a second stage vocabulary.
- API tests run against `MagicMock` sessions (`apps/api/tests/conftest.py`) — there is no test database. Logic that must be tested has to be reachable without one.
- Python: `cd apps/api && uv run pytest`.
- Web typecheck: `cd apps/web && ../../node_modules/.bin/tsc --noEmit`. **Never `npx tsc`** — there is no local tsc binary in `apps/web`, so npx fetches an unrelated package called `tsc`, prints a joke banner and exits 0. It checks nothing and reports success.
- Web unit tests: `cd apps/web && npm test` (vitest). The repo has vitest 4, jsdom, `@testing-library/react` and `@testing-library/user-event`, and 9 existing component tests — `components/admin/__tests__/brief-overview-table.test.tsx` is the precedent for a table component.

## Review Focus

Five conditions the spec implies that no task's happy path would exercise. Each has a test assigned to the task that owns the code.

1. **Assigning an editor to a soft-deleted brief** must 404 before provisioning, or it creates an orphan project against a dead brief. → Task 5.
2. **Moving an editor to a soft-deleted stage id** must 404 via the existing `_get_stage`, not write a dangling reference. → Task 5.
3. **A non-admin who is neither editor nor owner** hitting the editor-stage PATCH must get 404, not 403. → Task 1 (unit) and Task 5 (route).
4. **`visible_editors` with a null viewer id** must return `[]` for a non-admin, not the whole list. A missing id is the failure mode where a leak would be silent. → Task 1.
5. **Assigning the brief's own creator as an editor** must not 500. `_provision_submission_project` already skips the duplicate `ProjectMember` for that case (`apps/api/routers/submissions.py:1746`); the endpoint must not re-add it. → Task 5.

**Known untested:** the `get_task_board` scoping union (Task 4) is raw SQL over two tables. With no test database it cannot be asserted meaningfully — a mock-chained assertion would test the mock, not the query. Task 10 verifies it by hand against the running API and says so in its output rather than claiming coverage it does not have.

---

### Task 1: The isolation and permission rules

Two decisions carry the whole change's safety: which editor rows a viewer may see, and whose status they may move. They live in their own module because they are the only parts that are testable without a database, and because "can this person see that person's progress" deserves to be one readable function rather than a condition inside a loop.

**Files:**
- Create: `apps/api/services/brief_editors.py`
- Test: `apps/api/tests/test_brief_editors.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `visible_editors(editors: list, viewer_id, is_admin: bool) -> list` — filters a list of objects with an `.id` attribute.
  - `may_move_editor_stage(viewer_id, target_user_id, is_admin: bool) -> bool`

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/test_brief_editors.py`:

```python
"""Tests for who may see, and who may move, another editor's work on a brief.

Intent encoded: per-submitter isolation is the whole reason submission links
exist. An editor learning who else is on a brief, and how far along they are,
is the leak this module prevents — so the tests are written against the leak,
not against the filter.
"""
import uuid
from types import SimpleNamespace

from apps.api.services.brief_editors import may_move_editor_stage, visible_editors


def _editor(user_id=None):
    return SimpleNamespace(id=user_id or uuid.uuid4())


def test_an_editor_sees_only_their_own_row():
    """The leak this exists to stop: co-editor names and progress in the body.

    Filtering in the UI would not do — the response would still carry them.
    """
    me, them = _editor(), _editor()
    assert visible_editors([me, them], me.id, is_admin=False) == [me]


def test_an_admin_sees_every_editor():
    """Admins are who the roll-up is for; hiding rows would make it useless."""
    a, b = _editor(), _editor()
    assert visible_editors([a, b], a.id, is_admin=True) == [a, b]


def test_a_viewer_with_no_row_sees_nothing():
    """An internal owner who is not an editor sees the brief but not the people."""
    assert visible_editors([_editor(), _editor()], uuid.uuid4(), is_admin=False) == []


def test_a_missing_viewer_id_hides_everyone_rather_than_everyone_being_shown():
    """Fail closed. A null id is the case where a leak would be silent."""
    assert visible_editors([_editor(), _editor()], None, is_admin=False) == []


def test_an_editor_may_move_their_own_status():
    me = uuid.uuid4()
    assert may_move_editor_stage(me, me, is_admin=False) is True


def test_an_editor_may_not_move_a_co_editors_status():
    """Two editors on one brief are doing separate work; neither reports for the
    other. Allowing it would also disclose that the other row exists."""
    assert may_move_editor_stage(uuid.uuid4(), uuid.uuid4(), is_admin=False) is False


def test_an_admin_may_move_anyones_status():
    assert may_move_editor_stage(uuid.uuid4(), uuid.uuid4(), is_admin=True) is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd apps/api && uv run pytest tests/test_brief_editors.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'apps.api.services.brief_editors'`

- [ ] **Step 3: Write the implementation**

Create `apps/api/services/brief_editors.py`:

```python
"""Who may see, and who may move, an editor's status on a brief.

A brief can be assigned to several editors, each carrying their own pipeline
stage. Two rules govern that, and both are here rather than inline in the
router: they are the parts worth reading on their own, and they are the parts
this test suite can exercise without a database.
"""
from typing import Any, Optional
import uuid


def visible_editors(
    editors: list[Any],
    viewer_id: Optional[uuid.UUID],
    is_admin: bool,
) -> list[Any]:
    """The editor rows this viewer is allowed to receive.

    Per-submitter isolation is what submission links are for: editors on one
    brief never see each other's uploads, so they must not see each other's
    names or progress either. Applied to the response body rather than the UI,
    because hiding a row on screen still ships it over the wire.

    Fails closed on a missing viewer id — that is the case where handing back
    the full list would go unnoticed.
    """
    if is_admin:
        return list(editors)
    if viewer_id is None:
        return []
    return [e for e in editors if e.id == viewer_id]


def may_move_editor_stage(
    viewer_id: Optional[uuid.UUID],
    target_user_id: uuid.UUID,
    is_admin: bool,
) -> bool:
    """Whether this viewer may set `target_user_id`'s status on a brief.

    Admins move anyone: the board is their roll-up. Everyone else moves only
    themselves — two editors on one brief are doing separate work, and neither
    reports progress on the other's behalf.
    """
    return bool(is_admin or (viewer_id is not None and viewer_id == target_user_id))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd apps/api && uv run pytest tests/test_brief_editors.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add apps/api/services/brief_editors.py apps/api/tests/test_brief_editors.py
git commit -m "Add the rules for who sees and who moves an editor's status on a brief"
```

---

### Task 2: The column

**Files:**
- Create: `apps/api/alembic/versions/c7d8e9f0a1b2_add_task_stage_to_submissions.py`
- Modify: `apps/api/models/submission.py` (the `Submission` class, after `paid_at`)

**Interfaces:**
- Consumes: nothing.
- Produces: `Submission.task_stage_id: Optional[uuid.UUID]`, nullable, FK to `task_stages.id`, indexed.

- [ ] **Step 1: Write the migration**

Create `apps/api/alembic/versions/c7d8e9f0a1b2_add_task_stage_to_submissions.py`:

```python
"""add task_stage_id to submissions

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-09-28

Each editor assigned to a brief carries their own pipeline stage, so two
editors on one brief can be at different points. The brief keeps its own
stage on submission_links; this is the per-editor one.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'c7d8e9f0a1b2'
down_revision: Union[str, Sequence[str], None] = 'b6c7d8e9f0a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'submissions',
        sa.Column('task_stage_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_submissions_task_stage', 'submissions', 'task_stages',
        ['task_stage_id'], ['id'],
    )
    op.create_index('ix_submissions_task_stage_id', 'submissions', ['task_stage_id'])


def downgrade() -> None:
    op.drop_index('ix_submissions_task_stage_id', table_name='submissions')
    op.drop_constraint('fk_submissions_task_stage', 'submissions', type_='foreignkey')
    op.drop_column('submissions', 'task_stage_id')
```

No backfill. Null means "not started", which is the state every existing assignment is genuinely in.

- [ ] **Step 2: Add the model column**

In `apps/api/models/submission.py`, in the `Submission` class, immediately after the `paid_at` column:

```python
    # This editor's own status on this brief. Reads the same task_stages rows as
    # the brief and the assets, so a stage name means one thing everywhere. Null
    # = not started. Distinct from SubmissionLink.task_stage_id, which is the
    # brief's overall state: two editors on one brief can be at different points.
    task_stage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("task_stages.id"), nullable=True, index=True
    )
```

- [ ] **Step 3: Verify the revision chain is linear and the model imports**

Run: `cd apps/api && uv run python -c "from apps.api.models.submission import Submission; print(Submission.task_stage_id)"`
Expected: prints the column, no error.

Run: `cd apps/api && grep -rc "down_revision: Union\[str, Sequence\[str\], None\] = 'b6c7d8e9f0a1'" alembic/versions/`
Expected: exactly one file reports `1` — the new migration is the only child of the old head.

- [ ] **Step 4: Run the existing suite to confirm nothing broke**

Run: `cd apps/api && uv run pytest -q 2>&1 | tail -5`
Expected: the same counts as before this task (this repo carries 16 pre-existing failures; the passed count must not drop and the failed count must not rise).

- [ ] **Step 5: Commit**

```bash
git add apps/api/alembic/versions/c7d8e9f0a1b2_add_task_stage_to_submissions.py apps/api/models/submission.py
git commit -m "Give each editor on a brief their own pipeline stage column"
```

---

### Task 3: The API contract for an editor row

**Files:**
- Modify: `apps/api/schemas/task_stage.py` (`BriefEditor` ~line 74; add `BriefEditorAssign` at the end)
- Modify: `apps/api/routers/tasks.py` (`_brief_item` line 605; call sites at lines 577 and 602)

**Interfaces:**
- Consumes: `visible_editors` from Task 1; `Submission.task_stage_id` from Task 2.
- Produces:
  - `BriefEditor.task_stage_id: Optional[uuid.UUID]`
  - `class BriefEditorAssign(BaseModel): user_id: uuid.UUID`
  - `_brief_item(db: Session, link: SubmissionLink, viewer: User) -> BriefTaskItem`

- [ ] **Step 1: Widen `BriefEditor` and add the assign body**

In `apps/api/schemas/task_stage.py`, replace the `BriefEditor` class with:

```python
class BriefEditor(BaseModel):
    """An editor assigned to the request — by accepting the link, or by an admin.

    Derived from `submissions`, one row per (brief, editor). A non-admin viewer
    receives only their own row: co-editors' names and progress are exactly what
    per-submitter isolation exists to withhold.
    """
    id: uuid.UUID
    name: Optional[str] = None
    email: Optional[str] = None
    # This editor's own status. Null = not started. Independent of the brief's
    # task_stage_id above: two editors can be at different points on one brief.
    task_stage_id: Optional[uuid.UUID] = None
```

At the end of the file, after `BriefAssigneeAssign`:

```python
class BriefEditorAssign(BaseModel):
    """The editor to put on this brief.

    One-way: assigning provisions their private upload project, and there is no
    unassign — removing the row would orphan whatever they uploaded into it.
    """
    user_id: uuid.UUID
```

- [ ] **Step 2: Scope `_brief_item` to its viewer**

In `apps/api/routers/tasks.py`, add to the imports from `..schemas.task_stage`: `BriefEditorAssign`. Add a new import line — `visible_editors` only, since nothing here moves a stage yet; Task 5 extends this line:

```python
from ..services.brief_editors import visible_editors
```

Replace `_brief_item` (line 605) with:

```python
def _brief_item(db: Session, link: SubmissionLink, viewer: User) -> BriefTaskItem:
    """One brief, without its assets — the PATCH endpoints return the row the
    board just changed, and the board already holds the nested files.

    Editors are scoped to the viewer for the same reason the board scopes them:
    the row a PATCH hands back must not disclose more than the board would have.
    """
    owner = db.query(User).filter(User.id == link.assignee_id).first() if link.assignee_id else None
    editors = [
        BriefEditor(id=u.id, name=u.name, email=u.email, task_stage_id=stage_id)
        for stage_id, u in db.query(Submission.task_stage_id, User)
        .join(User, User.id == Submission.user_id)
        .filter(Submission.submission_link_id == link.id)
        .all()
    ]
    return BriefTaskItem(
        id=link.id,
        title=link.title,
        taxonomy_path=resolve_link_home_path(db, link),
        task_stage_id=link.task_stage_id,
        assignee_id=link.assignee_id,
        assignee_name=owner.name if owner else None,
        editors=visible_editors(editors, viewer.id, is_platform_admin(viewer)),
        has_brief=bool(link.brief_pdf_s3_key),
        has_brief_json=bool(link.brief_json),
        submit_url=f"{settings.frontend_url}/submit/{link.token}",
        created_at=link.created_at,
        assets=[],
    )
```

- [ ] **Step 3: Update the two existing call sites**

`apps/api/routers/tasks.py` line 577 (in `set_brief_task_stage`) and line 602 (in `set_brief_assignee`): change `return _brief_item(db, link)` to `return _brief_item(db, link, current_user)`.

- [ ] **Step 4: Run the suite to confirm the brief-level contract did not move**

Run: `cd apps/api && uv run pytest tests/test_brief_overview.py tests/test_mcp_briefs.py -q`
Expected: same result as before this task — these cover the brief-level contract, which this change must not disturb.

Run: `cd apps/api && uv run pytest -q 2>&1 | tail -5`
Expected: passed count unchanged, failed count unchanged.

- [ ] **Step 5: Commit**

```bash
git add apps/api/schemas/task_stage.py apps/api/routers/tasks.py
git commit -m "Carry each editor's stage on the brief row, scoped to its viewer"
```

---

### Task 4: The board shows a brief to everyone assigned to it

Today a non-admin sees a brief only when `assignee_id` points at them. This is the change that makes a second editor possible at all.

**Files:**
- Modify: `apps/api/routers/tasks.py` (`get_task_board`, scoping block ~line 333, editors block ~line 388, `BriefTaskItem` construction ~line 400)

**Interfaces:**
- Consumes: `visible_editors` (Task 1), `Submission.task_stage_id` (Task 2), `BriefEditor.task_stage_id` (Task 3).
- Produces: no new names. `/task-board` now returns a brief to any assigned editor, with per-editor stages on `editors[]`.

- [ ] **Step 1: Widen the non-admin scope to a union**

In `get_task_board`, replace the `owned_link_ids` assignment with:

```python
    owned_link_ids = None
    if not admin:
        # Union, not replacement: a brief reaches someone because they own it
        # (assignee_id — whose desk it sits on) OR because they are assigned to
        # make it (a submissions row). Dropping the first would take briefs away
        # from internal owners who are not editors.
        owned_link_ids = {
            lid for (lid,) in db.query(SubmissionLink.id).filter(
                SubmissionLink.assignee_id == current_user.id,
                SubmissionLink.deleted_at.is_(None),
            ).all()
        } | {
            lid for (lid,) in db.query(Submission.submission_link_id)
            .join(SubmissionLink, SubmissionLink.id == Submission.submission_link_id)
            .filter(
                Submission.user_id == current_user.id,
                SubmissionLink.deleted_at.is_(None),
            ).all()
        }
        if not owned_link_ids:
            return TaskBoardResponse(briefs=[], unbriefed=[])
```

- [ ] **Step 2: Carry each editor's stage through the bulk load**

Replace the `if links:` block that builds `editors_by_link` with:

```python
    if links:
        rows = (
            db.query(
                Submission.submission_link_id,
                Submission.paid_at,
                Submission.task_stage_id,
                User,
            )
            .join(User, User.id == Submission.user_id)
            .filter(Submission.submission_link_id.in_([l.id for l in links]))
            .all()
        )
        for link_id, paid_at, stage_id, user in rows:
            editors_by_link.setdefault(link_id, []).append(
                BriefEditor(id=user.id, name=user.name, email=user.email, task_stage_id=stage_id)
            )
            sub_counts[link_id] = sub_counts.get(link_id, 0) + 1
            if paid_at is not None:
                paid_counts[link_id] = paid_counts.get(link_id, 0) + 1
```

`sub_counts` and `paid_counts` still count every row, not the visible ones — they are the admin's roll-up and are already zeroed for non-admins further down.

- [ ] **Step 3: Scope the editor list per brief**

In the `briefs = [...]` comprehension, change the `editors=` line to:

```python
            editors=visible_editors(editors_by_link.get(l.id, []), current_user.id, admin),
```

- [ ] **Step 4: Run the suite**

Run: `cd apps/api && uv run pytest -q 2>&1 | tail -5`
Expected: passed count unchanged, failed count unchanged.

- [ ] **Step 5: Commit**

```bash
git add apps/api/routers/tasks.py
git commit -m "Show a brief on the task board to every editor assigned to it"
```

---

### Task 5: Assigning an editor, and moving their status

**Files:**
- Modify: `apps/api/routers/tasks.py` (two new endpoints, after `set_brief_assignee` and before `_brief_item`)
- Test: `apps/api/tests/test_brief_editor_endpoints.py` (create)

**Interfaces:**
- Consumes: `BriefEditorAssign`, `_brief_item(db, link, viewer)` (Task 3); `may_move_editor_stage` (Task 1); `_provision_submission_project` from `apps/api/routers/submissions.py:1711`.
- Produces:
  - `assign_brief_editor(link_id: uuid.UUID, body: BriefEditorAssign, db, current_user) -> BriefTaskItem` at `POST /submission-links/{link_id}/editors`
  - `set_brief_editor_task_stage(link_id: uuid.UUID, user_id: uuid.UUID, body: TaskStageAssign, db, current_user) -> BriefTaskItem` at `PATCH /submission-links/{link_id}/editors/{user_id}/task-stage`

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/test_brief_editor_endpoints.py`:

```python
"""Tests for assigning editors to a brief and moving their individual statuses.

Intent encoded:
- assignment is one-way and provisions an upload project, so it must refuse a
  dead brief rather than leave an orphan project pointing at one;
- an editor's status is theirs — moving it must not disturb the brief's own,
  which is the entire reason there are two;
- a non-participant is told the brief does not exist, not that they lack rights.
"""
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from apps.api.models.user import UserStatus


def _user(*, is_superadmin=False, name="Editor"):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.name = name
    u.email = f"{name.replace(' ', '.').lower()}@example.com"
    u.status = UserStatus.active
    u.is_superadmin = is_superadmin
    u.is_subadmin = False
    u.deleted_at = None
    return u


def _link(deleted=False):
    l = MagicMock()
    l.id = uuid.uuid4()
    l.token = "tok-abc"
    l.title = "Static — iPhone 17 Pro Max"
    l.task_stage_id = uuid.uuid4()
    l.assignee_id = None
    l.brief_pdf_s3_key = None
    l.brief_json = None
    l.created_at = None
    l.deleted_at = "gone" if deleted else None
    # These three MUST be None, not left as auto-created MagicMock attributes.
    # _brief_item resolves the brief's path through folder_paths, which builds a
    # recursive CTE and iterates db.execute(...).all(). A truthy folder id sends
    # it down that road against a mock session and the request 500s. None makes
    # link_home_paths short-circuit with no DB work at all.
    l.home_folder_id = None
    l.home_project_id = None
    l.taxonomy_path = None
    return l


def _client(mock_db, current_user):
    from apps.api.routers.tasks import router
    from apps.api.database import get_db
    from apps.api.middleware.auth import get_current_user

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: current_user
    return TestClient(app, raise_server_exceptions=False)


# ── Assigning ────────────────────────────────────────────────────────────────

def test_a_plain_editor_cannot_assign_anyone(mock_db):
    """Assignment hands out work and provisions a project. Not self-service."""
    link = _link()
    client = _client(mock_db, _user())
    r = client.post(f"/submission-links/{link.id}/editors", json={"user_id": str(uuid.uuid4())})
    assert r.status_code == 403


def test_assigning_to_a_deleted_brief_is_refused_before_provisioning(mock_db):
    """Otherwise a private project is created pointing at a brief that is gone."""
    mock_db.first.return_value = None  # the deleted-aware lookup finds nothing
    client = _client(mock_db, _user(is_superadmin=True, name="Admin"))
    with patch("apps.api.routers.submissions._provision_submission_project") as prov:
        r = client.post(
            f"/submission-links/{uuid.uuid4()}/editors", json={"user_id": str(uuid.uuid4())}
        )
    assert r.status_code == 404
    prov.assert_not_called()


def test_assigning_an_unknown_user_is_refused(mock_db):
    link = _link()
    editor_id = uuid.uuid4()
    # First lookup finds the link; the user lookup finds nobody.
    mock_db.first.side_effect = [link, None]
    client = _client(mock_db, _user(is_superadmin=True, name="Admin"))
    with patch("apps.api.routers.submissions._provision_submission_project") as prov:
        r = client.post(f"/submission-links/{link.id}/editors", json={"user_id": str(editor_id)})
    assert r.status_code == 404
    prov.assert_not_called()


def test_assigning_the_briefs_own_creator_is_allowed(mock_db):
    """An owner testing their own brief is a real case the provisioner already
    handles (it skips the duplicate membership). It must not blow up here."""
    link = _link()
    admin = _user(is_superadmin=True, name="Admin")
    mock_db.first.side_effect = [link, admin, None]
    mock_db.all.return_value = []
    client = _client(mock_db, admin)
    with patch(
        "apps.api.routers.submissions._provision_submission_project",
        return_value=uuid.uuid4(),
    ) as prov:
        r = client.post(f"/submission-links/{link.id}/editors", json={"user_id": str(admin.id)})
    assert r.status_code == 200
    prov.assert_called_once()


# ── Moving an editor's status ────────────────────────────────────────────────

def test_an_editor_cannot_move_a_co_editors_status(mock_db):
    """404, not 403 — a co-editor's participation is not theirs to discover."""
    link = _link()
    mock_db.first.return_value = link
    client = _client(mock_db, _user())
    r = client.patch(
        f"/submission-links/{link.id}/editors/{uuid.uuid4()}/task-stage",
        json={"task_stage_id": None},
    )
    assert r.status_code == 404


def test_moving_an_editors_status_leaves_the_briefs_own_status_alone(mock_db):
    """The entire reason there are two statuses. If this fuses them, the feature
    is pointless: one editor finishing would mark the whole brief done."""
    link = _link()
    brief_stage_before = link.task_stage_id
    me = _user()
    submission = MagicMock()
    submission.task_stage_id = None
    stage = MagicMock()
    stage.id = uuid.uuid4()
    stage.deleted_at = None
    # link lookup, stage validation, submission lookup, then _brief_item's owner lookup
    mock_db.first.side_effect = [link, stage, submission, None]
    mock_db.all.return_value = []
    client = _client(mock_db, me)
    r = client.patch(
        f"/submission-links/{link.id}/editors/{me.id}/task-stage",
        json={"task_stage_id": str(stage.id)},
    )
    assert r.status_code == 200
    assert submission.task_stage_id == stage.id
    assert link.task_stage_id == brief_stage_before


def test_moving_to_a_deleted_stage_is_refused(mock_db):
    """_get_stage filters on deleted_at; a dangling reference would render as a
    status that is not in the picker."""
    link = _link()
    me = _user()
    mock_db.first.side_effect = [link, None]  # link found, stage not found
    client = _client(mock_db, me)
    r = client.patch(
        f"/submission-links/{link.id}/editors/{me.id}/task-stage",
        json={"task_stage_id": str(uuid.uuid4())},
    )
    assert r.status_code == 404


def test_an_editor_with_no_row_on_this_brief_gets_a_404(mock_db):
    """Being signed in is not participation."""
    link = _link()
    me = _user()
    stage = MagicMock()
    stage.deleted_at = None
    mock_db.first.side_effect = [link, stage, None]  # no submission row
    client = _client(mock_db, me)
    r = client.patch(
        f"/submission-links/{link.id}/editors/{me.id}/task-stage",
        json={"task_stage_id": str(uuid.uuid4())},
    )
    assert r.status_code == 404
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd apps/api && uv run pytest tests/test_brief_editor_endpoints.py -v`
Expected: FAIL — every request 404s because the routes do not exist yet.

- [ ] **Step 3: Write the endpoints**

First extend the existing import added in Task 3:

```python
from ..services.brief_editors import may_move_editor_stage, visible_editors
```

Then, in `apps/api/routers/tasks.py`, after `set_brief_assignee` and before `_brief_item`:

```python
@router.post("/submission-links/{link_id}/editors", response_model=BriefTaskItem)
def assign_brief_editor(
    link_id: uuid.UUID,
    body: BriefEditorAssign,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Put an editor on a brief, provisioning their private upload project.

    Assignment IS a submissions row, the same row accepting the token link
    creates — so a brief reaches an editor the same way whichever route they
    arrived by, and there is one answer to "who is on this".

    One-way on purpose: that row owns a project with their uploads in it, so
    there is no unassign. The brief is checked before anything is provisioned,
    or a dead brief would acquire a live project.
    """
    require_platform_admin(current_user)
    link = db.query(SubmissionLink).filter(
        SubmissionLink.id == link_id, SubmissionLink.deleted_at.is_(None)
    ).first()
    if not link:
        raise HTTPException(status_code=404, detail="Request not found")
    editor = db.query(User).filter(User.id == body.user_id).first()
    if not editor:
        raise HTTPException(status_code=404, detail="User not found")

    # Local import: the provisioner lives with the accept flow it was written
    # for, and importing it at module level would tie these two routers together.
    from .submissions import _provision_submission_project

    # Idempotent — assigning someone already on the brief returns their existing
    # project rather than opening a second one.
    _provision_submission_project(db, link, editor)
    db.commit()
    db.refresh(link)
    return _brief_item(db, link, current_user)


@router.patch(
    "/submission-links/{link_id}/editors/{user_id}/task-stage",
    response_model=BriefTaskItem,
)
def set_brief_editor_task_stage(
    link_id: uuid.UUID,
    user_id: uuid.UUID,
    body: TaskStageAssign,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Move one editor along the pipeline, leaving the brief's own stage alone.

    The separation is the point: a brief with three editors has three answers to
    "how far along is this", and collapsing them into the brief's single stage
    would mean the first editor to finish marked the whole thing done.
    """
    link = db.query(SubmissionLink).filter(
        SubmissionLink.id == link_id, SubmissionLink.deleted_at.is_(None)
    ).first()
    if not link:
        raise HTTPException(status_code=404, detail="Request not found")
    if not may_move_editor_stage(current_user.id, user_id, is_platform_admin(current_user)):
        # 404, not 403: whether someone else is on this brief is not this
        # caller's to learn.
        raise HTTPException(status_code=404, detail="Request not found")
    if body.task_stage_id is not None:
        _get_stage(db, body.task_stage_id)  # validate it exists / is not deleted

    submission = db.query(Submission).filter(
        Submission.submission_link_id == link_id,
        Submission.user_id == user_id,
    ).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Request not found")

    submission.task_stage_id = body.task_stage_id
    db.commit()
    db.refresh(link)
    return _brief_item(db, link, current_user)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd apps/api && uv run pytest tests/test_brief_editor_endpoints.py -v`
Expected: 8 passed

Run: `cd apps/api && uv run pytest -q 2>&1 | tail -5`
Expected: passed count up by 8, failed count unchanged.

- [ ] **Step 5: Commit**

```bash
git add apps/api/routers/tasks.py apps/api/tests/test_brief_editor_endpoints.py
git commit -m "Assign editors to a brief and move each one's status independently"
```

---

### Task 6: Deleting a stage releases the editors sitting in it

`delete_task_stage` already detaches assets. Without the same for submissions, a soft-deleted stage keeps rendering as an editor status that is not in the picker.

**Files:**
- Modify: `apps/api/routers/tasks.py` (`delete_task_stage`, ~line 140)
- Test: `apps/api/tests/test_brief_editor_endpoints.py` (append)

**Interfaces:**
- Consumes: `Submission.task_stage_id` (Task 2).
- Produces: no new names.

- [ ] **Step 1: Write the failing test**

Append to `apps/api/tests/test_brief_editor_endpoints.py`:

```python
def test_deleting_a_stage_releases_the_editors_sitting_in_it(mock_db):
    """A soft-deleted stage would otherwise keep showing as an editor's status
    while being absent from the picker — a status nobody can clear."""
    from apps.api.models.submission import Submission

    stage = MagicMock()
    stage.id = uuid.uuid4()
    stage.deleted_at = None
    mock_db.first.return_value = stage

    client = _client(mock_db, _user(is_superadmin=True, name="Admin"))
    assert client.delete(f"/task-stages/{stage.id}").status_code == 204

    detached = [
        c.args[0] for c in mock_db.update.call_args_list
        if c.args and isinstance(c.args[0], dict)
    ]
    assert any(Submission.task_stage_id in d for d in detached), (
        "submissions in the deleted stage were not detached"
    )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/api && uv run pytest tests/test_brief_editor_endpoints.py::test_deleting_a_stage_releases_the_editors_sitting_in_it -v`
Expected: FAIL — `AssertionError: submissions in the deleted stage were not detached`

- [ ] **Step 3: Detach submissions on delete**

In `apps/api/routers/tasks.py`, in `delete_task_stage`, immediately after the block that detaches assets:

```python
    # Same for the editors sitting in this stage. Without this a soft-deleted
    # stage keeps rendering as someone's status while being gone from the picker.
    db.query(Submission).filter(Submission.task_stage_id == stage.id).update(
        {Submission.task_stage_id: None}, synchronize_session=False
    )
```

Leave `submission_links.task_stage_id` alone — that gap predates this change and widening the scope here would bury it.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd apps/api && uv run pytest tests/test_brief_editor_endpoints.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add apps/api/routers/tasks.py apps/api/tests/test_brief_editor_endpoints.py
git commit -m "Release editors from a stage when it is deleted"
```

---

### Task 7: The MCP tools

**Files:**
- Modify: `apps/api/routers/mcp.py` (`_brief_task_summary` ~line 1225; `assign_brief_owner` description ~line 1262; two new tools after it)
- Test: `apps/api/tests/test_mcp_brief_editors.py` (create)

**Interfaces:**
- Consumes: `tasks_router.assign_brief_editor`, `tasks_router.set_brief_editor_task_stage` (Task 5); `BriefEditorAssign` (Task 3).
- Produces: MCP tools `assign_brief_editor(link_id, user_id)` and `set_brief_editor_stage(link_id, user_id, task_stage_id)`.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_mcp_brief_editors.py`:

```python
"""Tests for the MCP tools that put editors on a brief and move their statuses.

Intent encoded: an agent reading a brief must be able to see who is on it and
how far each of them is, and the tool descriptions must say that assignment
cannot be undone — an agent that discovers this by trying has already done it.
"""
import asyncio
import uuid
from unittest.mock import MagicMock

from apps.api.routers import mcp as mcp_router


def test_a_brief_summary_reports_every_editor_and_their_stage():
    """Without this an agent can assign work but never see where it got to."""
    stage_id = uuid.uuid4()
    editor = MagicMock()
    editor.id = uuid.uuid4()
    editor.name = "Ada Editor"
    editor.email = "ada@example.com"
    editor.task_stage_id = stage_id

    item = MagicMock()
    item.id = uuid.uuid4()
    item.title = "Static — iPhone 17 Pro Max"
    item.taxonomy_path = "ecom/Phones"
    item.task_stage_id = None
    item.assignee_id = None
    item.assignee_name = None
    item.editors = [editor]
    item.submit_url = "http://localhost:3000/submit/tok"
    item.created_at = None

    out = mcp_router._brief_task_summary(item)
    assert out["editors"] == [
        {
            "id": str(editor.id),
            "name": "Ada Editor",
            "email": "ada@example.com",
            "task_stage_id": str(stage_id),
        }
    ]


def _tool(name):
    """One registered MCP tool.

    `mcp.tool(...)` returns the undecorated function, so the description an agent
    actually receives lives in the server's registry, not on the function. Assert
    against the registry or the assertion proves nothing.
    """
    tools = asyncio.new_event_loop().run_until_complete(mcp_router.mcp.list_tools())
    return next(t for t in tools if t.name == name)


def test_the_assign_tool_warns_that_it_cannot_be_undone():
    """An agent finding out by trying has already created the project."""
    assert "cannot be undone" in (_tool("assign_brief_editor").description or "").lower()


def test_the_editor_stage_tool_points_at_a_real_stage_id():
    """A stage id cannot be guessed, so the tool has to name where to get one."""
    assert "list_task_stages" in (_tool("set_brief_editor_stage").description or "")


def test_both_tools_are_registered_under_the_names_agents_will_call():
    """A tool renamed by a decorator default is a tool no prompt can reach."""
    names = {t.name for t in asyncio.new_event_loop().run_until_complete(mcp_router.mcp.list_tools())}
    assert {"assign_brief_editor", "set_brief_editor_stage"} <= names
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/api && uv run pytest tests/test_mcp_brief_editors.py -v`
Expected: FAIL — `KeyError: 'editors'`, and `StopIteration` from `_tool` because neither tool is registered yet.

- [ ] **Step 3: Add the editors to the summary and write the two tools**

In `apps/api/routers/mcp.py`, in `_brief_task_summary`, after the `assignee_name` entry:

```python
        # Who is making it, and how far each of them is. An agent that can
        # assign work but cannot read its progress can only ever assign more.
        "editors": [
            {
                "id": str(e.id),
                "name": e.name,
                "email": e.email,
                "task_stage_id": str(e.task_stage_id) if e.task_stage_id else None,
            }
            for e in (item.editors or [])
        ],
```

Add `BriefEditorAssign` to the existing import of schemas from `..schemas.task_stage`.

In `assign_brief_owner`'s description, replace "Distinct from the editors who accepted the link, which is derived and not settable here." with "Distinct from the editors making it — put those on with assign_brief_editor."

After `assign_brief_owner`:

```python
@mcp.tool(
    description=(
        "Put an editor on a brief so it appears on their task list and they can "
        "upload against it. This provisions their private upload folder and "
        "CANNOT BE UNDONE — there is no unassign, because that folder holds "
        "their work. Assigning the same person twice is harmless. Get a real "
        "user id from list_assignable_users first. Platform-admin only."
    )
)
def assign_brief_editor(link_id: str, user_id: str) -> dict[str, Any]:
    """Args: link_id — the brief to staff. user_id — a user id from
    list_assignable_users. Cannot be undone."""
    _require_scope(SCOPE_WRITE)
    updated = _call(
        tasks_router.assign_brief_editor,
        link_id=_uuid(link_id, "link_id"),
        body=BriefEditorAssign(user_id=_uuid(user_id, "user_id")),
    )
    return _brief_task_summary(updated)


@mcp.tool(
    description=(
        "Move one editor along the pipeline on a brief, or pass null to clear "
        "their stage. Each editor on a brief carries their own status, and this "
        "leaves the brief's own status alone. Get a real stage id from "
        "list_task_stages first. Platform admins may move any editor; anyone "
        "else only themselves."
    )
)
def set_brief_editor_stage(
    link_id: str, user_id: str, task_stage_id: str | None
) -> dict[str, Any]:
    """Args: link_id — the brief. user_id — which editor on it. task_stage_id —
    a stage id from list_task_stages, or null to clear their stage."""
    _require_scope(SCOPE_WRITE)
    updated = _call(
        tasks_router.set_brief_editor_task_stage,
        link_id=_uuid(link_id, "link_id"),
        user_id=_uuid(user_id, "user_id"),
        body=TaskStageAssign(
            task_stage_id=_uuid(task_stage_id, "task_stage_id") if task_stage_id else None
        ),
    )
    return _brief_task_summary(updated)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd apps/api && uv run pytest tests/test_mcp_brief_editors.py tests/test_mcp_briefs.py -v`
Expected: the 4 new tests pass; `test_mcp_briefs.py` unchanged.

- [ ] **Step 5: Commit**

```bash
git add apps/api/routers/mcp.py apps/api/tests/test_mcp_brief_editors.py
git commit -m "Staff briefs and move editor statuses over MCP"
```

---

### Task 8: Editor rows in the task list

**Files:**
- Modify: `apps/web/types/index.ts` (`BriefEditor`, line 73)
- Modify: `apps/web/components/tasks/brief-row.tsx`

**Interfaces:**
- Consumes: `BriefEditor.task_stage_id` from the API (Task 3); `PATCH /submission-links/{id}/editors/{user_id}/task-stage` and `POST /submission-links/{id}/editors` (Task 5).
- Produces: `BriefRow` gains a `viewerId?: string` prop. New exported component `EditorSubRow`.

- [ ] **Step 1: Widen the type**

In `apps/web/types/index.ts`, replace the `BriefEditor` interface:

```ts
export interface BriefEditor {
  id: string;
  name: string | null;
  email: string | null;
  /** This editor's own status on the brief. Independent of the brief's own —
   *  two editors on one brief can be at different points. A non-admin viewer
   *  only ever receives their own row here. */
  task_stage_id: string | null;
}
```

- [ ] **Step 2: Add the editor sub-row**

In `apps/web/components/tasks/brief-row.tsx`, after the `AssetSubRow` component, add:

```tsx
/** An editor working this brief, with the status only they (and admins) can
 *  move. Sits above the delivered files because who is on it comes before what
 *  has arrived. */
export function EditorSubRow({
  briefId,
  editor,
  stages,
  canMove,
}: {
  briefId: string
  editor: BriefEditor
  stages: TaskStage[]
  /** Admins move anyone; everyone else only their own row. */
  canMove: boolean
}) {
  const setStage = async (stageId: string | null) => {
    await api.patch(`/submission-links/${briefId}/editors/${editor.id}/task-stage`, {
      task_stage_id: stageId,
    })
    mutate(BOARD_KEY)
  }
  const stageName = stages.find((s) => s.id === editor.task_stage_id)?.name

  return (
    <tr className="border-t border-border/50 bg-bg-secondary/20">
      <td className="px-3 py-2 pl-12">
        <span className="flex items-center gap-2 text-xs text-text-secondary">
          <UserRound className="h-3.5 w-3.5 shrink-0 text-text-tertiary" />
          <span className="truncate">{editor.name || editor.email || 'Editor'}</span>
        </span>
      </td>
      <td className="px-3 py-2 text-xs text-text-tertiary">—</td>
      <td className="px-3 py-2 text-xs text-text-tertiary">Editor</td>
      <td className="px-3 py-2 text-center text-xs text-text-tertiary"></td>
      <td className="px-3 py-2">
        {canMove ? (
          <StagePicker value={editor.task_stage_id} stages={stages} onChange={setStage} />
        ) : (
          <span className="text-xs text-text-tertiary">{stageName || 'Not started'}</span>
        )}
      </td>
    </tr>
  )
}
```

Add `UserRound` to the `lucide-react` import and `BriefEditor` to the `@/types` import.

- [ ] **Step 3: Render the editor rows and the assign control**

Add `viewerId` to `BriefRow`'s props (`viewerId?: string`, documented as "which editor row belongs to the reader"). Add beside `setOwner`:

```tsx
  const [assigning, setAssigning] = React.useState(false)

  const assignEditor = async (userId: string) => {
    const who = owners.find((u) => u.id === userId)
    // One-way: the editor's upload folder is created here and there is no
    // unassign, so this asks rather than silently doing it.
    if (!confirm(`Put ${who?.name || who?.email || 'this editor'} on “${brief.title}”?\n\nThis creates their upload folder and cannot be undone.`))
      return
    setAssigning(true)
    try {
      await api.post(`/submission-links/${brief.id}/editors`, { user_id: userId })
      mutate(BOARD_KEY)
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to assign that editor')
    } finally {
      setAssigning(false)
    }
  }
```

Replace the `{expanded && (...)}` block at the end of `BriefRow` with:

```tsx
      {expanded && (
        <>
          {brief.editors.map((e) => (
            <EditorSubRow
              key={e.id}
              briefId={brief.id}
              editor={e}
              stages={stages}
              canMove={canAssign || e.id === viewerId}
            />
          ))}

          {canAssign && (
            <tr className="border-t border-border/50 bg-bg-secondary/20">
              <td colSpan={5} className="px-3 py-2 pl-12">
                <select
                  value=""
                  disabled={assigning}
                  onChange={(e) => {
                    if (e.target.value) assignEditor(e.target.value)
                    e.target.value = ''
                  }}
                  className="rounded-md border border-border bg-bg-secondary px-2 py-1 text-xs text-text-primary focus:outline-none focus:border-border-focus disabled:opacity-60 cursor-pointer"
                >
                  <option value="">Assign an editor…</option>
                  {owners
                    .filter((u) => !brief.editors.some((e) => e.id === u.id))
                    .map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.name || u.email}
                      </option>
                    ))}
                </select>
              </td>
            </tr>
          )}

          {assets.length === 0 ? (
            <tr className="border-t border-border/50 bg-bg-secondary/30">
              <td colSpan={5} className="px-3 py-2 pl-12 text-xs text-text-tertiary">
                Nothing submitted yet.
              </td>
            </tr>
          ) : (
            assets.map((a) => <AssetSubRow key={a.asset_id} asset={a} stages={stages} />)
          )}
        </>
      )}
```

- [ ] **Step 4: Show the editor count on the collapsed row**

In the chip `<span>` beside the Brief and Paid chips, add before the paid chip, and widen the surrounding `{(...) && (` condition to include `brief.editors.length > 0`:

```tsx
                  {brief.editors.length > 0 && (
                    <span className="inline-flex items-center gap-1 text-xs text-text-tertiary">
                      <UserRound className="h-3 w-3" />
                      {brief.editors.length}
                    </span>
                  )}
```

A brief with three editors should read as one without expanding it.

- [ ] **Step 5: Component tests for the permission logic**

Create `apps/web/components/tasks/__tests__/brief-row.test.tsx`, following the
conventions of the existing `apps/web/components/admin/__tests__/brief-overview-table.test.tsx`
(vitest + `@testing-library/react`, `vi.mock` for `@/lib/api`). `BriefRow` renders
`<tr>` elements, so render it inside a `<table><tbody>` wrapper.

`canMove={canAssign || e.id === viewerId}` is the frontend half of the rule
deciding who may move whose status, and the confirm-before-POST guard protects a
one-way action that provisions a project. Neither is covered anywhere else. Four
tests, each named for the consequence it guards:

1. A non-admin sees a live status control on their own editor row and read-only
   text on a co-editor's. Inverted, an editor could drive a request that 404s, or
   lose control of their own status.
2. An admin sees a live control on every editor row — the roll-up is what admins
   are for.
3. The "Assign an editor…" control renders for an admin and not for a non-admin.
   Assignment is not self-service.
4. Declining the confirm dialog issues no POST. Assignment cannot be undone, so a
   mis-click must not provision a project. Stub `window.confirm` to return false
   and assert the mocked `api.post` was never called.

- [ ] **Step 6: Typecheck and commit**

Run: `cd apps/web && ../../node_modules/.bin/tsc --noEmit`
Expected: exit 0, no output.

```bash
git add apps/web/types/index.ts apps/web/components/tasks/brief-row.tsx
git commit -m "Show each editor on a brief with the status they own"
```

---

### Task 9: The editor's own pipeline

An editor's board grouped by a status they cannot move is the confusion this whole change exists to fix.

**Files:**
- Modify: `apps/web/app/(dashboard)/tasks/page.tsx`
- Modify: `apps/web/components/tasks/pipeline-board.tsx`

**Interfaces:**
- Consumes: `BriefRow`'s `viewerId` prop (Task 8); `BriefEditor.task_stage_id`.
- Produces: `PipelineBoard` gains `viewerId?: string`.

- [ ] **Step 1: Thread the viewer through the page**

In `apps/web/app/(dashboard)/tasks/page.tsx`:

- On `<BriefRow ... />`, add `viewerId={user?.id}`.
- On `<PipelineBoard ... />`, add `viewerId={user?.id}`.
- Change the non-admin header description to:

```tsx
              : 'The briefs assigned to you. Move your own status as you work — the brief’s overall status stays with whoever owns it.'
```

- [ ] **Step 2: Group an editor's board by their own status**

In `apps/web/components/tasks/pipeline-board.tsx`, add `viewerId?: string` to `PipelineBoard`'s props, then add above `columns`:

```tsx
  // Which status a card sits in, and which one a drag writes. Admins work the
  // brief's overall status. An editor works their own — a board grouped by a
  // status they cannot move tells them nothing and lets them change nothing.
  // A non-admin who owns the brief but has no editor row of their own falls
  // back to the brief's status: they own it, so it is theirs to move.
  const ownRow = (b: BriefTaskItem) =>
    canManage ? undefined : b.editors.find((e) => e.id === viewerId)

  const stageOf = (b: BriefTaskItem) => {
    const own = ownRow(b)
    return own ? own.task_stage_id : b.task_stage_id
  }
```

Replace `inColumn` with:

```tsx
  const inColumn = (columnId: string) =>
    briefs.filter((b) =>
      columnId === UNASSIGNED ? stageOf(b) === null : stageOf(b) === columnId,
    )
```

Replace the body of `drop` after the `if (!current ...)` guard:

```tsx
    const current = briefs.find((b) => b.id === id)
    if (!current || stageOf(current) === target) return
    const own = ownRow(current)
    const url = own
      ? `/submission-links/${id}/editors/${own.id}/task-stage`
      : `/submission-links/${id}/task-stage`
    try {
      await api.patch(url, { task_stage_id: target })
      mutate(BOARD_KEY)
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Could not move that brief')
    }
```

- [ ] **Step 3: Show the editor count on the card**

In `BriefCard`, in the metadata row, before the file count:

```tsx
          {brief.editors.length > 1 && <span>{brief.editors.length} editors</span>}
```

- [ ] **Step 4: Component tests for the pipeline's two readings**

Add to `apps/web/components/tasks/__tests__/pipeline-board.test.tsx`, following the
same conventions. `stageOf` is the expression that decides which column a card
sits in and which endpoint a drag writes, and it means two different things for
the two audiences. Three tests:

1. An admin's card sits in the column matching the **brief's** status.
2. A non-admin's card sits in the column matching **their own** editor status, not
   the brief's. Make the two differ, or the test proves nothing.
3. A non-admin who owns the brief but has no editor row of their own falls back to
   the brief's status — they own it, so it is theirs to move.

- [ ] **Step 5: Typecheck**

Run: `cd apps/web && ../../node_modules/.bin/tsc --noEmit`
Expected: exit 0, no output.

- [ ] **Step 6: Commit**

```bash
git add "apps/web/app/(dashboard)/tasks/page.tsx" apps/web/components/tasks/pipeline-board.tsx apps/web/components/tasks/__tests__/pipeline-board.test.tsx
git commit -m "Group an editor's pipeline by the status they actually own"
```

---

### Task 10: Whole-branch verification

**Files:** none modified.

**Interfaces:**
- Consumes: everything above.
- Produces: a verification record, and an honest statement of what is not covered.

- [ ] **Step 1: Run the full Python suite and compare to baseline**

Run: `cd apps/api && uv run pytest -q 2>&1 | tail -5`

Expected: passed up by 20 new tests (Task 1: 7, Task 5: 8, Task 6: 1, Task 7: 4), failed unchanged at the repo's 16 pre-existing failures. Recount against the real totals rather than trusting this arithmetic. If the failed count rose, stop and fix; do not report the run as green.

- [ ] **Step 2: Typecheck and unit-test the web app**

Run: `cd apps/web && ../../node_modules/.bin/tsc --noEmit`
Expected: exit 0, no output. **Do not substitute `npx tsc`** — it fetches an
unrelated package, prints a joke banner and exits 0 without checking anything.

Run: `cd apps/web && npm test`
Expected: all vitest suites pass, including the new `brief-row` and
`pipeline-board` component tests. Record the counts.

- [ ] **Step 3: Verify the migration chain offline**

Run: `cd apps/api && uv run python -c "
import pathlib, re
revs = {}
for f in pathlib.Path('alembic/versions').glob('*.py'):
    t = f.read_text()
    r = re.search(r\"^revision: str = '([^']+)'\", t, re.M)
    d = re.search(r\"^down_revision[^=]*= '([^']+)'\", t, re.M)
    if r: revs[r.group(1)] = d.group(1) if d else None
children = {}
for r, d in revs.items(): children.setdefault(d, []).append(r)
forks = {d: c for d, c in children.items() if len(c) > 1}
print('forks:', forks or 'none')
print('heads:', [r for r in revs if r not in children])
"`
Expected: `forks: none` and exactly one head, `c7d8e9f0a1b2`.

- [ ] **Step 4: Verify the board scoping union by hand**

This is the one path with no automated coverage — it is raw SQL over two tables and the suite has no database. Against a running API (local stack or hetzmet):

1. As an admin, assign an editor to a brief they do not own (`POST /submission-links/{id}/editors`).
2. As that editor, `GET /task-board` — the brief must be present, and its `editors` array must contain exactly one entry, their own.
3. As a *different* editor on the same brief, `GET /task-board` — the brief must be present, and `editors` must again contain exactly one entry, theirs, not the first editor's.
4. As the brief's `assignee_id` owner (not an editor), `GET /task-board` — the brief must still be present. This is the regression the union exists to prevent.
5. As the admin, `POST` the *same* editor to the same brief a second time — it must return 200 and the brief must still show exactly one row for them. Idempotency is inherited from `_provision_submission_project` and the `uq_submissions_link_user` constraint rather than asserted in a test, because a mock session cannot enforce a unique constraint.

Record the five results. If step 3 shows two editors, stop: that is the isolation leak and it ships to every editor at once.

- [ ] **Step 5: Report**

State plainly: the test counts before and after, that the 16 failures are pre-existing, the four manual results from Step 4, and that the board scoping union has no automated test. Do not describe the branch as verified if Step 4 was not actually run.
