---
name: jobref
description: Scope this session to the Jobref vertical only. Reads PROGRESS.md + PROGRESS_JOBREF.md, restricts work to Jobref's own backend/frontend/migrations, and flags before touching Applaut files or shared platform code. Invoke with /jobref at the start of a session.
---

# Jobref-only session

The user invoked this to scope the **entire rest of this session** to the
**Jobref** vertical only — not Applaut, not platform-wide work — unless
they explicitly say otherwise mid-session. This scoping persists for every
turn from here on, not just the first one.

## Start here

Read, in order:
1. `PROGRESS.md` — platform-level context (shared infra, ground rules,
   Multi-Vertical Architecture). Jobref's code still lives on shared
   infra (one backend VM/process, one Postgres), so this matters even
   though the *work* is Jobref-scoped.
2. `PROGRESS_JOBREF.md` — Jobref-specific status, the current primary
   task banner, and recent history.

This matches the project's own documented session-start convention — see
`PROGRESS.md`'s header comment.

## In scope — work freely here

- `backend/app/jobref/**` (models, schemas, services, `api/v1/`)
- `frontend/src/jobref/**`
- `backend/migrations/versions/*` **only** when the migration touches
  Jobref's own tables (`jobref_users`, `jobref_employee_profiles`,
  `jobref_seeker_profiles`)
- `PROGRESS_JOBREF.md`, `docs/jobref/**`

## Out of scope — flag before touching

Stop, explain exactly what needs to change and why, and wait for explicit
go-ahead before editing any of these:

- `backend/app/applaut/**`, `frontend/src/applaut/**` — Applaut's own code
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
Multi-Vertical Architecture) — there's no way to deploy just Jobref's
changes in isolation. Before running `deploy.sh` or `git push`, check
`git log`/`git status` for any committed-but-undiscussed Applaut changes
that would ride along, and flag them to the user before deploying if
found. Frontend deploys (Cloudflare Pages) are similarly all-or-nothing
per push.
