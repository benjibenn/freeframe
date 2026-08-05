"""OAuth 2.1 authorization-server tables for the MCP endpoint.

claude.ai custom connectors are OAuth-only, so X-API-Key cannot reach them. Client
current has Authentik but client2.0 has no IdP and must not borrow the other tenant's
SSO, so Freeframe issues its own tokens.

Secrets, codes and tokens are stored as SHA-256 hashes only — the same choice
api_keys already makes, so a database dump yields nothing usable.

Revision ID: a5b462ca5336
Revises: e6f7a8b9c0d2
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a5b462ca5336"
down_revision = "e6f7a8b9c0d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "oauth_clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", sa.String(64), nullable=False),
        # Null for public clients, which authenticate with PKCE alone.
        sa.Column("client_secret_hash", sa.String(64), nullable=True),
        sa.Column("client_name", sa.String(255), nullable=False),
        sa.Column("redirect_uris", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("scope", sa.String(255), nullable=False, server_default=""),
        sa.Column("grant_types", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_oauth_clients_client_id", "oauth_clients", ["client_id"], unique=True)
    op.create_index("ix_oauth_clients_created_by", "oauth_clients", ["created_by"])

    op.create_table(
        "oauth_authorization_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("client_id", sa.String(64), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("redirect_uri", sa.String(2048), nullable=False),
        sa.Column("code_challenge", sa.String(255), nullable=False),
        sa.Column("code_challenge_method", sa.String(16), nullable=False, server_default="S256"),
        sa.Column("scopes", postgresql.JSONB(), nullable=False, server_default="[]"),
        # RFC 8707 resource indicator, carried onto the issued token.
        sa.Column("resource", sa.String(2048), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_oauth_authorization_codes_code_hash",
        "oauth_authorization_codes",
        ["code_hash"],
        unique=True,
    )
    op.create_index(
        "ix_oauth_authorization_codes_client_id", "oauth_authorization_codes", ["client_id"]
    )
    op.create_index(
        "ix_oauth_authorization_codes_user_id", "oauth_authorization_codes", ["user_id"]
    )

    op.create_table(
        "oauth_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("client_id", sa.String(64), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("scopes", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("resource", sa.String(2048), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        # Self-FK: refresh tokens rotate, and replaying a rotated token revokes the
        # whole chain rather than just failing one request.
        sa.Column(
            "rotated_from",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("oauth_tokens.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_oauth_tokens_token_hash", "oauth_tokens", ["token_hash"], unique=True)
    op.create_index("ix_oauth_tokens_kind", "oauth_tokens", ["kind"])
    op.create_index("ix_oauth_tokens_client_id", "oauth_tokens", ["client_id"])
    op.create_index("ix_oauth_tokens_user_id", "oauth_tokens", ["user_id"])
    op.create_index("ix_oauth_tokens_rotated_from", "oauth_tokens", ["rotated_from"])


def downgrade() -> None:
    # oauth_tokens first: it self-references, and nothing else points at it.
    op.drop_table("oauth_tokens")
    op.drop_table("oauth_authorization_codes")
    op.drop_table("oauth_clients")
