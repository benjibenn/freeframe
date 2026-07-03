# End-to-end browser tests

Playwright suite that logs in as a real user and drives each page in a real
browser. Use it after any feature change to confirm the app still renders and
behaves — this is the "did I break anything" gate that unit tests + `tsc` can't
give you.

## What it covers

- **`smoke.spec.ts`** — every key page loads without crashing: not bounced to
  `/login`, key landmark visible, no uncaught JS errors, no 5xx from our API.
  Screenshots every page into `e2e/screenshots/`.
- **`lazy-loading.spec.ts`** — the infinite-scroll / reveal-on-scroll behaviour on
  the library, my-assets, project-detail, and projects-list pages: the list grows
  as you scroll. Skips a page if the account lacks enough data to trigger it.

## Prerequisites

1. **The stack must be running** — web on `:3000` and API on `:8000` (or point the
   env vars below elsewhere). Start them however you normally do (e.g. `npm run dev`
   in `apps/web`, and the FastAPI app in `apps/api`).
2. **A login account with a password.** The app is magic-code / SSO first, so many
   accounts have no password. Run `PYTHONPATH=. uv run python apps/api/scripts/seed_e2e.py`
   to create `admin@demo.com` / `password123` (the defaults here) **plus** enough
   projects/assets to actually exercise the infinite-scroll tests. For other
   environments set `E2E_EMAIL` / `E2E_PASSWORD` to an account that has a password.
3. **Browsers installed once:** `npx playwright install chromium`.

### Bringing up a local stack from scratch

```bash
createdb freeframe_dev
# root .env with at least: DATABASE_URL, REDIS_URL, JWT_SECRET (see .env.example)
cd apps/api && uv run alembic upgrade head && cd ../..
PYTHONPATH=. uv run python apps/api/scripts/seed_e2e.py
PYTHONPATH=. uv run uvicorn apps.api.main:app --port 8000    # API
cd apps/web && printf 'NEXT_PUBLIC_API_URL=http://127.0.0.1:8000\n' > .env.local && npm run dev  # web
```

Notes:
- The API's startup checks the S3 bucket, so it needs object storage reachable at
  `S3_ENDPOINT`. Run MinIO, or (for a data-only run where thumbnails don't matter)
  point `S3_ENDPOINT`/`S3_PUBLIC_ENDPOINT` at any endpoint that 200s a `HEAD` — broken
  thumbnails are ignored by the harness since they aren't app/API-origin requests.
- **CORS:** browse at `http://localhost:3000` (in the API's allow-list), not
  `127.0.0.1:3000`, or every API call fails preflight.

## Run

```bash
cd apps/web
npm run test:e2e            # headless, all tests
npm run test:e2e -- --headed        # watch it drive the browser
npm run test:e2e -- smoke           # just the smoke suite
npm run test:e2e:ui                 # interactive UI mode
npm run test:e2e:report             # open the last HTML report
```

## Configuration (env vars)

| Var | Default | Meaning |
| --- | --- | --- |
| `E2E_BASE_URL` | `http://localhost:3000` | Web app URL |
| `E2E_API_URL` | `http://localhost:8000` | FastAPI URL (used for login) |
| `E2E_EMAIL` | `admin@demo.com` | Login email (needs a password) |
| `E2E_PASSWORD` | `password123` | Login password |
| `E2E_PROJECT_ID` | *(first project)* | Project to open for the detail test |

Copy `.env.e2e.example` and source it, or pass inline:

```bash
E2E_BASE_URL=https://review.debugged.com.my \
E2E_API_URL=https://api.review.debugged.com.my \
E2E_EMAIL=you@example.com E2E_PASSWORD=... \
npm run test:e2e -- smoke
```

> Running against production only reads data (navigates + scrolls), but be aware
> it logs in as whoever you configure.

## How auth works

`auth.setup.ts` runs first: it POSTs to `/auth/login`, then seeds the browser with
both the `ff_access_token` / `ff_refresh_token` **localStorage** entries (the source
of the Bearer header) and the matching **cookies** (read by Next middleware), and
saves that as `e2e/.auth/state.json`. Every other test reuses it, so login happens
once per run. That file (and `screenshots/`, `report/`, `test-results/`) is
git-ignored.

## Extending it for new features

Add a spec in `e2e/`. Use the shared helpers:

```ts
import { watchForErrors, assertHealthy, snap, countAfterScroll } from './helpers'
```

For any new list/grid, add a `data-testid` to the card and assert on it — that's
what keeps these tests stable as markup changes.
