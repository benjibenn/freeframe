# Many editors per brief, each with their own status

Date: 2026-09-28

Today a brief can be worked on by one editor: `submission_links.assignee_id` is
a single nullable user FK, and `/task-board` shows a non-admin only the briefs
where that column points at them. Assign a brief to a second editor and the
first one loses it.

This change makes assignment many-to-many and gives every editor their own
status, while the brief keeps a status of its own.

## The two statuses

- **Brief status** — `submission_links.task_stage_id`. Unchanged. The overall
  state of the work item, owned by whoever the brief sits with.
- **Editor status** — new, `submissions.task_stage_id`. One per (brief, editor)
  pair. Editor A can be "In Progress" while Editor B is "Delivered".

Both read the same `task_stages` rows, so a stage name means one thing wherever
it appears — the rule the asset-level stage already follows.

Brief status is **manual**. It is not derived from the editor statuses; a rule
for collapsing several editors' states into one would be a guess.

## Assignment is a `submissions` row

`submissions` is already one row per (brief, editor), unique-constrained on
`(submission_link_id, user_id)`, and already carries per-editor state
(`paid_at`). Per-editor status is the second fact about that pair, so it lives
on the same row and needs no new table.

Two paths create the row, and they are the same row:

- An editor accepts the token link (`POST /submission-links/{token}/accept`).
- An admin assigns them (new endpoint below), which calls the same
  `_provision_submission_project` helper.

So an editor who accepted a link in the past **is** assigned, and those briefs
appear on their task page from the day this ships. That is intended.

`assignee_id` survives untouched, with its current meaning: the internal owner,
whose desk the brief sits on. Editors are who is making it.

### Assignment cannot be undone

There is no unassign endpoint. A `submissions` row owns a private project with
the editor's uploads in it; removing the row would orphan them. Assigning is
therefore a deliberate, one-way act — both the web control and the MCP tool say
so before doing it.

## 1. Migration

`apps/api/alembic/versions/c7d8e9f0a1b2_add_task_stage_to_submissions.py`,
`down_revision = 'b6c7d8e9f0a1'` (current head).

```python
op.add_column('submissions', sa.Column('task_stage_id', postgresql.UUID(as_uuid=True), nullable=True))
op.create_foreign_key('fk_submissions_task_stage', 'submissions', 'task_stages', ['task_stage_id'], ['id'])
op.create_index('ix_submissions_task_stage_id', 'submissions', ['task_stage_id'])
```

Downgrade drops index, FK, column. No backfill: null means "no status yet",
which is the state every existing assignment is actually in.

## 2. Model

`apps/api/models/submission.py` — on `Submission`, beside `paid_at`:

```python
# This editor's own status on this brief. Same task_stages table as the brief
# and the assets use, so a stage name means one thing everywhere. Null = not
# started. Distinct from SubmissionLink.task_stage_id, which is the brief's
# overall state: two editors can be at different points on one brief.
task_stage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
    UUID(as_uuid=True), ForeignKey("task_stages.id"), nullable=True, index=True
)
```

## 3. Schemas

`apps/api/schemas/task_stage.py`:

- `BriefEditor` gains `task_stage_id: Optional[uuid.UUID] = None`, and its
  docstring changes from "accepted the request" to "assigned to the request —
  by accepting the link or by an admin".
- New:
  ```python
  class BriefEditorAssign(BaseModel):
      """The editor to put on this brief. One-way: see the router."""
      user_id: uuid.UUID
  ```
- The editor-stage PATCH reuses the existing `TaskStageAssign`.

## 4. API — `apps/api/routers/tasks.py`

### `get_task_board` scoping (line ~330)

A non-admin's `owned_link_ids` becomes the **union** of briefs they own and
briefs they are assigned to:

```python
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
```

The union, rather than a replacement, so an internal owner who is not an editor
does not lose the briefs they can see today.

### Editors carry their stage, and non-admins see only themselves

The `editors_by_link` query (line ~388) selects `Submission.task_stage_id` too
and puts it on each `BriefEditor`. For a non-admin, the loop keeps only rows
where `Submission.user_id == current_user.id`.

Withholding co-editors is not a UI nicety: per-submitter isolation is what
submission links exist for, and the response body would otherwise hand every
editor the names and progress of everyone else on the brief.

`_brief_item` (line ~605) takes a new `viewer: User` argument and applies the
same rule, so the row a PATCH returns matches the row the board would have sent.
Its two existing call sites — `set_brief_task_stage` (line 577) and
`set_brief_assignee` (line 602) — pass `current_user`.

### `POST /submission-links/{link_id}/editors` → `BriefTaskItem`

Platform-admin only (`require_platform_admin`). Body `BriefEditorAssign`.

- 404 if the link is missing or soft-deleted; 404 if the user does not exist.
- Calls `_provision_submission_project(db, link, user)` — imported inside the
  function, matching the local-import style already used in this file — so the
  editor gets their private upload project in the same request. The helper is
  idempotent, so assigning someone twice returns their existing project and does
  not create a second row.
- Commits, returns `_brief_item(db, link, current_user)`.

### `PATCH /submission-links/{link_id}/editors/{user_id}/task-stage` → `BriefTaskItem`

Body `TaskStageAssign` (null clears the status).

- An admin may move any editor's status.
- A non-admin may move **only their own** (`user_id == current_user.id`), and
  only if they have a `submissions` row on this link. Anything else is 404, not
  403 — a non-participant should not learn the brief exists.
- The stage id is validated through the existing `_get_stage`.
- Sets `submission.task_stage_id` only. The brief's own stage is untouched: that
  is the whole point of having both.

### `delete_task_stage` (line ~140)

Already detaches assets sitting in the stage; must now also detach submissions,
or a soft-deleted stage keeps rendering as a status that is not in the list:

```python
db.query(Submission).filter(Submission.task_stage_id == stage.id).update(
    {Submission.task_stage_id: None}, synchronize_session=False
)
```

Out of scope: the same function does not detach `submission_links.task_stage_id`
either. That gap predates this change and is left alone.

## 5. MCP — `apps/api/routers/mcp.py`

- `_brief_task_summary` (line ~1225) gains
  `"editors": [{"id", "name", "email", "task_stage_id"}]`, so an agent can read
  who is on a brief and where each of them is.
- New `assign_brief_editor(link_id, user_id)`. Description states that it
  provisions the editor's private upload folder and **cannot be undone**, and
  that it is distinct from `assign_brief_owner` (the desk it sits on).
- New `set_brief_editor_stage(link_id, user_id, task_stage_id)`. Description
  points at `list_task_stages` for a real stage id and states that admins may
  move any editor, anyone else only themselves.
- `assign_brief_owner`'s description drops "which is derived and not settable
  here" — editors are settable now, via `assign_brief_editor`.

## 6. Web

`apps/web/types/index.ts` — `BriefEditor` gains `task_stage_id: string | null`.

`apps/web/components/tasks/brief-row.tsx`:

- New `viewerId?: string` prop, threaded from the page (which already holds
  `user`), so a row knows which editor sub-row belongs to the reader.
- New `EditorSubRow`: the editor's name indented in column 1, "Editor" in the
  submitter column, and a `StagePicker` in the status column writing to
  `PATCH /submission-links/{id}/editors/{user_id}/task-stage`. Enabled when the
  reader is an admin or it is their own row; read-only text otherwise.
- The expanded region renders editor sub-rows first, then the asset sub-rows.
  Who is working on it comes before what they have delivered.
- Admins get an "Assign editor" select in the expanded region, populated from
  the `owners` list the row already receives (`/users/assignable`). Because
  assignment is one-way, it asks for confirmation before the POST.
- The collapsed row shows an editor count beside the existing brief/paid chips,
  so a brief with three editors reads as one without expanding.

`apps/web/app/(dashboard)/tasks/page.tsx`:

- Passes `viewerId={user?.id}` to `BriefRow` and `PipelineBoard`.
- The non-admin header line changes to name the two statuses: the brief's, and
  their own.

`apps/web/components/tasks/pipeline-board.tsx`:

- Admins: unchanged — columns group by brief status, drag writes the brief
  endpoint.
- Non-admins: columns group by the reader's **own** editor status
  (`brief.editors[0]?.task_stage_id`, which is the only row a non-admin's
  response carries), and drag writes the editor endpoint. Grouping an editor's
  board by a status they do not control is the confusion this change exists to
  fix.
- A non-admin who is the brief's owner but has no editor row of their own falls
  back to the admin behaviour: brief status, brief endpoint. They own it, so
  they can move it.

## 7. Tests

New `apps/api/tests/test_brief_editor_tasks.py`. Each test names the intent, not
the mechanics:

1. Assigning an editor provisions their private project and puts the brief on
   their board.
2. Assigning the same editor twice is idempotent — one `submissions` row, same
   project.
3. An editor sees only their own editor row, never a co-editor's name or status.
4. An editor can move their own status.
5. An editor cannot move a co-editor's status.
6. An admin can move any editor's status.
7. Moving an editor's status leaves the brief's own status alone — the two are
   separate on purpose.
8. A non-admin cannot assign an editor.
9. Soft-deleting a stage detaches the submissions sitting in it.

Existing `apps/api/tests/test_brief_overview.py` and `test_mcp_briefs.py` cover
`/task-board` and the brief MCP tools and must keep passing unchanged: the
brief-level contract does not move.

## Out of scope

- Deriving brief status from editor statuses.
- Unassigning an editor.
- Letting an editor move the brief-level status (an editor who is also
  `assignee_id` can already, and that is not changing).
- `submission_links.assignee_id` remains single. Internal ownership is one desk.
