# Applaut AI — in-house model, nightly pipeline

| | |
|---|---|
| Status | Design, not built. Phase 0 (benchmark) decides the model before any build |
| Written | 2026-10-31 |
| Changes | Engine 2 of [`JOB_ENGINES_DESIGN.md`](JOB_ENGINES_DESIGN.md) (§5, §7.4): AI now runs on our own VM instead of the Claude API, so there are no per-user AI costs and no credits |
| Reuses | Phase 1 shared core (`job_assessments`, `engine_tasks`, `generated_documents` PDFs, visibility rule); the routine's templates and fact checks (`routine/setup_kit/`) |

---

## 1. The idea

Every night at **22:00** Applaut does the whole job search for every user, so
when they log in in the morning their matches, CVs and cover letters are
ready to review and apply.

- **Code does everything that needs no judgment, in parallel**: fetching jobs,
  filtering, rule pre-scoring, choosing CV bullets, rendering PDFs, uploading.
- **One in-house 7–8B model does the judgment, one request at a time, FIFO**:
  reading job descriptions for scoring, and writing the few lines of each
  document that can't be templated.
- The model runs on `lvamo-backend` (Ampere A1, 4 ARM cores, 24 GB, no GPU),
  **limited to 3 cores**, so the APIs, Postgres and nginx always keep one.

Documents always look the same because **the layout is code** and the model
only ever produces text in fixed slots. Two layout options (§7):
1. **Standard template**: the routine's CV and cover letter design.
2. **Your own template**: the user's own CV file, turned once into a
   template, so every generated CV looks exactly like theirs.

---

## 2. The nightly flow

```
22:00  nightly_run (engine_tasks)
  │
  ├─ Stage 1  DISCOVERY            code, parallel         ~10–20 min
  │    fetch all company boards once → shared `opportunities`
  │    per user: filter (roles, countries, excluded words, already seen)
  │    → one `job_assessments` row per (user, job), status = raw
  │
  ├─ Stage 2  AI SCORING           model, FIFO queue
  │    per raw job: model extracts facts → code computes the score
  │    score ≥ 80 → docs_status = pending   (your "doc_generated = 0")
  │    score < 80 → docs_status = not_needed
  │
  └─ Stage 3  DOCUMENTS
       model, FIFO queue: write headline + cover-letter paragraphs (JSON)
       code, parallel:    pick bullets, render PDFs, check, upload to R2
       → docs_status = done, generated_documents rows
07:00  users log in: everything ready
```

**Which users:** every active Applaut user with `job_engine` `basic` or
`applaut_ai` gets Stage 1 (code only, free). Stages 2–3 run only for
`applaut_ai` users. `own_routine` users are skipped; their routine finds
their jobs.

**Order in the queue:** all scoring items are queued as soon as Stage 1
finishes. A user's document items are queued as each of their jobs scores
≥ 80, so they land behind every remaining scoring item. A single FIFO queue
therefore gives exactly this order: all users scored first, then all users'
documents. Users are queued in the order they turned Applaut AI on
(`profiles.job_engine_changed_at`), earliest first.

---

## 3. The model service

| | |
|---|---|
| Runtime | `llama.cpp` server (`llama-server`), ARM64 image, new compose service `llm` |
| Limits | `cpuset: "1-3"` (core 0 stays free for API/Postgres/nginx), `--threads 3`, `--parallel 1` (one request at a time), `mem_limit: 8g` |
| Model | One 7–8B instruct model, 4-bit (~5 GB). Candidates for Phase 0: Qwen 2.5/3 7–8B, Llama 3.1 8B, Mistral-class 7–8B. Prefer an Apache-2.0 licence. Must handle English **and German** job descriptions |
| Network | Internal Docker network only; no port published to the host |
| API | OpenAI-compatible (`/v1/chat/completions`), so it plugs into `core/ai.py`'s client with a `base_url`. Behind a provider interface (principle 7), so a Claude provider can replace it per task later |
| Output | JSON constrained by a JSON schema (`response_format`), so a small model can't return broken JSON |
| Speed trick | Prompt order is fixed instructions → the user's profile → the job. The server reuses the cached prefix, so for each job only the job's own tokens are processed |

### 3.1 Capacity (estimates; Phase 0 measures the real numbers)

Assumed with 3 cores, 4-bit 7–8B: ~15 tokens/s reading the prompt, ~4
tokens/s writing.

| Queue item | New prompt tokens | Output tokens | Time |
|---|---|---|---|
| Score one job | ~900 (job description trimmed to its requirements by code) | ~150 (JSON facts) | ~1.6 min |
| Write one document set | ~1,200 (job + selected bullets) | ~400 (headline + 3 paragraphs) | ~3 min, ~3.5 with retries |

The night window is 22:15–07:00, about **525 minutes** of model time.

| | AI-scored jobs | Doc sets | Model time per user | Users per night |
|---|---|---|---|---|
| A user's first night (backlog) | capped at 40 | ~8 | ~90 min | **~5** |
| A normal night (new jobs only) | ~12 | ~3 | ~30 min | **~17** |

Rules that follow from this:
- **Code filters first.** The model only sees jobs that pass the hard
  filters and that it hasn't assessed for this user before.
- **Cap of 40 AI-scored jobs per user per night**, highest rule score first;
  the rest wait for the next night. This keeps one new user's backlog from
  eating everyone's night.
- **An admission cap on Applaut AI users** (start at 10), raised once real
  run times are known (§8). Users beyond the cap join a waitlist (the
  existing disabled card already has one).
- **If the queue isn't empty at 07:00, it keeps going** in the same order.
  Those users see "still preparing — N jobs ahead of you" (§6).

---

## 4. The AI queue

The scheduler (`engine_tasks`) is for "run X at time T" and allows one open
task per kind per profile. The AI work needs one row per job, strict order
and exactly one consumer, so it gets its own table.

**`applaut.ai_queue`** (migration `NNNN_applaut_ai_engine`):

| Column | |
|---|---|
| `id` | `bigserial`; **FIFO = `ORDER BY id`** |
| `kind` | `score_job` / `write_docs` / `build_template` |
| `night_run_id` | → `night_runs` (NULL for daytime items such as `build_template`) |
| `user_id`, `profile_id`, `opportunity_id` | |
| `status` | `pending` / `running` / `done` / `failed` |
| `attempts`, `last_error` | |
| `enqueued_at`, `started_at`, `finished_at` | |
| `prompt_tokens`, `output_tokens`, `duration_ms`, `model` | measured on every item; this is how capacity gets tuned |

**`applaut.night_runs`**: `id, run_date, started_at, discovery_done_at,
scoring_done_at, docs_done_at, users, jobs_found, jobs_scored, jobs_80_plus,
docs_done, docs_failed` (the morning report and the dashboard card read this).

**One consumer.** A new compose service `ai-worker` (same backend image,
command `python -m app.applaut.ai.worker`) is the only process that takes
items:

```sql
SELECT * FROM applaut.ai_queue
WHERE status = 'pending'
ORDER BY id
LIMIT 1
FOR UPDATE SKIP LOCKED
```

It runs the item, writes the result, and takes the next. It is kept out of
the uvicorn workers so API requests never wait on a 3-minute model call.
Model calls are serial anyway (`--parallel 1`); a single consumer also makes
the order exact.

**Failures.** A failed item retries **at the back of the queue** (FIFO stays
fair), at most 2 retries, then `failed`, shown on the job. If `ai-worker` is
restarted, a `running` item older than 15 minutes goes back to `pending`.

**Daytime.** The queue is empty most of the day, so a `build_template`
(§7.2) or a rescore after a profile edit runs within seconds. It still goes
through the same queue, so it never collides with a night run.

---

## 5. Scoring: the model reads, code scores

A 7–8B model is reliable at pulling facts out of text and unreliable at
giving a calibrated number. So the model never outputs the score:

1. **The model extracts** (JSON schema): must-have skills, nice-to-have
   skills, required German level, years of experience, seniority, contract
   type (permanent / fixed-term), work mode and location, visa or
   relocation notes, anything unusual worth flagging.
2. **Code compares** the facts to the user's master profile (§7.1), using
   `core/role_synonyms.py` and the profile's skill aliases.
3. **Code computes `match_score` 0–100**, with fixed, visible weights:

| Part | Weight | Rule |
|---|---|---|
| Must-have skills covered | 45 | share of must-haves the profile has |
| Role fit | 20 | title and responsibilities vs target roles |
| Language | 15 | the user's German level vs the required level; a hard miss caps the total at 60 |
| Seniority / years | 10 | within range, one level off, further |
| Nice-to-haves | 5 | share covered |
| Location / work mode | 5 | matches the profile's preference |

It's stored in the existing `job_assessments` row: `match_score`,
`matched_skills`, `missing_skills`, `german_required`, `seniority`, `flags`
(e.g. `CHECK: fixed-term`), `notes`, and the raw extraction in `raw`. Every
score can be explained line by line (principle 4), the same score always
comes out of the same facts, and changing a weight rescores without asking
the model again.

**New columns on `job_assessments`:** `status` (`raw` / `scored` / `failed`)
and `docs_status` (`not_needed` / `pending` / `done` / `failed`).
`docs_status = pending` is the "doc_generated = 0" flag. The threshold is
**80** for this engine.

---

## 6. Documents: code picks, the model writes a few lines

Per job with `docs_status = pending`:

| Part | Done by |
|---|---|
| Name, contact, education, certifications, dates, layout | Template + master profile, never changed |
| Experience bullets | **Code** picks the best bullets for each role from the user's **bullet bank** (each role's `facts` in the master profile), ranked by overlap with the job's must-haves, within each role's bullet limits |
| Skill rows | **Code** puts the job's matching skills first in each row, keeps the profile's labels and spelling |
| Technologies per role | **Code**, from the profile |
| CV headline (1 line) | **Model**, from `default_headline` adapted to the job |
| Cover letter: subject, recipient, date, salutation | **Code**, from the job (title, company, requisition id) |
| Cover letter: paragraphs 1–3 (hook, main evidence, second angle) | **Model**, about 200–280 words |
| Cover letter: logistics paragraph, thank-you, closing | **Code**, from the profile (`personal`, `languages`) |

Then, all in code:

1. **Fact guard** (ported from `pipeline.py`'s `build_cv_context` /
   `build_cl_context`): every skill must be in the profile; every number must
   appear in the profile or the job description; nothing is said about the
   company that isn't in the posting. A failure is fed back to the model once
   with the exact error; a second failure marks the job `failed` with the
   reason (principle 8).
2. **Render** (parallel workers): template 1 with WeasyPrint (as the
   routine), template 2 with docxtpl + LibreOffice headless (§7.2).
3. **Fit check**: CV ≤ 2 pages, cover letter exactly 1. If the CV is too
   long, **code drops the lowest-ranked bullet and re-renders**. No model call.
4. **Upload** to R2 at `applaut/documents/{user_id}/{opportunity_id}/{sha8}/`,
   create `generated_documents` rows (`engine = applaut_ai`,
   `content_type = application/pdf`), set `docs_status = done`.

Language: English, unless the profile says German applications are wanted
and the posting is in German (the routine's rule).

**What the user sees in the morning:** a dashboard card "Last night: 23 new
jobs, 6 matches ≥ 80, 6 CVs ready" (from `night_runs`); matches on
Opportunities with the score breakdown; View / Download CV and cover letter;
"still preparing — N ahead of you" if the queue ran past 07:00.

---

## 7. Templates

### 7.1 The master profile (needed by both templates)

Templates and the fact guard need richer data than `profiles` holds today
(a flat skills list, JSON education). New table
**`applaut.master_profiles`** (`user_id`, `profile_id`, `data jsonb`,
`version`), with `data` in the routine's `master_profile.yaml` shape:
`personal`, skill rows with labels, `experience[]` (id, title, company,
dates, `facts` = bullet bank, `technologies`, `cv_bullets`), `projects[]`,
`certifications`, `education`, `languages`, `default_headline`,
`default_cover_tagline`, `skill_aliases`.

Built once from the uploaded CV (text extraction + a `build_template` or
`extract_profile` queue item), then **reviewed and edited by the user**
in a new Settings → Master profile screen. The user is asked to make each
role's bullet bank 6–12 bullets long; the more good bullets, the better code
can tailor without the model.

### 7.2 Option 1 — Standard template

The routine's `cv.html.j2` and `cover_letter.html.j2` with their fonts
(Carlito, Roboto), moved from `routine/setup_kit/templates/` to a shared
`generation/templates/standard/` that both the setup kit and the engine read.
WeasyPrint is added to the backend image (needs Pango on the slim base). For
Venkat, Phase 1 checks that Applaut renders **the same PDF** as his routine
from the same content.

### 7.3 Option 2 — The user's own template (one-time build)

The look is copied by keeping **the user's own file** and replacing only its
text with placeholders. Rebuilding a layout from a PDF can't be made exact,
so this needs a **.docx** (Word, or Google Docs → Download → .docx). A PDF
upload gets a clear message asking for the .docx, or the standard template.

One-time build (`build_template` queue item, minutes, runs once):

1. **Code reads the .docx** (python-docx): paragraphs, styles, runs, tables,
   lists, header/footer.
2. **The model labels each paragraph** (JSON schema): name, contact line,
   headline, section heading, role title, company/date line, bullet of role
   *n*, skill row, education, other. Labelling is a strong task for a small
   model, and it runs once.
3. **Code turns the file into a docxtpl template**: the first bullet of each
   role becomes `{%p for b in exp.bullets %}`, the headline becomes
   `{{ cv.headline }}` and so on. The original paragraph's style, font, size,
   colour and spacing stay, so generated text looks like the original.
4. **Code builds the master profile** from the same labels (so the user
   doesn't type it twice).
5. **Round-trip check**: render the new template with the content extracted
   from the user's own CV. The result must contain the same text in the same
   order as the upload, and the user sees both side by side. Only after the
   user accepts it does the template go live.

Cover letter: if the user also uploads their cover letter .docx, it goes
through the same steps. Otherwise the standard cover letter is used.

Fonts: LibreOffice can only use fonts on the server. Carlito (metric-
compatible with Calibri) and the common free fonts are installed. If the
.docx uses a font we don't have, the round-trip preview shows it, and the
user is told which font was substituted before accepting.

LibreOffice (~400 MB) goes into the image only in Phase 4.

---

## 8. Build order

| Phase | Scope | Done when |
|---|---|---|
| **0. Benchmark** | `llm` container on the VM (3 cores), 2–3 candidate models. Measure prompt and output speed. On real data: score extraction on 20 jobs (incl. German postings); document writing on 5 jobs ≥ 80, blind-compared by Venkat against Sonnet 5.5 output for the same jobs | A model is chosen, and real per-item times replace §3.1's estimates. **If no local model's writing passes the blind check, writing uses the Claude API through the same provider interface and only scoring stays local** |
| 1. Master profile + standard template | `master_profiles` table and edit screen, port templates + fact guard + renderer into `generation/`, bullet picker, PDF + R2 + `generated_documents` | Venkat's profile renders the same PDFs as his routine; tests for fact guard, bullet picker, page fit |
| 2. Queue + scoring | `llm` and `ai-worker` services, `ai_queue`, `night_runs`, `nightly_run` task at 22:00, one-fetch discovery + per-user filters, extraction prompt + code scoring, assessment columns | A night run in production scores Venkat's jobs; queue order and retries covered by tests (two users, FIFO proven) |
| 3. Documents | `write_docs` items, render workers, morning dashboard card, "still preparing" state, onboarding card enabled for allow-listed users | Venkat logs in to finished CVs for every ≥ 80 job for a week |
| 4. Own template | .docx upload, `build_template`, round-trip preview, docxtpl + LibreOffice rendering | A test user's own .docx CV round-trips and generates matching documents |
| 5. Capacity | Admission cap from measured times, per-night caps tuned, run report | Cap set from a week of real `ai_queue` timings |

Each phase: tests in `backend/tests/applaut/`, `deploy.sh`, verify in
production, record in `PROGRESS_APPLAUT.md`.

---

## 9. Assumptions and open decisions

Assumed (smallest reasonable choice; say if any is wrong):

1. **22:00 is Europe/Berlin time** (DST handled), the same for every user.
2. **The nightly 22:00 discovery replaces Basic's 6/12/24-hour setting**:
   one schedule for everyone. Basic users keep the manual "Run discovery".
3. **Users are queued in the order they turned Applaut AI on.** The same
   early users are always first; if that becomes unfair, rotate the start
   user each night (a one-line change).
4. **Doc threshold is a fixed 80** for Applaut AI (Basic keeps the
   profile's `good_threshold`).
5. **Jobs stay shared rows** (`owner_user_id` NULL). They come from public
   boards, so storing one copy per user would duplicate them. "Raw jobs at
   user level" are the per-user `job_assessments` rows. The Opportunities list
   for an Applaut AI user shows only jobs with an assessment for them.
   (`JOB_ENGINES_DESIGN.md` §3.1 had assumed engine 2 jobs would be private
   copies.)

To decide after Phase 0:

6. **Local or API for writing**, from the blind comparison (§8, Phase 0).
7. **Admission cap** on Applaut AI users, from measured times (§3.1).
