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
from ..services import mcp_oauth
from ..services.mcp_oauth import SCOPE_READ, SCOPE_WRITE
from ..models.user import User
from ..schemas.submission import (
    BriefJsonUpdate,
    BulkDeleteRequest,
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
# Scopes the caller holds. API keys are unscoped and get everything, preserving
# today's behaviour; OAuth tokens carry whatever the issuer granted.
_current_scopes: ContextVar[Optional[list[str]]] = ContextVar("mcp_current_scopes", default=None)


def _require_scope(scope: str) -> None:
    """Enforce a scope, treating "unscoped" as full access.

    An API key has no scopes and must keep working exactly as before — so None
    means "not scope-limited", which is different from an empty list (a token that
    was granted nothing).
    """
    held = _current_scopes.get()
    if held is None:
        return
    if scope not in held:
        raise ValueError(
            f"This token is missing the {scope} scope; it holds {held or 'no scopes'}"
        )

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
    _require_scope(SCOPE_READ)
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
    _require_scope(SCOPE_READ)
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
    _require_scope(SCOPE_READ)
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
        "Attach a reference image or video to a brief by URL. The server fetches "
        "the URL itself, so it must be publicly reachable — a local file path will "
        "not work, and neither will a private or internal address. Use this for the "
        "'adapt this ad' examples shown on the brief page. kind defaults to auto, "
        "which picks image or video from what the URL actually serves. Images up to "
        "15 MB (JPEG, PNG, WebP, GIF), videos up to 50 MB; larger videos have to go "
        "through the web UI. At most 10 of each per brief. Signed URLs work but must "
        "still be valid at the moment of the call."
    )
)
def add_brief_reference(link_id: str, url: str, kind: str = "auto") -> dict[str, Any]:
    """Args: url — a public http(s) URL; kind — auto, image or video."""
    _require_scope(SCOPE_WRITE)
    wanted = (kind or "auto").strip().lower()
    if wanted not in ("auto", "image", "video"):
        raise ValueError(f"kind must be auto, image or video, got {kind!r}")

    link_uuid = _uuid(link_id, "link_id")
    body = submissions_router.ReferenceFromUrlRequest(url=url)

    # "auto" tries image first and falls back to video, because the image route
    # rejects on content type before storing anything — so a video URL costs one
    # wasted fetch, never a wrong attachment.
    attempts = ["image", "video"] if wanted == "auto" else [wanted]
    last_error: Optional[str] = None
    for attempt in attempts:
        fn = (
            submissions_router.add_reference_image_from_url
            if attempt == "image"
            else submissions_router.add_reference_video_from_url
        )
        try:
            updated = _call(fn, link_id=link_uuid, body=body)
        except ValueError as exc:
            last_error = str(exc)
            continue
        out = _brief_summary(updated)
        out["attached"] = attempt
        out["reference_image_count"] = updated.reference_image_count
        out["reference_video_count"] = updated.reference_video_count
        return out

    raise ValueError(last_error or "Could not attach that URL")


@mcp.tool(
    description=(
        "Submit finished work against a brief — the deliverable an editor would "
        "upload, not an 'adapt this' example (that is add_brief_reference). The "
        "server fetches the URL itself, so it must be publicly reachable; a local "
        "path or private address will not work. Signed URLs work but must still be "
        "valid at the moment of the call. Images and videos up to 200 MB; anything "
        "larger has to go through the web UI. When the brief prescribes deliverable "
        "names (its hook_variations), asset_name must be exactly one of them — "
        "call get_brief first to read them. Submitting the same name twice adds a "
        "new version to that deliverable rather than a second one beside it."
    )
)
def submit_work(link_id: str, url: str, asset_name: Optional[str] = None) -> dict[str, Any]:
    """Args: url — a public http(s) URL; asset_name — which deliverable this is."""
    _require_scope(SCOPE_WRITE)
    link_uuid = _uuid(link_id, "link_id")
    body = submissions_router.SubmitWorkFromUrlRequest(url=url, asset_name=asset_name)
    result = _call(submissions_router.submit_work_from_url, link_id=link_uuid, body=body)
    return {
        "submission_project_id": str(result.submission_project_id),
        "asset_id": str(result.asset_id),
        "asset_name": result.asset_name,
        "version_number": result.version_number,
        "status": result.status,
    }


@mcp.tool(
    description=(
        "Detach reference media from a brief. Pass an index to remove one item "
        "(0-based, in the order get_brief reports them), or omit it to remove every "
        "reference of that kind. The stored file is deleted; submissions and their "
        "uploaded work are untouched. There is no undo."
    )
)
def remove_brief_reference(
    link_id: str, kind: str, index: Optional[int] = None
) -> dict[str, Any]:
    """Args: kind — image or video; index — which one, or omit for all of that kind."""
    _require_scope(SCOPE_WRITE)
    wanted = (kind or "").strip().lower()
    if wanted not in ("image", "video"):
        raise ValueError(f"kind must be image or video, got {kind!r}")

    link_uuid = _uuid(link_id, "link_id")
    if index is None:
        fn = (
            submissions_router.delete_reference_images
            if wanted == "image"
            else submissions_router.delete_reference_videos
        )
        _call(fn, link_id=link_uuid)
        removed = "all"
    else:
        if index < 0:
            raise ValueError("index must be 0 or greater")
        fn = (
            submissions_router.delete_reference_image_at
            if wanted == "image"
            else submissions_router.delete_reference_video_at
        )
        _call(fn, link_id=link_uuid, index=index)
        removed = str(index)

    # The delete routes return 204, so re-read to report the resulting state
    # rather than asserting a count we did not observe.
    link = _call(submissions_router.get_submission_link, link_id=link_uuid)
    return {
        "id": str(link.id),
        "kind": wanted,
        "removed": removed,
        "reference_image_count": link.reference_image_count,
        "reference_video_count": link.reference_video_count,
    }


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
    _require_scope(SCOPE_WRITE)
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
    _require_scope(SCOPE_WRITE)
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
    _require_scope(SCOPE_WRITE)
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
        "Edit a brief in place: rename it, change its instructions, re-file it, or "
        "change when it expires. Only the fields you pass change — everything else "
        "is read off the brief and sent back unchanged, so a rename cannot quietly "
        "blank the instructions or unfile the brief. Pass an empty string to clear "
        "instructions or expiry. Naming a new home_project_id without a "
        "home_folder_id files the brief at that project's root, because a folder "
        "belongs to one project and cannot follow it. The structured brief is not "
        "touched here — use set_brief_json for that."
    )
)
def update_brief(
    link_id: str,
    title: str | None = None,
    instructions: str | None = None,
    home_project_id: str | None = None,
    home_folder_id: str | None = None,
    expires_at: str | None = None,
) -> dict[str, Any]:
    """Args: link_id — the brief to edit. Omitted fields keep their current value.

    expires_at is an ISO 8601 timestamp; "" removes the expiry entirely.
    """
    _require_scope(SCOPE_WRITE)
    uid = _uuid(link_id, "link_id")
    # Read-merge-write, and not for tidiness: the endpoint behind this assigns
    # every field of the record from the body it is given. Sending a title on its
    # own would null the instructions and strip the brief out of the tree.
    current = _call(submissions_router.get_submission_link, link_id=uid)

    # A folder lives inside exactly one project, so it cannot follow a brief into
    # a different one — moving project without naming a folder lands at the root.
    if home_project_id:
        project = _uuid(home_project_id, "home_project_id")
        folder = _uuid(home_folder_id, "home_folder_id") if home_folder_id else None
    else:
        project = current.home_project_id
        folder = (
            _uuid(home_folder_id, "home_folder_id")
            if home_folder_id
            else current.home_folder_id
        )

    if project is None:
        # Legacy links can be filed nowhere. Pydantic would reject that below with
        # a message about a missing field, which reads like a bug in the tool.
        raise ValueError(
            "This brief is not filed under any project — pass home_project_id to give it one"
        )

    if expires_at is None:
        expiry = current.expires_at
    else:
        expiry = datetime.fromisoformat(expires_at) if expires_at else None

    body = SubmissionLinkCreate(
        title=title if title is not None else current.title,
        # "" is how a caller says "remove this", which is not the same as omitting it.
        instructions=current.instructions if instructions is None else (instructions or None),
        home_project_id=project,
        home_folder_id=folder,
        expires_at=expiry,
    )
    return _brief_summary(
        _call(submissions_router.update_submission_link, link_id=uid, body=body)
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
    _require_scope(SCOPE_WRITE)
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


@mcp.tool(
    description=(
        "Close one or more briefs. This is a soft delete: the brief stops accepting "
        "work and disappears from the tree, but every submission already made "
        "against it — and every file uploaded with those submissions — is left "
        "alone in its own project. There is no undo through this API. A brief with "
        "submissions is usually one someone is still working from, so check "
        "submission_count in list_briefs before closing anything you did not create."
    )
)
def delete_brief(link_ids: list[str]) -> dict[str, Any]:
    """Args: link_ids — one or more brief ids; all are closed together."""
    _require_scope(SCOPE_WRITE)
    if not link_ids:
        raise ValueError("link_ids must contain at least one brief id")
    result = _call(
        submissions_router.bulk_delete_submission_links,
        body=BulkDeleteRequest(link_ids=[_uuid(i, "link_ids") for i in link_ids]),
    )
    # Same honesty as move_brief: ids that were already closed are skipped rather
    # than failing the batch, so report what changed instead of what was asked for.
    return {
        "deleted": result.updated,
        "requested": len(link_ids),
        "note": "Soft delete: submissions and their uploaded files are retained.",
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
    # Two credentials are accepted. Bearer is tried first because a client that
    # sent one meant it; falling through to the API key on a bad token would hide
    # a token problem behind whatever key happened to be configured.
    scopes: Optional[list[str]] = None
    auth = headers.get("authorization", "")
    try:
        if auth.lower().startswith("bearer ") and settings.mcp_oauth_enabled:
            user, scopes = mcp_oauth.verify_access_token(db, auth[7:].strip())
        else:
            # Unscoped: an API key keeps the full access it has always had.
            user = resolve_api_key_user(db, headers.get("x-api-key"))
    except mcp_oauth.MCPAuthError as exc:
        db.close()
        await _send_json_error(send, 401, str(exc), challenge=True)
        return
    except HTTPException as exc:
        db.close()
        # A 401 must carry the discovery pointer; a 403 is an answered question,
        # so re-challenging there would just loop the client.
        await _send_json_error(
            send, exc.status_code, str(exc.detail), challenge=exc.status_code == 401
        )
        return

    # The session stays open for the whole request so `user` remains attached to it.
    user_token = _current_user.set(user)
    db_token = _current_db.set(db)
    scopes_token = _current_scopes.set(scopes)
    try:
        await _inner_app(scope, receive, send)
    finally:
        _current_user.reset(user_token)
        _current_db.reset(db_token)
        _current_scopes.reset(scopes_token)
        db.close()


async def _send_json_error(send, status_code: int, detail: str, challenge: bool = False) -> None:
    import json

    body = json.dumps({"error": detail}).encode()
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode()),
    ]
    # Without this a compliant client cannot discover where to authenticate. It is
    # only honoured on a 401 — never on a 200 — and its absence is the single most
    # common reason a connector fails with nothing reaching the issuer at all.
    if challenge and settings.mcp_oauth_enabled:
        headers.append((
            b"www-authenticate",
            mcp_oauth.www_authenticate_header(scope=" ".join(mcp_oauth.SUPPORTED_SCOPES)).encode(),
        ))
    await send({"type": "http.response.start", "status": status_code, "headers": headers})
    await send({"type": "http.response.body", "body": body})


def session_manager():
    """The transport's session manager, which the parent app's lifespan must run.

    Starlette does not run a mounted sub-app's lifespan, and the MCP app puts its
    session manager there — so without this the mount accepts requests and then
    fails on the first one.
    """
    return mcp.session_manager
