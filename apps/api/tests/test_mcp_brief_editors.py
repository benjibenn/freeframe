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
