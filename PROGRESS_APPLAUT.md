# Applaut — Progress

> Vertical-specific progress for Applaut. Platform-level infra/architecture
> lives in [`PROGRESS.md`](PROGRESS.md) — read that first if you haven't.
> Applaut's product spec is [`docs/applaut/SPEC.md`](docs/applaut/SPEC.md)
> (moved there from the repo-root `CLAUDE.md` on 2026-10-11, when `CLAUDE.md`
> became the LVAMO master spec).

---

## 🎯 NEXT SESSION PRIMARY TASK

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
