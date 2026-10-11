# ProSho — Progress

> Vertical-specific progress for ProSho (Project Showcase). Platform-level
> infra/architecture lives in [`PROGRESS.md`](PROGRESS.md) and the structure
> rules in [`CLAUDE.md`](CLAUDE.md) — read those first if you haven't.

---

## 🎯 NEXT SESSION PRIMARY TASK

**Phase 0 — Foundation** of [`docs/prosho/BETA_PLAN.md`](docs/prosho/BETA_PLAN.md) §12:

1. ~~Finish the platform cutover (`api.lvamo.com`)~~ — **done 2026-10-11**.
   The recipe is proven and reusable for ProSho's hostname: Cloudflare DNS
   record via API → `certbot certonly --webroot` → nginx block → test in a
   throwaway container → `docker compose restart nginx` (see `PROGRESS.md`
   "Platform settings move" for the exact commands and the bind-mount gotcha).
2. `backend/app/prosho/` skeleton (empty `models/`, `schemas/`,
   `services/`, `api/v1/routers/health.py`), mounted at `/api/v1/prosho`.
3. Migration `0022_prosho_schema.py`: schema `prosho` + `prosho.users`.
4. `frontend/src/prosho/` skeleton + `/prosho` landing route; hub card
   added but hidden (`prosho` not in `platform.settings.verticals_enabled`).
5. `api.prosho.lvamo.com`: DNS A record, webroot cert, nginx block;
   `VITE_PROSHO_API_BASE_URL` in Cloudflare Pages. Claude can do all of
   this directly now (Cloudflare token + `ssh lvamo-prod` — see `PROGRESS.md`
   Deployment) — no user dashboard steps needed.
6. Exit check: `GET https://api.prosho.lvamo.com/api/v1/prosho/health` → 200.

Migration number: next free is `0022` (head is `0021` after the platform
settings work) → `0022_prosho_schema.py`.

Before starting Phase 1, get answers to the plan's §16 open questions
(sign-in method, mentor naming, pilot #2, supervisor contact, URL) —
**still unanswered as of 2026-10-11.**

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

## Session log

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
