# ProSho — Progress

> Vertical-specific progress for ProSho (Project Showcase). Platform-level
> infra/architecture lives in [`PROGRESS.md`](PROGRESS.md) and the structure
> rules in [`CLAUDE.md`](CLAUDE.md) — read those first if you haven't.

---

## 🎯 NEXT SESSION PRIMARY TASK

**Phases 1 and 2 are code-complete and live (2026-10-17).** Their exit
checks both need the real HeatRisk EU repo, so the next step is the same
for both — get the pilot onto ProSho:

1. **First, two loose ends from 2026-10-17 (5 minutes):**
   - The first *scheduled* source check runs at **05:00 UTC on 2026-10-18**.
     Confirm it ran in production: the throwaway project
     `prod-p2-check-zz` (owner `prod-check-p2`, github_id `9190000020`) should
     have 3 new `source.*` evidence rows with `payload->>'trigger' = 'daily'`.
     Then **delete that user** (cascades to its project, claims, evidence,
     tokens) plus its audit rows — it's leftover test data.
   - The Jobref API cert (`api.jobref.lvamo.com`, expires 2026-11-16) should
     have auto-renewed at the 09:46 UTC certbot run on 2026-10-17 — the first
     real renewal since the 2026-10-11 fix. Confirm the new expiry.
2. **Founder dry run on `testproj1`** (signed in already, 2026-10-15): install
   the App on a scratch repo, add `prosho.yaml`, push → confirm the webhook
   sync; then create a CI token and run the GitHub Actions step once.
3. **Invite the HeatRisk EU student** (`PROSHO_SIGNUP_ALLOWLIST`, then
   restart the backend) → they connect the repo, add `prosho.yaml` with
   `data.sources` and metric claims, add the CI step → page **unlisted**.
   That closes Phase 1's exit check, and Phase 2's once their CI reports
   evidence and the daily source check shows on the page.

Then Phase 3 (work over time: commit timeline, milestones, mentor role +
feedback, admin mentor assignment, page-view counts).

---

## Status

**Phase 2 (Evidence + data module) — code complete and live, 2026-10-17**
(`083ed1b`, migration `0025`). Exit check pending the real pilot (banner).

### Phase 2 — what was built

- **Tables** (`0025`): `prosho.evidence` — append-only; unique per
  (project, key, commit) when a commit is given, so CI retries are
  idempotent; scheduler rows just accumulate. `prosho.ingest_tokens` —
  `psho_` + 32 random bytes, only the SHA-256 stored, prefix kept for
  display, shown once, max 10 active per project, revocable, `last_used_at`.
  `projects.module_config` (JSONB) — the validated `data:`/`frontend:`
  section from prosho.yaml, so scheduled checks need no GitHub call and new
  modules need no schema change.
- **`POST /ingest/evidence`** (ingest token, no JWT): ≤ 50 items, ≤ 64 KB
  (413), each item validated alone → `accepted` / `duplicate` / `rejected`
  + reason. Kinds: `metric` (value_num), `check` (pass/fail/warn), `run`
  (success/failure/cancelled); optional unit, payload ≤ 4 KB, `claim` link
  by id. `source.*` keys are reserved for LVAMO's own checks.
  `artifact` uploads are Phase 4.
- **Computed claim status** (`services/claim_status.py`): latest metric for
  the claim's `metric_key` vs target (`gte`, `lte`, `abs_lte`, `between`,
  `eq` with float tolerance; NaN never meets) → `met` / `not_met` /
  `awaiting_evidence`. `services/claims_view.py` resolves claims once for
  both the owner dashboard and the public page, including the deciding
  value, unit, time and commit.
- **Data module** (`modules/`): daily source health checks at **05:00 UTC**
  (`app/prosho/scheduler.py`, ProSho's own AsyncIOScheduler started in
  `main.py`'s lifespan). Production runs **2 uvicorn workers**, so the job
  takes a Postgres advisory lock and skips projects checked in the last 20 h
  — verified in prod: two simultaneous runs wrote one set of rows. On-demand
  "Check now" (owner, max once per 10 min → 429). Panels: Results (metrics
  vs targets), Pipeline (latest run per key, tests, duration), Data sources
  ("checked daily by LVAMO — not reported by the student").
- **SSRF-safe fetcher** (`services/safe_fetch.py`, plan §11 — built and
  tested before the scheduler job, as the plan's risk table requires):
  http/https only; no URL credentials; every resolved address must be
  public (private, loopback, link-local incl. 169.254.169.254, multicast,
  reserved, IPv4-mapped IPv6 all refused); the connection is **pinned to the
  checked IP** (Host header + TLS SNI keep normal certificate checking —
  confirmed live: real sites pass, expired/wrong-host certs fail); redirects
  re-checked (max 3); 10 s; 64 KB. DNS failure is reported as "down", not as
  a security block.
- **Owner UI:** "Evidence from CI" (create token → shown once with the
  repo-secret instructions, an example `prosho-evidence.json` built from the
  project's own metric keys, and a copy-paste GitHub Actions step using
  `jq` + `curl`; list/revoke), "Data sources" with Check now, "Recent
  evidence" table; claims card shows computed status + latest value.
- **Public page:** claims show the latest value; Results / Pipeline / Data
  sources panels for data-science projects.

**Tests:** 41 new (claim operators 16, SSRF guard 17, ingest/tokens/panels/
daily job 8) → **83 total** (incl. Applaut's 4 from `002f6e6`).

**Verified locally:** real browser, desktop + phone: token created through
the UI, evidence sent with the exact `jq | curl` step → claim flipped to
✓ Met; Check now hit real URLs (Eurostat, Copernicus up; a dead domain
down); public page panels; no console errors, no horizontal scroll.

**Verified in production** (throwaway project): ingest 2 accepted + the
spoofed `source.` key rejected; same-commit retry → 2 duplicates; no token →
401; claim `met` from 0.93 ≥ 0.9; **2 concurrent daily runs → exactly 3
source rows**; from the VM, Eurostat up, dead domain down, cloud metadata
address refused; Check now right after → 429; page rendered on
`www.lvamo.com` with all panels, no console errors.

**Not verified yet:** the first *scheduled* 05:00 UTC run in production
(see banner, step 1).

**Phase 1 (Core page) — code complete and live, 2026-10-15.** Exit check
pending real users (see the banner above). Shipped in four slices, each
tested locally, deployed and re-verified in production before the next.

### Phase 1 — what was built

**1. GitHub sign-in** (`5d94fdf`). `/auth/github/authorize` → GitHub →
`/auth/github/callback` (signed 10-min `state`; upsert by GitHub's numeric
id; display fields refreshed every sign-in) → redirect to
`/prosho/auth/callback#code=…` with a **2-minute login code in the URL
fragment** → frontend POSTs it to `/auth/exchange` for the access token
(`vertical: prosho`). The access token never appears in a URL; the
fragment is never sent to a server. Closed beta: new accounts need their
GitHub login in **`PROSHO_SIGNUP_ALLOWLIST`** (env var, comma-separated;
prod value `vsvedantham`); existing accounts can always sign in unless
deactivated. A 401 anywhere signs the user out. *Known limit:* the login
code is time-limited, not single-use.

**2. Projects, visibility, audit log** (`1825a10`, migration `0023`).
`prosho.projects` + `prosho.audit_logs`. `GET/POST /projects`,
`GET/PATCH /projects/{id}`; someone else's project → 404. Slugs: 3–60
chars, lowercase/digits/hyphens, reserved words (`schemas/project.py`),
**locked once the page has ever been shared** (`published_at`). Public
needs supervisor confirmation (API **and** DB CHECK); approval can't be
withdrawn while public. Every change is audited with before/after. UI:
project list, new-project form (slug from title), manage page.
Shared `index.css` fix: checkboxes/radios were rendered as empty text-field
boxes app-wide (also fixes Applaut's Opportunities keyword checkboxes).

**3. GitHub repo connection, `prosho.yaml` sync, claims** (`c71f68f`,
migration `0024`). `prosho.claims` (+ `projects.manifest_checked_at`).
- Parser (`services/manifest.py`): pydantic v1 schema + YAML node tree →
  every error has a line number and path; catches duplicate YAML keys,
  misspelt fields, duplicate claim ids, the wrong module section for the
  type; 64 KB cap. Module sections live in `app/prosho/modules/`
  (`data_science.DataSection`, `frontend.FrontendSection`).
- Connect: the backend asks GitHub for the App installation on the
  signed-in user's **own personal account** (matched by numeric id) and
  only offers repos from it; nothing from the browser is trusted. One
  project per repo (partial unique index). Orgs not supported in beta.
- Sync on connect, "Sync now", and the **HMAC-verified push webhook**
  (default branch only, background task). A failed sync records the error
  and keeps the last good story. The manifest owns title/summary/problem/
  type/demo/claims; claims upsert by id, archived when dropped (and
  restored if re-added), manual status kept. Uninstall/repo-removed events
  mark access lost; disconnect unlocks the story fields and archives claims.
- Claims: status set by hand only for claims without a metric; measured
  claims say "awaiting evidence" until Phase 2.
- UI: repository card (install → pick → status with **line numbers linked
  to the file on GitHub**, starter `prosho.yaml`, Sync now, Disconnect),
  claims card. The App's Setup URL (`/prosho/projects/new`) forwards to the
  project via the install `state`.

**4. Public page** (`8470ede`). `GET /public/projects/{slug}`:
unlisted/public for anyone; private only as an **owner preview** (optional
auth — a junk token just means anonymous); inactive project/owner → 404.
`Cache-Control: no-cache` (`private, no-store` for previews) so making a
page private takes effect at once. Page at `/prosho/:slug`: type chip,
title, summary, student byline (links to their GitHub), problem, claims
tracker with status pills, Streamlit embed (`?embed=true`, sandboxed) plus
a wake-up note and open-in-new-tab fallback, small "Built with LVAMO
ProSho" footer, `noindex` unless public, not-found page.

**Tests:** pytest added (`backend/requirements-dev.txt`, installed only in
the dev image; run `docker compose exec backend python -m pytest`).
**38 tests**: sign-in 8, projects 8, manifest 11, GitHub/sync/webhook 8,
public page 3. GitHub's HTTP calls are faked; everything else (DB, JWTs,
routing) is real.

**Verified locally** each slice in a real browser at desktop and phone
widths (no horizontal scroll, no console errors), plus migrations
`0023`/`0024` up/down/up with zero model-vs-DB diffs.

**Verified in production:**
- Sign-in: authorize → github.com with the prod client id and redirect
  URI; denied/forged-state callbacks redirect to `/prosho/login?error=…`;
  junk code 400; `/me` without a token 401; CORS for `www.lvamo.com`.
  `VITE_PROSHO_API_BASE_URL` now confirmed in the live bundle (closes
  Phase 0's open item).
- Projects: create 201, duplicate slug 409, reserved slug 422, someone
  else's project 404, public without supervisor 409, with it 200.
- Webhook: unsigned → 401; **GitHub's own ping, redelivered via the App
  API, signed with the real secret → 200 `pong`**.
- Public page: private anonymous 404, owner preview flag, unlisted 200
  with `no-cache`; the page rendered on `www.lvamo.com` with claims, demo
  link and `noindex`, no console errors; unknown slug shows not-found.
- All throwaway prod data deleted afterwards (ProSho tables back to 0
  rows). Applaut/Jobref unaffected (health 200 after every deploy).

**Not verified yet (needs a real person):** the real GitHub consent
screen, a real App installation, and a real `prosho.yaml` fetch + push —
that's the exit check in the banner.

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

### 2026-10-17 — Phase 2 built and deployed
- Evidence ingestion with per-project tokens, computed claim statuses, the
  data module (daily SSRF-safe source checks + results/pipeline/sources
  panels). Migration `0025`. 83 tests.
- Found while designing the scheduler: prod runs 2 uvicorn workers, each
  with its own scheduler, so Applaut's discovery would run twice per
  profile once enabled. Flagged as a separate task; fixed the same day in
  another session (`002f6e6`, `1d756e2` — see `PROGRESS_APPLAUT.md`).

### 2026-10-15 — Phase 1 built and deployed
- Four slices, each live and production-verified: GitHub sign-in;
  projects + visibility + audit log (`0023`); repo connection + manifest
  sync + claims + webhook (`0024`); the public page. 38 tests.
- Bugs caught along the way: sync error paths read an expired
  `updated_at` after commit (async lazy-load crash) → always
  commit-and-refresh; the public API first sent `Cache-Control: public,
  max-age=60`, which would have kept a just-made-private page visible for
  a minute → `no-cache`.

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
