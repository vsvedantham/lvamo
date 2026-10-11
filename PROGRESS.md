# LVAMO — Master Progress

> **How to use this file**
> This is the **platform-level** file — shared infra, cross-vertical
> architecture, and ground rules. Vertical-specific work (features, DB
> schema, roadmap) lives in its own file: `PROGRESS_APPLAUT.md`,
> `PROGRESS_JOBREF.md`, `PROGRESS_PROSHO.md`. Platform-wide structure rules
> live in `CLAUDE.md`.
>
> At the start of a session: read **this file first**, then whichever
> vertical file(s) are relevant to the work at hand.
> At the end of a session: "save progress" — update this file if anything
> platform-level changed, and/or the relevant vertical file(s), then commit.
>
> **Scoping a session to one vertical**: invoke `/applaut`, `/jobref` or `/prosho` at
> the start of a session (`.claude/skills/applaut/`,
> `.claude/skills/jobref/`) to restrict that session to one vertical's own
> files only — touching the other vertical's code or shared platform files
> then requires flagging to the user first. No skill invoked = full-platform
> scope (today's default). See either skill file for the exact in/out-of-
> scope path lists.

---

## Session log — 2026-10-11 (latest)

Picked up after ~7 weeks idle (last commit 2026-08-19). Work moved from the
Windows laptop to a Mac this session. Done, all deployed and verified in
production unless noted:

1. **TLS cert auto-renewal fixed** — `api.applaut.lvamo.com` still renewed
   via `standalone` (fails: nginx holds port 80) and no cert had an nginx
   reload hook. Re-issued with webroot (now expires 2027-01-09) + hook
   installed; dry-run renewal passes for every cert. See Deployment.
2. **Jobref evidence-view feature confirmed live** (it was built and pushed
   in Aug but never recorded as deployed).
3. **Platform layer created** — `backend/app/platform/`, schema `platform`,
   `/api/v1/platform`, hostname `api.lvamo.com`. `verticals_enabled` moved
   there from `applaut.application_settings`; the hub reads it from
   `api.lvamo.com`. Migrations `0020`, `0021`. See "Platform settings move".
4. **`CLAUDE.md` is now the LVAMO master spec** (structure rule table for
   every vertical + add-a-vertical checklist); Applaut's spec moved to
   `docs/applaut/SPEC.md`. README, `deploy.sh` header, frontend package
   name and FastAPI title no longer say Applaut.
5. **ProSho planned** — third vertical; see `PROGRESS_PROSHO.md` and
   `docs/prosho/BETA_PLAN.md`.
6. **Claude's infra access from the Mac** — `ssh lvamo-prod` (alias in
   `~/.ssh/config`), Cloudflare API token (`~/.cloudflare/token`: DNS for
   `lvamo.com` + Pages), OCI API key (`~/.oci/`, new key; old Windows key
   deleted). Claude Code allow rules for `ssh lvamo-prod` and
   `git push origin main` live in `.claude/settings.local.json`
   (gitignored, this Mac only).
7. **Mac local dev**: Docker Desktop; local Postgres volume is fresh (all
   migrations applied; only the Applaut `verify2@test.com` test account, see
   `PROGRESS_APPLAUT.md`). `.claude/launch.json` starts the frontend
   dev server for Claude's browser preview.
8. **Bare `lvamo.com` fixed**: it never served the site. Its two A records
   pointed at a registrar parking page and Cloudflare returned 522. Replaced
   them with a proxied apex CNAME → `lvamo.pages.dev`, added `lvamo.com` as a
   Pages custom domain (active), and added `https://lvamo.com` to prod
   `BACKEND_CORS_ORIGINS`. Verified: apex serves the hub (deep links too),
   CORS header returned for the apex origin, hub's platform call works from
   the apex in a real browser. Zoho MX/TXT records untouched.
9. **Compose project + VM dir renamed to `lvamo`**: both compose files pin
   `name: lvamo`. On the VM: `pg_dump` backup → old stack `down` → data
   copied `lvamo-applaut_postgres_data` → `lvamo_postgres_data` → dir moved
   `/home/ubuntu/lvamo-applaut` → `/home/ubuntu/lvamo` → `up -d`. ~17 s of
   downtime. Verified: row counts identical before/after, alembic at `0021`
   head, all API hostnames + both frontend hostnames 200, both bad-login
   checks 401, LinkedIn authorize 307, cert reload hook finds the new nginx
   container. Local Mac stack moved to the `lvamo` project the same way.
10. **Housekeeping**: `frontend/package-lock.json` committed (a clean
    `npm install` leaves it unchanged; build passes), the unused
    `lvamo-logo-1024.png` gitignored as a local design source, stale notes in
    the progress files fixed.

**Rollback / cleanup leftovers on the VM:** the old volume
`lvamo-applaut_postgres_data` (untouched pre-rename copy) and
`/home/ubuntu/backups/` (`lvamo-pre-rename-20261011.dump` plus the
pre-CORS-change `.env.production.bak-20261011`). Delete them once the
new setup has run cleanly for a while. Not urgent.

**Open / next (pick one next session):**
- ProSho Phase 0 — see `PROGRESS_PROSHO.md` (needs nothing from the user).
- ProSho §16 open questions — need the user's answers before Phase 1.
- Finish the repo rename: GitHub `vsvedantham/lvamo-applaut` → `lvamo`
  (user, via the GitHub UI), then update the `origin` remote locally and on
  the VM, and confirm Cloudflare Pages still auto-deploys on push. Local Mac
  folder `~/Projects/lvamo/applaut` can be renamed between sessions (it
  doesn't matter to Docker any more).
- Vertical primary tasks unchanged: Applaut — scale `company_boards.json`;
  Jobref — notify seekers when a request is decided.

---

## Verticals

| Vertical | Status | Progress file |
|---|---|---|
| **Applaut** | Live, in active development | [`PROGRESS_APPLAUT.md`](PROGRESS_APPLAUT.md) — primary task: keep scaling `company_boards.json` |
| **ProSho** | Planning (Oct 2026) — Project Showcase: evidence-backed capstone project pages; beta targeted mid-Jan 2027 | [`PROGRESS_PROSHO.md`](PROGRESS_PROSHO.md) — primary task: Phase 0 foundation; full plan in [`docs/prosho/BETA_PLAN.md`](docs/prosho/BETA_PLAN.md) |
| **Jobref** | Live — auth, companies, and the full referral request lifecycle (routing, employee inbox, seeker limits, accept/reject with evidence) deployed Aug 2026 | [`PROGRESS_JOBREF.md`](PROGRESS_JOBREF.md) — primary task: notifying a seeker when their request is decided |

---

## Deployment

| Layer | Status | URL / Location |
|---|---|---|
| Frontend | Live | `www.lvamo.com` and bare `lvamo.com` (both Cloudflare Pages custom domains, project `lvamo`; auto-deploys on push to `main`) — root `/` is the **LVAMO hub** (`frontend/src/pages/Hub.tsx`), listing verticals: Applaut at `/applaut/*`, Jobref at `/jobref/*` (landing, LinkedIn-gated register, login, dashboard). |
| Backend API | Live | Oracle Cloud VM `lvamo-backend` (`130.61.106.172`, Ampere A1.Flex, 4 OCPU/24GB, Docker) runs one shared backend process, fronted by nginx on two hostnames: `api.applaut.lvamo.com` (Applaut, `/api/v1/applaut/*`) and `api.jobref.lvamo.com` (Jobref, `/api/v1/jobref/*`, live since Aug 2026). See "Oracle Backend Migration" below for how this VM came to be; see "Multi-Vertical Architecture" below for the per-vertical-hostname pattern. |
| Database | Live | PostgreSQL 16 in Docker on `lvamo-backend`, DB/role named `lvamo` (renamed from `applaut` Aug 2026 — see below) — one Postgres database, one alembic migration chain (head: `0021`), shared by all verticals but namespaced at the schema level — plus a `platform` schema for LVAMO-wide tables (`platform.settings`, migration `0020`, Oct 2026): Applaut's 10 tables live in an `applaut` Postgres schema (migration `0012`, deployed to prod, see `PROGRESS_APPLAUT.md`). Jobref went further: its 3 tables were merged into a single `jobref.users` table (migration `0013`), plus `jobref.companies` (migration `0014`) and `jobref.referral_requests` (migrations `0015`–`0018`) — the full referral request/routing/limits/employee-decision feature set, deployed to prod, see `PROGRESS_JOBREF.md`. |
| Storage | Live | Cloudflare R2, real credentials configured in production — confirmed working via a genuine Jobref referral-evidence upload (`head_object`-verified in the actual bucket, Aug 2026). Local dev has no R2 credentials (uploads there fall back to a `local/`-prefixed key, no real upload attempted — see Applaut's `resumes/` and Jobref's `jobref/referral-evidence/` for the two current uploaders). |

**VM access:** `ssh lvamo-prod` from the Mac (see "SSH from the Mac" below). The Aug 2026 Windows-laptop command was `ssh -i C:\Users\vvenk\Downloads\ssh-key-2026-07-10.key ubuntu@130.61.106.172`.
**Windows-only artifacts:** the `.deploy-backup/` folder (pre-migration DB dump, old `.env.production` copy, launch-attempt log) referenced in "Oracle Backend Migration" below exists only on the Windows laptop (`C:\Projects\lvamo-applaut\`). It is not in git and not on the Mac.
**Old VM (`applaut-backend`, `130.61.65.131`):** deleted as part of the Aug 2026 migration — do not use.
**App dir on VM:** `/home/ubuntu/lvamo/` (was `/home/ubuntu/lvamo-applaut/` until 2026-10-11). Compose project `lvamo`: containers `lvamo-{postgres,backend,nginx}-1`, volume `lvamo_postgres_data`, network `lvamo_default`.
**Deploy backend:** `sudo docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build backend`
**Or just run `bash deploy.sh`** on the VM — pulls, rebuilds, migrates, restarts, prunes.
**OCI API access is set up** (Python SDK + API key at `~/.oci/config` on the dev machine — re-created on the Mac 2026-10-11 as a new key, fingerprint `0c:82:f6…`; the Aug 2026 Windows key `8e:d4:a5…` was never backed up, so it was deleted via the API the same day — this Mac's key is the only one. On the Mac, install the SDK into a throwaway venv with `uv pip install oci` — no system-wide install needed) — instance create/terminate/resize no longer needs manual Console clicks; see "Oracle Backend Migration" below for the one-time setup and gotchas.
**Cloudflare API access is set up** (scoped token saved at `~/.cloudflare/token` on the dev machine — re-created on the Mac Oct 2026 with **Zone → DNS → Edit** on `lvamo.com` + **Account → Cloudflare Pages → Edit**). Zone id `fb08020e0634c5add91336af3cb709f6`, account id `7f42edf57b4b76098b5b6efdf1c89bab`, Pages project `lvamo`. DNS records and Pages build env vars no longer need the dashboard. (`GET /accounts` returns empty for this token — read the account id from the zone instead.)
**SSH from the Mac**: `ssh lvamo-prod` (alias in `~/.ssh/config`, key `~/.ssh/lvamo-oci.key`).
**TLS cert renewal (fixed 2026-10-11)**: both certs (`api.applaut.lvamo.com`, re-issued, exp 2027-01-09; `api.jobref.lvamo.com`, exp 2026-11-16, auto-renews ~2026-10-17) renew via `certbot.timer` using the **webroot** authenticator (`/var/www/certbot`, served by nginx's port-80 `/.well-known/acme-challenge/` location). A deploy hook at `/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh` (source: `nginx/certbot-deploy-hook.sh`) reloads the nginx container after any renewal. Set up by `sudo bash nginx/setup-cert-renewal.sh` (idempotent; already run in prod, dry-run renewal passed for both). Note: run non-interactively, certbot adds a random delay of up to ~8 min before renewing — not a hang. Never use `--standalone` for a new cert here — nginx permanently holds port 80.
**⚠️ `nginx` gotcha**: if the VM is ever rebooted, `nginx`'s `restart: always` policy will bring it back even if it was manually `docker stop`ped before — a host reboot resets Docker's memory of that. Not a problem currently (cert exists, nginx starts fine), just worth knowing if this ever needs debugging again.
**DB role/database renamed `applaut` → `lvamo` (Aug 2026)**: both the Postgres role and the database itself were named `applaut` purely as a holdover from before Jobref existed, even though the same role/database now serves both verticals (via the `applaut`/`jobref` schemas). Renamed live via `ALTER DATABASE`/`ALTER ROLE RENAME` (a temporary superuser was needed to rename the role, since Postgres won't let a role rename its own session) in both local dev and production — no data migration, password unchanged, `docker-compose.yml`/`.env.example`/`backend/.env.example` updated to match. `.env`/`.env.production` (both gitignored) were updated directly, not committed. If connecting a DB client (e.g. DBeaver) via an SSH tunnel to prod: database name and username are now both `lvamo`, not `applaut`.
**Jobref deployed (Aug 2026, five rounds same day)**: LinkedIn-gated registration (migrations `0007`+`0008`) → split registration so LinkedIn is job-seeker-only, employees register directly, plus an app-wide mobile CSS fix affecting Applaut too (migration `0009`, see `PROGRESS_APPLAUT.md`) → progressive-disclosure registration UX (frontend-only) → new required employee field ("daily referral-view cap") + reworded seeker disclaimer (migration `0010`) → removed the "can I refer" checkbox in favor of an always-asked, bucketed referral-capacity question (migration `0011`). All five pushed and redeployed via `deploy.sh` + Cloudflare Pages, each verified in production with real data: a genuine employee account created end-to-end via the live API (register → 201, duplicate email → 409, login → 200, missing-required-field → 422), LinkedIn authorize redirect correct, Applaut regression clean every round, frontend re-verified live against `www.lvamo.com` itself each time. The LinkedIn job-seeker registration gap noted here previously is now closed — see the next entry.
**Jobref: full referral request feature built and deployed (Aug 2026, one long session)**: DB restructure (`jobref.users` merged single-table, migration `0013`) → a real job-seeker registration completed through the actual LinkedIn consent screen, closing out the last standing auth gap → `jobref.companies` seeded from employee registration (migration `0014`) and shown to seekers on their dashboard → full referral request flow: company tile → instructions + form → `jobref.referral_requests` (migration `0015`) → routed to a specific employee via a random-among-under-cap algorithm respecting each employee's own daily cap (migration `0016`) → employee-side inbox → dashboard redesign (profile info moved into a slide-out panel with real editing, main page now just companies/requests in a responsive grid) → seeker limited to 1 request/day with a dashboard note + company badges, no duplicate job link per company (migration `0017`) → employee accept/reject actions, with optional evidence-of-referral upload to Cloudflare R2 and a required response-to-seeker on reject (migration `0018`). Every step pushed, deployed via `deploy.sh` + Cloudflare Pages, and re-verified against the real production API immediately after (not just locally) — see `PROGRESS_JOBREF.md` for the full detail, verification logs, and two things worth knowing: the daily-limit rule has no DB-level backstop (Postgres won't allow a `timestamptz::date` index expression), and an earlier claim that R2 storage was unconfigured in production was wrong (a flawed `grep -o` check) — it's genuinely configured and confirmed working with a real uploaded object.

---

## Multi-Vertical Architecture

LVAMO is explicitly a multi-vertical platform now (Applaut and Jobref
live, ProSho planned). The pattern, established Aug 2026, for any vertical `<x>`:

- **Frontend routes** live under `/<x>/*` (e.g. `/applaut/login`,
  `/applaut/dashboard`). The LVAMO hub at `/` lists all verticals and links
  into each.
- **Backend API routes** live under `/api/v1/<x>/*` on the shared backend
  (e.g. `/api/v1/applaut/auth/login`). A vertical's whole FastAPI router
  tree mounts under this prefix — see `backend/app/main.py`.
- **Auth is isolated per vertical** — separate localStorage token key
  (`<x>_access_token`), separate JWT issuance, so one vertical's session
  can't collide with another's even though they currently share one backend
  process and one Postgres instance.
- Verticals currently **share** the backend VM, Docker process, and database
  server. Nothing about the URL namespacing requires this — a vertical can
  be split onto its own process, container, database, or VM later without
  touching the others, if/when it needs independent scaling or deploy
  cycles. Jobref's auth now lives on this shared backend/DB too (its own
  tables, own JWTs scoped with a `"vertical": "jobref"` claim so a token
  can't be replayed across verticals — see `PROGRESS_JOBREF.md`).
- **The full rule set now lives in `CLAUDE.md`** (Oct 2026) — it was the
  Applaut product spec until then (moved to `docs/applaut/SPEC.md`), and is
  now the LVAMO master spec: a table of every place verticals are told
  apart (code folder, API path, hostname, DB schema, migration filename,
  frontend route/env var, auth, R2 prefix, docs, Claude skill), the
  platform-level equivalent of each, and an add-a-vertical checklist.
- **Platform layer** (Oct 2026): LVAMO-wide things that belong to no
  vertical get `backend/app/platform/`, schema `platform`, API
  `/api/v1/platform/*`, and hostname `api.lvamo.com`. First resident:
  `platform.settings` (`verticals_enabled`, previously in
  `applaut.application_settings`). See "Platform settings move" below.
- **Database namespacing follows the same per-vertical pattern, one layer
  down** (Aug 2026): within the single shared Postgres database, each
  vertical gets its own Postgres schema (`applaut`, `jobref`) rather than
  all tables sitting unqualified in `public`. Applaut's 10 tables + 4 enum
  types were moved into the `applaut` schema via migration `0012`; Jobref's
  tables live in `jobref` (migrations `0013`+). Both deployed. `alembic_version` stays unschemaed in `public` —
  shared migration bookkeeping, not vertical data. Each SQLAlchemy model
  declares its own `schema=` explicitly (table args, FK targets, enum
  types) rather than relying on the DB connection's `search_path`, so
  `db/base.py`/`db/session.py`/`config.py` needed no changes.
- **Backend hostname is per-vertical even though the backend itself is
  shared** (Aug 2026) — `api.applaut.lvamo.com` was named before Jobref
  existed as a concept; rather than have Jobref sit under a hostname
  carrying another vertical's name, it got its own: `api.jobref.lvamo.com`.
  Both are just nginx `server_name` blocks on the same VM/container,
  proxying to the same `backend:8000` — the routing that actually matters
  (which vertical's code handles the request) is still the `/api/v1/<x>/*`
  path prefix above, not the hostname. Each new vertical should get its own
  `api.<x>.lvamo.com` DNS record + nginx block + Let's Encrypt cert (all
  three cheap — DNS/cert/nginx-reload, no code or deploy-pipeline change)
  rather than stacking onto an existing vertical's hostname. See
  `nginx/nginx.conf` for both blocks, and `PROGRESS_JOBREF.md` for the
  Jobref-specific setup log.

Applaut's namespacing work (the actual migration, file-by-file) is recorded
in `PROGRESS_APPLAUT.md`, not here — this section is the durable policy, not
a change-log entry.

### Codebase structure matches the URL structure (Aug 2026)

The URL namespacing above only covers *routes*. Until Aug 2026 the actual
**file layout** didn't know verticals existed — `backend/app/models/user.py`,
`frontend/src/pages/Login.tsx` etc. were Applaut-only code sitting in flat,
unmarked shared folders (a historical artifact: this codebase *was* Applaut
before Jobref existed as a concept). Restructured both sides so the folder
structure matches the URL structure, for every vertical going forward — this
is "package by feature" / a modular-monolith split, not something unusual:

**Backend** (`backend/app/`):
- `applaut/` — everything Applaut-specific: models (except `base.py`),
  schemas, services, `api/v1/` routers, `discovery/`, `generation/`,
  `scoring/`, plus the Applaut-only `core/ai.py` (resume-extraction AI),
  `core/extract_text.py`, `core/role_synonyms.py`.
- Shared top-level, **only** things with zero vertical-specific logic:
  `main.py` (mounts each vertical's router), `config.py` (Settings),
  `db/session.py` + `db/base.py` (engine, `get_db`, SQLAlchemy `Base`/
  `TimestampMixin`/`UUIDPrimaryKey`), `core/security.py` (password/JWT
  helpers), `core/storage.py` (R2 client).
- A future `jobref/` sibling to `applaut/` follows the identical shape.

**Frontend** (`frontend/src/`):
- `applaut/{api,components,context,pages}/` — everything Applaut-specific.
- `jobref/{api,components,context,pages}/` — Jobref's auth flow
  (login/register/dashboard); grows the same shape as more gets built.
- Shared top-level: `main.tsx`, `App.tsx`, `index.css`,
  `components/{Logo,BrandedPage}.tsx`, `hooks/useDocumentTitle.ts`,
  `pages/Hub.tsx`.

**The rule for what's shared vs. vertical-specific**: only promote something
to the shared layer once it's *proven* to have zero product-specific logic
(verified by reading it, not guessed) — sharing too eagerly creates hidden
coupling between verticals; not sharing genuinely-generic infra just
duplicates it. When in doubt, keep it in the vertical folder; promote later
if a second vertical actually needs it.

This was a pure reorganization (verified: byte-identical frontend bundle
hashes before/after, zero backend behavior change) — see `PROGRESS_APPLAUT.md`
for the file-by-file move log if ever needed for reference.

### Platform settings move (Oct 2026 — complete, live in production)

`verticals_enabled` (which vertical cards the hub lists) lived in
`applaut.application_settings` and was read from Applaut's API — platform
config sitting inside one vertical. Now:

- ✅ Migration `0020`: schema `platform`, table `platform.settings`
  (`setting_name`, `value`, `description`, `is_public`), live value copied
  over. Only `is_public` rows are served unauthenticated; private ones 404
  like missing ones. `allow_new_registrations` stays in Applaut — it only
  gates Applaut sign-ups.
- ✅ `GET /api/v1/platform/settings/{name}` on the new platform hostname
  **`api.lvamo.com`**: Cloudflare DNS A record (DNS only) → VM, webroot
  cert (expires 2027-01-09, auto-renews via the timer + reload hook), nginx
  `server` block.
- ✅ Hub reads `VITE_PLATFORM_API_BASE_URL` (set in Cloudflare Pages
  production env vars via the API) + `/api/v1/platform`. Verified live on
  `www.lvamo.com`: the request goes to
  `api.lvamo.com/api/v1/platform/settings/verticals_enabled`, Jobref card
  shown, no console errors.
- ✅ Migration `0021` deletes the old applaut copy of the row.

**To change which verticals the hub lists** (no deploy needed):
`UPDATE platform.settings SET value = 'applaut,jobref' WHERE setting_name = 'verticals_enabled';`

**⚠️ nginx gotcha (new)**: `nginx.conf` is a single-file bind mount, and
`git pull` replaces the file (new inode), so the running container keeps
seeing the *old* config — `nginx -s reload` alone does nothing. After
pulling an nginx change: test with a throwaway container on the compose
network, then `docker compose restart nginx` (~2 s blip):
`sudo docker run --rm --network lvamo_default -v $PWD/nginx/nginx.conf:/etc/nginx/nginx.conf:ro -v /etc/letsencrypt:/etc/letsencrypt:ro nginx:alpine nginx -t`

**Fixed 2026-10-11**: bare `https://lvamo.com` is now a Pages custom domain
and a CORS origin (see session log).

---

## Oracle Backend Migration (COMPLETE, Aug 2026)

**Why:** the old VM (OCI display name `applaut-backend`, `130.61.65.131`) was
a **fixed** `VM.Standard.E2.1.Micro` shape — 1 OCPU / 1GB RAM, not resizable,
already down to ~250MB free RAM with just Applaut running (no room for
Jobref later). Moved to Oracle's Ampere A1.Flex tier instead — started the
launch attempt at 2 OCPU/12GB (Oracle's free Ampere allotment had just been
reduced from the historical 4 OCPU/24GB — noted 2026-08 via an Oracle
console banner), ended up at the full **4 OCPU / 24GB** after the account
was upgraded to Pay-As-You-Go mid-migration (see step 7 — still $0, Always
Free entitlements stay free on PAYG). New instance name: `lvamo-backend`
(generic, not vertical-specific, per the Multi-Vertical Architecture above).
**Total elapsed time: ~24 hours, almost all of it waiting on Oracle capacity,
not active work.**

**Sequencing note:** the user explicitly chose to delete the old instance
*before* creating the new one (not a side-by-side blue-green migration) —
so there was no rollback safety net, only the backup below. This was a
known, accepted trade-off, not an accident.

### What was done
1. ✅ **Backed up** from the old VM before deletion, verified good:
   - `C:\Projects\lvamo-applaut\.deploy-backup\applaut_backup.dump` — full
     `pg_dump -Fc` of the `applaut` database (70,875 bytes). Verified via
     `pg_restore --list` — all 11 tables present (`users`, `profiles`,
     `resumes`, `opportunities`, `scores`, `applications`,
     `generated_documents`, `notifications`, `audit_logs`,
     `application_settings`, `alembic_version`).
   - `C:\Projects\lvamo-applaut\.deploy-backup\.env.production` — exact
     byte-for-byte copy of the old VM's secrets/config (791 bytes).
   - Both gitignored (`.deploy-backup/` added to `.gitignore`), never
     committed.
2. ✅ **Audited the old VM's full live config** before deletion (not just
   what's in git) so the new one could be a faithful rebuild:
   - Docker installed via **`apt install docker.io docker-compose-plugin
     docker-buildx-plugin`** (Ubuntu's own repo, NOT Docker's official CE
     repo/get.docker.com script).
   - `certbot` + `python3-certbot` via apt (classic, not snap) — ships its
     own `certbot.timer` systemd unit for auto-renewal, enabled by default
     on install, no manual setup needed.
   - Cert: standalone HTTP-01 authenticator, standard Let's Encrypt prod
     server, for `api.applaut.lvamo.com` only.
   - Host firewall: Oracle's Ubuntu cloud image ships iptables with a
     default-REJECT policy after allowing established/related/ICMP/SSH —
     ports 80 and 443 were opened via `iptables -I INPUT <pos> -m state
     --state NEW -p tcp --dport {80,443} -j ACCEPT`, then persisted via
     `apt install -y iptables-persistent && netfilter-persistent save`.
   - No swap configured. No custom `/etc/docker/daemon.json`. No crontab
     entries. Nothing manually added to the repo dir outside git except
     `.env.production` (confirmed via `git status --ignored`).
3. ✅ **OCI API access set up** (durable, reusable going forward — not just
   for this migration):
   - OCI Python SDK installed locally (`pip install --user oci`) — the
     full `oci-cli` package **fails to install** on this machine (Python
     3.14 is too new for PyYAML's prebuilt wheels, and there's no MSVC
     build toolchain to compile it from source) — use the raw SDK via
     Python scripts instead, not the CLI.
   - API signing key pair generated at `~/.oci/oci_api_key.pem` (private)
     / `~/.oci/oci_api_key_public.pem` (public), registered against the
     user's OCI account (Console → Profile → API Keys). Config at
     `~/.oci/config`.
   - **Known gotcha**: right after adding a new API key, the Identity
     service authenticates instantly, but Compute/Network ("iaas")
     endpoints can take several minutes to see the new key — expect
     transient `401 NotAuthenticated` on `ComputeClient` calls for a few
     minutes after first setup even though `IdentityClient` calls succeed
     immediately. Not a real problem, just wait and retry.
4. ✅ Old instance **terminated** (`preserve_boot_volume=False` — no
   orphaned boot volume left eating into the shared 200GB free block
   storage allowance).
5. ✅ **Instance launched** — after ~22.5 hours of retrying (a 5-min cron
   job checking `attempt_launch_once.py`), succeeded on AD-1:
   `RWGt:EU-FRANKFURT-1-AD-1`, instance OCID
   `ocid1.instance.oc1.eu-frankfurt-1.antheljr7fvjruaci7an2vityonovsx6dhyqobw2xf7zmfop3evimbuqrpyq`,
   public IP **`130.61.106.172`**. Confirmed `RUNNING`, correct image
   (Ubuntu 24.04.4 LTS aarch64), SSH working immediately with the existing
   key — no new credentials needed. Full retry-attempt history logged at
   `C:\Projects\lvamo-applaut\.deploy-backup\launch_attempts.log`.

   Journey to get here, for reference — tried multiple angles, all hit the
   same wall until it finally cleared:
   - API `launch_instance` for `VM.Standard.A1.Flex` (2 OCPU/12GB) failed
     `500 Out of host capacity` across all 3 ADs in `eu-frankfurt-1`
     (`RWGt:EU-FRANKFURT-1-AD-1/2/3`), repeatedly, for hours.
   - User also tried creating it **manually via the OCI Console** — same
     result, same capacity wall (confirmed it was real infra capacity, not a
     bug in the API calls).
   - Investigated whether another OCI **region** might have capacity: **not
     an option for staying free** — Always Free compute is only provisionable
     in the tenancy's home region, which is locked to `eu-frankfurt-1` and
     can't be changed after signup ([Oracle docs](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)).
     Confirmed via `list_region_subscriptions`. A brand-new account in a
     different region (e.g. Singapore, anecdotally easier per community
     reports) was considered but the user opted not to pursue it — flagged
     risk: Oracle generally allows one Always Free account per
     identity/card, and a second account created to route around this
     would risk suspension. **Decision: stick with this tenancy, keep
     retrying Frankfurt.**
   - Background retry loop ran every 5 min per full cycle (15s stagger
     between the 3 ADs — an earlier tighter loop hit `429 Too many
     requests` and was replaced with this slower pacing).
   - **Bug hit and fixed along the way**: the loop initially only caught
     `oci.exceptions.ServiceError`, so a transient network blip (DNS
     resolution failure, e.g. laptop sleep/wifi drop) raised an uncaught
     `oci.exceptions.RequestException` and silently killed the whole loop —
     it sat dead for a while before anyone noticed. Fixed with a catch-all
     `except Exception` around the launch call. **If a retry script like
     this is ever needed again, keep that catch-all** — it's the difference
     between "retries for hours unattended" and "dies on the first hiccup."
   - Eventually switched from an in-session background loop to a `CronCreate`
     recurring job (5 min interval) calling an idempotent
     `attempt_launch_once.py` (checks first whether `lvamo-backend` already
     exists in a live state before attempting anything) — this proved more
     durable across session boundaries than a plain background process.
6. ✅ **Provisioned** — replicated the audited old-VM config on the new box:
   - Docker packages differ by Ubuntu version: old box (20.04) used
     `docker.io docker-compose-plugin docker-buildx-plugin`; new box (24.04)
     needed **`docker.io docker-compose-v2 docker-buildx`** instead — apt
     aborts the whole install line if any package name is wrong.
   - iptables: fresh Ubuntu 24.04 image has the identical default-REJECT
     baseline as the old 20.04 one — opened 80/443 the same way, persisted
     with `netfilter-persistent save`.
   - certbot via apt as before — `certbot.timer` auto-enabled.
   - Repo cloned, `.env.production` + DB dump `scp`'d up from the local
     backup, `postgres` brought up first and the dump restored via
     `pg_restore` inside the container before starting anything else —
     verified row counts matched the backup.
   - `backend` built and started cleanly on ARM64 — all Python dependencies
     in `requirements.txt` had prebuilt `aarch64` wheels, no compile-from-
     source issues.
   - Alembic migrations ran clean (no-op, DB was already at head from the
     restored dump).
   - Validated the backend directly, bypassing `nginx` (chicken-and-egg:
     `nginx`'s config requires a TLS cert that can't be issued until DNS
     points here) — the `python:3.12-slim` image has no `curl`, so used
     `python3 -c "import urllib.request..."` inside the container instead.
7. ✅ **Account upgraded to Pay-As-You-Go mid-migration** — almost certainly
   *why* the ~22.5h capacity wait finally succeeded (PAYG gets priority
   capacity access even for Always-Free-eligible shapes). User then resized
   the instance up to the *full* Always-Free Ampere allotment (4 OCPU/24GB,
   still $0) and rebooted. Verified clean afterward: same public IP, shape
   confirmed 4 OCPU/24GB at both the OCI API and OS level (`nproc`=4,
   `free -h`=23Gi), Docker daemon active, `backend`+`postgres` survived
   the reboot and stayed healthy, iptables rules persisted. Only `nginx`
   needed re-stopping (a full host reboot resets Docker's memory of a
   manual `docker stop`, unlike a daemon-only restart).
8. ✅ **Cloudflare API access set up** (durable, same pattern as OCI) —
   scoped API Token (Zone → DNS → Edit, restricted to the `lvamo.com` zone
   only, no other-zone/billing access), created via the dashboard
   (**dash.cloudflare.com/profile/api-tokens** → Create Token → "Edit zone
   DNS" template), saved locally at `~/.cloudflare/token`. Verified via
   `GET /client/v4/user/tokens/verify` before use.
9. ✅ **DNS cutover** — updated the `api.applaut.lvamo.com` A record (zone
   `fb08020e0634c5add91336af3cb709f6`, record
   `34df1e922eeeb9157a21bd432b8fcf49`) via `PATCH
   /client/v4/zones/{zone}/dns_records/{id}` from `130.61.65.131` (dead) to
   `130.61.106.172`. Propagated within seconds (it's a DNS-only/grey-cloud
   record on Cloudflare, so no proxy cache to wait on).
10. ✅ **Cert issued**: `certbot certonly --standalone -d
    api.applaut.lvamo.com` — succeeded immediately once DNS pointed here.
    Expires 2026-11-15, auto-renewal via `certbot.timer` already confirmed
    enabled. `nginx` started clean.
11. ✅ **Full end-to-end verification**: health check over HTTPS through
    nginx, real login attempt against a real production account (wrong
    password, confirmed proper 401 not a crash), and a full Playwright
    browser pass against `https://www.lvamo.com/applaut/login` — frontend →
    DNS → TLS → nginx → backend → DB, all through the new server, all
    correct.

---

## Tech Stack Quick Reference

| Layer | Tech |
|---|---|
| Frontend | React 18, Vite, TypeScript |
| Backend | Python 3.12, FastAPI |
| Database | PostgreSQL 16 |
| Storage | Cloudflare R2 |
| Automation | Playwright (used for verification; not yet wired into the product for auto-apply) |
| Hosting | Oracle Cloud VM (backend), Cloudflare Pages (frontend) |

Vertical-specific stack choices (e.g. Applaut's OpenAI usage) are documented
in that vertical's progress file, not here.

---

## Ground Rules (Non-Negotiable)

1. **Industry standards by default** — mobile-first, accessibility, security, REST conventions. Claude calls out deviations before implementing.
2. **No Co-Authored-By in git commits.**
3. **Never commit `.env` or `.env.production`.**
4. **Human approval first** — no auto-apply without explicit user opt-in.
5. **Never invent profile data** in document generation — only reorder/rephrase.
