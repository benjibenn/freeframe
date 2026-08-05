"""MCP server exposing brief lifecycle actions to AI clients.

Mounted at /mcp. An MCP client (Claude Code, Claude Desktop, anything speaking
streamable HTTP) authenticates with the same `ffpk_` API key the admin UI already
mints, sent as `X-API-Key`.

The tools are thin: each one resolves the key to a `User` and then calls the very
same function the REST route calls, passing that user as `current_user`. Ownership,
destination validation and path stamping therefore stay in `submissions.py` — this
module owns argument marshalling and nothing else. A rule enforced here as well as
there is a rule that will eventually disagree with itself.

Stateless by design: `stateless_http=True` means every request carries its own auth
and completes in its own task, so the resolved user propagates cleanly through a
ContextVar and the app stays safe to run behind more than one worker.
"""
import uuid
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Optional

from fastapi import HTTPException
from mcp.server.fastmcp import FastMCP
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from ..middleware.api_key import resolve_api_key_user
from ..models.user import User
from ..schemas.submission import (
    BulkRefileRequest,
    DuplicateLinkRequest,
    SubmissionLinkCreate,
)
from . import folders as folders_router
from . import projects as projects_router
from . import submissions as submissions_router

# Set by the ASGI wrapper below, read by the tools. Safe because a stateless
# streamable-HTTP request is handled start-to-finish in one task.
_current_user: ContextVar[Optional[User]] = ContextVar("mcp_current_user", default=None)

mcp = FastMCP(
    name="freeframe",
    instructions=(
        "Manage Freeframe video request briefs. A brief is a token-gated request "
        "that editors submit work against. Call list_destinations before creating "
        "or moving a brief — both need a real project id, which cannot be guessed."
    ),
    stateless_http=True,
    json_response=True,
    # The app is mounted under /mcp, so the transport's own path is the mount root.
    # Leaving the default here would serve the endpoint at /mcp/mcp.
    streamable_http_path="/",
)


def _user() -> User:
    user = _current_user.get()
    if user is None:
        # Only reachable if the transport is wired up without the auth wrapper.
        raise ValueError("No authenticated user on this MCP request")
    return user


def _uuid(value: str, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise ValueError(f"{field} must be a UUID, got {value!r}")


def _submit_url(token: str) -> str:
    return f"{settings.frontend_url}/submit/{token}"


def _brief_summary(link: Any) -> dict[str, Any]:
    """The fields an agent can act on, not the whole response model.

    Reference counts and brief flags are omitted deliberately: they are not inputs
    to any tool here, and a wide payload per brief burns the caller's context on a
    list of fifty.
    """
    return {
        "id": str(link.id),
        "title": link.title,
        "home_project_id": str(link.home_project_id) if link.home_project_id else None,
        "home_folder_id": str(link.home_folder_id) if link.home_folder_id else None,
        "home_path": link.home_path,
        "submission_count": link.submission_count,
        "is_enabled": link.is_enabled,
        "submit_url": _submit_url(link.token),
        "created_at": link.created_at.isoformat() if link.created_at else None,
    }


def _call(fn, **kwargs) -> Any:
    """Run a route function against a fresh session, translating its HTTP errors.

    An HTTPException escaping into the transport becomes an opaque failure the
    agent cannot act on. "Not a member of that project" is actionable; a 500 is not.
    """
    db: Session = SessionLocal()
    try:
        return fn(db=db, current_user=_user(), **kwargs)
    except HTTPException as exc:
        raise ValueError(str(exc.detail)) from exc
    finally:
        db.close()


# ── Discovery ────────────────────────────────────────────────────────────────

@mcp.tool(
    description=(
        "List video request briefs. Returns each brief's id, title, where it is "
        "filed, how many submissions it has received, and its public submit URL."
    )
)
def list_briefs(project_id: str | None = None) -> list[dict[str, Any]]:
    """Args: project_id — optional; only briefs filed in this project."""
    links = _call(submissions_router.list_submission_links)
    out = [_brief_summary(l) for l in links]
    if project_id:
        wanted = str(_uuid(project_id, "project_id"))
        out = [b for b in out if b["home_project_id"] == wanted]
    return out


@mcp.tool(
    description=(
        "List the projects and folders a brief can be filed into. Call this first: "
        "create_brief and move_brief both need a real project id. Omit project_id "
        "to list projects only; pass one to get that project's folder tree."
    )
)
def list_destinations(project_id: str | None = None) -> dict[str, Any]:
    """Args: project_id — optional; when given, also returns that project's folders."""
    if project_id is None:
        projects = _call(projects_router.list_projects)
        return {
            "projects": [
                {"id": str(p.id), "name": p.name, "description": p.description}
                for p in projects
            ]
        }

    pid = _uuid(project_id, "project_id")
    tree = _call(folders_router.get_folder_tree, project_id=pid)

    def flatten(nodes, prefix="") -> list[dict[str, Any]]:
        # Flat paths, not a nested tree: an agent picking a destination wants to
        # match "ecom/Phones", and reassembling that from nested JSON is a step
        # it can get wrong for no benefit.
        rows = []
        for node in nodes:
            path = f"{prefix}/{node.name}" if prefix else node.name
            rows.append({"id": str(node.id), "path": path})
            rows.extend(flatten(node.children, path))
        return rows

    return {"project_id": project_id, "folders": flatten(tree)}


# ── Lifecycle ────────────────────────────────────────────────────────────────

@mcp.tool(
    description=(
        "Create a new video request brief and return its public submit URL. "
        "home_project_id is required — get one from list_destinations. Omit "
        "home_folder_id to file the brief at the project root."
    )
)
def create_brief(
    title: str,
    home_project_id: str,
    home_folder_id: str | None = None,
    instructions: str | None = None,
    expires_at: str | None = None,
) -> dict[str, Any]:
    """Args: expires_at — optional ISO 8601 timestamp after which the link stops accepting work."""
    body = SubmissionLinkCreate(
        title=title,
        instructions=instructions,
        home_project_id=_uuid(home_project_id, "home_project_id"),
        home_folder_id=_uuid(home_folder_id, "home_folder_id") if home_folder_id else None,
        expires_at=datetime.fromisoformat(expires_at) if expires_at else None,
    )
    return _brief_summary(_call(submissions_router.create_submission_link, body=body))


@mcp.tool(
    description=(
        "Duplicate an existing brief. Anything not overridden is copied from the "
        "source, including its brief PDF and reference media. Submissions are NOT "
        "copied — the duplicate starts accepting fresh work. Returns the new brief "
        "with its own submit URL; the original is untouched."
    )
)
def duplicate_brief(
    link_id: str,
    title: str | None = None,
    home_project_id: str | None = None,
    home_folder_id: str | None = None,
    instructions: str | None = None,
) -> dict[str, Any]:
    """Args: link_id — the brief to copy. Omitted overrides fall back to the source's values."""
    body = DuplicateLinkRequest(
        title=title,
        instructions=instructions,
        home_project_id=_uuid(home_project_id, "home_project_id") if home_project_id else None,
        # The endpoint only applies a folder when a project came with it, so
        # sending one alone would be silently dropped. Say so instead.
        home_folder_id=_uuid(home_folder_id, "home_folder_id") if home_folder_id else None,
    )
    if home_folder_id and not home_project_id:
        raise ValueError("home_folder_id needs home_project_id — a folder is meaningless without its project")
    return _brief_summary(
        _call(
            submissions_router.duplicate_submission_link,
            link_id=_uuid(link_id, "link_id"),
            body=body,
        )
    )


@mcp.tool(
    description=(
        "Re-file one or more briefs into a different project or folder. "
        "IMPORTANT: this only affects work submitted from here on. Assets already "
        "uploaded keep the path they were stamped with at upload time and do not "
        "move. Omit home_folder_id to file at the project root."
    )
)
def move_brief(
    link_ids: list[str],
    home_project_id: str,
    home_folder_id: str | None = None,
) -> dict[str, Any]:
    """Args: link_ids — one or more brief ids; all are moved to the same destination."""
    if not link_ids:
        raise ValueError("link_ids must contain at least one brief id")
    body = BulkRefileRequest(
        link_ids=[_uuid(i, "link_ids") for i in link_ids],
        home_project_id=_uuid(home_project_id, "home_project_id"),
        home_folder_id=_uuid(home_folder_id, "home_folder_id") if home_folder_id else None,
    )
    result = _call(submissions_router.bulk_refile_submission_links, body=body)
    # `updated` can be lower than len(link_ids) — ids that are already deleted are
    # skipped rather than failing the batch. Report the number, don't imply all moved.
    return {
        "moved": result.updated,
        "requested": len(link_ids),
        "note": "Already-uploaded assets keep their original stamped path.",
    }


# ── ASGI ─────────────────────────────────────────────────────────────────────

_inner_app = mcp.streamable_http_app()


async def mcp_app(scope, receive, send):
    """Authenticate, then hand off to the MCP transport.

    Written as raw ASGI rather than BaseHTTPMiddleware so the streaming response
    body passes through untouched.
    """
    if scope["type"] != "http":
        await _inner_app(scope, receive, send)
        return

    headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
    db: Session = SessionLocal()
    try:
        user = resolve_api_key_user(db, headers.get("x-api-key"))
    except HTTPException as exc:
        await _send_json_error(send, exc.status_code, str(exc.detail))
        return
    finally:
        db.close()

    token = _current_user.set(user)
    try:
        await _inner_app(scope, receive, send)
    finally:
        _current_user.reset(token)


async def _send_json_error(send, status_code: int, detail: str) -> None:
    import json

    body = json.dumps({"error": detail}).encode()
    await send({
        "type": "http.response.start",
        "status": status_code,
        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
    })
    await send({"type": "http.response.body", "body": body})


def session_manager():
    """The transport's session manager, which the parent app's lifespan must run.

    Starlette does not run a mounted sub-app's lifespan, and the MCP app puts its
    session manager there — so without this the mount accepts requests and then
    fails on the first one.
    """
    return mcp.session_manager
