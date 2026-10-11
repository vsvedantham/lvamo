# ProSho — Beta Plan

**ProSho** (*Pro*ject *Sho*wcase) is the third LVAMO vertical, alongside
Applaut and Jobref. It turns a student's capstone repository into one
public, evidence-backed project page: what the project promised, proof
that each promise was met, a live demo, and the work behind it.

| | |
|---|---|
| Status | Planning — nothing built yet |
| Plan written | 2026-10-11 |
| Beta launch target | Mid-January 2027, before end-of-semester capstone presentations (assumed Feb 2027) |
| First pilot | HeatRisk EU — MSc Data Science capstone, University of Europe for Applied Sciences (Potsdam) |
| Concept deck | [`ProSho-concept-deck.pptx`](ProSho-concept-deck.pptx) (HeatRisk EU + a made-up frontend example, side by side) |
| Structure rules | [`CLAUDE.md`](../../CLAUDE.md) — ProSho follows the vertical pattern exactly |

---

## 1. Why ProSho exists

At the end of a capstone, a student has three disconnected things: a GitHub
repo (code, but not the story), a dashboard link (free Streamlit hosting
sleeps when idle, so examiners hit a wake-up screen), and a PDF report
(results frozen on submission day). The people who look at the project each
ask something none of these answer directly:

- **Examiner**: did it hit the targets it promised?
- **Supervisor**: is it on track?
- **Recruiter**: what can this person actually do?

ProSho does **not** replace Streamlit or rebuild dashboards. It packages
everything *around* the demo that those three audiences need.

**Why it belongs in LVAMO:** LVAMO helps people get hired (Applaut:
applications; Jobref: referrals). ProSho is the step before: *project →
proof of skill → job*. Every published page is a public `lvamo.com` link
students put on CVs and LinkedIn, and the "Mentored via LVAMO" credit makes
the founder's data engineering mentoring visible.

## 2. The core idea: shared core + evidence modules

Every capstone, whatever the subject, has six parts:

| Part | Same for every project? | Handled by |
|---|---|---|
| Problem | Yes | Core |
| Claims ("X, to standard Y") | Yes (format) | Core — claims tracker |
| Work over time | Yes | Core — commit timeline, milestones, mentor feedback |
| Outcome | Yes | Core — project page, portfolio link (CV bullets post-beta) |
| **Evidence** | **No** | **Module per project type** |
| **Demo** | **No** | **Module per project type** |

One generic building block underneath: **anything can attach a piece of
evidence (a metric, a check result, a file) to a project, optionally against
a claim.** A module is a preset on top of that block: which checks run, what
evidence keys it expects, and how its panel renders. This is the same
adapter pattern as Applaut's job-source adapters — a new project type means
a new module; the core never changes.

| Module | Beta? | Evidence it produces |
|---|---|---|
| **Data science** | ✅ Beta (pilot: HeatRisk EU) | Data source health (LVAMO checks each listed source), model metrics vs target (from CI), pipeline runs (from CI) |
| **Frontend** | ✅ Beta (pilot #2, to be recruited) | Screenshots at phone/tablet/desktop (LVAMO, Playwright), uptime of the live site (LVAMO), Lighthouse scores (from CI) |
| Backend / API | Later | API docs, test coverage, response times |
| Mobile | Later | Build status, screen recordings, test-install link |
| Research / thesis | Later | Paper PDF, references, key findings |

## 3. Beta goals and success criteria

The beta proves three things: students will use it, examiners/supervisors
find it useful, and the core really generalises beyond data science.

| # | Criterion | Target |
|---|---|---|
| 1 | Real projects published | ≥ 5, from ≥ 2 project types (at least one non-data) |
| 2 | HeatRisk EU uses ProSho in its final presentation | Yes |
| 3 | Evidence flows automatically | ≥ 3 projects with CI reporting evidence on ≥ 50% of pushes |
| 4 | A supervisor or examiner looks at a page and gives feedback | ≥ 1 |
| 5 | Pages get seen | ≥ 200 page views across all pages during beta |
| 6 | LVAMO gets attention | Clicks from ProSho pages to the LVAMO hub tracked; ≥ 1 student signs up for Jobref or Applaut via that path |
| 7 | Generalisation holds | Frontend module shipped **without changing core code or schema** |

## 4. Beta scope

**In scope**
- Student sign-in with GitHub; one or more projects per student.
- Repo connection via a GitHub App; `prosho.yaml` manifest synced on every push.
- Public project page: problem, claims tracker, demo, evidence panels, work timeline, mentor badge.
- Visibility: private (owner + mentor), unlisted (anyone with the link), public (listed in the ProSho gallery).
- Evidence ingestion API with per-project ingest tokens, plus a copy-paste GitHub Actions snippet.
- Data science and frontend modules.
- Milestones and mentor feedback (mentor role = LVAMO mentors, assigned by an admin).
- Simple gallery at `/prosho` of public projects.
- Audit log of every change; aggregate page-view counts.

**Out of scope for beta (post-beta backlog)**
- CV bullet generation (will reuse Applaut's generation rules: rephrase, never invent).
- Cohort/university workspaces and supervisor accounts (beta supervisors use unlisted links).
- Backend/API, mobile, research modules.
- Hosting students' Streamlit apps on LVAMO's VM.
- A single LVAMO account across verticals.
- Paid plans.

## 5. Users and roles

| Role | Who | Can |
|---|---|---|
| Student (owner) | Signs in with GitHub | Create projects, connect repos, manage ingest tokens, set visibility, add milestones, reply to feedback |
| Mentor | LVAMO mentors (the founder first); assigned per project by an admin | View private projects they mentor, leave feedback, mark milestones reviewed; their name appears in the "Mentored via LVAMO" badge |
| Admin | Founder | Assign mentors, deactivate users/projects (`is_active`, same pattern as Jobref), view audit log |
| Visitor | Examiners, supervisors, recruiters — no account | View unlisted/public pages |

**Auth follows the vertical pattern:** `prosho.users` table, ProSho-issued
JWTs with `"vertical": "prosho"`, localStorage key `prosho_access_token`.
GitHub is the identity source (students need it anyway, and it proves repo
ownership), the way LinkedIn is for Jobref job seekers. No passwords stored.

## 6. Architecture (per `CLAUDE.md`)

| Layer | ProSho |
|---|---|
| Backend code | `backend/app/prosho/` — `models/`, `schemas/`, `services/`, `api/v1/routers/`, `modules/` (one subpackage per evidence module), `github/` (App client, webhook verification) |
| API | `/api/v1/prosho/*` on `api.prosho.lvamo.com` |
| Database | Postgres schema `prosho`; migrations `NNNN_prosho_<what>.py` |
| Frontend | `frontend/src/prosho/` — `api/`, `components/`, `context/`, `pages/`; routes `/prosho/*`; env var `VITE_PROSHO_API_BASE_URL` |
| Public page URL | `lvamo.com/prosho/<slug>` (slugs reserved: `login`, `dashboard`, `projects`, `admin`, `gallery`, `auth`, `new`) |
| Storage | R2 keys `prosho/<project_id>/screenshots/...`, `prosho/<project_id>/artifacts/...` |
| Scheduling | APScheduler (already running in the shared backend) for source checks, uptime pings, screenshots |
| Screenshots | Playwright + headless Chromium in the backend image (new dependency; cap at 1 concurrent browser) |
| Claude scoping | `/prosho` skill (`.claude/skills/prosho/`) |
| Hub | ProSho card in `pages/Hub.tsx`; shown only once `prosho` is added to `platform.settings.verticals_enabled` |

### How data flows

```
Student laptop ──push──▶ GitHub repo (prosho.yaml)
                              │
           ┌──────────────────┼────────────────────────┐
           ▼                  ▼                        ▼
   GitHub App webhook   Student's CI step         LVAMO scheduler
   (push events)        (curl / Action)           (source checks, uptime,
           │                  │                    screenshots)
           ▼                  ▼                        ▼
   POST /prosho/github/  POST /prosho/ingest/    services write
   webhook               evidence (token)        evidence rows
           │                  │                        │
           └──────────────────┴───────────┬────────────┘
                                          ▼
                     prosho schema (projects, claims, evidence, …)
                                          ▼
                     GET /prosho/public/projects/{slug}
                                          ▼
                     lvamo.com/prosho/<slug>  (React page)
```

## 7. The manifest: `prosho.yaml` (v1)

Lives at the repo root. Synced on every push via the webhook; the
dashboard shows the last sync result and any validation errors with line
numbers. The manifest is the source of truth for the project's *story*
(problem, claims, sources); evidence values never live in it.

```yaml
version: 1
title: HeatRisk EU
type: data-science            # data-science | frontend  (beta)
summary: Who is most at risk from summer heat in five European countries
problem: >
  Each country counts heat deaths differently; no open cross-country view
  links how hot it gets to who is exposed and how many people die.
demo:
  kind: streamlit             # streamlit | url | video
  url: https://heatrisk.streamlit.app
claims:
  - id: predict-2026
    text: Predict 2026 heat deaths within ±25% of official estimates
    metric: prediction_error_pct      # evidence key that decides status
    target: { op: abs_lte, value: 25 }
  - id: city-maps
    text: 1 km heat vulnerability maps for five capitals
    # no metric → status set manually by the student, shown as "self-reported"
data:                         # data-science module section
  sources:
    - name: Eurostat weekly deaths by NUTS 3
      url: https://ec.europa.eu/eurostat/...
      licence: CC BY 4.0
```

Frontend projects use a `frontend:` section instead (e.g. `urls_to_screenshot`,
`lighthouse_targets`). Each module validates its own section.

**Claim status** is computed, never typed in, whenever a claim has a
`metric`: the latest evidence row for that key is compared to the target
(`gte`, `lte`, `abs_lte`, `between`, `eq`). Claims without a metric are
set manually and labelled *self-reported* on the page — explainable, no
black boxes.

## 8. Database schema (`prosho`)

All tables carry `id UUID`, `created_at`, `updated_at` (the shared
`TimestampMixin`) unless noted.

| Table | Key columns | Notes |
|---|---|---|
| `users` | `github_id` (unique), `github_login`, `name`, `email`, `avatar_url`, `role` (`student`/`mentor`/`admin`), `is_active` | Identity from GitHub OAuth |
| `projects` | `owner_id`, `slug` (unique), `title`, `summary`, `problem`, `project_type`, `university`, `programme`, `visibility` (`private`/`unlisted`/`public`), `supervisor_ok_at`, `repo_full_name`, `github_installation_id`, `demo_kind`, `demo_url`, `manifest_sha`, `manifest_synced_at`, `manifest_error`, `is_active`, `published_at` | `supervisor_ok_at` must be set before `public` (see §11) |
| `project_mentors` | `project_id`, `mentor_id` | Unique pair |
| `claims` | `project_id`, `key` (from manifest), `text`, `metric_key`, `target_op`, `target_value`, `target_value_hi`, `manual_status`, `position` | Unique (`project_id`, `key`); upserted on manifest sync, removed claims soft-archived |
| `evidence` | `project_id`, `claim_id` (nullable), `module`, `kind` (`metric`/`check`/`artifact`/`run`), `key`, `value_num`, `value_text`, `unit`, `payload` (JSONB), `r2_key`, `commit_sha`, `source` (`ci`/`webhook`/`scheduler`/`manual`), `recorded_at` | **Append-only** — history is the audit trail. Index (`project_id`, `key`, `recorded_at desc`). Idempotency: unique (`project_id`, `key`, `commit_sha`) when `commit_sha` is set |
| `ingest_tokens` | `project_id`, `token_hash` (SHA-256), `label`, `last_used_at`, `revoked_at`, `created_by` | Token shown once; stored hashed |
| `repo_events` | `project_id`, `commit_sha`, `message`, `author_login`, `committed_at` | From push webhooks — powers the work timeline |
| `milestones` | `project_id`, `title`, `due_on`, `completed_at`, `reviewed_by`, `reviewed_at`, `position` | |
| `feedback` | `project_id`, `author_id`, `claim_id`/`milestone_id` (nullable), `body`, `resolved_at` | Mentor ↔ student; never public in beta |
| `page_view_daily` | `project_id`, `day`, `views`, `referrer_domain` | Aggregates only; no IPs, no cookies |
| `audit_logs` | `actor_id` (nullable for system), `action`, `entity`, `entity_id`, `before`, `after` (JSONB), `created_at` | Every write to projects/claims/visibility/tokens/mentors |

Enums live in the `prosho` schema (declared with `schema="prosho"` on the
model, as Applaut's do).

## 9. API contracts (`/api/v1/prosho`)

**Auth**
- `GET /auth/github/authorize` → 302 to GitHub OAuth
- `GET /auth/github/callback` → upsert user, 302 to frontend with token
- `GET /auth/me`

**Projects (owner/mentor, JWT)**
- `GET /projects` — mine (student) or mentored (mentor)
- `POST /projects` — `{title, slug, project_type}`
- `GET|PATCH /projects/{id}` — visibility, demo, university, supervisor confirmation
- `POST /projects/{id}/github/connect` — link an installation + repo the user owns
- `POST /projects/{id}/sync` — re-read `prosho.yaml` now
- `GET|POST /projects/{id}/milestones`, `PATCH /milestones/{id}`
- `GET|POST /projects/{id}/feedback`, `PATCH /feedback/{id}`
- `GET|POST /projects/{id}/tokens`, `DELETE /tokens/{id}` (revoke)
- `GET /projects/{id}/evidence?key=&limit=` — history for the dashboard

**Ingestion (ingest token, no JWT)**
- `POST /ingest/evidence` — `{commit_sha?, items: [{key, kind, value_num?, value_text?, unit?, claim?, payload?}]}`; max 50 items, 64 KB; returns per-item accepted/duplicate/rejected
- `POST /ingest/artifact` — multipart upload to R2 (≤ 5 MB, images/PDF/JSON)

**GitHub**
- `POST /github/webhook` — HMAC-verified (`X-Hub-Signature-256`); handles `push`, `installation`, `installation_repositories`

**Public (no auth)**
- `GET /public/projects/{slug}` — 404 for private, unknown, or inactive
- `GET /public/gallery?type=&cursor=` — public projects only
- `POST /public/projects/{slug}/view` — increments the daily aggregate

**Admin**
- `POST /admin/projects/{id}/mentors`, `PATCH /admin/users/{id}` (`is_active`, `role`), `GET /admin/audit`

Ownership failures return 404 (platform rule). Rate limits on `/ingest/*`
(per token) and `/public/*` (per IP, not stored).

## 10. Frontend pages (`frontend/src/prosho/`)

| Route | Page | Who |
|---|---|---|
| `/prosho` | Landing + public gallery | Everyone |
| `/prosho/login` | "Continue with GitHub" | Everyone |
| `/prosho/dashboard` | My projects (student) / mentored projects (mentor) | Signed in |
| `/prosho/projects/new` | Create project → install GitHub App → pick repo | Student |
| `/prosho/projects/:id` | Manage: sync status + manifest errors, visibility, demo, tokens + CI snippet, milestones, feedback, evidence history | Owner, mentor |
| `/prosho/:slug` | **The project page** (see the concept deck): header + type chip + "Mentored via LVAMO" badge, claims tracker, demo, module evidence panels, work timeline, "Built with LVAMO ProSho" footer linking to the hub | Visitors |

Demo embedding: Streamlit apps load in an iframe (`?embed=true`) **below**
natively-rendered results cards, so the page is useful even while a free
Streamlit app is waking up. Our own `_headers` (`X-Frame-Options: DENY`)
only stops others framing *us*; it doesn't block us embedding Streamlit.
Mobile-first per platform rules.

## 11. Security, privacy and academic integrity

- **Academic integrity:** a project can only go `public` after the owner
  confirms *"My supervisor has agreed this can be public"* (stored as
  `supervisor_ok_at`, audit-logged). Default visibility is `private`.
  LVAMO branding stays small: a badge and a footer — the page must read as
  the student's work.
- **GitHub App, least privilege:** repository *Contents: read* (only to
  read `prosho.yaml`), *Metadata: read*, push webhooks. Webhook secret and
  App private key in env vars, never in code.
- **Ingest tokens:** random 32-byte, shown once, stored as SHA-256, scoped
  to one project, revocable, `last_used_at` tracked.
- **SSRF guard for server-side fetching** (source checks, uptime,
  screenshots of student URLs): http/https only, resolve DNS and refuse
  private/loopback/link-local ranges, 10 s timeout, size cap, no
  redirects to blocked ranges, max 1 browser at a time.
- **GDPR:** students are EU users. Privacy notice before sign-up; no
  tracking cookies; page views stored only as daily aggregates; deleting a
  project deletes its evidence rows and R2 objects; deleting an account
  deletes everything owned.
- **Upload limits:** type allowlist, 5 MB cap, R2 keys never derived from
  user-supplied filenames.

## 12. Timeline

Solo founder building with Claude Code; each phase ends with a production
deploy and production verification recorded in `PROGRESS_PROSHO.md`.
Dates are targets, not commitments.

| Phase | Dates (2026–27) | Deliverables | Exit check |
|---|---|---|---|
| **0. Foundation** | Oct 12 – Oct 18 | Finish the `api.lvamo.com` platform cutover; `/prosho` skill; `backend/app/prosho` + `frontend/src/prosho` skeletons; migration creating schema `prosho` + `users`; health endpoint; `api.prosho.lvamo.com` (DNS, webroot cert, nginx); `VITE_PROSHO_API_BASE_URL` in Pages; hub card wired but hidden | `GET https://api.prosho.lvamo.com/api/v1/prosho/health` → 200 |
| **1. Core page** | Oct 19 – Nov 1 | GitHub OAuth sign-in; projects CRUD; GitHub App + webhook + manifest sync with validation errors; claims (manual status); public page with claims tracker and demo; visibility + supervisor confirmation; audit log | HeatRisk EU page live as *unlisted*, built from its real repo |
| **2. Evidence + data module** | Nov 2 – Nov 15 | Ingest tokens + `/ingest/evidence` + CI snippet; computed claim status; data module: source health checker (scheduler), metrics-vs-target panel, pipeline-run panel | HeatRisk EU's CI pushes evidence; a source going down shows on the page within a day |
| **3. Work over time** | Nov 16 – Nov 29 | Push-webhook commit timeline; milestones; mentor role + feedback; admin mentor assignment; page-view aggregates | Founder mentors HeatRisk EU through ProSho for 1 week |
| **4. Frontend module** | Nov 30 – Dec 20 | Playwright screenshots (3 sizes) to R2; uptime pings; Lighthouse ingest + panel; artifact upload; **no core/schema changes** | Pilot #2 (a frontend project) live as *unlisted* |
| **5. Beta hardening** | Dec 21 – Jan 10 | Gallery; rate limits; SSRF tests; privacy notice; account/project deletion; mobile polish; docs for students ("set up ProSho in 15 minutes") | Security checklist (§11) all ✅ |
| **Beta launch** | ~Jan 11, 2027 | `prosho` added to `verticals_enabled`; invite 5–10 students via the founder's mentoring network | Success criteria tracking starts |
| **Beta review** | ~Mar 2027 | Measure §3 criteria after presentations; decide on post-beta backlog | Go / adjust / stop decision |

## 13. Testing

- **Backend:** pytest for manifest validation (valid, invalid, partial),
  claim-status computation (each operator, missing evidence), ingestion
  (token auth, idempotency, size limits, revoked token), webhook HMAC
  verification, visibility rules (private/unlisted/public, inactive),
  SSRF guard (private IP, redirect to private IP, non-http scheme).
- **Migrations:** upgrade from empty + downgrade/upgrade round trip
  locally before every deploy (as done for `0020`).
- **Frontend:** `tsc --noEmit` + `vite build` clean; Playwright pass over
  the public page at phone/tablet/desktop widths, against local and then
  production.
- **End-to-end per phase:** a real repo (HeatRisk EU, then pilot #2) going
  through the real flow in production, recorded in `PROGRESS_PROSHO.md`.

## 14. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Students don't wire up CI | High | Evidence is optional; claims work self-reported; founder pairs with each pilot for 30 min; copy-paste snippet |
| University objects to public pages / branding | Medium | Private by default; supervisor confirmation before public; small branding |
| Free Streamlit apps sleep | High | Native results cards above the iframe; "open dashboard" fallback link |
| SSRF / abuse via student-supplied URLs | Medium | §11 guard + tests before any scheduler job ships |
| Headless Chromium load on the shared VM | Medium | 1 concurrent browser, screenshots on push + daily at most; VM has 24 GB shared with Applaut/Jobref |
| GitHub API rate limits | Low | App installation tokens (5k/h each); manifest fetched only on push |
| Scope creep before beta | High | Out-of-scope list (§4) is binding; new ideas go to the post-beta backlog |
| Only data-science students sign up | Medium | Recruit pilot #2 (frontend) deliberately in Phase 3 |

## 15. Assumptions (smallest reasonable, per CLAUDE.md)

1. Capstone presentations are around February 2027 — beta must be live by mid-January.
2. GitHub is acceptable as the only sign-in method for beta.
3. ProSho is free during beta.
4. The founder is the only mentor and admin during beta.
5. Supervisors view pages via unlisted links; no supervisor accounts in beta.
6. Manifest filename `prosho.yaml` (the concept deck's earlier `lvamo.yaml` is renamed to match the vertical).
7. PyYAML and a GitHub App client library (or plain `httpx` + `PyJWT`) are added to `requirements.txt`; Playwright + Chromium added to the backend image in Phase 4.

## 16. Open questions for the founder

1. Is GitHub-only sign-in OK, or do some students use GitLab / university Git servers?
2. Should "Mentored via LVAMO" name the individual mentor, or just LVAMO?
3. Who is pilot #2 — is there a frontend (or non-data) student in the same cohort?
4. Do you want to approach the HeatRisk EU supervisor about ProSho early, or let the student decide?
5. Public page URL: `lvamo.com/prosho/<slug>` (current plan) or a shorter domain later?
