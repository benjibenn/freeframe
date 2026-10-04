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


def test_the_unassign_tool_says_it_refuses_once_files_exist():
    """An agent must know up front that uploaded work pins an editor in place."""
    d = (_tool("unassign_brief_editor").description or "").lower()
    assert "uploaded nothing" in d and "refuses" in d


# ── Reading editor stages in bulk ────────────────────────────────────────────
#
# Intent: "how many Mobilezhub briefs are unassigned or not in Review" must be
# one read. Before this, stages were only visible in the reply to a write.

import pytest
from unittest.mock import patch

from apps.api.tests.test_mcp_briefs import _listing, _row, as_admin  # noqa: F401


def _ed(name, stage=None, files=0):
    return {
        "id": str(uuid.uuid4()), "name": name, "email": f"{name}@x.com",
        "task_stage_id": None, "task_stage": stage, "file_count": files,
    }


@pytest.fixture
def stages():
    review, pending = uuid.uuid4(), uuid.uuid4()
    with patch.object(mcp_router, "_stage_rows", return_value=[(review, "Review"), (pending, "Pending")]):
        yield review


def _with_editors(rows, editors):
    return patch.object(mcp_router, "_editor_map", side_effect=lambda db, viewer, ids: {
        i: editors[i] for i in ids if i in editors
    })


def test_editor_filters_must_all_hold_for_the_same_editor(as_admin, stages):
    """"genesis in Review" must not match a brief where genesis is Pending and
    someone else is in Review — that would overcount genesis's finished work."""
    mixed, done = _row(title="mixed"), _row(title="done")
    eds = {
        mixed.id: [_ed("genesis", "Pending"), _ed("alex", "Review")],
        done.id: [_ed("genesis", "Review", files=2)],
    }
    with _listing([mixed, done]), _with_editors([mixed, done], eds):
        out = mcp_router.list_briefs(editor="Genesis", editor_stage="review")
    assert [b["title"] for b in out["briefs"]] == ["done"]


def test_list_briefs_shows_each_editors_stage_and_files(as_admin, stages):
    r = _row()
    with _listing([r]), _with_editors([r], {r.id: [_ed("honey", None, files=0)]}):
        out = mcp_router.list_briefs()
    assert out["briefs"][0]["editors"][0]["task_stage"] is None
    assert out["briefs"][0]["editors"][0]["file_count"] == 0


def test_count_by_editor_stage_counts_unassigned_and_unstaged_apart(as_admin, stages):
    """Unassigned and assigned-but-never-moved are different work: one needs an
    editor, the other needs chasing. Merging them hides which."""
    a, b, c = _row(), _row(), _row()
    eds = {a.id: [_ed("genesis", "Review")], b.id: [_ed("honey")]}
    with _listing([a, b, c]), _with_editors([a, b, c], eds):
        out = mcp_router.count_briefs(group_by="editor_stage")
    got = {g["key"]: g["count"] for g in out["groups"]}
    assert got == {"Review": 1, mcp_router._NO_STAGE: 1, mcp_router._UNASSIGNED: 1}


def test_has_files_false_finds_assigned_editors_with_nothing_uploaded(as_admin, stages):
    a, b = _row(title="empty"), _row(title="delivered")
    eds = {a.id: [_ed("honey", files=0)], b.id: [_ed("honey", files=3)]}
    with _listing([a, b]), _with_editors([a, b], eds):
        out = mcp_router.count_briefs(has_files=False)
    assert out["total"] == 1


def test_an_unknown_stage_name_lists_the_real_ones(as_admin, stages):
    with _listing([_row()]):
        with pytest.raises(ValueError, match="Review, Pending"):
            mcp_router.count_briefs(editor_stage="Reviewed")


def test_get_brief_editors_is_registered_and_says_it_is_read_only():
    assert "read-only" in (_tool("get_brief_editors").description or "").lower()
