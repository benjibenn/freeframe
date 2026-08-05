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
    BriefJsonUpdate,
    BulkRefileRequest,
    DuplicateLinkRequest,
    SubmissionLinkCreate,
)
from . import folders as folders_router
from . import projects as projects_router
from . import submissions as submissions_router

# Set by the ASGI wrapper below, read by the tools. Safe because a stateless
# streamable-HTTP request is handled start-to-finish in one task.
#
# The session is request-scoped and shared with the tools on purpose. Resolving
# the key stamps `last_used_at` and commits, which expires the User; if that
# session were then closed, the User would be detached and the first lazy
# attribute read inside a tool would raise DetachedInstanceError. One session per
# request — the same shape as `get_db` on the REST routes — keeps it live.
_current_user: ContextVar[Optional[User]] = ContextVar("mcp_current_user", default=None)
_current_db: ContextVar[Optional[Session]] = ContextVar("mcp_current_db", default=None)

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


# brief_json is stored free-form and rendered defensively — only sections the
# tenant's brief template knows about are displayed. An agent inventing its own
# key names produces a brief that saves cleanly and then shows nothing, so the
# tools advertise the shape the rest of the product already uses (the same one
# apps/web/lib/sample-brief.ts seeds every surface with).
_BRIEF_SHAPE = (
    "Free-form object. Use these keys so it renders: "
    '"title" (str), "overview" (str), "output_languages" (list of str), '
    '"final_deliverable" {"label": str, "hook_variations": [{"variation", '
    '"script_voiceover", "shot", "on_screen_text"}]}, "guidelines" (list of str). '
    "Extra keys are stored but only display if the tenant's brief template "
    "renders them."
)


def _brief(value: Any, field: str = "brief_json") -> dict[str, Any]:
    """Validate a structured brief before anything is written.

    Checked up front rather than left to the endpoint so create_brief can fail
    before it creates a request — a rejected brief must not leave an empty
    request behind with a live submit URL.
    """
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be a JSON object, got {type(value).__name__}")
    if not value:
        raise ValueError(f"{field} must not be empty — pass null to clear a brief instead")
    return value


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
    """Run a route function on this request's session, translating its HTTP errors.

    Uses the session the auth wrapper opened rather than a fresh one: the
    authenticated User is attached to it, and a second session would leave that
    User detached.

    An HTTPException escaping into the transport becomes an opaque failure the
    agent cannot act on. "Not a member of that project" is actionable; a 500 is not.
    The rollback matters because one MCP request may carry several tool calls — a
    failed one must not leave a poisoned transaction for the next.
    """
    db = _current_db.get()
    if db is None:
        raise ValueError("No database session on this MCP request")
    try:
        return fn(db=db, current_user=_user(), **kwargs)
    except HTTPException as exc:
        db.rollback()
        raise ValueError(str(exc.detail)) from exc


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


@mcp.tool(
    description=(
        "Read one brief in full, including its structured brief_json. list_briefs "
        "omits brief_json to keep listings small, so fetch a brief here before "
        "editing it. Also reports whether a brief PDF and reference media are "
        "attached; their contents are not exposed over MCP."
    )
)
def get_brief(link_id: str) -> dict[str, Any]:
    """Args: link_id — the brief to read."""
    link = _call(
        submissions_router.get_submission_link, link_id=_uuid(link_id, "link_id")
    )
    out = _brief_summary(link)
    out["instructions"] = link.instructions
    out["brief_json"] = link.brief_json
    out["has_brief_json"] = link.has_brief_json
    # Flagged, not returned: the PDF and reference media live in S3 and no MCP
    # tool serves them. Saying so beats an agent concluding the brief is empty.
    out["has_brief_pdf"] = link.has_brief
    out["reference_video_count"] = link.reference_video_count
    out["reference_image_count"] = link.reference_image_count
    return out


@mcp.tool(
    description=(
        "Set or replace the structured brief on an existing request. This "
        "REPLACES the whole object rather than merging — call get_brief first and "
        "send the full brief back with your edits. Pass null to remove the brief. "
        "Independent of the brief PDF; a request may carry both. brief_json: "
        + _BRIEF_SHAPE
    )
)
def set_brief_json(link_id: str, brief_json: dict[str, Any] | None) -> dict[str, Any]:
    """Args: brief_json — the complete brief object, or null to clear it."""
    updated = _call(
        submissions_router.set_submission_brief_json,
        link_id=_uuid(link_id, "link_id"),
        body=BriefJsonUpdate(brief=_brief(brief_json) if brief_json is not None else None),
    )
    out = _brief_summary(updated)
    out["brief_json"] = updated.brief_json
    out["has_brief_json"] = updated.has_brief_json
    return out


# ── Lifecycle ────────────────────────────────────────────────────────────────

@mcp.tool(
    description=(
        "Create a new video request brief and return its public submit URL. "
        "home_project_id is required — get one from list_destinations. Omit "
        "home_folder_id to file the brief at the project root. Pass brief_json "
        "to attach the structured brief in the same call. brief_json: " + _BRIEF_SHAPE
    )
)
def create_brief(
    title: str,
    home_project_id: str,
    home_folder_id: str | None = None,
    instructions: str | None = None,
    expires_at: str | None = None,
    brief_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Args: expires_at — optional ISO 8601 timestamp after which the link stops accepting work."""
    # Validated before the request exists. The underlying API has no way to create
    # a request and attach a brief in one write, so a brief rejected afterwards
    # would strand an empty request with a live submit URL.
    checked = _brief(brief_json) if brief_json is not None else None

    body = SubmissionLinkCreate(
        title=title,
        instructions=instructions,
        home_project_id=_uuid(home_project_id, "home_project_id"),
        home_folder_id=_uuid(home_folder_id, "home_folder_id") if home_folder_id else None,
        expires_at=datetime.fromisoformat(expires_at) if expires_at else None,
    )
    created = _call(submissions_router.create_submission_link, body=body)
    if checked is None:
        return _brief_summary(created)

    try:
        attached = _call(
            submissions_router.set_submission_brief_json,
            link_id=created.id,
            body=BriefJsonUpdate(brief=checked),
        )
    except Exception:
        # Belt and braces after the validation above: rather than leave a live
        # request the caller did not get told about, retract it and re-raise.
        _call(submissions_router.disable_submission_link, link_id=created.id)
        raise

    out = _brief_summary(attached)
    out["has_brief_json"] = True
    return out


@mcp.tool(
    description=(
        "Duplicate an existing brief. Anything not overridden is copied from the "
        "source, including its brief PDF, structured brief and reference media. "
        "Submissions are NOT copied — the duplicate starts accepting fresh work. "
        "Returns the new brief with its own submit URL; the original is untouched. "
        "Pass brief_json to give the copy a different structured brief: " + _BRIEF_SHAPE
    )
)
def duplicate_brief(
    link_id: str,
    title: str | None = None,
    home_project_id: str | None = None,
    home_folder_id: str | None = None,
    instructions: str | None = None,
    brief_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Args: link_id — the brief to copy. Omitted overrides fall back to the source's values."""
    body = DuplicateLinkRequest(
        title=title,
        instructions=instructions,
        home_project_id=_uuid(home_project_id, "home_project_id") if home_project_id else None,
        # The endpoint only applies a folder when a project came with it, so
        # sending one alone would be silently dropped. Say so instead.
        home_folder_id=_uuid(home_folder_id, "home_folder_id") if home_folder_id else None,
        # Straight passthrough — the duplicate endpoint takes this natively, so
        # unlike create there is no second write and nothing to unwind.
        brief_json=_brief(brief_json) if brief_json is not None else None,
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
        db.close()
        await _send_json_error(send, exc.status_code, str(exc.detail))
        return

    # The session stays open for the whole request so `user` remains attached to it.
    user_token = _current_user.set(user)
    db_token = _current_db.set(db)
    try:
        await _inner_app(scope, receive, send)
    finally:
        _current_user.reset(user_token)
        _current_db.reset(db_token)
        db.close()


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
