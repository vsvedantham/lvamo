# ProSho — Progress

> Vertical-specific progress for ProSho (Project Showcase). Platform-level
> infra/architecture lives in [`PROGRESS.md`](PROGRESS.md) and the structure
> rules in [`CLAUDE.md`](CLAUDE.md) — read those first if you haven't.

---

## 🎯 NEXT SESSION PRIMARY TASK

**Phase 1 — Core page** of [`docs/prosho/BETA_PLAN.md`](docs/prosho/BETA_PLAN.md)
§12 (target Oct 19 – Nov 1): GitHub OAuth sign-in, projects CRUD, GitHub App
+ webhook + `prosho.yaml` sync, claims, public page, visibility + supervisor
confirmation, audit log. Exit check: HeatRisk EU page live as *unlisted*,
built from its real repo.

**Blocked on the user first:**
1. Answers to the plan's §16 open questions (sign-in method, mentor naming,
   pilot #2, supervisor contact, URL). Still unanswered as of 2026-10-13.
2. ~~GitHub App~~ **Done 2026-10-13**, see "GitHub App" below.

First code task once unblocked: GitHub OAuth sign-in. That will also be
the first real use of `frontend/src/prosho/api/client.ts`, which confirms
`VITE_PROSHO_API_BASE_URL` reaches the build (see below).

---

## Status

**Phase 0 (Foundation) — done and live, 2026-10-13.** Exit check passed:
`GET https://api.prosho.lvamo.com/api/v1/prosho/health` → 200
(`{"status":"ok","service":"prosho-api"}`), served with a valid
`CN=api.prosho.lvamo.com` cert.

### GitHub App (2026-10-13, ready for Phase 1)

There's **one GitHub App, not an OAuth App plus a GitHub App**. A GitHub
App also does user sign-in, and GitHub recommends Apps over OAuth Apps.
This means fewer secrets and a single consent screen. The beta plan was
updated to match.

- `lvamo-prosho` (https://github.com/apps/lvamo-prosho), App ID `5295836`,
  client ID `Iv23liqTfRG7KW3CswoE`, owner `vsvedantham`. Installable by
  **any account** (confirmed public via an unauthenticated API lookup).
- Callback URLs: `https://api.prosho.lvamo.com/api/v1/prosho/auth/github/callback`
  and the `http://localhost:8000/...` equivalent. Setup URL (after install):
  `https://www.lvamo.com/prosho/projects/new`, with redirect-on-update
  turned on. Authorization during installation is **off**, so sign-in and
  install stay separate steps.
- Webhook: `https://api.prosho.lvamo.com/api/v1/prosho/github/webhook`,
  JSON, SSL verification on, secret set. That route doesn't exist until
  Phase 1, so GitHub's initial ping failed, which is expected.
- Permissions: Contents read, Metadata read, Email addresses read. Event:
  push.
- **Secrets**: the masters are in `~/.config/lvamo/prosho/` on the Mac
  (`client-secret`, `private-key.pem`, `webhook-secret`; dir 700, files
  600). They're loaded into the local `.env` and prod `.env.production` as
  `PROSHO_GITHUB_*` (private key base64 on one line), file to file, never
  printed. Settings fields are in `backend/app/config.py`. The prod
  `.env.production` was tightened from 644 to 600 at the same time.
  Backup: `/home/ubuntu/backups/.env.production.bak-20261013`.
- **Verified** against GitHub's API: the private key authenticates as the
  App and the client id matches; permissions and events are exactly as
  above; the webhook config is as above; the client secret is accepted
  (via the bogus-token check on `POST /applications/{client_id}/token`,
  which returns 404 for valid credentials, not 401). Inside both the local
  and the **prod** backend containers, Settings load all 7 values, the key
  decodes to a PEM, and `python-jose` RS256 + `httpx` get `GET /app` →
  200 as `lvamo-prosho`.

### Phase 0 — what was built

**Backend** (`backend/app/prosho/`, same shape as Jobref/platform):
- `api/v1/router.py` + `api/v1/routers/health.py`, mounted at
  `/api/v1/prosho` in `main.py`.
- `models/prosho_user.py` (`ProshoUser`): `github_id` (BIGINT, unique,
  GitHub's stable numeric id, the dedup key), `github_login`, `name`,
  `email`, `avatar_url`, `role`, `is_active`, plus the shared id and
  timestamp mixins. No password column, since sign-in is GitHub-only per
  plan §8. `models/enums.py` (`ProshoUserRole`: student/mentor/admin) is a
  **native Postgres enum in the `prosho` schema**
  (`prosho.user_role_enum`), as the plan specifies. That follows Applaut's
  style, not Jobref's VARCHAR + CHECK.
- Empty `schemas/` and `services/` packages, ready for Phase 1.

**Migration `0022_prosho_schema.py`**: `CREATE SCHEMA prosho`, the enum type,
`prosho.users`. Downgrade drops all three. Model registered in
`migrations/env.py`.

**Frontend** (`frontend/src/prosho/`):
- `api/client.ts`: axios instance on `VITE_PROSHO_API_BASE_URL` +
  `/api/v1/prosho`, token key `prosho_access_token`. Nothing imports it yet,
  so Vite drops it from the bundle. `components/` and `context/` come with
  Phase 1's auth.
- `pages/Prosho.tsx`: a placeholder landing page at `/prosho` ("In
  development", "Not open for sign-ups yet"). The real landing and gallery
  come in later phases.
- Hub card (`pages/Hub.tsx`, status "Coming soon"), **hidden** because
  `prosho` isn't in `platform.settings.verticals_enabled` (prod value is
  still `jobref`).

**Infra:**
- Cloudflare DNS `A api.prosho.lvamo.com → 130.61.106.172`, DNS-only.
- Webroot cert (`certbot certonly --webroot`), expires 2027-01-11. Renewal
  config uses `authenticator = webroot`, so the existing timer and nginx
  reload hook cover it.
- `nginx/nginx.conf` server block. Tested in a throwaway container, then
  `docker compose restart nginx` (bind-mount gotcha, see `PROGRESS.md`).
- Cloudflare Pages production env var
  `VITE_PROSHO_API_BASE_URL=https://api.prosho.lvamo.com`, set via API.
  `.env.example` lists it too.

**Verified locally:** migration up, down and up again clean; `alembic
autogenerate` comparison shows zero diffs between the model and the DB for
`prosho`; an ORM insert/read/delete round trip (role defaults to
`student`, `is_active` to true); `tsc` and `vite build` clean. In a real
browser at desktop and mobile widths: `/prosho` renders, the hub card
links to it when enabled locally, and there are no console errors. The
local setting was reverted afterwards.

**Verified in production:** `deploy.sh` ran migration `0021 → 0022`;
`alembic_version` = `0022`, `prosho.users` exists (0 rows); ProSho
health 200 with the correct cert; Applaut, Jobref and platform endpoints
all still 200; Applaut/Jobref user and request counts unchanged (2/7/1).
Pages deployed `b9ee675`: `www.lvamo.com/prosho` renders the placeholder,
the hub still shows only Jobref, no console errors.

**Not verified yet:** that `VITE_PROSHO_API_BASE_URL` reaches the built
bundle. The client is tree-shaken out until something calls it, so Phase 1's
first API call is the check.

## Decisions so far

- **Name:** ProSho = *Pro*ject *Sho*wcase. Third LVAMO vertical, alongside
  Applaut and Jobref; follows the vertical pattern in `CLAUDE.md` everywhere
  (code folders, `/api/v1/prosho`, `api.prosho.lvamo.com`, schema `prosho`,
  `/prosho/*` routes, `VITE_PROSHO_API_BASE_URL`, R2 prefix `prosho/`).
- **Product shape:** shared core (problem, claims tracker, demo slot, work
  timeline, mentor feedback, outcome) + one evidence module per project
  type. Beta ships the data science and frontend modules — the frontend one
  is the proof that the core generalises.
- **Don't rebuild Streamlit:** student dashboards are embedded, with
  natively-rendered results cards above them.
- **First pilot:** HeatRisk EU (MSc Data Science capstone, UE Potsdam).
- **Academic integrity:** private by default; public only after the
  student confirms supervisor approval; LVAMO branding kept small.

## Artifacts

- [`docs/prosho/BETA_PLAN.md`](docs/prosho/BETA_PLAN.md) — the full beta plan
  (scope, roles, architecture, manifest, schema, API, pages, security,
  timeline, testing, risks, assumptions, open questions).
- [`docs/prosho/ProSho-concept-deck.pptx`](docs/prosho/ProSho-concept-deck.pptx)
  — 14-slide concept deck comparing HeatRisk EU with a made-up frontend
  project (TransitBuddy). All example values in it are illustrative.

## Session log

### 2026-10-13 — Phase 0 shipped
- Built and deployed the foundation listed under "Status" above, in one
  session: backend skeleton, migration `0022`, frontend skeleton + hidden
  hub card, `api.prosho.lvamo.com` (DNS, cert, nginx), Pages env var.
- Before this, the same session renamed the repo and Compose project to
  `lvamo` and made bare `lvamo.com` serve the site (see `PROGRESS.md`).

### 2026-10-11 — idea → name → plan
- Idea came from helping a friend's MSc Data Science capstone (HeatRisk EU).
  Explored what a capstone platform should offer beyond Streamlit hosting;
  the user pushed back that the first tool list was HeatRisk-specific, which
  led to the shared core + per-type module design.
- Built the concept deck (HeatRisk EU vs a made-up frontend project,
  TransitBuddy). The user reviewed it in Keynote and liked it.
- Named the vertical **ProSho**; wrote the beta plan; created this file,
  the `/prosho` skill, and a ProSho row in `CLAUDE.md`/`PROGRESS.md`/`README.md`.
- Before ProSho, cleaned up platform naming so it has a correct pattern to
  follow (platform settings schema, `api.lvamo.com`, `CLAUDE.md` split) —
  see `PROGRESS.md` session log.
