import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .routers import auth, oidc, users, projects, upload, events, assets, me, comments, approvals, share, metadata, branding, notifications, admin, setup, folders, hls_proxy, submissions, activity, tasks, public_api, portal, import_router, frame_tags, tag_palette, drive_sync, library, brief_template
from .routers import mcp as mcp_router
from .services import mcp_oauth
from .services.s3_service import ensure_bucket_exists
from .middleware.global_rate_limit import GlobalRateLimitMiddleware
from .middleware.setup_guard import SetupGuardMiddleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_bucket_exists()
    # Starlette does not run a mounted sub-app's lifespan, and the MCP transport
    # keeps its session manager there — so it has to be started from here or the
    # /mcp mount fails on its first request.
    async with mcp_router.session_manager().run():
        yield

_disable_docs = os.getenv("DISABLE_DOCS", "").lower() in ("true", "1", "yes")

app = FastAPI(
    title="FreeFrame API",
    description="Media review platform API",
    version="1.0.0",
    lifespan=lifespan,
    contact={"name": "FreeFrame", "url": "https://github.com/Techiebutler/freeframe"},
    license_info={"name": "MIT"},
    docs_url=None if _disable_docs else "/docs",
    redoc_url=None if _disable_docs else "/redoc",
    openapi_url=None if _disable_docs else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "http://localhost:3000",
        "http://localhost:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GlobalRateLimitMiddleware)
app.add_middleware(SetupGuardMiddleware)

app.include_router(auth.router)
app.include_router(oidc.router)
app.include_router(users.router)
app.include_router(projects.router)
app.include_router(upload.router)
app.include_router(events.router)
app.include_router(assets.router)
app.include_router(me.router)
app.include_router(comments.router)
app.include_router(approvals.router)
app.include_router(share.router)
app.include_router(metadata.router)
app.include_router(branding.router)
app.include_router(notifications.router)
app.include_router(admin.router)
app.include_router(setup.router)
app.include_router(folders.router)
app.include_router(hls_proxy.router)
app.include_router(submissions.router)
app.include_router(activity.router)
app.include_router(tasks.router)
app.include_router(public_api.router)
app.include_router(portal.router)
app.include_router(import_router.router)
app.include_router(frame_tags.router)
app.include_router(tag_palette.router)
app.include_router(drive_sync.router)
app.include_router(library.router)
app.include_router(brief_template.router)

# Mounted rather than included: the MCP transport is its own ASGI app, not a
# collection of routes. Its auth is the X-API-Key header, checked inside the mount.
app.mount("/mcp", mcp_router.mcp_app)


# RFC 9728. Must be unauthenticated by requirement. Publicly this is
# /api/.well-known/oauth-protected-resource — not the origin root, because Traefik
# routes only /api here; clients are pointed at it by the `resource_metadata`
# parameter on the 401, which the spec allows to live at any HTTPS location.
# Authorization-server endpoints (/authorize, /token, /register, /revoke and the
# RFC 8414 metadata). Mounted here rather than inside the /mcp mount: that mount
# is wrapped in an auth guard, which would make /authorize unreachable for the
# user trying to authenticate through it.
if settings.mcp_oauth_enabled:
    from .routers import mcp_oauth_routes

    app.include_router(mcp_oauth_routes.router)
    app.router.routes.extend(mcp_oauth_routes.authorization_server_routes())


@app.get("/.well-known/oauth-protected-resource")
def oauth_protected_resource():
    # 404 rather than a document with an empty authorization_servers list: an
    # empty list is a valid-looking answer that sends the client nowhere, which is
    # harder to diagnose than the endpoint simply not being there.
    if not settings.mcp_oauth_enabled:
        raise HTTPException(status_code=404, detail="OAuth is not configured on this server")
    return mcp_oauth.protected_resource_metadata()

@app.get("/health")
def health():
    return {"status": "ok"}

