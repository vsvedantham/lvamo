# LVAMO — Master Spec

LVAMO is the master product. It is a platform of independent tools
("verticals"), each solving one part of getting hired or growing a career:

| Vertical | What it does | Product spec | Progress |
|---|---|---|---|
| **Applaut** | AI job discovery, scoring, tailored resumes and cover letters | [`docs/applaut/SPEC.md`](docs/applaut/SPEC.md) | [`PROGRESS_APPLAUT.md`](PROGRESS_APPLAUT.md) |
| **Jobref** | Referrals from employees to job seekers | none yet — `PROGRESS_JOBREF.md` is the source of truth | [`PROGRESS_JOBREF.md`](PROGRESS_JOBREF.md) |
| **ProSho** | Project Showcase — turns student capstone repos into evidence-backed project pages | [`docs/prosho/BETA_PLAN.md`](docs/prosho/BETA_PLAN.md) | [`PROGRESS_PROSHO.md`](PROGRESS_PROSHO.md) |

This file holds the rules that apply to **every** vertical. Each vertical's
own spec covers its product behaviour; where the two overlap, this file wins.

Session start: read `PROGRESS.md` (platform status), then the relevant
vertical's progress file. `/applaut`, `/jobref`, `/prosho` scope a session
to one vertical (see `.claude/skills/`).

---

## The structure rule: LVAMO first, then the vertical

Every place that can tell verticals apart must do so the same way. For a
vertical `<x>` (lowercase: `applaut`, `jobref`, `prosho`):

| Layer | Vertical-specific | Platform-wide (LVAMO) |
|---|---|---|
| Backend code | `backend/app/<x>/` (`models/`, `schemas/`, `services/`, `api/v1/routers/`) | `backend/app/platform/` (same shape) + generic infra in `main.py`, `config.py`, `db/`, `core/` |
| API path | `/api/v1/<x>/*` | `/api/v1/platform/*` |
| API hostname | `api.<x>.lvamo.com` | `api.lvamo.com` |
| Database | Postgres schema `<x>` (every model sets `schema="<x>"` explicitly) | Postgres schema `platform` |
| Migrations | One shared alembic chain; new files named `NNNN_<x>_<what>.py` | `NNNN_platform_<what>.py` |
| Frontend code | `frontend/src/<x>/` (`api/`, `components/`, `context/`, `pages/`) | `frontend/src/{pages,components,hooks}/`, `App.tsx`, `index.css` |
| Frontend route | `/<x>/*` | `/` (the LVAMO hub) |
| Frontend env var | `VITE_<X>_API_BASE_URL` | `VITE_PLATFORM_API_BASE_URL` |
| Auth | Own users table, own JWTs with a `"vertical": "<x>"` claim, own localStorage key `<x>_access_token` | none yet (one LVAMO account is a future decision) |
| File storage (R2) | Key prefix `<x>/...` | `platform/...` |
| Docs | `docs/<x>/` + `PROGRESS_<X>.md` | `CLAUDE.md` + `PROGRESS.md` |
| Claude scoping | `.claude/skills/<x>/SKILL.md` | — |

**Shared vs. vertical-specific:** only promote code to the platform layer
once it is proven to contain zero product-specific logic (verified by
reading it, not guessed). When in doubt, keep it in the vertical and
promote later if a second vertical needs it. A vertical never imports from
another vertical.

**Known exceptions, not to copy:** the repo is still named `applaut`
(GitHub `lvamo-applaut`, VM dir `/home/ubuntu/lvamo-applaut/`) — a rename to
`lvamo` is planned as its own task (it changes the Docker Compose project
name, so the Postgres volume must be pinned first). Applaut's early
migrations (`0001`–`0006`) predate the filename prefix rule and are not
renamed.

### Adding a new vertical — checklist
1. `backend/app/<x>/` package; mount its router in `main.py` at `/api/v1/<x>`.
2. Migration creating schema `<x>` and its tables; import its models in `migrations/env.py`.
3. `frontend/src/<x>/`; routes under `/<x>/*` in `App.tsx`; a card in `pages/Hub.tsx`.
4. Hub visibility: add `<x>` to `platform.settings.verticals_enabled` when it should be listed.
5. `api.<x>.lvamo.com`: DNS A record → VM, webroot cert (`certbot certonly --webroot -w /var/www/certbot -d api.<x>.lvamo.com`), nginx `server` block.
6. `VITE_<X>_API_BASE_URL` in `.env.example` and in Cloudflare Pages build settings.
7. `docs/<x>/`, `PROGRESS_<X>.md`, `.claude/skills/<x>/SKILL.md`, and a row in the table at the top of this file and in `PROGRESS.md`.

---

## Core principles (all verticals)

1. Cloud first
2. Multi-user
3. AI-assisted
4. Explainable decisions — no black-box scores or verdicts
5. Auditability
6. Human approval first — nothing acts on a user's behalf without explicit opt-in
7. Provider agnostic — every external provider (AI, storage, data source) sits behind an abstraction
8. Never invent user data — generated content may reorder, rephrase and prioritise, never fabricate

## Technology stack

| Layer | Tech |
|---|---|
| Frontend | React 18, Vite, TypeScript — hosted on Cloudflare Pages (auto-deploys on push to `main`) |
| Backend | Python 3.12, FastAPI — one shared process in Docker on an Oracle Cloud VM, behind nginx |
| Database | PostgreSQL 16 — one database (`lvamo`), one schema per vertical + `platform` |
| Storage | Cloudflare R2 (files) — metadata in Postgres |
| Automation | Playwright |
| Scheduling | APScheduler |
| AI | Provider abstraction; OpenAI first, Claude/Gemini later |

**Do not replace** FastAPI, PostgreSQL, React, R2 or the Oracle VM without
explicit approval.

## API rules
- REST, versioned: `/api/v1/<x>/...` or `/api/v1/platform/...`.
- Unauthenticated endpoints must be deliberate (e.g. `platform.settings` only serves rows with `is_public = true`).
- Ownership failures return 404, not 403, so existence isn't leaked.

## Database rules
- Designed for multi-user SaaS, auditability and scalability.
- Every table lives in its vertical's schema or `platform` — never `public` (only `alembic_version` stays there).
- Each SQLAlchemy model declares `schema=` itself (table args, FK targets, enum types); nothing relies on `search_path`.

## Security rules
- JWT auth, hashed passwords, HTTPS everywhere.
- Never store secrets in source code. Never commit `.env` or `.env.production`.

## Working rules
- Make the smallest reasonable assumption when details are missing, and document it.
- Implement complete vertical slices (DB → API → UI → tests → docs), not file-by-file fragments.
- When reporting code changes to the user, give file paths and full file contents, never partial snippets.
- No `Co-Authored-By` lines in git commits.
- Verify in production after every deploy, and record what was verified in the progress file.
