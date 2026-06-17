# Authentik SSO — Standup & Wiring Runbook

Self-hosted OIDC identity provider for the Creative Flywheel. One team login,
trusted by all four apps (freeframe, creative-flywheel, UploadUnicorn, adstash).

**Where domains live:** `.env.authentik` is the single source of truth. Edit a
domain there → re-apply the blueprint (step 4). Nothing is hardcoded.

**Scope:** internal team only. External clients keep freeframe's share-link /
guest access and are never added here.

---

## 0. Prerequisites (you, on the freeframe server)

- freeframe's `docker-compose.prod.yml` stack is already running (Traefik live).
- A DNS `A` record for `AUTHENTIK_DOMAIN` (e.g. `auth.example.com`) → the freeframe host.
- DNS records already exist for each app's domain (they're in production).

## 1. Configure

```bash
cd infra/authentik
cp .env.authentik.example .env.authentik
```

Fill in `.env.authentik`. Generate secrets:

```bash
openssl rand -base64 60 | tr -d '\n'   # AUTHENTIK_SECRET_KEY
openssl rand -base64 24                 # AUTHENTIK_BOOTSTRAP_PASSWORD
openssl rand -base64 36 | tr -d '\n'    # AUTHENTIK_PG_PASSWORD
openssl rand -base64 48 | tr -d '\n'    # each *_OIDC_CLIENT_SECRET (one per app)
```

Find freeframe's Docker network name and set `FREEFRAME_NETWORK`:

```bash
docker network ls | grep default     # e.g. freeframe_default
```

## 2. Bring Authentik up

```bash
docker compose --env-file .env.authentik -f docker-compose.authentik.yml up -d
docker compose --env-file .env.authentik -f docker-compose.authentik.yml logs -f authentik-server
```

Wait for Traefik to issue the TLS cert, then open `https://<AUTHENTIK_DOMAIN>/if/admin/`
and log in as `akadmin` with `AUTHENTIK_BOOTSTRAP_PASSWORD`.

## 3. (Sanity) confirm the issuer is reachable

```bash
curl -s https://<AUTHENTIK_DOMAIN>/application/o/freeframe/.well-known/openid-configuration | jq .issuer
```

Each app's OIDC endpoints are:
- **Issuer:** `https://<AUTHENTIK_DOMAIN>/application/o/<app-slug>/`
- Discovery: append `.well-known/openid-configuration`
- App slugs: `freeframe`, `creative-flywheel`, `uploadunicorn`, `adstash`

## 4. Apply the OIDC blueprint (registers all four apps)

The blueprint at `blueprints/flywheel-oidc.yaml` is auto-discovered. To apply/refresh:

- **Admin UI:** Customize → Blueprints → find `flywheel-oidc-apps` → it should show
  **Successful**. Use the ↻ button to re-apply after editing `.env.authentik`
  (re-create the containers so the worker picks up new env: `up -d --force-recreate
  authentik-server authentik-worker`).
- **Verify:** Applications → you should see FreeFrame, Creative Flywheel,
  UploadUnicorn, adstash, each with an OAuth2 provider.

> **If the blueprint shows an error** (schema drift between Authentik versions —
> most likely `redirect_uris` or `signing_key`): create one provider+application
> manually in the UI to see the expected shape, then fix `flywheel-oidc.yaml` to
> match. The `.env`-driven values stay the same; only the YAML keys change.

## 5. Wiring each app (done in each app's own repo + `.env`)

Each app reads these from its OWN environment. Copy the matching values from
`.env.authentik`. The integration code per app is built in separate worktrees.

| Env var (per app) | Value |
|---|---|
| `OIDC_ISSUER` | `https://<AUTHENTIK_DOMAIN>/application/o/<app-slug>/` |
| `OIDC_CLIENT_ID` | the app's `*_OIDC_CLIENT_ID` |
| `OIDC_CLIENT_SECRET` | the app's `*_OIDC_CLIENT_SECRET` |
| `OIDC_REDIRECT_URI` | the app's `*_OIDC_REDIRECT_URI` |

(Exact var names per app are finalized in each app's integration; the four values
above are what every app needs.)

## 6. Single logout

RP-initiated logout endpoint: `https://<AUTHENTIK_DOMAIN>/application/o/<app-slug>/end-session/`.
Each app's logout redirects here after clearing its local session. Wired in the
cross-app logout task (last plan in Phase ①).

---

## Teardown / rollback

Authentik runs in its own containers with its own volumes — it does **not** touch
freeframe's data. To remove it entirely:

```bash
docker compose --env-file .env.authentik -f docker-compose.authentik.yml down
# add -v to also delete authentik's database volumes (irreversible)
```

Apps fall back to their existing local login as long as their OIDC env vars are unset.
