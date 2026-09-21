#!/usr/bin/env bash
# ============================================================
# Deploy this working tree to the hetzmet tenant via rsync.
#   freeframe.multiadsx.com  →  root@135.181.29.2  (ssh alias: hetzmet)
#
# This tenant has NO git and NO GitHub deploy key. Whatever is in
# your local working tree right now is what ships — including
# uncommitted changes. That is the point, but check `git status`
# first if you care.
#
# Usage:
#   ./deploy-hetzmet.sh              # sync + rebuild + restart
#   ./deploy-hetzmet.sh --dry-run    # show what would transfer, change nothing
#   ./deploy-hetzmet.sh --no-build   # sync + restart only (config/env tweaks)
# ============================================================
set -euo pipefail

HOST="hetzmet"
DEST="/opt/freeframe"
COMPOSE="docker compose --env-file .env.prod -f docker-compose.prod.yml -f docker-compose.hetzmet.yml"

DRY_RUN=""
DO_BUILD=1
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN="--dry-run" ;;
    --no-build) DO_BUILD=0 ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

cd "$(dirname "$0")"

# --delete keeps the server an exact mirror, so deleted files actually
# disappear instead of lingering as stale imports. Excluded paths are
# NOT deleted by rsync, which is what protects the server's .env.prod.
#
# .env.prod is deliberately excluded: it holds this tenant's own DB
# password, Redis password, JWT secret and Backblaze keys, and must
# never be overwritten by (or copied from) a local file.
#
# .claude/ is excluded because Claude Code puts its worktrees under
# .claude/worktrees — each one a full second copy of this repo. The
# '.worktrees/' pattern never matched that nested path, so they shipped
# to production until 2026-08-04. Nothing under .claude/ is needed to
# build or run the app.
# NOTE: macOS ships openrsync (advertises "rsync 2.6.9 compatible"), which
# lacks --info=stats1 and --human-readable. --stats works on both, so this
# stays portable if you later install GNU rsync via Homebrew.
rsync -az --delete --stats $DRY_RUN \
  --exclude '.git/' \
  --exclude '.env' \
  --exclude '.env.local' \
  --exclude '.env.prod' \
  --exclude '.venv/' \
  --exclude 'node_modules/' \
  --exclude '.next/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '.pytest_cache/' \
  --exclude '.worktrees/' \
  --exclude '.claude/' \
  --exclude '.playwright-mcp/' \
  --exclude 'test-results/' \
  --exclude 'playwright-report/' \
  --exclude 'access.json' \
  --exclude '.DS_Store' \
  ./ "$HOST:$DEST/"

if [ -n "$DRY_RUN" ]; then
  echo "dry run — nothing changed on $HOST"
  exit 0
fi

if [ "$DO_BUILD" -eq 1 ]; then
  ssh "$HOST" "cd $DEST && $COMPOSE build"
fi
ssh "$HOST" "cd $DEST && $COMPOSE up -d && docker image prune -f >/dev/null"

# The api container runs `alembic upgrade head` on start, so migrations
# apply themselves. Print the head to confirm they actually landed.
echo "--- migration head ---"
ssh "$HOST" "docker exec -w /workspace/apps/api freeframe-api-1 alembic current 2>&1 | tail -1"
echo "--- services ---"
ssh "$HOST" "cd $DEST && $COMPOSE ps --format '{{.Service}}\t{{.State}}\t{{.Status}}'"
