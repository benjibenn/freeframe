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
import secrets
import uuid
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException
from mcp.server.fastmcp import FastMCP
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from ..middleware.api_key import resolve_api_key_user
from ..services import mcp_oauth
from ..services.mcp_oauth import SCOPE_READ, SCOPE_WRITE, SCOPE_USERS_ADMIN
from ..models.share import SharePermission
from ..models.user import User
from ..schemas.approval import ApprovalCreate
from ..schemas.asset import AssetUpdate
from ..schemas.auth import AdminSetPasswordRequest, InviteRequest
from ..schemas.brief_overview import BriefLabelsUpdate
from ..schemas.folder import AssetMoveRequest, FolderCreate, FolderUpdate
from ..schemas.share import MultiShareCreate, ShareLinkCreate
from ..services.brief_title import build_title
from ..schemas.submission import (
    BriefJsonUpdate,
    BulkDeleteRequest,
    BulkRefileRequest,
    DuplicateLinkRequest,
    SubmissionLinkCreate,
)
from ..schemas.task_stage import BriefAssigneeAssign, BriefEditorAssign, TaskStageAssign
from . import admin as admin_router
from . import brief_labels as brief_labels_router
from . import approvals as approvals_router
from . import assets as assets_router
from . import folders as folders_router
from . import projects as projects_router
from . import share as share_router
from . import submissions as submissions_router
from . import tasks as tasks_router
from . import users as users_router

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


def _require_admin() -> None:
    """Enforce that the resolved caller is a platform admin.

    users_router.invite_user's real gate is Depends(require_admin) — a FastAPI
    dependency that only runs when the route is invoked through the app, not when
    _call() invokes the function directly with current_user already supplied.
    Without this, any MCP caller could invite a user regardless of their own
    admin status.
    """
    if not _user().is_superadmin:
        raise ValueError("Admin access required")


mcp = FastMCP(
    name="freeframe",
    instructions=(
        "Manage Freeframe video request briefs. A brief is a token-gated request "
        "that editors submit work against. Call list_destinations before creating "
        "or moving a brief — both need a real project id, which cannot be guessed. "
        "Folders to file briefs into are made with create_folder, which takes a "
        "path and creates whatever part of it is missing. The work editors send "
        "back is reached with list_submitted_files, and every file tool below "
        "takes an asset_id from it. To send work outside Freeframe, share_file "
        "and share_folder mint a public link anyone can open."
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
        "Search video request briefs. Returns each brief's id, title, where it is "
        "filed, how many submissions it has received, and its public submit URL. "
        "Narrow with query (matches the title or the folder path, case-insensitive), "
        "project_id, or folder_id. A tenant can hold hundreds of briefs, so the "
        "result is capped at limit and reports total_matched when it truncates — "
        "narrow the search rather than raising limit."
    )
)
def list_briefs(
    project_id: str | None = None,
    query: str | None = None,
    folder_id: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Args: project_id, query, folder_id — all optional filters; limit — 1..200.

    Filtering happens here rather than in the endpoint on purpose: the endpoint
    backs the admin grid, which wants every row, and adding search parameters to
    it would mean two places deciding what a brief matches.
    """
    _require_scope(SCOPE_READ)
    if not 1 <= limit <= 200:
        raise ValueError("limit must be between 1 and 200")
    links = _call(submissions_router.list_submission_links)
    out = [_brief_summary(l) for l in links]
    if project_id:
        wanted = str(_uuid(project_id, "project_id"))
        out = [b for b in out if b["home_project_id"] == wanted]
    if folder_id:
        wanted = str(_uuid(folder_id, "folder_id"))
        out = [b for b in out if b["home_folder_id"] == wanted]
    if query:
        needle = query.casefold().strip()
        out = [
            b for b in out
            if needle in (b["title"] or "").casefold()
            or needle in (b["home_path"] or "").casefold()
        ]
    total = len(out)
    return {
        "total_matched": total,
        "returned": min(total, limit),
        # Said out loud rather than left for the caller to infer from a length:
        # a silently truncated list reads as "that is all of them".
        "truncated": total > limit,
        "briefs": out[:limit],
    }


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
        "call get_brief first to read them. If the brief lists two or more "
        "output_languages, language is required too and must be exactly one of "
        "them; the file is then stored as 'German — A. before you buy'. "
        "Submitting the same deliverable and language twice adds a new version to "
        "it rather than a second one beside it. source_url is required and is "
        "where the file was made (the Figma or Canva link, not the render): it is "
        "kept as the version's first comment so the next person can open the "
        "working file."
    )
)
def submit_work(
    link_id: str,
    url: str,
    source_url: str,
    asset_name: Optional[str] = None,
    language: Optional[str] = None,
) -> dict[str, Any]:
    """Args: url — a public http(s) URL of the finished file; source_url — where it
    was made (Figma, Canva, …), kept as the version's first comment; asset_name —
    which deliverable this is; language — which of the brief's output_languages it
    is in."""
    _require_scope(SCOPE_WRITE)
    link_uuid = _uuid(link_id, "link_id")
    body = submissions_router.SubmitWorkFromUrlRequest(
        url=url, asset_name=asset_name, language=language, source_url=source_url
    )
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

_TITLE_CONVENTION = "YYYYMMDD - <sku> - <Persona> - <Lens> - <Hook> - <Format>."

# Parts that exist only to build the title. Persona is not among them: it is also
# a label, so it stays meaningful alongside a whole title.
_TITLE_PARTS = ("sku", "lens", "hook", "ad_format", "date")


def _title(*, title, sku, persona, lens, hook, ad_format, date) -> str:
    """The brief's title: the one given, or one built from its parts.

    Refusing a title together with its parts is deliberate. Ignoring the parts
    would create a brief whose title and whose labels disagree about what it is,
    and honouring them would silently overwrite the title the caller asked for.
    """
    given = [n for n, v in zip(_TITLE_PARTS, (sku, lens, hook, ad_format, date)) if v]
    if title and title.strip():
        if given:
            raise ValueError(
                "title is already a whole title — drop " + ", ".join(given)
                + ", or drop title and let them build one"
            )
        return title
    if not given and not persona:
        raise ValueError(
            "pass title, or the parts to build one: sku, persona, lens, hook, ad_format "
            f"({_TITLE_CONVENTION})"
        )
    return build_title(
        sku=sku, persona=persona, lens=lens, hook=hook, ad_format=ad_format, date_str=date,
    )


@mcp.tool(
    description=(
        "Create a new video request brief and return its public submit URL. "
        "home_project_id is required — get one from list_destinations. Omit "
        "home_folder_id to file the brief at the project root. "
        "Title it by passing sku, persona, lens, hook and ad_format and the "
        "convention is applied for you: " + _TITLE_CONVENTION + " Pass angle too "
        "— it is not part of the title and the playbook's coverage matrix counts "
        "it, so a brief without one is uncounted. A whole title instead of the "
        "parts is accepted for a brief that does not follow the convention. Pass "
        "brief_json to attach the structured brief in the same call. brief_json: "
        + _BRIEF_SHAPE
    )
)
def create_brief(
    home_project_id: str,
    title: str | None = None,
    sku: str | None = None,
    persona: str | None = None,
    lens: str | None = None,
    hook: str | None = None,
    ad_format: str | None = None,
    date: str | None = None,
    angle: str | None = None,
    home_folder_id: str | None = None,
    instructions: str | None = None,
    expires_at: str | None = None,
    brief_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Args: date — YYYYMMDD, today unless given; expires_at — optional ISO 8601
    timestamp after which the link stops accepting work."""
    _require_scope(SCOPE_WRITE)
    # Everything below is validated before the request exists. The underlying API
    # has no way to create a request and attach a brief in one write, so anything
    # rejected afterwards would strand an empty request with a live submit URL.
    final_title = _title(
        title=title, sku=sku, persona=persona, lens=lens, hook=hook,
        ad_format=ad_format, date=date,
    )
    checked = _brief(brief_json) if brief_json is not None else None

    body = SubmissionLinkCreate(
        title=final_title,
        instructions=instructions,
        home_project_id=_uuid(home_project_id, "home_project_id"),
        home_folder_id=_uuid(home_folder_id, "home_folder_id") if home_folder_id else None,
        expires_at=datetime.fromisoformat(expires_at) if expires_at else None,
        persona_label=persona,
        angle_label=angle,
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
        "alone in its own project. Undo it with restore_brief. A brief with "
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


@mcp.tool(
    description=(
        "Reopen a brief that delete_brief closed. Its submit URL starts working "
        "again and it reappears in list_briefs. Find the id with "
        "list_deleted_briefs. A brief that was already past its expiry comes back "
        "still expired — give it a new expires_at with update_brief to reopen the "
        "window."
    )
)
def restore_brief(brief_id: str) -> dict[str, Any]:
    """Args: brief_id — the closed brief to reopen."""
    _require_scope(SCOPE_WRITE)
    link = _call(
        submissions_router.restore_submission_link,
        link_id=_uuid(brief_id, "brief_id"),
    )
    return _brief_summary(link)


@mcp.tool(
    description=(
        "List closed briefs, most recently closed first, so one can be reopened "
        "with restore_brief. Deleting a brief never destroys it or the work "
        "submitted to it."
    )
)
def list_deleted_briefs(limit: int = 50) -> list[dict[str, Any]]:
    """Args: limit — 1..100, newest deletions first."""
    _require_scope(SCOPE_READ)
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    links = _call(submissions_router.list_deleted_submission_links, skip=0, limit=limit)
    return [
        {
            "id": str(l.id),
            "title": l.title,
            "submission_count": l.submission_count,
            "deleted_at": (
                d.isoformat() if (d := getattr(l, "deleted_at", None)) else None
            ),
        }
        for l in links
    ]


@mcp.tool(
    description=(
        "Tag one or more briefs with a persona and/or angle label — the two axes "
        "the playbook view groups and counts by. Omit a field to leave it as it is; "
        "pass \"\" to clear it. All-or-nothing: if any id is unknown or deleted, "
        "nothing is saved."
    )
)
def set_brief_labels(
    link_ids: list[str],
    persona_label: str | None = None,
    angle_label: str | None = None,
) -> dict[str, Any]:
    """Args: link_ids — briefs to tag; persona_label / angle_label — the labels to set."""
    _require_scope(SCOPE_WRITE)
    if not link_ids:
        raise ValueError("link_ids must contain at least one brief id")
    body = BriefLabelsUpdate(
        link_ids=[_uuid(i, "link_ids") for i in link_ids],
        persona_label=persona_label,
        angle_label=angle_label,
    )
    return _call(brief_labels_router.set_brief_labels, body=body)


# ── Folders ──────────────────────────────────────────────────────────────────

def _folder_summary(folder: Any) -> dict[str, Any]:
    return {
        "id": str(folder.id),
        "project_id": str(folder.project_id),
        "parent_id": str(folder.parent_id) if folder.parent_id else None,
        "name": folder.name,
        "item_count": folder.item_count,
    }


def _find_node(nodes: list[Any], folder_id: uuid.UUID) -> Any | None:
    for node in nodes:
        if node.id == folder_id:
            return node
        hit = _find_node(node.children, folder_id)
        if hit is not None:
            return hit
    return None


def _split_path(path: str) -> list[str]:
    segments = [s.strip() for s in path.split("/") if s.strip()]
    if not segments:
        raise ValueError("path must name at least one folder, e.g. 'Phones/Stokora'")
    return segments


@mcp.tool(
    description=(
        "Create a folder inside a project, by path. Segments that already exist "
        "are reused and only the missing tail is created, so calling this twice "
        "with the same path is safe. Pass parent_folder_id to resolve the path "
        "beneath an existing folder instead of the project root. Names are matched "
        "case-insensitively. Use the returned id as home_folder_id when creating, "
        "duplicating or moving a brief."
    )
)
def create_folder(
    project_id: str,
    path: str,
    parent_folder_id: str | None = None,
) -> dict[str, Any]:
    """Args: path — one or more names separated by '/', relative to parent_folder_id or the project root."""
    _require_scope(SCOPE_WRITE)
    pid = _uuid(project_id, "project_id")
    segments = _split_path(path)

    tree = _call(folders_router.get_folder_tree, project_id=pid)
    if parent_folder_id:
        parent = _uuid(parent_folder_id, "parent_folder_id")
        node = _find_node(tree, parent)
        if node is None:
            raise ValueError(f"No folder {parent_folder_id} in project {project_id}")
        current_id: uuid.UUID | None = parent
        siblings = node.children
    else:
        current_id = None
        siblings = tree

    created: list[str] = []
    landed: Any = None
    for index, segment in enumerate(segments):
        # Nothing stops two siblings sharing a name, so a path can be genuinely
        # ambiguous. Guessing would file briefs into the wrong tree silently.
        matches = [n for n in siblings if n.name.casefold() == segment.casefold()]
        if len(matches) > 1:
            raise ValueError(
                f"{len(matches)} folders here are named {segment!r} — "
                "pass parent_folder_id to say which branch you mean"
            )
        if matches:
            landed = matches[0]
            current_id = landed.id
            siblings = landed.children
            continue
        # First gap in the path: everything from here down is new, and each one
        # is the next one's parent, so the tree read above is stale from here on.
        for name in segments[index:]:
            landed = _call(
                folders_router.create_folder,
                project_id=pid,
                body=FolderCreate(name=name, parent_id=current_id),
            )
            created.append(name)
            current_id = landed.id
        break

    return {
        "id": str(current_id),
        "project_id": project_id,
        "name": landed.name,
        "path": "/".join(segments),
        # Which segments were new, so a caller can tell "created" from "was already there".
        "created": created,
    }


@mcp.tool(
    description=(
        "Rename a folder, move it under a different parent, or both. Only the "
        "fields you pass change. parent_folder_id must be another folder in the "
        "same project; pass an empty string to move the folder to the project "
        "root. A folder cannot be moved inside itself or one of its own subfolders."
    )
)
def update_folder(
    folder_id: str,
    name: str | None = None,
    parent_folder_id: str | None = None,
) -> dict[str, Any]:
    """Args: folder_id — the folder to change. Omitted fields keep their current value."""
    _require_scope(SCOPE_WRITE)
    if name is None and parent_folder_id is None:
        raise ValueError("Pass name, parent_folder_id, or both — nothing to change otherwise")

    fields: dict[str, Any] = {}
    if name is not None:
        fields["name"] = name
    if parent_folder_id is not None:
        # "" is how a caller says "to the root". The endpoint distinguishes unset
        # from null via model_fields_set, so parent_id only goes in when asked for.
        fields["parent_id"] = _uuid(parent_folder_id, "parent_folder_id") if parent_folder_id else None

    return _folder_summary(
        _call(
            folders_router.update_folder,
            folder_id=_uuid(folder_id, "folder_id"),
            body=FolderUpdate(**fields),
        )
    )


@mcp.tool(
    description=(
        "Delete a folder. This is a soft delete: the folder, every subfolder "
        "under it and every asset inside them are hidden from the tree but kept, "
        "and restore_folder puts the whole subtree back. Briefs filed here are "
        "not deleted — they keep pointing at the folder and reappear with it. "
        "Note the returned id if you might want to undo this later."
    )
)
def delete_folder(folder_id: str) -> dict[str, Any]:
    """Args: folder_id — the folder to delete, along with everything beneath it."""
    _require_scope(SCOPE_WRITE)
    fid = _uuid(folder_id, "folder_id")
    _call(folders_router.delete_folder, folder_id=fid)
    return {
        "deleted": str(fid),
        "note": "Soft delete — call restore_folder with this id to undo.",
    }


@mcp.tool(
    description=(
        "Undo a folder deletion. Restores the folder, its subfolders and their "
        "assets. If the folder's old parent is itself still deleted, the folder "
        "comes back at the project root instead. Use list_deleted_folders to find "
        "the id of something deleted earlier."
    )
)
def restore_folder(folder_id: str) -> dict[str, Any]:
    """Args: folder_id — a previously deleted folder."""
    _require_scope(SCOPE_WRITE)
    fid = _uuid(folder_id, "folder_id")
    _call(folders_router.restore_folder, folder_id=fid)
    return {"restored": str(fid)}


@mcp.tool(
    description=(
        "List a project's deleted folders, most recently deleted first, so a "
        "deletion can be undone after its id has been forgotten. Deleted assets "
        "are not listed here."
    )
)
def list_deleted_folders(project_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Args: project_id — the project to look in. limit — 1 to 100, default 50."""
    _require_scope(SCOPE_READ)
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    trash = _call(
        folders_router.list_trash,
        project_id=_uuid(project_id, "project_id"),
        skip=0,
        limit=limit,
    )
    return trash["folders"]


# ── Submitted files ──────────────────────────────────────────────────────────

def _file_summary(asset: Any) -> dict[str, Any]:
    """The handful of fields a file tool acts on, not the whole AssetResponse.

    The response model also carries versions, thumbnails and tags; none of them
    are inputs to anything here, and a brief with fifty submitted files would
    otherwise flood the caller's context.
    """
    kind = getattr(asset, "asset_type", None)
    return {
        "asset_id": str(asset.id),
        "name": asset.name,
        "project_id": str(asset.project_id),
        "folder_id": str(asset.folder_id) if asset.folder_id else None,
        "asset_type": getattr(kind, "value", None) or (str(kind) if kind else None),
    }


def _latest_version_id(asset_id: uuid.UUID) -> uuid.UUID:
    """The version a review applies to.

    list_asset_versions orders by version_number descending, so the head of the
    list is the newest upload. Reviewing anything else silently would approve a
    superseded cut.
    """
    versions = _call(assets_router.list_asset_versions, asset_id=asset_id)
    if not versions:
        raise ValueError("That file has no uploaded version to review yet")
    return versions[0].id


@mcp.tool(
    description=(
        "List the work editors have submitted against a brief, grouped by "
        "submitter. Every file carries the asset_id that get_file_url, "
        "rename_file, move_file, delete_file and review_file all take."
    )
)
def list_submitted_files(brief_id: str) -> list[dict[str, Any]]:
    """Args: brief_id — the brief whose submissions to list."""
    _require_scope(SCOPE_READ)
    subs = _call(
        submissions_router.list_submissions,
        link_id=_uuid(brief_id, "brief_id"),
    )
    return [
        {
            "submission_id": str(s.id),
            "submitter": s.display_name or s.user_name or s.user_email,
            "submitter_email": s.user_email,
            "project_id": str(s.project_id),
            "submitted_at": s.created_at.isoformat() if s.created_at else None,
            "files": [{"asset_id": str(f.asset_id), "name": f.name} for f in s.files],
        }
        for s in subs
    ]


@mcp.tool(
    description=(
        "Get a time-limited URL for a submitted file, to view or download it. "
        "The link is presigned and expires, so fetch it when you are ready to "
        "use it rather than storing it."
    )
)
def get_file_url(asset_id: str, download: bool = True) -> dict[str, Any]:
    """Args: asset_id — from list_submitted_files; download — false streams inline."""
    _require_scope(SCOPE_READ)
    res = _call(
        assets_router.get_stream_url,
        asset_id=_uuid(asset_id, "asset_id"),
        version_id=None,
        download=download,
    )
    kind = getattr(res, "asset_type", None)
    return {
        "url": res.url,
        "asset_type": getattr(kind, "value", None) or (str(kind) if kind else None),
        "expires_in": res.expires_in,
    }


@mcp.tool(
    description=(
        "Rename a submitted file. Renames the file only — it stays in the same "
        "folder and keeps every version it has."
    )
)
def rename_file(asset_id: str, name: str) -> dict[str, Any]:
    """Args: asset_id — from list_submitted_files; name — the new filename."""
    _require_scope(SCOPE_WRITE)
    new_name = name.strip()
    if not new_name:
        raise ValueError("name must not be blank")
    return _file_summary(_call(
        assets_router.update_asset,
        asset_id=_uuid(asset_id, "asset_id"),
        body=AssetUpdate(name=new_name),
    ))


@mcp.tool(
    description=(
        "Move a submitted file into a folder of the same project. Pass an empty "
        "string to move it to the project root. Cross-project moves are refused: "
        "a folder only ever holds files from its own project."
    )
)
def move_file(asset_id: str, folder_id: str) -> dict[str, Any]:
    """Args: asset_id — from list_submitted_files; folder_id — target, "" for root.

    folder_id is required rather than defaulted: an omitted argument that quietly
    means "root" would move a file out of its folder every time a caller forgot it.
    """
    _require_scope(SCOPE_WRITE)
    aid = _uuid(asset_id, "asset_id")
    target = _uuid(folder_id, "folder_id") if folder_id else None
    _call(folders_router.move_asset, asset_id=aid, body=AssetMoveRequest(folder_id=target))
    return {"asset_id": str(aid), "folder_id": str(target) if target else None}


@mcp.tool(
    description=(
        "Delete a submitted file. Soft delete — the file is hidden but kept, and "
        "restore_file brings it back with its versions intact."
    )
)
def delete_file(asset_id: str) -> dict[str, Any]:
    """Args: asset_id — from list_submitted_files."""
    _require_scope(SCOPE_WRITE)
    aid = _uuid(asset_id, "asset_id")
    _call(assets_router.delete_asset, asset_id=aid)
    return {
        "deleted": str(aid),
        "note": "Soft delete — call restore_file with this id to undo.",
    }


@mcp.tool(
    description=(
        "Undo delete_file. If the folder the file was in has since been deleted "
        "too, the file comes back at the project root."
    )
)
def restore_file(asset_id: str) -> dict[str, Any]:
    """Args: asset_id — the deleted file to bring back."""
    _require_scope(SCOPE_WRITE)
    aid = _uuid(asset_id, "asset_id")
    _call(folders_router.restore_asset, asset_id=aid)
    return {"restored": str(aid)}


@mcp.tool(
    description=(
        "Approve or reject a submitted file, with an optional note as feedback. "
        "Applies to the file's newest version. This emails the person who "
        "uploaded it and raises a notification for them, so only call it when the "
        "decision is final."
    )
)
def review_file(asset_id: str, decision: str, note: str | None = None) -> dict[str, Any]:
    """Args: asset_id — from list_submitted_files; decision — "approve" or
    "reject"; note — feedback sent with the decision."""
    _require_scope(SCOPE_WRITE)
    choice = decision.strip().casefold()
    if choice not in ("approve", "reject"):
        raise ValueError('decision must be "approve" or "reject"')
    aid = _uuid(asset_id, "asset_id")
    version_id = _latest_version_id(aid)
    endpoint = (
        approvals_router.approve_asset if choice == "approve"
        else approvals_router.reject_asset
    )
    _call(endpoint, asset_id=aid, body=ApprovalCreate(version_id=version_id, note=note))
    return {
        "asset_id": str(aid),
        "decision": choice,
        "version_id": str(version_id),
        "note": note,
        "notified": "The uploader was emailed and notified in-app.",
    }


@mcp.tool(
    description=(
        "Look inside one folder: its subfolders, the files in it, and the briefs "
        "filed there. Omit folder_id for the project root. Use this instead of "
        "listing a whole project when you already know where you are."
    )
)
def list_folder_contents(
    project_id: str,
    folder_id: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Args: project_id; folder_id — omit for the root; limit — 1..200 files.

    Every defaulted parameter of list_assets is passed explicitly. Called
    directly rather than through FastAPI, an omitted argument is left as the
    Query object itself — which is truthy, so include_failed would silently
    turn on.
    """
    _require_scope(SCOPE_READ)
    if not 1 <= limit <= 200:
        raise ValueError("limit must be between 1 and 200")
    pid = _uuid(project_id, "project_id")
    tree = _call(folders_router.get_folder_tree, project_id=pid)

    if folder_id:
        fid = _uuid(folder_id, "folder_id")
        node = _find_node(tree, fid)
        if node is None:
            raise ValueError(f"No folder {folder_id} in project {project_id}")
        children, scope, here = node.children, str(fid), str(fid)
    else:
        children, scope, here = tree, "root", None

    assets = _call(
        assets_router.list_assets,
        project_id=pid,
        include_failed=False,
        folder_id=scope,
        tag=None,
        frame_label=None,
        exclude_archived=False,
        skip=0,
        limit=limit,
    )
    links = _call(submissions_router.list_submission_links)
    briefs = [
        _brief_summary(l) for l in links
        if str(l.home_project_id) == str(pid)
        and (str(l.home_folder_id) if l.home_folder_id else None) == here
    ]

    return {
        "folder_id": here,
        "subfolders": [
            {"id": str(c.id), "name": c.name, "item_count": c.item_count}
            for c in children
        ],
        "files": [_file_summary(a) for a in assets],
        "briefs": briefs,
    }


# ── Public share links ───────────────────────────────────────────────────────

# A share link is reachable by anyone holding the URL — no Freeframe account, no
# membership of the project it points into. That is the point of it, and it is also
# why every tool below says so out loud: an agent that cannot tell a presigned
# get_file_url from a standing public link will hand out the wrong one.
_SHARE_PERMISSIONS = ("view", "comment", "approve")


def _share_url(token: str) -> str:
    return f"{settings.frontend_url}/share/{token}"


def _share_permission(permission: str) -> SharePermission:
    choice = permission.strip().casefold()
    if choice not in _SHARE_PERMISSIONS:
        raise ValueError(
            f'permission must be one of {", ".join(_SHARE_PERMISSIONS)}, got {permission!r}'
        )
    return SharePermission(choice)


def _share_expiry(expires_in_days: int | None) -> datetime | None:
    """Days-from-now rather than a timestamp.

    A tool taking an absolute expires_at invites an agent to invent one from a
    date it believes today to be, and a link that expired before it was created
    fails only when the recipient opens it.
    """
    if expires_in_days is None:
        return None
    if expires_in_days < 1:
        raise ValueError(
            "expires_in_days must be 1 or more — omit it for a link that never expires"
        )
    return datetime.now(timezone.utc) + timedelta(days=expires_in_days)


def _share_body(
    permission: str,
    allow_download: bool,
    password: str | None,
    expires_in_days: int | None,
    title: str | None,
) -> dict[str, Any]:
    return {
        "permission": _share_permission(permission),
        "allow_download": allow_download,
        "password": password or None,
        "expires_at": _share_expiry(expires_in_days),
        "title": title,
    }


def _permission_value(perm: Any) -> str | None:
    return getattr(perm, "value", None) or (str(perm) if perm else None)


def _share_summary(link: Any) -> dict[str, Any]:
    """What the link is and where it points, plus the URL to hand out.

    The password is deliberately not echoed back. The caller passed it in, and
    repeating it here would copy it into a second tool-call log for no gain.
    """
    return {
        "token": link.token,
        "url": _share_url(link.token),
        "title": link.title,
        "shares": (
            "file" if link.asset_id
            else "folder" if link.folder_id
            else "selection"
        ),
        "asset_id": str(link.asset_id) if link.asset_id else None,
        "folder_id": str(link.folder_id) if link.folder_id else None,
        "project_id": str(link.project_id) if link.project_id else None,
        "permission": _permission_value(getattr(link, "permission", None)),
        "allow_download": link.allow_download,
        "password_protected": bool(link.password_hash),
        "is_enabled": link.is_enabled,
        "expires_at": link.expires_at.isoformat() if link.expires_at else None,
    }


@mcp.tool(
    description=(
        "Create a public share link for one submitted file. ANYONE WITH THE URL "
        "CAN OPEN IT — no account, no project membership — and it stands until "
        "revoked. Use get_file_url instead for a private, expiring link you fetch "
        "and use yourself. Defaults to view-only with downloading off; pass "
        "allow_download to let the recipient save the file."
    )
)
def share_file(
    asset_id: str,
    permission: str = "view",
    allow_download: bool = False,
    password: str | None = None,
    expires_in_days: int | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    """Args: asset_id — from list_submitted_files. permission — "view",
    "comment" or "approve". allow_download — let the viewer save the file.
    password — gate the link. expires_in_days — omit for no expiry. title —
    defaults to the file's name."""
    _require_scope(SCOPE_WRITE)
    link = _call(
        share_router.create_share_link,
        asset_id=_uuid(asset_id, "asset_id"),
        body=ShareLinkCreate(
            **_share_body(permission, allow_download, password, expires_in_days, title)
        ),
    )
    return _share_summary(link)


@mcp.tool(
    description=(
        "Create a public share link for a whole folder — everything in it, and "
        "everything in its subfolders. ANYONE WITH THE URL CAN OPEN IT, and the "
        "link keeps up with the folder: files added later appear to whoever "
        "already has it. Defaults to view-only with downloading off."
    )
)
def share_folder(
    folder_id: str,
    permission: str = "view",
    allow_download: bool = False,
    password: str | None = None,
    expires_in_days: int | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    """Args: folder_id — from list_folder_contents or create_folder.
    permission — "view", "comment" or "approve". allow_download — let viewers
    save files. password — gate the link. expires_in_days — omit for no expiry.
    title — defaults to the folder's name."""
    _require_scope(SCOPE_WRITE)
    link = _call(
        share_router.create_folder_share_link,
        folder_id=_uuid(folder_id, "folder_id"),
        body=ShareLinkCreate(
            **_share_body(permission, allow_download, password, expires_in_days, title)
        ),
    )
    return _share_summary(link)


@mcp.tool(
    description=(
        "Create one public share link covering a hand-picked set of files and "
        "folders — for sending a client three cuts out of ten without exposing "
        "the rest. ANYONE WITH THE URL CAN OPEN IT. Everything picked must live "
        "in the one project_id given; a file from elsewhere is refused rather "
        "than skipped. Defaults to view-only with downloading off."
    )
)
def share_many(
    project_id: str,
    asset_ids: list[str] | None = None,
    folder_ids: list[str] | None = None,
    permission: str = "view",
    allow_download: bool = False,
    password: str | None = None,
    expires_in_days: int | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    """Args: project_id — the project everything picked belongs to. asset_ids /
    folder_ids — what to include; at least one between them. permission —
    "view", "comment" or "approve". allow_download — let viewers save files.
    password — gate the link. expires_in_days — omit for no expiry. title —
    defaults to a count of the items."""
    _require_scope(SCOPE_WRITE)
    body = _share_body(permission, allow_download, password, expires_in_days, title)
    link = _call(
        share_router.create_multi_share_link,
        project_id=_uuid(project_id, "project_id"),
        body=MultiShareCreate(
            asset_ids=[_uuid(a, "asset_ids") for a in (asset_ids or [])],
            folder_ids=[_uuid(f, "folder_ids") for f in (folder_ids or [])],
            **body,
        ),
    )
    return _share_summary(link)


@mcp.tool(
    description=(
        "List the public share links pointing at one file or one folder, with "
        "each link's permission, whether downloading is on, whether it has a "
        "password, and when it expires. Pass exactly one of asset_id or "
        "folder_id. Call this before sharing again — a file can carry several "
        "live links, and the one already sent may be the one to fix."
    )
)
def list_shares(asset_id: str | None = None, folder_id: str | None = None) -> list[dict[str, Any]]:
    """Args: asset_id — a file's links; folder_id — a folder's links. Exactly one."""
    _require_scope(SCOPE_READ)
    if bool(asset_id) == bool(folder_id):
        raise ValueError("Pass exactly one of asset_id or folder_id")
    if asset_id:
        links = _call(share_router.list_share_links, asset_id=_uuid(asset_id, "asset_id"))
    else:
        links = _call(
            share_router.list_folder_share_links,
            folder_id=_uuid(folder_id, "folder_id"),
        )
    return [_share_summary(l) for l in links]


@mcp.tool(
    description=(
        "List every public share link in a project, with how many times each has "
        "been opened. This is how a link made by share_many is found again — it "
        "belongs to the project rather than to any one file. Reports less per "
        "link than list_shares does: for download, password and expiry, look the "
        "file or folder up there."
    )
)
def list_project_shares(project_id: str, query: str | None = None) -> list[dict[str, Any]]:
    """Args: project_id; query — match part of a link's title."""
    _require_scope(SCOPE_READ)
    links = _call(
        share_router.list_project_share_links,
        project_id=_uuid(project_id, "project_id"),
        search=query,
    )
    return [
        {
            "token": l.token,
            "url": _share_url(l.token),
            "title": l.title,
            # share_type is what the project listing reports, and it labels a
            # hand-picked selection "folder". Passed through rather than
            # corrected here: the admin UI reads the same field.
            "share_type": l.share_type,
            "target_name": l.target_name,
            "permission": _permission_value(l.permission),
            "is_enabled": l.is_enabled,
            "view_count": l.view_count,
            "last_viewed_at": l.last_viewed_at.isoformat() if l.last_viewed_at else None,
        }
        for l in links
    ]


@mcp.tool(
    description=(
        "Revoke a public share link, by the token from the URL. Whoever holds "
        "the URL loses access immediately; the file or folder itself is "
        "untouched. Takes the token — the part after /share/ — not a file or "
        "folder id."
    )
)
def revoke_share(token: str) -> dict[str, Any]:
    """Args: token — the trailing segment of the share URL."""
    _require_scope(SCOPE_WRITE)
    cleaned = token.strip().rstrip("/").rsplit("/", 1)[-1]
    if not cleaned:
        raise ValueError("token must be the part of the share URL after /share/")
    _call(share_router.revoke_share_link, token=cleaned)
    return {"token": cleaned, "revoked": True}

# ── Task pipeline ────────────────────────────────────────────────────────────

def _stage_summary(stage: Any) -> dict[str, Any]:
    return {
        "id": str(stage.id),
        "name": stage.name,
        "position": stage.position,
        "color": stage.color,
        "is_default": stage.is_default,
    }


@mcp.tool(
    description=(
        "List the pipeline stages a brief moves through (e.g. Pending, In "
        "Progress, Review, Done), in board order. Call this before "
        "set_brief_task_stage — it needs a real stage id."
    )
)
def list_task_stages() -> list[dict[str, Any]]:
    _require_scope(SCOPE_READ)
    return [_stage_summary(s) for s in _call(tasks_router.list_task_stages)]


@mcp.tool(
    description=(
        "List everyone who can own a brief: platform admins plus any editor who "
        "has accepted a submission link. Call this before assign_brief_owner — "
        "it needs a real user id."
    )
)
def list_assignable_users() -> list[dict[str, Any]]:
    _require_scope(SCOPE_READ)
    return [
        {"id": str(u.id), "name": u.name, "email": u.email}
        for u in _call(users_router.list_assignable_users)
    ]


def _brief_task_summary(item: Any) -> dict[str, Any]:
    # Mirrors what the board shows for one brief, without the nested asset list —
    # these tools change one field on one brief and hand back what changed, not
    # the file tree underneath it.
    return {
        "id": str(item.id),
        "title": item.title,
        "taxonomy_path": item.taxonomy_path,
        "task_stage_id": str(item.task_stage_id) if item.task_stage_id else None,
        "assignee_id": str(item.assignee_id) if item.assignee_id else None,
        "assignee_name": item.assignee_name,
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
        "submit_url": item.submit_url,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


@mcp.tool(
    description=(
        "Move a brief to a different pipeline stage, or pass null to clear its "
        "stage. Get a real stage id from list_task_stages first. Platform admins "
        "may move any brief; anyone else only a brief they own."
    )
)
def set_brief_task_stage(link_id: str, task_stage_id: str | None) -> dict[str, Any]:
    """Args: link_id — the brief to move. task_stage_id — a stage id from
    list_task_stages, or null to clear the stage."""
    _require_scope(SCOPE_WRITE)
    updated = _call(
        tasks_router.set_brief_task_stage,
        link_id=_uuid(link_id, "link_id"),
        body=TaskStageAssign(
            task_stage_id=_uuid(task_stage_id, "task_stage_id") if task_stage_id else None
        ),
    )
    return _brief_task_summary(updated)


@mcp.tool(
    description=(
        "Set the internal owner of a brief — whose desk it sits on — or pass "
        "null to unassign it. Distinct from the editors making it — put those on "
        "with assign_brief_editor. Get a real user id from list_assignable_users "
        "first. Platform-admin only."
    )
)
def assign_brief_owner(link_id: str, assignee_id: str | None) -> dict[str, Any]:
    """Args: link_id — the brief to reassign. assignee_id — a user id from
    list_assignable_users, or null to unassign."""
    _require_scope(SCOPE_WRITE)
    updated = _call(
        tasks_router.set_brief_assignee,
        link_id=_uuid(link_id, "link_id"),
        body=BriefAssigneeAssign(
            assignee_id=_uuid(assignee_id, "assignee_id") if assignee_id else None
        ),
    )
    return _brief_task_summary(updated)


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


# ── User management ──────────────────────────────────────────────────────────

def _user_summary(user: Any) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "status": user.status.value if hasattr(user.status, "value") else user.status,
        "email_verified": user.email_verified,
    }


@mcp.tool(
    description=(
        "Invite a new user by email. Creates the account in a pending-invite "
        "state and emails them a link to set their own password; nothing here "
        "sets one. Fails if the email is already registered. Platform-admin only."
    )
)
def invite_user(email: str, name: str) -> dict[str, Any]:
    """Args: email — the address to invite. name — display name for the new account."""
    _require_scope(SCOPE_USERS_ADMIN)
    _require_admin()
    created = _call(users_router.invite_user, body=InviteRequest(email=email, name=name))
    return _user_summary(created)


@mcp.tool(
    description=(
        "Force-activate a user still waiting on email verification or an invite, "
        "without them completing that flow. Vouches for their email and burns any "
        "outstanding invite token. Deactivated users need reactivation instead, "
        "not this. Platform-admin only."
    )
)
def activate_user(user_id: str) -> dict[str, Any]:
    """Args: user_id — the user to activate."""
    _require_scope(SCOPE_USERS_ADMIN)
    updated = _call(admin_router.activate_user, user_id=_uuid(user_id, "user_id"))
    return _user_summary(updated)


@mcp.tool(
    description=(
        "Reset a user's password to a freshly generated random one and return it "
        "once in this result — there is no other way to retrieve it afterwards. "
        "Takes no password argument by design: a caller-supplied password would "
        "sit in plaintext in this request's tool-call log. Does not activate a "
        "pending account; call activate_user separately if needed. "
        "Platform-admin only."
    )
)
def reset_user_password(user_id: str) -> dict[str, Any]:
    """Args: user_id — the user whose password to reset."""
    _require_scope(SCOPE_USERS_ADMIN)
    new_password = secrets.token_urlsafe(18)
    updated = _call(
        admin_router.set_user_password,
        user_id=_uuid(user_id, "user_id"),
        body=AdminSetPasswordRequest(password=new_password),
    )
    out = _user_summary(updated)
    out["password"] = new_password
    return out


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
