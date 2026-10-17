# Applaut — Job Engines (three ways to find jobs and write documents)

| | |
|---|---|
| Status | Phase 1 (shared core) and Phase 2 (engine 3 sync) built and live 2026-10-17; Phases 3–5 not built |
| Written | 2026-10-17 |
| Replaces | `AGENT_IMPORT_DESIGN.md` (push-API idea, dropped) |
| First real user | Venkat's own Claude routine "Job search automation" (§6.10) |

---

## 1. The idea

At onboarding every Applaut user picks **one job engine**: the thing that
finds jobs for them and writes their CV and cover letter. All three engines
deliver into the **same Applaut store and screens**, so reviewing, scoring
explanations, documents and application tracking look the same whatever the
engine is.

| # | Engine | Who it is for | AI | Paid by |
|---|---|---|---|---|
| 1 | **Applaut Basic** | Anyone, as a fallback | None — keyword search on company job boards, rule-based match, template documents | Free |
| 2 | **Applaut AI** *(recommended for most people)* | People outside IT, or anyone who wants it to just work | Claude, run by Applaut | The user, via Applaut credits (later phase, §7.4) |
| 3 | **Your own Claude routine** *(recommended for IT professionals)* | People comfortable with GitHub, a database and cloud storage | Claude, run in the user's own Claude account | The user's own Claude plan; Applaut is free |

ChatGPT and other assistants are **out of scope**. Engine 3 needs a shell,
Python, a database and file uploads, which today only a Claude routine gives
us.

**Not in scope:** auto-applying (Applaut never submits anything — principle 6),
sharing one user's jobs with another user, reading anything from a user's
Claude account.

---

## 2. Facts this design rests on (checked 2026-10-17)

- **Venkat's routine** (`trig_01THH4MviEAx8gxHg2Tj33xo`, repo
  `vsvedantham/job-search-automation`) runs `7 6,18 * * *` UTC on Claude Opus
  5.5. The last run took **14½ minutes**, 88 steps. It writes job rows to one
  Neon table, `jobsearchautomationresults` (27 rows, all `docs_status = done`),
  and five files per job to R2 bucket `job-search-automation-documents` under
  `jobautomationdocs/<uid>/`: `Venkat_Sai_Vedantham_CV.pdf`,
  `Venkat_Sai_Vedantham_CoverLetter.pdf`, `cv_content.json`,
  `cover_letter_content.json`, `job_description.md` (~60 KB per job).
- The routine has **no run table**: when it fails, the reason exists only in
  the run's transcript inside Venkat's Claude account.
- **Applaut can never read a user's Claude account**, its run history or its
  logs: that would need the user's Claude login. So every run status Applaut
  shows for engine 3 comes from what the routine itself writes to the user's
  Neon/R2 (§6.4).
- **Applaut today:** `opportunities` is one global pool (no owner);
  `scores` is one row per (opportunity, profile) and rule-based scoring
  rewrites it for every opportunity on every run; `generated_documents` holds
  Markdown; the discovery scheduler runs in-process in each uvicorn worker
  (guarded since commit `002f6e6`).
- **Claude API prices** (pricing page, 2026-10-17, per million tokens):
  Opus 5.5 $4 in / $20 out / $0.20 cache read; Sonnet 5.5 $2 / $10 / $0.10;
  Haiku 5.5 $0.10 / $0.50 / $0.01; web search $10 per 1,000.

---

## 3. Shared core (built once, used by all three engines)

### 3.1 Data model — migration `NNNN_applaut_job_engines`

Take the next free number (`0025` is ProSho's, uncommitted at the time of
writing).

**`applaut.profiles`** gains `job_engine` (`basic | applaut_ai | own_routine`,
default `basic`) and `job_engine_changed_at`. Switching engines keeps all
history; only new jobs come from the new engine.

**`applaut.opportunities`** gains `owner_user_id` (nullable → users, CASCADE).
`NULL` = found by Applaut Basic, shared; set = brought in by engine 2 or 3 for
that user only. The unique key `(source, external_id)` becomes two partial
unique indexes: `(source, external_id) WHERE owner_user_id IS NULL` and
`(owner_user_id, source, external_id) WHERE owner_user_id IS NOT NULL`.

**`applaut.job_assessments`** (new) — the AI engines' verdict on a job, kept
apart from `scores` so rule-based scoring can never overwrite it:
`id, user_id, profile_id, opportunity_id, engine, match_score (0–100),
matched_skills text[], missing_skills text[], german_required, seniority,
notes, flags text[]` (e.g. `CHECK: fixed-term?`)`, model, raw jsonb,
first_seen_at, last_seen_at, times_seen`. Unique `(profile_id, opportunity_id, engine)`.

**`applaut.generated_documents`** gains `engine` (`basic | applaut_ai |
own_routine`), `content_type` (`text/markdown` or `application/pdf`) and
`content_sha256`. PDFs live in Applaut's R2 under
`applaut/documents/{user_id}/{opportunity_id}/{sha8}/{cv|cover_letter}.pdf`;
`content` keeps a text version for copy/search.

### 3.2 Visibility rule (the main correctness risk)

Every read of `opportunities` goes through one helper,
`visible_to(user) = owner_user_id IS NULL OR owner_user_id = :user_id`, and
every `db.get(Opportunity, …)` becomes `get_visible_opportunity(id, user)`
(404 otherwise). Sites to change today: `services/scoring.py` (2 queries,
2 gets), `services/opportunity.py` (list, get), `services/document.py`,
`services/application.py` (4 gets), `routers/stats.py`, and
`discovery/engine.py`'s dedupe (global rows only). Tests prove user B can't
list, open, score, download or apply to user A's jobs.

### 3.3 One scheduler, driven by the database

Replace "one APScheduler job per profile in every worker" with **one
dispatcher job every 2 minutes** that claims due work from the database:

```sql
SELECT … FROM applaut.engine_tasks
WHERE due_at <= now() AND status = 'pending'
ORDER BY due_at
FOR UPDATE SKIP LOCKED
LIMIT 5
```

`engine_tasks` (`id, user_id, kind, due_at, status, attempts, last_error,
payload jsonb`) holds every scheduled thing: Basic discovery runs, engine-3
status checks and syncs, engine-2 runs. Because the schedule lives in
Postgres, it survives restarts, every worker sees the same schedule (this
also fixes the drift noted in `PROGRESS_APPLAUT.md`), and two workers can't
take the same task. Failed tasks retry with backoff (1 min, 5 min, 30 min),
then stop and show the error.

### 3.4 Screens every engine shares

- **Opportunities**: engine badge, AI match % (engines 2–3) or rule score
  (engine 1), NEW badge, filters (score, city, work mode, new since last
  visit). "Run discovery" only appears for engine 1.
- **Opportunity detail**: the AI assessment (matched vs missing skills in
  two lists, notes, `CHECK:` flags highlighted), job description, posting and
  apply links, **View / Download** CV and cover letter PDFs, and application
  tracking (to review → applied → interviewing → offer / rejected).
- **Dashboard**: an **Engine card** (§6.8) instead of today's "Auto discovery"
  widget.
- **Settings → Job engine**: current engine, switch, and engine-specific
  settings.

---

## 4. Engine 1 — Applaut Basic

What exists today, unchanged in behaviour: ATS adapters, rule-based
scoring, template documents, discovery scheduler (moved onto `engine_tasks`,
and only for profiles with `job_engine = 'basic'`). The UI calls it the
fallback: it works with no setup and no cost, but finds fewer, less precise
matches.

---

## 5. Engine 2 — Applaut AI (summary; detailed design later)

Built after engine 3. Plain code does everything that doesn't need judgment;
AI is used only where it adds value.

1. **Filter rules, generated once by AI** from the profile and job
   expectations (title keywords and synonyms, excluded keywords and seniority,
   skill aliases, German level, locations, remote, excluded companies). Saved
   as data the user can read and edit; regenerated when the profile changes.
   A few cents per user.
2. **Fetch, by code**: today's ATS adapters plus new Arbeitsagentur and
   Arbeitnow adapters (both plain HTTP APIs, as the routine uses them).
3. **Filter, by code**: apply the rules and skip postings already seen, so
   AI only ever sees new postings.
4. **Score, with AI**: Haiku 5.5 screens each new description; Sonnet 5.5
   assesses the ones that pass (matched/missing must-haves → `job_assessments`).
5. **Documents, with AI**: Opus 5.5 writes CV and cover letter content as
   JSON for jobs above the user's threshold; Applaut validates it with the
   routine's fact guard (only facts and numbers from the profile or the job
   description), renders PDFs with Playwright, stores them.

Estimated cost **about $1 per run** (≈250 descriptions screened, ≈40
assessed, 3 document sets), less once already-seen postings are skipped.
Every AI call's token usage is recorded, so real costs are known from the
first run. Phase 1 runs only for allow-listed users (Venkat) on Applaut's own
Anthropic balance; per-user credits come later (§7.4).

---

## 6. Engine 3 — Your own Claude routine

### 6.1 How it works

```
User's side (their accounts)                       Applaut
────────────────────────────                       ───────
Claude routine (their plan, their schedule)
  └─ runs Applaut's skeleton repo (their GitHub copy)
       ├─ job rows + run log  ──► their Neon Postgres ──┐  read-only role
       └─ PDFs + summaries    ──► their Cloudflare R2  ──┤  read-only token
                                                         ▼
                                     status checks after each scheduled run
                                     sync 60 min after the run finishes:
                                       jobs → opportunities + job_assessments
                                       PDFs copied → Applaut R2 + generated_documents
                                     failures → shown on the dashboard + notification
```

Applaut only ever **reads** the user's Neon and R2, with credentials that
cannot write. The routine never talks to Applaut.

### 6.2 The skeleton (template repo `applaut-routine-skeleton`)

A GitHub template generalised from `job-search-automation`:

- `ROUTINE_PROMPT.md`: the same rules (search sources, eligibility, writing
  rules, fact guard), with everything Venkat-specific moved into the profile
  files (name for file names, logistics paragraph, experience ids, visa
  status, languages).
- `profile/master_profile.yaml`, `config/search_config.yaml`: **downloaded
  from Applaut** (Settings → Job engine → "Download my profile files"),
  generated from the user's Applaut profile, so they don't write YAML by hand.
- `scripts/pipeline.py` and `setup.sh` as today, plus the **`run_tracker`
  table** below.

**Contract v1** (what Applaut reads). Venkat is adding `run_tracker` to his
own routine (decided 2026-10-17), and the skeleton ships the same table, so
there is one contract for everyone:

| Where | What |
|---|---|
| Neon table `jobsearchautomationresults` | the existing columns, unchanged |
| Neon table `run_tracker` | one row per run (schema below) |
| R2 `jobautomationdocs/<uid>/` | the five files per job, as today |

**`run_tracker`** — written by the routine on every run:

| Column | Type | Meaning |
|---|---|---|
| `run_id` | text, primary key | e.g. `20261017_0808` (the routine's `RUN_ID`) |
| `contract_version` | integer, not null, default 1 | lets Applaut read older and newer layouts |
| `started_at` | timestamptz, not null | written in step 0 |
| `finished_at` | timestamptz | written at the end; null while running |
| `status` | text, not null | `running` → `succeeded` \| `partial` \| `failed` |
| `current_step` | text | last step started (`setup`, `search`, `assess`, `merge`, `documents`, `export`, `summary`) |
| `error` | text | why it failed (e.g. the `selftest` output), ≤ 4,000 characters |
| `searches_run`, `search_budget` | integer | e.g. 225 of 250 |
| `postings_found`, `postings_assessed`, `jobs_eligible` | integer | funnel counts |
| `jobs_new`, `jobs_updated`, `jobs_rejected` | integer | from `merge` |
| `docs_done`, `docs_failed` | integer | from render/upload |
| `sources_failed` | text | e.g. `Arbeitsagentur: connection timeout` |
| `summary` | text | the step-5 summary, ≤ 20,000 characters |
| `updated_at` | timestamptz, not null | every write |

**Two rules make it reliable:**
1. **Insert the row at the start** (`status = running`) and **update it at
   the end**. A run that crashes, times out or hits the Claude plan's usage
   limit can't write a "failed" row at the end; a `running` row that never
   finishes is how Applaut can still tell the user it stopped part-way, and at
   which step.
2. **Write it from `pipeline.py` commands** (`run-start`, `run-step <step>`,
   `run-finish --status … --error … --summary-file …`), not ad-hoc SQL in the
   prompt, so every run writes the same shape. The prompt calls `run-finish
   --status failed` before stopping on any failure it can see.

**As built in Venkat's routine** (commit `85d70a8`, 2026-10-17), which the
skeleton copies:
- `run-start` also marks any other run still `running` after 6 hours as
  `failed`, with error "no completion recorded within 6 h (session ended or
  crashed)" and its `current_step` left as it was. Applaut shows that the
  same way as its own "stopped part-way" check at T + 3 h (§6.5).
- `run-finish` computes `jobs_new`, `jobs_updated`, `jobs_rejected`,
  `docs_done` and `docs_failed` from the database itself, and sets `status`
  to `failed` when given an error, `partial` when any document wasn't
  produced, else `succeeded`. `sources_failed` can be set on a `succeeded`
  run, so Applaut treats a non-empty `sources_failed` as "finished with
  problems" whatever the status.
- Steps recorded: `setup, search, assess, merge, documents, export, summary`.

**Contract v0** = a routine with no `run_tracker` table (Venkat's routine
before 2026-10-17). Jobs and documents still sync; run status and failure reasons show as
"not available — add the run tracker to see them".

Applaut detects the version from `run_tracker` (absent → v0, otherwise the
highest `contract_version`), keeps reading every version it has shipped, and
shows "A newer skeleton is available — what changed" when a user is behind.

### 6.3 Scheduling: status checks, then a sync an hour after the run

The user enters their routine's schedule in Applaut (a picker that produces
the same cron as the routine, plus timezone; default `7 6,18 * * *` UTC). For
each expected run time **T**, Applaut queues tasks in `engine_tasks`:

1. **Status checks** at T + 30 min, T + 60 min, T + 2 h, T + 3 h. Each check
   opens one short read-only connection to the user's Neon and reads
   the row for that run in `run_tracker` (v1) or `max(last_seen_at)` (v0). As soon as a
   check sees the run finished, the remaining checks are cancelled. Limiting
   checks to these four keeps Neon's compute asleep the rest of the day, so
   it doesn't eat into the user's free allowance.
2. **Sync** at **finished_at + 60 min**, as requested (it also leaves room
   for any late uploads). If the run failed but some jobs were saved, they
   are still synced.
3. **Missed / stuck**: no run row by T + 3 h → "didn't run"; still `running`
   at T + 3 h → "stopped part-way". Both are shown (§6.5) and notified.

**Sync now** button: runs a check and, if a run has finished, a sync
immediately (at most once every 10 minutes).

### 6.4 What a sync does

- Reads rows changed since the last sync (`last_seen_at` or `docs_status`
  newer than the stored watermark).
- Upserts each into `opportunities` (`owner_user_id` = user, `source =
  'own_routine'`, `external_id = uid`) and `job_assessments`
  (`engine = 'own_routine'`). If Applaut Basic already has the same posting
  (same normalised apply URL), the job is linked to that one instead of
  duplicated.
- For rows with `docs_status = done` whose files changed (R2 ETag differs
  from what was copied): copies both PDFs into Applaut's R2 and creates
  `generated_documents` rows (`engine = 'own_routine'`); older ones become
  `is_current = false`. `job_description.md` becomes the opportunity's
  description; the content JSONs become the documents' text versions.
- Creates an application in **"To review"** for each new job (a review
  queue — nothing is submitted).
- Writes a `routine_syncs` row (started, finished, jobs new / updated, docs
  copied, error) and one audit-log entry.
- One notification per sync: "Your routine found 3 new jobs — CV and cover
  letter ready".

Rows deleted from the user's Neon are kept in Applaut (their history),
marked "no longer in your routine's database".

### 6.5 Showing why a run failed

What Applaut can show depends on what the routine wrote. It never guesses:

| What happened | How Applaut knows | What the dashboard says |
|---|---|---|
| Run failed with a reason (setup failed, selftest failed, a pipeline command failed) | `run_tracker.status = failed` + `error`, `current_step` | "Your routine run at 06:07 failed at step *Documents*: *<reason>*" + "Show details" (`error` and `summary`, displayed as plain text) |
| Run finished, but some sources or documents failed | `status = partial`, or a non-empty `sources_failed` on any status; `docs_failed`, per-job `docs_error` | "Finished with problems: Arbeitsagentur API unreachable; 1 document failed (*reason*)" — and on that job's page |
| Run started but never finished | `status = running` at T + 3 h, or later `failed` with the routine's "no completion recorded within 6 h" error; `current_step` | "Stopped during *Search* and never finished. This usually means the run hit your Claude plan's usage limit or a time limit. Open the routine in Claude to see its transcript." |
| Run never started | no row for T by T + 3 h | "Your routine didn't run at 06:07. Common causes: the routine is paused, your Claude plan's limit was reached, or its environment failed to start. Open the routine in Claude to check." |
| Applaut can't read your data | connection or auth error | "Applaut can't connect to your Neon database (*error*). Did the password or key change? Update your connection." |
| Contract v0 (no run log) | no `run_tracker` table | "Run details aren't available for your routine version. Update to the latest skeleton to see why runs fail." |

"Open the routine in Claude" links to the routine URL the user saved during
setup. The full transcript stays in their Claude account.

### 6.6 Credentials: read-only, encrypted, checked

`applaut.routine_connections` (one per user): `neon_url_enc,
r2_account_id, r2_bucket, r2_prefix, r2_access_key_id_enc,
r2_secret_enc, routine_url, schedule_cron, timezone, contract_version,
status (setup | active | error | paused), verified_at, last_check_at,
last_error`, timestamps.

- **Encryption**: Fernet (`cryptography`), key `APPLAUT_CREDENTIALS_KEY` in
  `.env.production` only, wrapped in `MultiFernet` so the key can be rotated.
  Values are decrypted only inside the sync task, never logged, never sent
  back to the browser (the UI shows "saved · ends in …f3a2" and offers
  Replace / Remove).
- **Neon must be read-only**: on save, Applaut connects and refuses the
  connection if the role is a superuser, can create roles or databases, or
  has `INSERT/UPDATE/DELETE` on any table (`has_table_privilege`). The setup
  guide gives the exact SQL to create the read-only role.
- **R2 must be read-only**: R2 keys can't report their own permissions, so on
  save Applaut tries to write one empty file
  (`applaut-permission-check/<random>`). If that succeeds, Applaut deletes it
  and refuses the key: "This key can write to your bucket. Please create a
  read-only key." The UI says this before the user presses Test.
- **Test connection** checks: Neon reachable, read-only, contract version
  found, the jobs table readable; R2 bucket listable, read-only.
- Every save, test, replace and removal is audit-logged. Removing the
  connection deletes the stored secrets immediately; synced jobs and copied
  documents stay.

### 6.7 Setup guide (in the app, step by step)

A wizard under Settings → Job engine → "Set up your Claude routine". Each step
shows time, why it's needed, and a **Done / Check** button; progress is saved
so users can stop and come back.

| Step | What the user does | About |
|---|---|---|
| 1. Check you have everything | A paid Claude plan with routines, a GitHub account, a Neon account, a Cloudflare account (Cloudflare may ask for a card to turn on R2, even on the free tier) | 5 min |
| 2. Copy the skeleton | GitHub → "Use this template" → private repo | 5 min |
| 3. Add your profile | Download the two profile files from Applaut, commit them | 5 min |
| 4. Database | Create a Neon project; keep its connection string for the routine; run the provided SQL to create a read-only role for Applaut (`SELECT` on all tables, including `run_tracker`, plus default privileges for tables added later) | 15 min |
| 5. File storage | Create an R2 bucket; create two API tokens: read & write (for the routine), read-only for this bucket (for Applaut) | 15 min |
| 6. Create the routine | In Claude: new routine from your repo, the one-line prompt, schedule, environment secrets (Neon URL, R2 write key) | 15 min |
| 7. First run | Press "Run now" in Claude; it takes about 15 minutes | 15–20 min |
| 8. Connect Applaut | Paste the read-only Neon URL, R2 read-only key, bucket, routine link and schedule; **Test connection** | 10 min |
| 9. Test my setup | Applaut checks the contract version, finds the first run and its jobs, and runs a first sync now | 5 min |

**Total: about 1½–2 hours the first time; about 45 minutes if you already
use GitHub, Neon and Cloudflare.**

### 6.8 Engine-3 dashboard card

```
Your Claude routine                                    ● Healthy
Last run   Today 06:07 → 06:22 · completed · 3 new jobs, 3 documents
Synced     Today 07:22 · 3 new, 15 updated
Next run   Today 18:07 (your routine) · next sync ≈ 19:20
[Sync now]  [Open routine in Claude]  [Run history]
```

States: Healthy, Finished with problems, Failed, Didn't run, Can't connect,
Setup incomplete — each with the message from §6.5. **Run history** lists
every run from `run_tracker` with its counts, status, error and summary.

### 6.9 Limits and safety

- Sync reads at most 2,000 rows and copies at most 200 documents per run;
  PDFs over 5 MB or not starting with `%PDF-` are skipped and reported.
- Everything read from a user's Neon/R2 is untrusted text: rendered as text
  (no HTML), URLs must be `http(s)`, files served only through short-lived
  signed links from Applaut's private bucket.
- A user's connection is paused after 5 consecutive connection failures; the
  card says so and offers "Try again".

### 6.10 Venkat's routine as the first user

His routine is **contract v1** since commit `85d70a8` (2026-10-17): the
`run_tracker` table exists in his Neon with the schema above (checked
read-only the same day; no rows until the next run). Steps:

1. Create a read-only Neon role (with `SELECT` on both tables) and a
   read-only R2 token for `job-search-automation-documents` (also rotate the
   R2 key printed in the 2026-10-17 session).
2. Connect it in Applaut as engine 3 → the 27 existing jobs and their
   documents sync, and each run's status, counts and failure reason show on
   the dashboard. Runs from before the tracker existed show without run
   details.

---

## 7. Onboarding and UI copy

### 7.1 Onboarding step "How should Applaut find jobs for you?"

Three cards side by side (stacked on mobile), each with who it's for, what
you need, setup time, cost, and a short "what you get".

**Applaut AI** — badge **Recommended for most people**
> Applaut's AI searches German job sites twice a day, reads every new job
> description against your profile, and writes a tailored CV and cover
> letter for the best matches. Nothing to set up.
> *Best for:* everyone, especially if you don't work in IT.
> *Setup:* none. *Cost:* pay per run from your Applaut credits (about €1 a
> run). *Coming soon* (until then, this card is disabled with "Join the waitlist").

**Your own Claude routine** — badge **Recommended for IT professionals**
> Run the same AI job search in your own Claude account, on your own
> schedule. Applaut gives you a ready-made template and a step-by-step guide,
> then collects your jobs and documents automatically an hour after each run.
> *Best for:* developers, data and IT people who have (or want) a paid Claude plan.
> *You need:* a paid Claude plan with routines, GitHub, Neon and Cloudflare accounts.
> *Setup:* about 1½–2 hours the first time (≈45 min if you know these tools).
> *Cost:* free in Applaut; the AI runs on your Claude plan.
> **You'll learn along the way** how to run an AI agent on a schedule
> (Claude routines), keep data in a cloud Postgres database (Neon), store
> files in object storage (Cloudflare R2), handle secrets safely, and read
> and adjust the prompt that drives the whole pipeline — a small, real
> project you can talk about in interviews.

**Applaut Basic** — badge **Fallback**
> Keyword search on company job boards with a rule-based match score and
> template documents. No AI, works instantly.
> *Best for:* trying Applaut out, or when you don't want AI involved.
> *Setup:* none. *Cost:* free. *Trade-off:* fewer and less precise matches,
> simpler documents.

Below the cards: "You can change this anytime in Settings. Your jobs and
documents stay when you switch."

### 7.2 Choosing "Your own Claude routine"

A confirmation panel before the wizard:
> **Before you start:** this takes about 1½–2 hours, and you can stop and
> continue later. Applaut only ever *reads* your database and storage, with
> read-only keys you create — it can't change or delete anything. You can
> disconnect at any time.
> [Start setup] [Choose another option]

Until setup is complete, the dashboard card shows "Setup 4 of 9 done —
continue" and the user can use Applaut Basic in the meantime.

### 7.3 Changes to existing screens

| Screen | Change |
|---|---|
| Landing | Copy describes the three engines, not only Applaut's own search |
| Onboarding | New engine step (§7.1); the discovery-frequency field moves to Basic's settings |
| Dashboard | Engine card (§6.8 for engine 3; simpler cards for 1 and 2) replaces "Auto discovery"; setup cards follow the engine |
| Opportunities | "Run discovery" only for Basic; engine badge, AI match %, filters |
| Opportunity detail | AI assessment panel; PDF view/download; application tracking |
| Document page | "Generate documents" only for Basic; otherwise a PDF viewer with text version and Copy |
| Resume | Shown for Basic (its templates use it); hidden for engine 3 (the routine uses its own profile files) |
| Settings → Job engine | Current engine, switch, engine-3 connection, schedule, profile-file download, run history |
| Audit log | New actions: engine switch, connection saved/tested/removed, sync |

### 7.4 Credits for Applaut AI (later phase)

Wallet per user, top-up through Stripe, each run charged at its recorded
token cost plus a margin, a run starts only if the wallet covers its worst
case, daily caps, EU VAT via Stripe Tax, wallet history in the UI. Designed
separately once engine 2 has real cost data.

---

## 8. Build order

| Phase | Scope | Done when |
|---|---|---|
| 1. Shared core | Migration (§3.1), visibility helper + tests, `engine_tasks` dispatcher, Opportunities / detail / document screens for AI-assessed jobs and PDFs | Basic still works unchanged; tests prove private jobs never leak |
| 2. Engine 3 sync | `routine_connections` + encryption + read-only checks, status checks, sync, failure states, dashboard card, Settings → Job engine | Venkat's routine syncs its 27 jobs and PDFs in production, and its `run_tracker` rows show as run status |
| 3. Skeleton + onboarding | `applaut-routine-skeleton` repo with contract v1, profile-file export, setup wizard, onboarding engine step, landing copy | A fresh test account completes the wizard end to end and sees a failed run's reason |
| 4. Engine 2 (allow-listed) | Filter-rule generation, new adapters, AI scoring and documents, fact guard, PDF rendering, token logging | Venkat runs it for a week; real cost per run recorded |
| 5. Credits | Wallet, Stripe, VAT, limits | Engine 2 open to all users |

Each phase: tests in `backend/tests/applaut/`, deploy with `deploy.sh` +
Cloudflare Pages, verify in production, record in `PROGRESS_APPLAUT.md`.

## 9. Decisions (2026-10-17, Venkat accepted the recommendations)

1. Skeleton repo: **public** GitHub template (it holds no secrets).
2. Sync delay: **fixed 60 minutes** after a run finishes.
3. Applaut AI card before engine 2 exists: **shown, disabled, with a waitlist**.
4. Switching away from engine 3 **deletes the stored credentials**, after a
   confirmation; synced jobs and documents stay.
