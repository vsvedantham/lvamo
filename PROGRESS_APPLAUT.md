# Applaut — Progress

> Vertical-specific progress for Applaut. Platform-level infra/architecture
> lives in [`PROGRESS.md`](PROGRESS.md) — read that first if you haven't.
> Applaut's product spec is [`docs/applaut/SPEC.md`](docs/applaut/SPEC.md)
> (moved there from the repo-root `CLAUDE.md` on 2026-10-11, when `CLAUDE.md`
> became the LVAMO master spec).

---

## 🎯 NEXT SESSION PRIMARY TASK

**Changed 2026-10-17: finish Job engines Phase 2 in production: connect
Venkat's routine.** Phase 2 (engine 3 sync) is built, tested and deployed
(see "Job engines — Phase 2" below). What's left needs Venkat:
1. In Neon's SQL editor: create the read-only role (the SQL is under
   Settings → Job engine → "Show the SQL that creates a read-only role").
2. In Cloudflare: an R2 API token with **Object Read only** for
   `job-search-automation-documents`; also rotate the routine's own R2 key
   (it was printed in an earlier session, §6.10).
3. In Applaut (prod): Settings → Job engine → "Your Claude routine", paste
   the read-only Neon URL, account id, key id and secret, routine link,
   schedule `7 6,18 * * *` UTC → **Test connection** → **Save and connect**.
   Full walkthrough: [`docs/applaut/CONNECT_YOUR_ROUTINE.md`](docs/applaut/CONNECT_YOUR_ROUTINE.md).
   Venkat is creating a fresh Applaut account for this (registration opened
   briefly on request, then closed again).
   The first sync starts at once.
4. Then verify and record here: the 27 jobs (one per uid) and their 54 PDFs
   synced, applications in To review, run_tracker rows under Run history,
   and the next scheduled run's checks (T + 30 min …) and sync (finish + 60 min).
Next build after that: Phase 3 (skeleton repo, profile-file export, setup
wizard, onboarding engine step), design §8.
The company-board scaling below is now secondary (it only feeds Applaut Basic).

**Keep scaling `backend/app/applaut/discovery/data/company_boards.json` — now at 500 companies, single-country density still below target. A proven sourcing method exists — use it.**

**This session found a working method.** Two failed/weak approaches first:
memory-guessing (790 candidates → 144 new, most already tried) and VC
portfolio pages (280 candidates → 26 hits, but +24 companies moved raw jobs
by 0 — skewed toward early-stage startups with no open data reqs). Then the
one that worked: **search for live target-role job postings already sitting
on the 7 supported ATS domains** (e.g. `site:jobs.personio.de "data
engineer"`, `site:boards.greenhouse.io "data engineer" Berlin`) — this
pre-qualifies a candidate as both "has a board on a supported adapter" and
"actively hiring for a target role" at once. Result: 34 candidates → 14 hits
(41%), and Germany raw jobs actually moved: 33 → 39 from just 14 companies.
**Use this method by default going forward** — see "Discovery Scaling —
Phase 1" below for the full write-up and the exact query pattern.

Quick start for next session:
1. `cd ~/Projects/lvamo/applaut && docker compose up -d postgres backend` (rebuild if images were pruned). The Mac's local DB is fresh (no data, no test account), so register a test user first. See "How to verify" below.
2. Search `site:<ats-domain> "<target role>" <German city>` across all 7
   adapter domains × the target role list × major German cities (see
   "Discovery Scaling — Phase 1" for the full method and domain list). Skip
   memory-guessing and VC-portfolio pages — both underperformed this method.
3. `docker compose exec backend python scripts/discover_company_slugs.py --seed <new_seed_file>`
4. **`docker compose restart backend`** after any `company_boards.json` change — uvicorn's
   `--reload` only watches `.py` files, not the JSON data file, so the running
   server keeps a stale in-memory company list until restarted. Bit us twice
   this session — don't skip it before re-verifying counts.
5. Re-verify with a clean single-country test (see "How to verify" below) —
   and pay attention to whether raw job count actually moves, not just
   company count.

---

## What Is Built and Working

### Auth
- JWT-based login / register
- Registration is currently **locked** (invite-only) via the `applaut.application_settings` table
- To open registration: set `allow_new_registrations = '1'` in `applaut.application_settings` via DBeaver
- Applaut is currently **hidden from the LVAMO hub** (still fully usable at `/applaut`). Hub visibility is platform config, not Applaut's: it lives in `platform.settings.verticals_enabled` since 2026-10-11 (migrations `0020`/`0021` moved it out of `applaut.application_settings`). To list Applaut on the hub again: `UPDATE platform.settings SET value = 'applaut,jobref' WHERE setting_name = 'verticals_enabled';`
- Token key in localStorage: `applaut_access_token` (namespaced per the platform's Multi-Vertical Architecture — see `PROGRESS.md`)

### User Profile
- Onboarding wizard (3 steps): name, roles, countries, employment types, skills, languages
- Per-profile `good_threshold` slider (70–100, default 85)
- Near-miss threshold = `good_threshold - 15`

### Discovery Engine
- Adapter pattern — **7 adapters implemented: Greenhouse, Lever, Ashby, Personio, Workable, SmartRecruiters, Recruitee** (all public/no-auth JSON APIs — no browser scraping). Personio's endpoint had gone dead (retired JSON API) and was fixed — see "Discovery Scaling" below.
- Company list: `backend/app/applaut/discovery/companies.py` — `CURATED_BOARDS` (hand-picked, ~22 entries) + `ADAPTER_REGISTRY` (keyed by `source_name`) + auto-merged entries from `backend/app/applaut/discovery/data/company_boards.json` (currently **500 companies total**, up from 18 at the start of the scaling effort — see "Discovery Scaling — Phase 1" below). Dedupes automatically against curated entries.
- Offline company-slug discovery script: `backend/scripts/discover_company_slugs.py` — probes a seed list of company names against all 7 adapters' raw endpoints, keeps only slugs that resolve to a real non-empty job board, appends to `company_boards.json`. Seed files: `backend/scripts/seed_companies.txt` (general EU batch) and `backend/scripts/seed_companies_de.txt` (sourced from real German startup directories).
- Role matching (`app/applaut/discovery/location.py`'s `matches_roles`) now uses the same synonym expansion as scoring (shared table: `backend/app/applaut/core/role_synonyms.py`) — a title like "Analytics Engineer" is now fetched for a "Data Engineer" search, not silently dropped before scoring ever sees it.
- Concurrency-capped: `DISCOVERY_CONCURRENCY` (default 20, env-configurable) semaphore in `engine.py` so a large `COMPANY_BOARDS` doesn't burst-hammer any single ATS host.
- Scheduled via APScheduler (`backend/app/applaut/discovery/scheduler.py`) — runs once per profile per interval even with several uvicorn workers (advisory lock + recency guard, 2026-10-17, see "Scheduled discovery across uvicorn workers" below)
- Location resolution: city → country code (`backend/app/applaut/discovery/location.py`)
- Manual trigger available via API — **and now auto-chains into rule-based scoring** (see Scoring section)

### Scoring
- **Rule-based scorer** (`backend/app/applaut/scoring/rule_based.py`):
  - 5 dimensions: role(35), skills(25), location(20), employment_type(10), experience(10)
  - Role synonym expansion (data engineer, devops, etc.)
  - Skills score uses JD keyword count as denominator (% of what job requires)
  - Re-scores ALL active opportunities on every run (upsert — no stale results)
  - Preserves user decisions across re-scoring runs
  - **Runs automatically after every discovery run** (`trigger_discovery` in `backend/app/applaut/services/opportunity.py` chains into `run_scoring`) — no separate "Run scoring" step needed
- **AI scorer** (`backend/app/applaut/scoring/ai_scorer.py`):
  - Uses `gpt-4o-mini` via `AsyncOpenAI`
  - Only scores previously-unscored opps (cost control)
  - Returns per-dimension explanations + near-miss keywords
  - **Gated in the UI** — "Scoring" dropdown on Opportunities page shows AI as disabled/greyed ("premium — coming soon"); wired up for a future subscription model, not user-selectable yet
- Near-miss gap analysis: keywords the user lacks, suitability assessment
- User decisions on near-misses: keep / dismiss / keep_with_keywords — actionable inline from the Opportunities page (see UI section)

### Document Generation
- Tailored resume + cover letter generation via OpenAI
- Stored in Cloudflare R2, metadata in PostgreSQL
- `generated_documents` table with download links

### Applications
- Application tracking (status: draft → submitted → interviewing → offer → rejected)
- Kanban-style view on Applications page

### Notifications
- In-app notification system with unread badge
- Auto-notified on discovery results
- Fixed: bell was calling `/notifications` instead of the correctly-prefixed path (404 on every page) — all four endpoints in `frontend/src/applaut/api/notifications.ts` now correctly resolve through the shared `applaut/api/client.ts` base URL

### Audit Log
- Every major action logged to `audit_logs` table
- Viewable in AuditLog page (`/applaut/audit`)

### UI
- Dark futuristic theme with CSS custom properties (design tokens)
- Inter font via Google Fonts
- Custom SVG favicon (geometric "A" mark)
- **Mobile-responsive**: slide-in sidebar with backdrop on ≤768px, fixed top bar with hamburger
- **Opportunities + Scores merged into one page** (`frontend/src/applaut/pages/Opportunities.tsx`) — the standalone Scores page is gone. Running discovery auto-scores; each card shows its score badge, per-dimension chips (hover for explanation), and near-miss gap keywords + keep/dismiss actions inline, or good-match actions (generate documents / start application) inline. Filters: Match (all/good/near-miss/below/unscored), Source, Country, Scoring mode (Rule-based; AI shown disabled). `/applaut/scores` route redirects to `/applaut/opportunities`; `?match=` query param supported for deep links from Dashboard
- Pages: Landing (`/applaut`), Login, Register, Onboarding, Dashboard, Opportunities, Applications, Resume, AuditLog, OpportunityDetail, DocumentDetail — all under `/applaut/*`

---

## Codebase restructuring into `app/applaut/` + `src/applaut/` (Aug 2026, committed)

All of Applaut's backend and frontend code moved from flat, unmarked shared
folders into `backend/app/applaut/` and `frontend/src/applaut/` — the
*durable policy* (what's shared vs. vertical-specific, and why) is
documented in `PROGRESS.md`'s "Codebase structure matches the URL structure"
section, not here. This entry is just the pointer + what changed file-path-
wise, since every path referenced elsewhere in this document now includes
the `applaut/` segment (already updated throughout this file).

Pure reorganization, zero behavior change — verified locally (backend boots
clean, full smoke test against real data: health, login, opportunities,
discovery run, audit, stats, `alembic upgrade head`; frontend `tsc` + `vite
build` clean with byte-identical bundle hashes to before the move) and in
production (same checks re-run against `api.applaut.lvamo.com` and
`www.lvamo.com` post-deploy).

One practical consequence: `backend/scripts/discover_company_slugs.py`'s
default output path is now `app/applaut/discovery/data/company_boards.json`
(was `app/discovery/data/company_boards.json`) — already updated in the
script, just noting it here since the "Quick start for next session" recipe
at the top of this file references running that script.

---

## Database

Applaut's own migrations (`backend/migrations/versions/`). The chain is shared
with Jobref and the platform layer (head `0021` as of 2026-10-11, see
`PROGRESS.md`). Only the Applaut-relevant ones are listed here:
- `0001` — initial schema (users, profiles, resumes, opportunities, scores, applications, generated_documents, notifications, audit_logs)
- `0002` — scoring columns
- `0003` — document columns
- `0004` — profile discovery timestamps
- `0005` — profile score threshold (`good_threshold`)
- `0006` — `application_settings` table
- `0012` — moved all 10 Applaut tables + 4 enum types from `public` into a
  dedicated `applaut` Postgres schema (see "Postgres schema separation"
  below). Jobref's own migrations (`0007`–`0011`) are interleaved in the
  same linear alembic chain since both verticals still share one DB/one
  migration history — see `PROGRESS_JOBREF.md`.
- `0019` — added `verticals_enabled` to `application_settings`; `0021`
  removed it again after it moved to `platform.settings` (`0020`).

**Key DB notes:**
- Scoring thresholds currently set to **GOOD=50, NEAR_MISS=35** in the DB for testing
- Revert to GOOD=85, NEAR_MISS=70 before go-live (update `good_threshold` in `applaut.profiles`)
- Applaut's tables live in their own `applaut` Postgres schema (see below) on
  the shared `lvamo-backend` VM/DB instance — namespaced at the schema level
  from Jobref, even though both still share one Postgres server/database and
  one alembic migration chain.

---

## Postgres schema separation: `applaut` + `jobref` schemas (Aug 2026, verified locally)

User's request: move from both verticals' tables sitting unnamespaced in
`public` to one Postgres schema per vertical, matching the existing
route/codebase namespacing pattern (`/api/v1/<x>/*`, `app/<x>/`) — done as
DB-first prep work before Jobref's own tables get built out further.

**This pass**: created both `applaut` and `jobref` schemas, moved all 10
existing Applaut tables and all 4 Applaut enum types
(`remote_preference_enum`, `employment_type_enum`,
`application_status_enum`, `document_type_enum`) from `public` into
`applaut`. Jobref's 3 existing tables (`jobref_users`,
`jobref_employee_profiles`, `jobref_seeker_profiles`) were deliberately
**left in `public`** — moving those into the `jobref` schema is explicit
follow-up work, not part of this pass (see `PROGRESS_JOBREF.md`).
`alembic_version` also stays unschemaed in `public` — it's shared migration-
history bookkeeping, not vertical data.

**Migration**: `0012_vertical_schemas.py` — `CREATE SCHEMA IF NOT EXISTS`
for both, then `ALTER TABLE ... SET SCHEMA applaut` / `ALTER TYPE ... SET
SCHEMA applaut` for each of the 10 tables / 4 enum types (in-place schema
moves, no data copy, no downtime). `downgrade()` reverses both sets of
moves and drops both schemas.

**Code changes** (`backend/app/applaut/models/*.py`, all 10 model files):
every model now declares `__table_args__ = {"schema": "applaut"}` (merged
into the existing tuple form for the two models — `Opportunity`, `Score` —
that already had a `UniqueConstraint` in `__table_args__`); every
cross-table `sa.ForeignKey(...)` target is now schema-qualified
(`"applaut.users.id"` etc. instead of `"users.id"`); every `sa.Enum(...,
create_type=False)` column now also carries `schema="applaut"`, so the
association is explicit at the SQLAlchemy layer rather than relying on the
DB connection's `search_path` — no engine/session/`db/base.py` changes were
needed, since schema is declared per-table/per-type, not connection-wide.

**Not changed**: `app/db/base.py`, `app/db/session.py`, `app/config.py`,
`migrations/env.py` — none needed edits; `Base.metadata` picks up each
table's `schema` attribute automatically. No raw SQL elsewhere in the
codebase references these table names directly (checked).

**Verified locally** (real, not mocked) — migration applied against the
local dev DB, then exercised through the live local API after a backend
restart:
- `\dn`/`\dt`/`\dT` in psql confirm the exact intended layout: 10 tables + 4
  enum types in `applaut`; `jobref_users`/`jobref_employee_profiles`/
  `jobref_seeker_profiles`/`alembic_version` still in `public`; `jobref`
  schema exists and is empty.
- Real API round-trip: `POST /api/v1/applaut/auth/register` → `201`, row
  confirmed present in `applaut.users` via psql, then deleted. A second
  registration → `GET /me` (JWT-authenticated read) → `200`; `POST
  /api/v1/applaut/profiles` (exercises both the `remote_preference` enum
  column and the `profiles.user_id → applaut.users.id` cross-table FK) →
  `201`. Both throwaway test users deleted afterward (profile cascaded).
- Regression: `POST /api/v1/jobref/auth/login` with bad credentials → `401`
  (not a crash) — Jobref unaffected, still reading/writing `public.jobref_*`
  tables as before.

**Deployed to production** (Aug 2026, see `PROGRESS.md` Deployment). Jobref's
tables were later moved into the `jobref` schema too (migration `0013`, see
`PROGRESS_JOBREF.md`).

---

## URL Namespacing migration (Aug 2026, committed)

Applied the platform's Multi-Vertical Architecture (see `PROGRESS.md`) to
Applaut specifically — this is the change-log; the durable policy is
documented there, not here.

- **Frontend**: all of Applaut's pages (`login`, `register`, `onboarding`,
  `dashboard`, `opportunities`, `resume`, `applications`, `audit`,
  `documents/:id`) moved from the frontend root to `/applaut/*`. `Jobref`
  was pulled out from under Applaut's `Layout` entirely — it now uses a
  small shared `frontend/src/components/BrandedPage.tsx` shell instead, so
  it has zero dependency on Applaut's routing/sidebar/auth code.
- **Backend**: `app.main` mounts the v1 router at `/api/v1/applaut` (was
  `/api/v1`) — single-line change in `backend/app/main.py`. Every endpoint
  path is otherwise unchanged, just prefixed.
- **localStorage token key** renamed `access_token` → `applaut_access_token`
  (in `frontend/src/applaut/api/client.ts`) so a future Jobref session can't collide
  with Applaut's.
- **Hostnames unchanged** — `www.lvamo.com` and `api.applaut.lvamo.com` stay
  as-is; only URL *paths* changed.

**Bug found + fixed along the way**: while tracing every API call site for
this rename, found that `frontend/src/applaut/api/applications.ts`, `audit.ts`,
`scheduler.ts`, and `stats.ts` were calling bare paths with no `/api/v1`
prefix at all — no rewriting interceptor and no path-rewriting nginx rule
compensating, so **Applications, Audit Log, Dashboard stats, and the
discovery scheduler toggle were silently 404ing in production** before this
fix. Fixed as part of centralizing the API base URL (see below) — all four
now confirmed working end-to-end via Playwright against real data (48 jobs /
2 good / 32 near-miss, 34 audit events) both locally and against the live
production API after deploy.

`frontend/src/applaut/api/client.ts` now bakes `/api/v1/applaut` into the axios
`baseURL` instead of repeating it per call site (root cause of the above
inconsistency) — every `src/applaut/api/*.ts` module calls resource-relative paths
now (e.g. `/opportunities`, not `/api/v1/opportunities`).

---

## Discovery Scaling — Phase 1 (In Progress, Committed)

**Goal (user-stated):** a single discovery run should return 100-200 raw job
listings with 50+ scoring as "good matches," for a realistic profile (multiple
target roles matching one tech stack, at least 1 target country).

**Status: code complete and verified working; company density still
insufficient for single-country searches, but meaningfully better.**

### Session update — Personio adapter fix (committed `efe3a95`)
Personio had quietly retired its `/api/v1/jobs` JSON endpoint (now 404s,
replaced by a client-rendered SPA). The adapter and the probing script were
both silently finding 0 Personio hits as a result. Fixed by switching to
Personio's legacy `/xml` feed (their "workzag-jobs" format), which is still
public and no-auth. This alone unlocked **201 new companies** — many of them
large German corporates (BASF, Bosch, Siemens, Continental, Deutsche Bank,
etc.) — sourced via a new seed list, `backend/scripts/seed_companies_de2.txt`
(1,397 candidate names: funded German startups + Mittelstand/industrial
companies + DAX/MDAX corporates + cybersecurity/software companies).
Board went **171 → 437 companies**.

`discover_company_slugs.py` gained a `--adapters` flag so old seed lists can
be cheaply re-probed against just Personio now that it works, instead of
re-running the full 7-adapter sweep.

**Re-verified with the clean Germany-only test** (see "How to verify"
below): raw job count **18 → 34**, no errors. Real progress — but the growth
is **sub-linear**: companies grew 2.4x (185→437) while jobs grew only 1.9x
(18→34), worse than the earlier "better-than-linear" trend that had been
extrapolated from a smaller sample (169→185 companies, +9%, drove 14→18 jobs,
+28%). Good-match count actually dipped slightly (3→2 @ threshold 85) while
near-misses jumped to 20 — more relevant-ish jobs are surfacing, just
scoring just under threshold. Small sample; not a red flag on its own.

**Revised extrapolation:** using all three data points (169→14, 185→18,
437→34), hitting the 100-200 raw-result target now looks like it needs
**~1,800-2,000 companies**, not the 800-1,500 estimated last session. Treat
this as a rough guide, not a hard target — re-extrapolate again after the
next batch.

### Session update — VC-portfolio batch (committed `90eb89b`) + a strategic finding

Kept sourcing toward the ~2,000 target, Germany-only per user request.
Memory-guessing hit a wall fast: generated ~790 candidate names from
memory across fintech/insurtech/healthtech/climate/mobility categories,
deduped against all prior seed files (2,290 already-tried names) — only
**144 were genuinely new**. Most of what's memorable from training data was
already sourced last session.

Switched to fetching real VC portfolio pages (Earlybird, HTGF, HV Capital,
Project A) via WebFetch — a different, less memory-biased source. Combined
batch: 280 deduped candidates → **26 new companies** (9.3% hit rate).
Board: 437 → **461**.

**Re-verified — and this is the important part:** Germany-only raw jobs came
back essentially flat: **33 raw / 2 good / 20 near-miss**, vs. 34/2/20
before this batch. Adding 24 companies (+5.5%) moved raw jobs by 0.

**Strategic takeaway:** company *count* alone is not what's driving raw job
volume — company *type* is. The VC-portfolio batch skewed toward
early/seed-stage startups, which typically have 0-1 open reqs at any given
time and often none in data engineering specifically. The Personio batch
(prior session update, +266 companies, 18→34 raw) worked because it happened
to include large, engineering-heavy German corporates (BASF, Bosch, Siemens,
Continental, Deutsche Bank, etc.) with sustained hiring pipelines — not
because it was large. The ~1,800-2,000 extrapolation above assumes company
mix stays constant; it likely overstates what's needed if sourcing gets more
targeted, and understates it if sourcing stays skewed toward small startups.

### Session update — job-posting-targeted sourcing (committed `35dc554`) — this is the method to keep using

Flipped the sourcing strategy again, and this one confirmed the hypothesis
directly. Instead of guessing company names and checking whether they have
*any* board, searched the web for live "data engineer" / "data platform
engineer" / "ETL developer" / etc. postings already sitting on our 7
supported ATS platforms in Germany (e.g. `site:jobs.personio.de "data
engineer"`, `site:boards.greenhouse.io "data engineer" Berlin`). This
pre-qualifies a candidate on **both** axes at once — has a board on a
supported adapter, *and* is actively hiring for a target role right now —
instead of just the first one.

Result: 34 candidates → **14 hits (41% hit rate)**, vs. 9.3% for the
VC-portfolio batch and far above blind memory-guessing. Board: 461 → **475**.
Re-verified: Germany raw jobs **33 → 39 (+6 from just 14 companies)** — a
real per-company lift, vs. the VC-portfolio batch's +24 companies → +0 jobs.

**This confirms the strategic finding and gives a concrete, repeatable
method: search `site:<ats-domain> "<target role>" Germany/Berlin/Munich/...`
across all 7 adapter domains (`boards.greenhouse.io`, `jobs.lever.co`,
`jobs.ashbyhq.com`, `jobs.personio.de`, `apply.workable.com`,
`jobs.smartrecruiters.com`, `jobs.recruitee.com`) crossed with the target
role list (Data Engineer, ETL Developer, Python Developer, SQL Developer,
PySpark Developer, Data Platform Engineer, Databricks Developer) and major
German cities. This is now the default sourcing method — prefer it over
VC-portfolio pages or memory-guessing.** It naturally self-limits (you run
out of distinct search-result pages per query), so expect to need many query
variants (role × city × adapter combinations) to keep finding fresh hits,
and to re-run periodically since job postings churn (today's non-match may
be hiring next month).

Two more rounds applied the same session (committed `974da97`): more role
variants (ETL, Python Developer, Databricks, data warehouse, SQL developer)
× more cities (Munich, Hamburg, Frankfurt, Stuttgart, Cologne, Leipzig,
Dresden, Nuremberg, Karlsruhe). 57 candidates → **19 hits (59% hit rate)** —
even better than the first round, likely because later queries increasingly
hit companies with several open roles/cities generating multiple distinct
search hits pointing at the same still-new company. Board: 475 → **494**.
Re-verified: Germany raw jobs **39 → 47** (+8 from 19 companies).

One final round (committed `7b120e9`): Databricks/PySpark role variants +
remaining adapter/city gaps. 11 candidates → 6 hits (55%). Notable find:
**Statista** (Hamburg-based, well-known, multiple open data-engineering
roles on Ashby — the first solid Ashby hit this session). Board: 494 → 500.
Re-verified: Germany raw jobs 47 → 48.

**Session total: 171 → 500 companies (2.9x), Germany raw jobs 18 → 48
(2.7x), good matches steady at 2 (@85 threshold), near-misses climbed to
32.** Diminishing but still real returns each round — the method keeps
working, it just takes more query variants each time to find fresh,
not-already-tried candidates. 6 seed files now exist
(`seed_companies_de.txt` through `_de6.txt`); future sessions should keep
appending `_de7.txt` etc. rather than reusing a name, since the probe
script's dedup is against `company_boards.json` slugs, not seed file
names — re-running an old file just wastes requests re-probing misses.

### What was built (all verified against live data via local docker-compose)
1. Closed a gap where `matches_roles` (discovery-time filter) only did literal
   substring matching while the scorer already had synonym expansion — jobs
   titled e.g. "Analytics Engineer" were being silently dropped before
   scoring ever saw them for a "Data Engineer" search. Fixed by extracting
   the synonym table to `app/core/role_synonyms.py`, shared by both.
2. Added an `asyncio.Semaphore` concurrency cap to the discovery engine.
3. Built and verified 3 new ATS adapters (Workable, SmartRecruiters,
   Recruitee) — each confirmed against a real company with real matching
   jobs, not just a 200-OK response.
4. Built `backend/scripts/discover_company_slugs.py` — an offline batch
   script that probes candidate company-name slug variants against all 7
   adapters and keeps only ones that resolve to a real non-empty job board.
   Output → `backend/app/applaut/discovery/data/company_boards.json`, merged into
   `COMPANY_BOARDS` at runtime, deduped against the hand-curated list.
5. Ran the script across ~660 seed company names in 4 batches (general EU
   guesses, a broader/gaming-and-marketplace batch, and a batch sourced from
   real German startup-directory web pages) → **185 companies found and
   verified live**, up from 18.

### The honest numbers (clean tests, wiped DB between runs)

| Test profile | Companies | Countries | Roles | Raw results | Good matches |
|---|---|---|---|---|---|
| User's exact scenario (Data Engineer + 6 tech-stack-adjacent roles) | 185 | Germany only | 7 | **18** | 3 (@ threshold 85) |
| Broader realistic profile | 185 | 8 EU countries | 5 | **575** | 13 (@85) / 230 (@70) |
| User's exact scenario, after Personio fix | 437 | Germany only | 7 | **34** | 2 (@85), 20 near-misses |
| Same, after VC-portfolio batch (weak) | 461 | Germany only | 7 | **33** | 2 (@85), 20 near-misses |
| Same, after job-posting-targeted batch (strong) | 475 | Germany only | 7 | **39** | 2 (@85), 24 near-misses |
| Same, after 2 more targeted rounds | 494 | Germany only | 7 | **47** | 2 (@85), 31 near-misses |
| Same, after final targeted round (session end) | 500 | Germany only | 7 | **48** | 2 (@85), 32 near-misses |

**Conclusion:** the 100-200/50+ target is easily hit for multi-country
searches today. It is **not yet hit for single-country searches** — Germany
raw results roughly doubled (18→34) after the Personio adapter fix added 266
companies (171→437), but the growth is **sub-linear**: companies grew 2.4x
while jobs grew only 1.9x — worse than the earlier 169→185 data point
suggested. Re-extrapolating from all three data points now suggests
**~1,800-2,000 companies** are needed for single-country search to reliably
hit the target on its own (revised up from the earlier 800-1,500 estimate,
which was based on a smaller, noisier sample). This is still the next
session's primary task (see banner at top of this file).

**Sourcing note:** memory-guessed company batches hit ~29% (script finds a
working slug). A batch sourced from real German-startup-directory web pages
still only hit ~14%, because many funded early-stage startups don't have a
public ATS board yet. Expect to need several hundred *candidate* names to
net a few hundred *working* companies — budget for that ratio.

### How to verify (clean single-country test recipe)
The test account `verify2@test.com` / `TestPass123!` exists in the **Mac's**
local dev DB (re-created 2026-10-11; the DB/role is `lvamo`, and Applaut's
tables are in the `applaut` schema). Its profile is the "Data Engineer + 6
tech-stack roles, Germany (`DE`) only" scenario. If the local volume is ever
wiped, re-create the account: set `allow_new_registrations` to `'1'`, then
`POST /auth/register`, then set it back to `'0'`, then `POST /profiles` with
those roles and `target_countries: ["DE"]`. To re-run cleanly:
```bash
# wipe accumulated opportunities so results reflect only the current company pool
docker compose exec -T postgres psql -U lvamo -d lvamo -c "TRUNCATE applaut.opportunities, applaut.scores CASCADE;"
# log in, get a fresh token (prior token may have expired)
curl -s -X POST http://localhost:8000/api/v1/applaut/auth/login -H "Content-Type: application/json" \
  -d '{"email":"verify2@test.com","password":"TestPass123!"}'
# run discovery — new_jobs_found IS the clean raw-result count right after a truncate
curl -s -X POST http://localhost:8000/api/v1/applaut/discovery/run -H "Authorization: Bearer <token>"
# breakdown by match category
curl -s "http://localhost:8000/api/v1/applaut/opportunities?match=good&page_size=1" -H "Authorization: Bearer <token>"
```
**Baseline as of 2026-10-11 (Mac, 500 companies):** 43 raw, 4 good (@85), 30
near-miss. That's down from 48 raw at the end of the Aug session with the
same company list, most likely because postings turned over. Compare new
batches against this number, not 48.

(All API paths live under `/api/v1/applaut/*`.) If testing country/role
breadth, `PATCH /api/v1/applaut/profiles/me` with new
`target_roles` / `target_countries` first — but re-truncate between tests, or
`scored` in the discovery response will reflect the whole accumulated pool
from prior tests, not just the current profile's matches (this tripped us up
mid-session).

### Also fixed
- Notification bell — see UI/Notifications section above (already committed).
- `deploy.sh` on the VM had an uncommitted quoting bug (already committed and deployed).
- Personio adapter (dead JSON endpoint → live XML feed) — see session update
  above (committed `efe3a95`, deployed).

---

## 2026-10-18: routine fix merged (job-search-automation PR #1, `6143804`, 13:47 UTC)

Venkat asked why runs "finished with problems". Cause (from the runs'
`sources_failed` and summaries): the routine's web search ignores `site:`
(so ATS-board and germantechjobs.de discovery found nothing), it guessed
board names (93 of 163 calls 404), and recovered errors were listed as
failures. https://github.com/vsvedantham/job-search-automation/pull/1 adds
`config/company_boards.json` (441 boards: Applaut's list + boards from his
jobs, dead ones removed, + germantechjobs.de RSS) and `pipeline.py
fetch-boards` (read-only, ~40 s), and changes the prompt (no `site:`, no
guessed boards, only real failures in `sources_failed`). Dry run with no
Neon/R2 writes: 413 live boards, 24,958 postings, 79 new candidates (vs 18
assessed from boards this morning); known jobs and duplicates skipped.
Before merging, `board_posted_within_days` was set to 7 like the other
sources (rejected postings aren't remembered, so a longer window would
re-read them every run): 52 candidates. With a refusing proxy the command
ends in ~10 s, exit 0, every board reported as an error. Merged on Venkat's
"merge if it works and doesn't make results worse". **To check:** the
18:07 UTC run on 2026-10-18 is the first with the change (Applaut's status
check at 18:37): expect `fetch-boards` counts in the summary, fewer or no
`sources_failed`, and "Boards to add"/"Boards gone" sections.
**Applaut Basic impact:** 77 of the 500 boards in
`backend/app/applaut/discovery/data/company_boards.json` now return 404
(60 Personio, 11 Greenhouse, 3 Lever, 3 Recruitee) and Check24 on
SmartRecruiters returns 401.

## 2026-10-18: Venkat's routine connected in production

- Venkat re-created his account (old one deleted after backup
  `lvamo-pre-user-delete-20261018-1304.dump`; registration open 13:05–13:20:18
  UTC, auto-closed) and connected his routine himself: connection active,
  contract v1, first sync 13:20–13:21 UTC: **30 jobs, 60 PDFs copied**, 0
  linked to shared Basic postings.
- **Fixed (commit `7f592ab`):** Run history stayed empty because
  `run_tracker` rows were only copied by the status checks after the next
  scheduled run. Now every sync copies the last 30 days of runs, and saving
  a connection copies them at once. Deployed (backup
  `lvamo-pre-runs-20261018-1327.dump`); his two runs backfilled with
  `checks.refresh_runs`: `20261018_0809` and `20261017_2008`, both
  `succeeded` with `sources_failed` set → shown as "Finished with problems".
- What his runs report as failed sources: the routine's web search doesn't
  honour `site:` filters, so ATS-board and germantechjobs/englishjobs
  discovery returns little; `boards-api.eu.greenhouse.io` blocked by the
  cloud egress proxy; Arbeitnow 429 (recovered). This supports giving the
  routine a saved list of company boards to poll in code (see the
  Basic-vs-routine comparison).
- Next scheduled check: 18:37 UTC (run at 18:07).

## 2026-10-18: job engine chosen in onboarding + routine setup kit

Venkat's request: decide how jobs are found during onboarding (Settings is
for later changes). Routine accounts get no discovery controls at all.
- **Onboarding step 4 "How should Applaut find jobs?"**: *Applaut job
  search* (Basic) → "Search automatically?" yes → every 6/12/24 h, no →
  manual Run discovery only; *Your own Claude routine* → "Already have
  one?" → after the profile is created, a step 5 with the connection form
  (yes) or the setup kit download (not yet), both skippable to Settings;
  *Applaut AI* shown disabled ("Coming soon"). The frequency control moved
  here from step 3. `CreateProfileRequest` gained `job_engine` (basic |
  own_routine) and `discovery_enabled` (ignored for own_routine);
  `create_profile` now also saves `good_threshold` (it was silently
  dropped) and audit-logs `profile.create`.
- **Routine accounts**: no Run discovery, no "Include Applaut Basic jobs"
  toggle (removed; the API's `include_shared` stays, default off for them),
  no engine or source filters; empty state links to Settings → Job engine.
- **Setup kit** (`GET /job-engine/routine/setup-kit`, `routine/kit.py`,
  static files in `routine/setup_kit/`): a zip generalised from
  `vsvedantham/job-search-automation@85d70a8`: ROUTINE_PROMPT (no names,
  employers, numbers or visa details; experience/project rules read from
  the profile), `pipeline.py` (file names from `personal.name`, generic
  sample letter), templates (photo optional), fonts (OFL / Apache), setup.sh,
  sync_to_mac.sh; plus generated `README.md` (setup steps), `CLAUDE.md`,
  `SETUP_PROMPT.md` (for Claude Code), `sql/applaut_reader.sql`, and
  `profile/master_profile.yaml` + `config/search_config.yaml` pre-filled from
  the user's Applaut profile (name, email, skills, roles, preferences; the
  rest is TODO, never invented). Not included: Venkat's profile, photo, or
  Mac unlock listener. Also downloadable from Settings.
- Read-only SQL (Settings, kit, guide) now grants `SELECT ON ALL TABLES` +
  default privileges, so it works before the routine's first run creates
  the tables.
- Tests: `tests/applaut/test_onboarding_engine.py` (three engine choices at
  creation incl. tasks queued / not, Applaut AI refused, kit contents, no
  personal words in any text file, generated YAML, the kit's own fact guard
  accepts the generated profile's sample). Full suite 142 passed.
- Verified locally in the browser: steps 1–4, both step-4 branches, routine +
  "Not yet" → profile created → kit download (200) → "Connect it now" shows
  the form; routine Opportunities without discovery controls; Settings kit
  card. **Not verified:** rendering the kit's PDFs (WeasyPrint isn't in the
  backend image); only the fact guard and YAML were exercised.
- Prod (commit `b61376c`): backup `lvamo-pre-onboarding-20261018-1253.dump`,
  `deploy.sh`, both workers up without errors, kit fonts present in the
  image, all API hosts 200, `/routine/setup-kit` 403 without auth, live
  bundle has the engine step and kit button (toggle gone), registration
  still closed. Venkat's existing profile was created before this, so it's
  on `basic`: he switches in Settings → Job engine.

## 2026-10-18: Venkat's new account, onboarding fix, shared jobs hidden for routine accounts

- **Registration** was opened on request at 12:22 UTC
  (`applaut.application_settings.allow_new_registrations = '1'`) and closed
  automatically by a one-off job on the VM at 12:37:52 UTC (verified via
  `GET /settings/allow_new_registrations` → `0`; script removed). Venkat
  created his new account then.
- **Blank page after onboarding** (commit `8511e4a`, frontend only): the
  discovery-frequency slider offered 1–72 h but `CreateProfileRequest`
  accepts only 6/12/24 (and decimal years are rejected); the 422's list of
  errors was put into JSX, which crashed React. Now a 6/12/24 choice, years
  rounded, employment type and 0–50 years checked first, and
  `api/errors.ts apiErrorMessage()` used on Login, Register, Resume,
  documents, Opportunities so no validation error can blank a page.
  Reproduced both 422s against the local API; verified onboarding with
  "4.5" years creates the profile and moves to Resume.
- **Shared Basic jobs hidden for routine accounts** (commit `f8b85ec`): a
  brand-new account saw 56 jobs because Applaut Basic's jobs are one shared
  pool (by design: public postings fetched once). For `own_routine`
  profiles, `GET /opportunities` now defaults to `include_shared=false`
  (private jobs + shared postings their routine also found); the
  Opportunities page has an **Include Applaut Basic jobs** checkbox
  (per browser, off by default); dashboard stats for routine accounts count
  the routine's jobs and use its match %. Basic accounts unchanged. Tests:
  136 passed. Verified locally (1 routine job by default, 44 with the toggle).
  Prod: backup `lvamo-pre-shared-20261018-1238.dump`, `deploy.sh`, both
  workers up without errors, all API hosts 200, toggle in the live bundle.

## Opportunities: routine jobs first + apply actions (2026-10-18, deployed)

Commit `3c0f9ed`. Venkat's request: his routine's jobs first, and per job
Apply / copy the documents folder / mark applied / mark unavailable.
- **List** (`services/opportunity.py`): jobs with a `routine_jobs` row for
  the user come first (heading "From your Claude routine", then "Other jobs
  (Applaut Basic)"), then by match %. Tabs **To review / Applied / Not
  available / All** with counts (`?state=`), default To review.
- **Actions** (`PUT /opportunities/{id}/tracking`, `services/application.py
  set_tracking`): **Mark as applied** → application `submitted` +
  `applied_at`; **Not available** → *Posting closed* (`closed`) or *I can't
  apply* (`withdrawn`); **Undo** → `pending_review`, dates cleared. One
  application per job, created if missing; audit action `application.tracking`.
- **Apply ↗** opens `application_url`. **Copy folder path** copies
  `<folder>/<uid>`, where `<folder>` is the Mac sync's destination
  (`sync_to_mac.sh`, default `~/JobSearchDocuments`), set per browser in
  Settings → "Documents on this computer" (localStorage, it's per computer);
  only shown when the routine's documents are done. Paste in Finder with ⇧⌘G.
  Clipboard falls back to `execCommand('copy')` when the Clipboard API is refused.
- Settings shows "Set up your profile first" (link to onboarding) for an
  account without a profile, instead of a 404 error.
- Tests: `tests/applaut/test_opportunity_tracking.py` (routine-first order
  and folder info, all three actions + undo + tab counts, per-user and
  private-job 404, bad input). Full suite 135 passed.
- Step-by-step guide for connecting a routine: [`docs/applaut/CONNECT_YOUR_ROUTINE.md`](docs/applaut/CONNECT_YOUR_ROUTINE.md).
- **Verified in production (2026-10-18):** backup
  `/home/ubuntu/backups/lvamo-pre-opps-20261018-1211.dump` first; `deploy.sh`
  (no migration); both workers up, no errors; all four API hosts 200; the
  new `PUT …/tracking` answers 403 without auth; the live Pages bundle has
  the new UI. Logged-in pages not checked in prod (no prod test login).
- Verified locally in the browser (seeded engine-3 user, deleted after):
  sections, tabs and counts, Mark as applied → "✓ Applied 18 Oct" + Undo,
  Not available → reasons → Not available tab, Copy folder path, 375 px.
- Known test flake (not from this change): `tests/prosho/test_evidence.py::
  test_daily_job_skips_recent_and_checks_due` counts every due source in the
  DB, so it fails when the local DB holds a hand-made ProSho project whose
  sources are due (seen once on 2026-10-18, passed on rerun).

---

## Job engines — Phase 2: your own Claude routine (2026-10-17, deployed)

Engine 3 of [`docs/applaut/JOB_ENGINES_DESIGN.md`](docs/applaut/JOB_ENGINES_DESIGN.md)
§6: Applaut reads a user's routine output from **their** Neon and R2 with
read-only credentials and copies it into Applaut. Commit `b41303d`.

**Code map** (`backend/app/applaut/routine/`):
- `source.py`: `NeonReader` (asyncpg; every query in a READ ONLY transaction
  with a 30 s statement timeout; works through Neon's pooler) and
  `R2RoutineStorage` (boto3, list/get only). `make_storage` is the one place
  an R2 client is built (tests replace it). Private/loopback hosts are refused
  unless `APPLAUT_ROUTINE_ALLOW_PRIVATE_HOSTS` (tests only).
- `schedule.py`: cron + timezone → status checks at T+30m/+60m/+2h/+3h,
  one open `routine_check` and one open `routine_sync` task per profile.
  APScheduler counts weekdays from Monday, cron from Sunday: numbers are
  translated to names. Runs must be ≥ 4 h apart.
- `checks.py`: copies `run_tracker` rows into `routine_runs`, decides
  finished / still running / stopped / didn't run, queues the sync at
  `finished_at + 60 min`, notifies once per bad run, pauses the connection
  after 5 consecutive failures.
- `sync.py`: §6.4. Reads `(uid, last_seen_at, docs_status)` for all jobs,
  then full rows only for new/changed ones; per job a savepoint, so one bad
  row doesn't stop the others.
- `core/credentials.py`: Fernet/MultiFernet, key `APPLAUT_CREDENTIALS_KEY`
  (comma-separated; first encrypts, all decrypt; `rotate()` re-encrypts).
- `services/job_engine.py`, `api/v1/routers/job_engine.py` (`/job-engine`),
  `schemas/job_engine.py`.

**Migration `0027`**: `routine_connections`, `routine_runs`,
`routine_syncs`, and `routine_jobs` (not in the design's table list, added
because the sync needs it: uid → opportunity, whether it was linked to a
shared Basic posting, the copied PDFs' ETags, and when the uid disappeared
from the routine's database).

**Decisions / assumptions made while building** (smallest reasonable ones):
- Saving a connection requires the engine to be "Your Claude routine" first
  (409 otherwise); the UI does both from one page.
- A save re-runs every check; nothing is stored unless all pass. Saving
  again with no changes is the "Try again" for a paused connection.
- The first save (or new secrets) queues a sync **now** (§6.7 step 9).
- Sync now: refreshes run status inline, then queues the sync and kicks the
  dispatcher in the background; 429 within 10 min of the last one.
- "Linked to a shared posting" uses the shared, active Basic opportunity
  (no private copy); its description is never overwritten.
- A sync notifies only when it found new jobs, copied documents, or failed.
- PDFs: the routine names files `<Name>_CV.pdf` / `<Name>_CoverLetter.pdf`,
  so they're found by suffix (works for the skeleton's other names too).
- Removed rows: `routine_jobs.removed_at` + shown in the sync history; the
  job page doesn't show it yet.

**Tests** (`backend/tests/applaut/test_routine_*.py`, fake routine schema
with a SELECT-only role in the local Postgres + in-memory R2,
`routine_fake.py`): 36 new, full suite **131 passed**. Covered: encryption
round trip and key rotation; secrets never in API responses or audit log;
refusal of writer roles, superusers, writable R2 keys, private hosts, bad
input; v0 detection; engine switch needs confirmation and deletes the
connection; other users see nothing; sync creates opportunities,
assessments (with `CHECK:` flags), PDFs at
`applaut/documents/{user}/{opp}/{sha8}/…`, text versions, description,
pending_review applications, one notification, audit entry; unchanged
second sync reads nothing from R2; changed PDF replaces the current
document; link to a shared posting by normalised URL; private jobs 404 for
others; removed rows kept; non-PDF/oversized files skipped and reported;
untrusted URLs dropped; source failure recorded; Sync now rate limit;
checks through the real dispatcher (finished → sync at +60 min, failed with
reason, running → stopped at T+3h, routine's 6 h stale marker, sources_failed
→ problems, missed, v0, pause after 5 failures and recovery).

**Verified locally (browser preview)**, seeded engine-3 user: dashboard
engine card (failed state with the §6.5 sentence, last run / synced / next
run rows, Sync now, Open routine, Run history); Settings: engine choice
(Applaut AI disabled), connection form shows only "Saved · host" / "ends in
…3f2a" hints, Test connection runs real network checks and lists each
failure, schedule picker, run history (funnel counts, details; a
`<script>` in the summary renders as text), sync history; 375 px wide
with no horizontal scroll. Seed data deleted.

**Verified in production (2026-10-17):** backup
`/home/ubuntu/backups/lvamo-pre-0027-20261017-1113.dump` taken first
(PGDMP header, 23 tables of data listed by `pg_restore -l`);
`.env.production` backed up to `/home/ubuntu/backups/.env.production.bak-20261017-0027`,
then `APPLAUT_CREDENTIALS_KEY` generated on the VM (never printed) and
appended; inside the container an encrypt/decrypt round trip works.
`deploy.sh` ran `0026 → 0027`; both workers started with no errors; DB at
`0027` with the four `routine_*` tables; data unchanged (12 shared
opportunities, 2 profiles on `basic`, no engine tasks). Applaut, Jobref,
ProSho health and platform `verticals_enabled` all 200; `/job-engine`
routes answer 403 without auth. Cloudflare Pages serves the new bundle.
**Not verified in prod:** the logged-in Settings/dashboard pages and a real
sync — both wait for Venkat to connect his routine (banner at the top).

**Not verified:** a read-only probe of Venkat's real Neon/R2 from the Mac
was blocked by the session's permission policy, so real-data compatibility
is checked for the first time by the first production sync (the code
follows the routine's `pipeline.py` table and file layout, read from
`vsvedantham/job-search-automation` at `85d70a8`).

---

## Job engines — Phase 1 shared core (2026-10-17, deployed)

Applaut is moving to three job engines chosen per user: **Applaut Basic**
(today's non-AI search, the fallback), **Applaut AI** (Claude run by Applaut,
paid via credits, later) and **your own Claude routine** (runs in the user's
Claude account; Applaut reads its Neon/R2 output). Full design, decisions and
build order: [`docs/applaut/JOB_ENGINES_DESIGN.md`](docs/applaut/JOB_ENGINES_DESIGN.md).
Venkat's routine already writes the `run_tracker` table Applaut will read
(routine commit `85d70a8`, schema checked read-only 2026-10-17).

**Phase 1 (commit `3e777fd`)** — groundwork every engine uses:
- **Migration `0026`**: `profiles.job_engine` (`basic | applaut_ai |
  own_routine`, everyone `basic`); `opportunities.owner_user_id` (NULL =
  shared Basic job, set = private job from an AI engine) with two partial
  unique indexes replacing `UNIQUE (source, external_id)`;
  `job_assessments` (AI match %, matched/missing must-haves, flags — kept
  apart from rule-based `scores`); `generated_documents.engine /
  content_type / content_sha256` for engine PDFs; `engine_tasks`.
- **Visibility** (`services/visibility.py`): every opportunity read goes
  through one rule; another user's private job is a 404 everywhere (list,
  detail, scoring, documents, applications, stats).
- **Bug fixed on the way:** dismissing a near miss used to set the shared
  opportunity `is_active = false`, hiding it for **every** user. Now it only
  hides it for the user who dismissed it.
- **Scheduler**: the schedule now lives in `applaut.engine_tasks`. Each
  worker runs one dispatcher every 2 min that claims due tasks with
  `FOR UPDATE SKIP LOCKED`; failed tasks retry after 1, 5, 30 min, then
  `failed`; a task stuck `running` > 1 h is retried. Basic discovery is the
  first task kind (only for `job_engine = basic` profiles with discovery
  on); the next run is queued one interval after each run. This replaces
  the per-worker APScheduler jobs, so the "still per-worker" caveat in the
  section below no longer applies. Behaviour change: turning auto-discovery
  on with no previous run now runs discovery within ~2 minutes (before: after
  one full interval).
- **API**: `assessment` and `is_private` on opportunity list/detail; `engine`
  filter; documents carry `engine`, `content_type`, `has_file`;
  `GET /documents/{id}/file` → 5-minute signed R2 link (owner only, 503 if R2
  isn't configured); Applaut's template generator returns 409 for an engine's
  job.
- **UI**: AI match %, matched/missing chips and "to check" flags on cards;
  AI assessment panel on the job page; engine badge and filter; "Run
  discovery" and the rule-based scoring picker only on Basic; **Open PDF** on
  the documents page; description and document text now use theme colours
  (were unreadable in dark mode).

**Tests:** `backend/tests/applaut/` (shared fixtures in `conftest.py`):
visibility (owner sees job + assessment; others get 404 on list, detail,
apply, documents; others' scoring and stats skip it), dismissal per user,
templates can't overwrite engine documents, PDF link owner-only / 503 without
R2, dispatcher (one open task, cancel on disable or engine switch, interval
change moves next run, two concurrent dispatchers run a task once, retry
backoff then fail, stale running task recovered). The leak tests fail when
the visibility rule is disabled. Full suite: 95 passed.

**Verified locally (browser preview):** with a seeded private job +
assessment + PDF docs on `verify2@test.com` switched to `own_routine`: list
card, engine filter, detail assessment panel, documents page without
generate controls, Open PDF error path (no local R2). Switched back to
Basic: page unchanged from before. Seed data deleted.

**Verified in production (2026-10-17):** backup
`/home/ubuntu/backups/lvamo-pre-0026-20261017.dump` taken first;
`deploy.sh` ran `0025 → 0026`; both workers started with no errors;
Applaut/Jobref/ProSho health 200, platform settings 200; new routes answer
(403 without auth); DB: both profiles `basic` with discovery off, so 0
engine tasks; all 12 opportunities shared; both new unique indexes present.
Cloudflare Pages deployed `3e777fd`; the live bundle contains the new UI.
**Not verified in prod:** the logged-in pages (no prod test login) and a
real PDF link (no engine documents exist until Phase 2).

---

## Scheduled discovery across uvicorn workers (2026-10-17, deployed)

**Problem:** prod runs `uvicorn --workers 2` (`backend/Dockerfile.prod`) and
`main.py`'s lifespan starts the discovery scheduler in each worker, so each
worker had its own APScheduler with its own job per profile: with discovery
on, every profile's discovery + auto-scoring + "Discovery complete"
notification would have run twice per interval. Latent only: both prod
profiles have `discovery_enabled = false`.

**Fix** (commit `002f6e6`, `scheduler.py` only): `_run_profile` now
1. takes `pg_try_advisory_xact_lock(hashtextextended('applaut.discovery:<profile id>', 0))`
   and skips if another worker holds it. The lock sits on its **own
   session** held open for the whole run, because `run_discovery_for_profile`
   and `run_scoring` both commit mid-run and a commit would release a lock
   held on the working session. It is released after `last_discovery_at`
   is committed.
2. skips if `last_discovery_at` is within 90% of the profile's interval
   (`_RECENT_RUN_FRACTION`), read from the DB, so a worker whose timer fires
   after the other finished doesn't re-run. A failed discovery doesn't set
   `last_discovery_at`, so another worker may retry it that interval.

The manual "Run discovery" API path (`services/opportunity.py`) is
unchanged: it doesn't take the lock or set `last_discovery_at`.

**Tests:** `backend/tests/applaut/test_discovery_scheduler.py` (first
Applaut tests; discovery and scoring stubbed): two concurrent runs → one;
run after a finished run → skipped; lock held elsewhere → skipped; 6h
interval: 5h old → skip, 5.5h old → runs. All 4 fail with the guards
disabled; full suite 42 passed.

**Verified in prod (2026-10-17)** after `deploy.sh`: VM at `002f6e6`, both
workers started clean, `/api/v1/{applaut,jobref,prosho}/health` 200. Inside
the prod container, holding the lock on one session made `_run_profile`
log "already running in another worker; skipping" for a real profile, and
`pg_locks` showed 0 advisory locks after release. Not exercised in prod:
an actual scheduled discovery run (no profile has discovery enabled).

**Still per-worker (harmless now):** `schedule_profile()` from the
enable/disable API only updates the worker that served the request, so
`GET /scheduler/status`'s `jobs` (next run time) reflects whichever worker
answers, and a worker started before a frequency change keeps its old
interval until restart. Runs stay correct: `_run_profile` re-reads
`discovery_enabled` and the interval from the DB, so a stale worker is
skipped or does nothing. A proper fix would be a single scheduler (separate
process or leader election).

---

## Known Issues / Deferred Work

- **Discovery company density** — see "Discovery Scaling — Phase 1" above. A working sourcing method now exists (search for live target-role postings on the supported ATS domains — 41-59% hit rate, and raw jobs actually move). Currently at 500 companies, Germany raw jobs at 48 (up from 18 at session start). Keep applying the method — still short of the 100-200 raw-result target.
- **Individual page mobile polish** — Layout is now responsive, but page-level content (cards, grids, tables) may still need padding/sizing tweaks on small screens. Not yet reviewed page-by-page.
- **Fixed (Aug 2026, from Jobref work but app-wide)**: shared `input, select, textarea` rule in `frontend/src/index.css` had `font-size: 0.875rem` (14px computed) — below the 16px threshold that triggers iOS Safari's auto-zoom-on-focus, a real mobile bug across every form in both verticals, not just style. Bumped to `1rem` + increased padding so tap targets clear the 44px comfort guideline too. See `PROGRESS_JOBREF.md`'s "Mobile-first follow-up" entry for the full detail — noted here since it affects every Applaut form (login, register, onboarding, resume, etc.) even though the fix originated from Jobref work.
- **AI scoring** — implemented but intentionally gated off in the UI (disabled dropdown option) pending the subscription/premium model. Not user-reachable right now.
- **Workday, LinkedIn, StepStone, Indeed, Xing, Teamtailor** — not yet built. Teamtailor investigated and rejected for the current adapter pattern (requires a per-company API key, doesn't fit the public-JSON model). Workday investigated and deferred ("Phase 1.5") — real endpoint exists but needs a heavier per-company probing strategy (subdomain + datacenter number + tenant/site, not a single guessable slug).
- **Auto-apply mode** — not built. Current mode is review-only (user approves before submission).
- **Multiple profiles per user** — schema supports it, UI does not yet expose it.
- **Registration** — locked. Flip `allow_new_registrations` in DB when ready for public launch.

---

## What's Next (Suggested)

- **Keep scaling company_boards.json using the job-posting-targeted search method** (see banner at top — primary task for next session)
- Page-by-page mobile polish (Opportunities, Resume pages most likely to need it)
- Subscription/premium model to unlock AI scoring in the UI
- Playwright-based application assist (prefill ATS forms)
- Open registration when ready for beta users
