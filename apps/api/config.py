import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Find .env file - check current dir, then project root
# __file__ = apps/api/config.py, so parent.parent = project root
def _find_env_file() -> str:
    project_root = Path(__file__).parent.parent.parent  # freeframe/
    candidates = [
        Path(".env"),
        Path(".env.local"),
        project_root / ".env",
        project_root / ".env.local",
    ]
    for p in candidates:
        if p.exists():
            return str(p.resolve())
    return ".env"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_find_env_file(),
        env_file_encoding="utf-8",
        extra="ignore"  # Ignore extra env vars not in model
    )

    database_url: str
    redis_url: str
    s3_storage: str = "minio"  # "s3" for AWS S3, "minio" for local MinIO
    s3_bucket: str = "freeframe"
    s3_endpoint: str = "http://minio:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_region: str = "us-east-1"
    s3_public_endpoint: str | None = None  # External URL for presigned URLs (e.g. http://localhost:9000 when S3_ENDPOINT is http://minio:9000)
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    frontend_url: str = "http://localhost:3000"
    transcoder_engine: str = "ffmpeg"

    # ── Gemini (AI auto-tag) ──
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"

    # ---- OIDC / SSO (Authentik) ----
    # When all four are set, the /auth/oidc/* endpoints are enabled and the
    # frontend can offer "Log in with SSO". Unset = OIDC disabled, local login only.
    # Issuer is the per-app issuer, e.g. https://auth.example.com/application/o/freeframe/
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_redirect_uri: str | None = None

    @property
    def oidc_enabled(self) -> bool:
        return all([
            self.oidc_issuer,
            self.oidc_client_id,
            self.oidc_client_secret,
            self.oidc_redirect_uri,
        ])

    # ---- MCP OAuth (resource server only) ----
    # Freeframe validates tokens; it does not issue them. Almost no MCP server
    # runs its own authorization server — the common pattern is to delegate to an
    # IdP and implement only the resource-server half (token verification plus
    # RFC 9728 metadata), so that is what this does.
    #
    # Freeframe is the authorization server, not a relying party. Delegating was
    # the first plan, but client2.0 has no IdP and client current's Authentik
    # stamps the client_id into `aud` rather than this server's URI, so it cannot
    # satisfy the audience binding that separates the tenants. Issuing our own
    # tokens fixes that at the root.
    #
    # Explicit opt-in: off means API-key auth only, which is how both tenants ship.
    mcp_oauth_enabled_flag: bool = False
    # Canonical resource URI for RFC 8707 audience binding. MUST equal the URL the
    # user types into the client, path and trailing slash included, or discovery
    # fails. Both tenants run this code, so a token minted for one must not be
    # accepted by the other — which is only enforceable if this is exact.
    mcp_resource_url: str | None = None
    # RFC 7591 dynamic registration. Off because it is a SHOULD, not a MUST, and
    # Claude accepts a manually issued client ID — so an open registration
    # endpoint on the public internet adds an abuse surface for no gain.
    mcp_oauth_allow_dcr: bool = False

    @property
    def mcp_oauth_issuer_url(self) -> str:
        """Our own issuer: the bare origin.

        Not `/api`, even though that is the only prefix a tenant's proxy may route
        here by default. RFC 8414 locates an issuer's metadata by inserting
        /.well-known/ at the ROOT — for `https://host/api` that is
        `https://host/.well-known/oauth-authorization-server/api`, which lands on
        the frontend. A client that cannot read the document falls back to
        conventional root paths, which is how claude.ai ended up requesting
        `https://host/authorize` and getting a 404.

        Each tenant's proxy must therefore route /.well-known/oauth-*, /authorize,
        /token, /revoke and /register to this app unstripped.
        """
        return self.frontend_url.rstrip("/")

    @property
    def mcp_oauth_enabled(self) -> bool:
        return self.mcp_oauth_enabled_flag

    @property
    def mcp_canonical_resource(self) -> str:
        # Derived from frontend_url because Traefik routes only /api to this app
        # and strips the prefix, so the app never sees the public path itself.
        if self.mcp_resource_url:
            return self.mcp_resource_url
        return f"{self.frontend_url.rstrip('/')}/api/mcp/"

    @property
    def mcp_resource_metadata_url(self) -> str:
        """Where the RFC 9728 document is served.

        Not at the origin root: `/.well-known/*` there is served by the frontend,
        since Traefik only routes /api here. Clients are told the real location via
        the `resource_metadata` parameter on the 401, which the spec allows to be
        any HTTPS location.
        """
        return f"{self.frontend_url.rstrip('/')}/.well-known/oauth-protected-resource"

    # ---- Authentik portal (Phase 2 Shell) ----
    # freeframe's /portal/apps endpoint reads each user's launchable apps from
    # Authentik. Both must be set for the endpoint to work; otherwise it 503s.
    # api_base is the Authentik origin (no trailing slash), e.g.
    # https://deb-sso.debugged.com.my
    authentik_api_base: str | None = None
    authentik_service_token: str | None = None

    @property
    def portal_enabled(self) -> bool:
        return bool(self.authentik_api_base and self.authentik_service_token)

    # Public (machine-to-machine) API key for the external integration that pulls
    # videos out to other platforms (e.g. Meta). Sent in the X-API-Key header.
    # If unset, the /public/* endpoints return 503 (disabled).
    public_api_key: str | None = None

    # The shared "References" project — the swipe-file library the browser
    # extension clips ads into, and the source briefs pick reference media from.
    # It is an ordinary project; naming it here only changes two things:
    # its uploads skip the default task stage (so the admin task board is not
    # flooded with swipes), and the UI knows which tree to show in the picker.
    # Unset = no References library configured; the picker is simply hidden.
    references_project_id: str | None = None

    # Fallback owner for briefs imported from Creative Flywheel via
    # POST /public/v1/briefs when the brief has no resolvable owner email.
    # The account is auto-created (active, verified) if it does not exist.
    brief_import_fallback_email: str | None = None

    # Google service account key JSON *contents* (not a file path).
    # Required for the Drive → Backblaze sync feature.
    # Copy the full JSON from the downloaded GCP key file into .env.prod.
    google_service_account_json: str | None = None

    # Worker concurrency settings
    transcoding_concurrency: int = 2  # Number of concurrent video transcoding jobs
    email_concurrency: int = 2  # Number of concurrent email sending jobs
    
    # Email settings - supports AWS SES or any SMTP server
    # If mail_provider is "ses", uses AWS SES with aws_mail_* credentials
    # If mail_provider is "smtp", uses standard SMTP with smtp_* settings
    mail_provider: str = "ses"  # "ses" or "smtp"
    mail_from_address: str = "noreply@example.com"
    mail_from_name: str = "FreeFrame"
    
    # AWS SES settings
    aws_mail_access_key_id: str | None = None
    aws_mail_secret_access_key: str | None = None
    aws_mail_region: str = "ap-south-1"
    
    # SMTP settings (for non-SES providers like SendGrid, Mailgun, self-hosted)
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True

settings = Settings()
