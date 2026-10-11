---
name: prosho
description: Scope this session to the ProSho vertical only. Reads PROGRESS.md + PROGRESS_PROSHO.md, restricts work to ProSho's own backend/frontend/migrations, and flags before touching Applaut or Jobref files or shared platform code. Invoke with /prosho at the start of a session.
---

# ProSho-only session

The user invoked this to scope the **entire rest of this session** to the
**ProSho** vertical only — not Applaut or Jobref, not platform-wide work — unless
they explicitly say otherwise mid-session. This scoping persists for every
turn from here on, not just the first one.

## Start here

Read, in order:
1. `PROGRESS.md` — platform-level context (shared infra, ground rules,
   Multi-Vertical Architecture). ProSho's code still lives on shared
   infra (one backend VM/process, one Postgres), so this matters even
   though the *work* is ProSho-scoped.
2. `PROGRESS_PROSHO.md` — ProSho-specific status, the current primary
   task banner, and recent history.
3. `docs/prosho/BETA_PLAN.md` — the beta plan this work implements.

This matches the project's own documented session-start convention — see
`PROGRESS.md`'s header comment.

## In scope — work freely here

- `backend/app/prosho/**` (models, schemas, services, `api/v1/`)
- `frontend/src/prosho/**`
- `backend/migrations/versions/*` **only** when the migration touches
  ProSho's own `prosho` schema (name new files `NNNN_prosho_<what>.py`)
- `PROGRESS_PROSHO.md`, `docs/prosho/**`

## Out of scope — flag before touching

Stop, explain exactly what needs to change and why, and wait for explicit
go-ahead before editing any of these:

- `backend/app/applaut/**`, `frontend/src/applaut/**`, `backend/app/jobref/**`,
  `frontend/src/jobref/**` — other verticals' code
- Shared platform files: `CLAUDE.md` (LVAMO master spec), `backend/app/platform/**`,
  `backend/app/main.py`, `backend/app/config.py`,
  `backend/app/core/security.py`, `backend/app/core/storage.py`,
  `backend/app/db/*`, `frontend/src/App.tsx`,
  `frontend/src/components/*`, `frontend/src/pages/Hub.tsx`,
  `frontend/src/hooks/*`, `nginx/nginx.conf`, `docker-compose*.yml`, root
  `.env*`
- `PROGRESS.md` (platform-level doc), any other vertical's `PROGRESS_*.md`,
  `docs/<other vertical>/**`, `backend/app/<other vertical>/**`,
  `frontend/src/<other vertical>/**` (e.g. ProSho's)

The one exception: read-only access to any of the above (to understand
context, verify something, check for conflicts) never needs flagging —
only *edits* do.

## Deploying

The backend is one shared process on one VM (see `PROGRESS.md`'s
Multi-Vertical Architecture) — there's no way to deploy just ProSho's
changes in isolation. Before running `deploy.sh` or `git push`, check
`git log`/`git status` for any committed-but-undiscussed Applaut or Jobref changes
that would ride along, and flag them to the user before deploying if
found. Frontend deploys (Cloudflare Pages) are similarly all-or-nothing
per push.
