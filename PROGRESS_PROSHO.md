# ProSho — Progress

> Vertical-specific progress for ProSho (Project Showcase). Platform-level
> infra/architecture lives in [`PROGRESS.md`](PROGRESS.md) and the structure
> rules in [`CLAUDE.md`](CLAUDE.md) — read those first if you haven't.

---

## 🎯 NEXT SESSION PRIMARY TASK

**Phase 0 — Foundation** of [`docs/prosho/BETA_PLAN.md`](docs/prosho/BETA_PLAN.md) §12:

1. Finish the platform cutover first (`api.lvamo.com` — see `PROGRESS.md`
   "Platform settings move"). It's the same DNS → webroot cert → nginx
   recipe ProSho's own hostname needs, so do it once and reuse.
2. `backend/app/prosho/` skeleton (empty `models/`, `schemas/`,
   `services/`, `api/v1/routers/health.py`), mounted at `/api/v1/prosho`.
3. Migration `0021_prosho_schema.py` (or next free number): schema
   `prosho` + `prosho.users`.
4. `frontend/src/prosho/` skeleton + `/prosho` landing route; hub card
   added but hidden (`prosho` not in `platform.settings.verticals_enabled`).
5. `api.prosho.lvamo.com`: DNS A record (user, Cloudflare), webroot cert,
   nginx block; `VITE_PROSHO_API_BASE_URL` in Cloudflare Pages (user).
6. Exit check: `GET https://api.prosho.lvamo.com/api/v1/prosho/health` → 200.

Before starting Phase 1, get answers to the plan's §16 open questions
(sign-in method, mentor naming, pilot #2, supervisor contact, URL).

---

## Status

**Planning (Oct 2026).** Nothing built yet.

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
