# Applaut AI — v2 plan: more model VMs, a writer that does more

Status: **plan only, nothing built** (2026-11-01). Builds on branch
`applaut-ai-local` (Phases 0–2 of
[`APPLAUT_AI_ENGINE_DESIGN.md`](APPLAUT_AI_ENGINE_DESIGN.md), not deployed).
Nothing here goes to `main` or prod until the first partner VM is ready.

---

## 0. Fixed decisions (Venkat, 2026-11-01)

1. **No CV or letter layout changes, ever.** Not for the standard template
   (the routine's), not for a user's own uploaded template. No summary
   paragraph. Only the text inside the existing slots changes per job.
2. **Specialised models, identical hosts.** Each task has its own model
   (scorer, writer), chosen and later trained for that task. Every model VM
   runs all task models and serves whatever task is next in the queue.
   Adding a VM = one address in config; no routing changes.
3. **One partner VM now**, built so more VMs are a config change.
4. **The writer does more**: picks bullets by meaning, rewords them for the
   job, orders skills, plus the headline and 3 letter paragraphs it already
   writes. Every reworded piece is checked against its source and falls back
   to the original on its own.
5. **Bullet bank builder**: AI drafts new bullets from the user's rough notes;
   only bullets the user approves enter the master profile.

---

## 1. What exists today (branch `applaut-ai-local`)

| Area | Today | Files |
|---|---|---|
| Model | Qwen3.5-9B Q4_0 for both tasks; llama-server; one URL (`APPLAUT_LLM_BASE_URL`) | `ai/provider.py` |
| Queue | `applaut.ai_queue`, FIFO by `seq`, 3 tries, retry to the back | `ai/queue.py` |
| Worker | One process, one item at a time, one model URL. A connection error counts as a try (18 items failed in 2 min when the model was stopped, 2026-10-31) | `ai/worker.py` |
| Nightly | 22:00 Berlin, `applaut_ai` users only, cap 40 jobs/user | `ai/nightly.py` |
| Scoring | Model extracts facts (one-line JSON, ~200 tokens), code scores | `ai/prompts.py`, `ai/scoring.py` |
| Writing | Model writes headline + 3 letter paragraphs. Code: bullets by keyword rank (`tailor._rank_facts`), skill order by keyword (`order_skill_rows`), letter fixed parts, fit loops (CV drops bullets, letter drops sentences) | `ai/handlers.py`, `documents/*` |
| Checks | Numbers must be in profile/job; first person; paragraph lengths | `documents/fact_guard.py` |
| Model host | One llama-server, one model, WireGuard + API key, manual setup | `model-host/` |
| Master profile | YAML editor in Settings; `facts` are plain strings per role/project | `documents/profile_schema.py` |
| Documents | `generated_documents` rows (PDF in R2). No per-document detail column | `models/generated_document.py` |

Measured (live run 2026-10-31, 3 cores): score ~2 min/job, write ~2.75
min/set → ~16 users/VM on a normal night.

---

## 2. Workstream A — model VMs that scale

### A1. Model host: two models, pinned (changed + new)

- **Changed** `model-host/docker-compose.yml`: two llama-server services,
  `scorer` on :8080 and `writer` on :8081, each its own `mem_limit`
  (scorer 6 GB, writer 12 GB; 24 GB VM), both `cpuset 0-3` (they never run
  at once: the app sends one request per VM at a time), `--parallel 1`,
  `--cache-ram 0`, `--api-key`, published on the WireGuard address only.
  Until a separate scorer/writer is chosen, both point at the Qwen 9B file
  (or one container serves both ports' tasks).
- **New** `model-host/models.lock`: per task: file name, download URL,
  sha256, alias (e.g. `scorer=qwen3.5-9b-q4_0@<sha8>`).
- **New** `model-host/setup.sh <wg-address> <app-pubkey>`: installs Docker
  + WireGuard, writes wg0.conf, opens UDP 51820 to the app VM only,
  downloads + verifies every file in models.lock, starts compose. Prints
  the VM's WireGuard public key to add on the app VM.
- **New** `model-host/update.sh`: pulls repo, downloads changed models,
  verifies, restarts. Used to roll a model change to every VM.

### A2. App side: one lane per VM (changed)

- **Config** (changed `config.py`, `.env.example`):
  `APPLAUT_MODEL_HOSTS=10.8.0.2[,10.8.0.3,…]`,
  `APPLAUT_LLM_API_KEY` (one key for all hosts),
  task → port map in code (`ai/hosts.py`: `score_job→8080`,
  `write_docs→8081`, `draft_bullets→8081`), expected model aliases from a
  copy of `models.lock` in the repo. `APPLAUT_LLM_BASE_URL` removed.
- **Worker** (changed `ai/worker.py`): one async loop ("lane") per host,
  all in the one `ai-worker` process. Each lane:
  1. At start and every 10 min: `GET /v1/models` on both ports; the aliases
     must equal models.lock, else the lane stays paused and logs why
     (mixed model versions would make scores incomparable).
  2. Claims the next pending item of any kind, preferring the user it
     served last (keeps that user's prompt prefix cached on that host).
     Preference is bounded: only among the oldest 20 pending items, so FIFO
     fairness holds.
  3. Calls the task's port on its host; records `host` + timings.
  4. **Host unreachable** (connect error / timeout / 5xx): puts the item
     back as it was (status pending, same `seq`, attempt not counted), lane
     backs off 30 s → 1 → 2 → 5 min. Other lanes carry on.
  5. Model errors (bad JSON, cut off, fact-guard twice) count as tries, as
     today.
- **Queue** (changed `ai/queue.py`): `claim_next(prefer_user, window=20)`,
  `release(item_id)` (undo a claim without a try).
- **DB** (changed migration `0030`, not deployed anywhere, so it is edited
  in place rather than adding `0031`): `ai_queue.host` text.
- **Capacity**: `nightly` logs healthy hosts; admission cap (§3.1 of the
  design) = `APPLAUT_AI_USERS_PER_HOST` (10, see B5) × healthy hosts.

### A3. Optional lane on the app VM

`lvamo-backend` cores 1–3 can be a lane (`10.8.0.1` / localhost) using the
same `model-host/` compose with `cpuset 1-3`. Phase 0 measured prod API
median 38 → 42 ms while the model ran. Off by default; a later decision.

### A4. Tests (new, `tests/applaut/test_ai_lanes.py`)

Two fake hosts drain one queue in FIFO order; a host going down releases
its item without a try and the other lane takes it; user preference within
the window; lane refuses a host with the wrong model alias.

---

## 3. Workstream B — the writer does more (same templates)

### B1. The writing call picks, short calls reword (changed)

As built (step 3). The first plan, one call returning every bullet reworded,
failed on the real model: Qwen3.5-9B copied the facts word for word in three
prompt rounds (0–10% reworded). The work is now split:

1. **Writing call** (`write_system` + the posting), returns:

   ```json
   {
     "headline": "…",
     "focus": [{"id": "exl_pa.3", "need": "reduce processing times"}, …],  // 5
     "bullets": ["exl_pa.3", "exl_jpa.2", …],                               // ranked ids
     "skills_first": ["Azure Databricks", "Apache PySpark", …],             // ≤ 8
     "paragraphs": ["…", "…", "…"]
   }
   ```

   Fact ids, bullet ids and skill names are JSON-schema enums built from the
   profile, so the model can only name the user's own facts and skills.
2. **One rewording call per focus bullet** (`reword_message`), sent after the
   same `write_system` prefix so llama-server keeps that prompt cached
   between jobs. It gets the fact, the need, the numbers and the tools (as
   the fact spells them) and returns `{"text"}`. If the checks reject it,
   one retry names the reason; a second rejection or a model error leaves
   the fact as written. Only a host going down fails the whole item (put
   back in the queue, as in A2).

### B2. Checks, piece by piece (changed `fact_guard.py`, `tailor.py`)

| Piece | Check | If it fails |
|---|---|---|
| Bullet IDs | Exist; belong to an entry; per-entry min/max respected | Code picker fills / trims that entry (today's `_rank_facts`) |
| Each reworded bullet | Not a copy; the same numbers as its fact, counted (the "2" in "R2" can't cover a new "2 hours"); every skill it names is in that fact or that entry's `technologies` (no cross-role moves) and every skill the fact names stays; 70–130% of the fact's length; no first person; **no word the fact doesn't have** in some form, other than joining words (`new_words`) | That bullet uses the original fact text; others keep theirs |
| `skills_first` | Every name is a profile skill | Code order (today's `order_skill_rows`) |
| Headline, paragraphs | As today (numbers, first person, lengths) | Feedback to the model once, then the job's docs fail (as today) |

Bullet and skill failures never fail the job; only headline/paragraph
failures do (they have no original to fall back to).

### B3. Fit and render (changed `render.py`)

The CV fit loop drops the lowest-ranked bullet using the model's ranking
(falls back to code ranking for entries the model didn't rank). Templates
untouched; the reworded text goes into the same `bullets` slots.

### B4. Original vs tailored (new)

As built (step 4, 2026-11-04):

- **DB**: `generated_documents.details` JSONB (in migration `0030`), on
  Applaut AI CVs only: a snapshot of the master profile, the headline, the
  skill rows, and per role its bullets `{id, original, tailored (or null),
  use: tailored|original, rank, note}`, plus `choices` (each switch: fact,
  version, the version it came from, time). ~12 KB per CV. The snapshot
  means a later edit to the master profile doesn't change an existing CV.
- **API**: `GET /documents/{id}/details`;
  `POST /documents/{id}/bullets/{fact_id}/use` `{version: original|tailored}`
  builds the CV again in code (`render.rerender_cv`: no model, ~0.1 s on
  Venkat's profile), stores the PDF, and saves a new `is_current` row; the
  previous row stays, and the audit log gets `document.bullet_choice`
  (plus `details.choices` on the CV itself). 409 on an old
  version, 422 for a bullet with no tailored wording, 404 for someone
  else's CV.
- **UI**: a "Tailored bullets" panel on the job's Documents page (CV tab):
  each reworded bullet with the other wording under it and a "Use my
  wording" / "Use tailored" button.

### B5. Before switching on (benchmark)

Re-run the 5 Phase 0 writing jobs with the new call on the test container:
per-bullet pass rate (target ≥ 85% kept as tailored), time per set, and a
human read of every reworded bullet for truthfulness. Then a few real nights
on the branch before calling it done.

**Result (2026-11-04, the two-stage writer of B1, Qwen3.5-9B on 3 cores of
`lvamo-backend`):** all 5 sets written on the first try.

| | Runs 1–3: one call rewords | Final: picks, then a call per bullet |
|---|---|---|
| Bullets reworded (of the 5 per job the writer picked) | 0–5 of 25 | 14 of 25 (56%) |
| Reworded bullets that say something the fact doesn't | 6 of 16 in a trial before the new-words check | 0 of 14 (read one by one) |
| Time per set | 4–6.5 min | 5.8–7.9 min (writing ~3.5, rewording ~2.7) |

- The 85% target is not met: 9 of 25 came back as copies, 2 were rejected by
  the checks. A copy or a rejection shows the fact as written, so the CV is
  never worse than the code-only one. What the accepted ones do is move the
  result to the front: "Reduced monthly Azure compute costs by 20% for
  Databricks clusters by implementing cost-optimization strategies, …".
- Before the new-words check, the model turned the posting's need into a
  claim ("Designed and built high-scale distributed services by …",
  "Automated resource type onboarding …", "Built" for "Owned and
  maintained"). No number or skill check catches that; `new_words` does.
- Capacity: ~6.5 min per set instead of ~2.5 makes a normal night ~50 min of
  model time per user, so about **10 users per host** (was 14).
  `APPLAUT_AI_USERS_PER_HOST` now defaults to 10.
- The writer's ranking of bullets and `skills_first` (deduped by code; the
  model repeats "Data Quality" to fill 8 slots) are in use either way.

---

## 4. Workstream C — bullet bank builder (new)

Goal: more facts per role (target 8–12), so tailoring has material. One-time,
daytime, every bullet approved by the user.

- **API** (built 2026-11-04, `/api/v1/applaut/master-profile`):
  - `POST /entries/{entry_id}/draft-bullets` `{notes}` (20–4000 chars) →
    202, a `bullet_drafts` row and an `ai_queue` item of kind
    `draft_bullets` (writer port). 409 unless the engine is Applaut AI and a
    model host is set, or while the role still has an open set; 404 for an
    unknown role.
  - `GET /entries/{entry_id}/drafts` → the open set or `null`: status
    (`pending` with `ahead` / `done` / `failed` with the error), `drafts`
    `[{text, confirm}]`, `left_out` `[{text, reason}]`.
  - `DELETE /entries/{entry_id}/drafts` closes the set; if the writer hasn't
    started on it, its queue item is removed too.
  - `POST /entries/{entry_id}/facts` `{facts, draft_id?}` appends the kept
    bullets (as the user edited them), validates the profile, bumps the
    version, closes the set, audit `master_profile.add_facts`.
- **Model** (`prompts.DRAFT_SYSTEM`, `draft_message`): the notes, the role and
  its existing facts and technologies, the profile's skills → 1–5 bullets
  (JSON schema) in English, each starting with a past-tense verb, 6–35
  words, no first person, only what the notes and existing bullets say; no
  added detail, the notes' hedges kept ("about 10"), the candidate's part
  never made bigger ("together with" never becomes "led").
- **Checks** (`fact_guard.check_drafts`), in this order, each a reason the
  user sees: 6–45 words; not first person; names nothing (a capitalised
  word, or a word with a digit or `.#+`, e.g. Kafka, S3, C#) outside the
  notes, the role and the profile's skills (a usual short form in the notes
  counts: k8s → Kubernetes, postgres → PostgreSQL); claims no lead the
  notes and the role's bullets don't back (opening "Led", "Managed",
  "Owned", "Drove", … or "led"/"leading" anywhere); not an existing fact of the role; not a near-copy of another draft
  (word overlap ≥ 0.6). A number in neither the notes nor the role is not a
  reason to leave it out: it is listed in `confirm` and the UI says "Check:
  15 isn't in your notes".
- **UI** (Settings → Master profile, only with Applaut AI): "Add bullets from
  notes": pick the role (shows its bullet count), write notes, "Draft
  bullets"; while queued it shows the place in the queue and checks every
  10 s; drafts come back as editable boxes with Keep / Discard, the left-out
  ones with their reasons, and "Add N kept bullets" (disabled while the YAML
  has unsaved edits).
- **Real-model run (2026-11-05)**: Qwen3.5-9B writer on `lvamo-backend`
  cores 1–3 (test container), the handler's exact call + checks, 7 kinds of
  notes on the fictional test profile (detailed with numbers; informal with
  "k8s"; short naming new tools; German; a side project; vague and easy to
  inflate; only repeating existing bullets). 16–55 s per request (~460–570
  prompt tokens). First run: padding ("interactive", "data validation
  procedures and operational workflows"), "about 10" became "10", and
  "together with the platform team" became "Led the migration". Fixed with
  the prompt rules above and the lead-claim check; k8s was left out until
  short forms counted. Final run: 17 drafts kept, 0 untrue on a human
  read (two small inferences, e.g. "for the data engineering team"), notes
  in German came back in English, and the repeat-only notes gave nothing
  new (4 left out: 3 as existing bullets, 1 as too short).
- **Tests**: `tests/applaut/test_bullet_bank.py` (checks, the queue → keep
  flow, audit, refusals, a failed set, discard before the writer starts,
  FIFO order with other users).
- **Queue timing**: daytime queue is normally empty → minutes. If a night
  backlog runs past 07:00, drafts wait their turn (FIFO). A priority lane
  for interactive items is a later decision (§7).

---

## 5. Workstream D — own template (Phase 4, unchanged in scope)

As in the design doc §7.3: user uploads their .docx CV/letter once,
Applaut builds a template from it (round-trip check), docxtpl + LibreOffice
render. It consumes exactly what B produces (headline, ordered bullets per
role, ordered skills, paragraphs), so B is built first and D plugs into it.
No layout changes to the user's template, same as the standard one.

**Built 2026-11-05 (CV only):**

- **What changes per job, and nothing else**: the headline line under the
  name (if the CV has one), the items of each skills row (`Label: a, b`; the
  label stays), each role's or project's bullets (one docxtpl loop in the
  first bullet's paragraph formatting; a hand-typed "•"/"-" mark stays), and
  a role's `Technologies: ...` line (the label stays). Names, contact lines,
  headings, role titles, dates, education and any summary paragraph are left
  exactly as uploaded. Text is replaced at run level, so bold labels,
  colours and fonts of the kept parts stay.
- **Roles stay the user's own** (a change from §7.3, which looped over
  roles): the CV shows the roles its file has, in its order. Each role is
  matched to a master-profile entry by the company and title (or project
  name) its own lines name; its bullets and technologies then come from that
  entry, picked and reworded for the job as in B. A role or skills row with
  no match keeps the upload's own text. Matching runs again at each render,
  so renaming an entry id doesn't break a template.
- **Reading** (queue kind `build_template`, writer, one-time): code reads
  every paragraph in document order (body, table cells, content controls,
  text boxes; not a drawing's fallback copy), the model labels each non-empty
  line (name, headline, contact, section, skills, role, bullet,
  technologies, other) with the paragraph style as a hint, and code makes
  the labels consistent (one short headline at most; bullets and technologies
  only inside a role's block). Labels are keyed by line number in the JSON
  schema: as a bare list the model lost its place in a table CV.
- **Refused with a reason**: a PDF ("upload the .docx"), not a .docx, over
  5 MB, more than 200 lines, text containing `{{`/`{%`, a role's bullets
  split by another line.
- **Round trip**: the template filled with the upload's own text must give
  back the upload's text line for line; otherwise the differences are shown
  and it can't be switched on. Both PDFs (the upload and the rebuilt
  template, via LibreOffice) are stored for the user to compare. Fonts the
  server doesn't have (other than Calibri/Cambria/Arial/Times New Roman/
  Courier New, which have metric-compatible twins installed) are listed.
- **Pages**: each CV keeps to the upload's page count, dropping the
  lowest-ranked bullet as for the standard template. If it still runs over
  with every role at its minimum, it's kept as it is.
- **Storage**: upload, template and both PDFs in R2 under
  `applaut/templates/{user}/{template}/`; `applaut.cv_templates` holds the
  labels, slots and report. Statuses: reading → ready / failed → active
  (one per user) → retired; discarded before use. Switching on and off is
  audited (`cv_template.use`, `cv_template.stop`).
- **Generation**: `write_docs` uses the active template (the cover letter
  stays standard); the CV's details record the template, so switching a
  bullet (B4) rebuilds it with the same template, even after the user
  switched it off.
- **UI**: Settings → CV template (Applaut AI only): what's in use, upload,
  "Reading…" with the queue position, then both PDFs, what each job changes
  (role → profile entry, skills rows), font notes, "Use this template" /
  "Discard"; "Use the standard template" switches it off.
- **Image**: LibreOffice Writer (no GUI) and the metric-compatible fonts are
  in both Dockerfiles; the backend image grew from ~0.6 GB to ~1.2 GB.
- **Real-model run (2026-11-05)**, writer on `lvamo-backend` cores 1–3, three
  test CVs (one column; a two-column table with German headings; a German
  CV with typed "•" bullets and tab-separated dates): 0, 2 and 0 lines
  mislabelled of 24, 21 and 19, all round trips exact, every role and
  skills row matched. The 2 misses (an education heading and its dates
  labelled as a role) change nothing: a block without bullets has nothing
  to fill and isn't shown. 49–77 s per CV, once.
- **Not built (still §7.3)**: the user's own cover letter template, and
  building the master profile from the uploaded CV.

---

## 6. Small fixes carried from the live run (2026-10-31)

1. Store the model's last answer on a failed `write_docs` (in `raw`) so
   failures can be read (the dymatrix letter failed the first-person check
   twice; its text was lost).
2. Company display name: the letter said "helsing" (board slug). Use the
   posting's company name capitalisation, or title-case slugs.
3. Scoring rules to decide (Venkat): penalise or filter roles marked
   junior for a 4+ year profile; whether a security clearance / ITAR
   requirement caps the score like German above the user's level.
4. "German OR English" check: confirm on the 20 Phase 0 jobs with the new
   prompt.

---

## 7. Later / open

- Scorer and writer models: benchmark a 4B scorer and a 14B writer on the
  test container (needs ~2.5 GB + ~8 GB downloads, ask first).
- Fine-tuning the scorer on the routine's Opus-scored jobs (rented GPU,
  LoRA; Venkat's own data only).
- Priority lane for interactive items (bullet drafts, "score this job now").
- Processing agreement with each VM owner + privacy-notice line (before any
  other user's data goes to a partner VM).
- Oracle Always Free idle reclamation: check each partner account (Pay As
  You Go accounts are not reclaimed, to verify).

---

## 8. Order of work

| Step | Scope | Done when |
|---|---|---|
| 1 | §6.1, §6.2 small fixes | Tests pass. **Done 2026-11-02**: failed `write_docs` keep the model's answer in `raw.write_docs_last_answer`; letters use `company_display()` (the posting's own spelling, else a capitalised slug) |
| 2 | A1 + A2 + A4 (lanes, host files) | Two fake hosts tested; one real host (test container) runs a night via a lane. **Done 2026-11-02**: `ai/hosts.py`, `ai/models.lock`, lanes in `ai/worker.py`, `queue.release`, `HostUnreachable`, capacity-aware allowlist, `model-host/setup.sh` + `update.sh` + two-server compose; `test_ai_lanes.py`. Live on `lvamo-backend` cores 1–3: `update.sh` brought both servers up from the lock, one lane scored 2 jobs and wrote 1 set; with the writer stopped its item went back untouched (tries 0) and finished on the first try once the writer was back. A3 (lane on the app VM) not done |
| 3 | B1–B3 (writer does more) | B5 benchmark passes; Venkat reads the reworded bullets. **Built 2026-11-04**: two-stage writer (B1), per-bullet checks incl. `new_words` (B2); B5 result above; waits on Venkat's read |
| 4 | B4 (original vs tailored) | Toggle re-renders a CV in < 1 s, tested. **Done 2026-11-04**: `details` column, two endpoints, Documents-page panel; re-render ~0.1 s; `test_cv_bullet_choice.py`. Checked in the browser locally up to the file upload (no R2 bucket locally); the full switch is covered by the API tests |
| 5 | C (bullet bank builder) | Venkat's bank reaches 8+ facts per role through it. **Built 2026-11-04**: §4 as built; checked in the browser locally with the fake model (keep, edit, discard, add, queued, cancel, no-host refusal). Real writer run 2026-11-05: 7 kinds of notes, 0 untrue drafts after a lead-claim check and prompt fixes (§4). Waits on Venkat drafting for his own roles |
| 6 | Partner VM goes live | `setup.sh` on the VM, `APPLAUT_MODEL_HOSTS` set, deploy, verify in prod, `PROGRESS_APPLAUT.md` |
| 7 | D (own template) | As design doc §8 Phase 4. **CV built 2026-11-05** (§5): upload, model labelling in the queue, round trip, both PDFs, switch on/off, generation and bullet switches with the template; `test_own_template.py`; real-model labelling on three test CVs. Not built: own cover letter template, master profile from the upload. Waits on a real CV of Venkat's through it |

Steps 1–5 run on `applaut-ai-local` with the test container on
`lvamo-backend`; step 6 needs Venkat's go-ahead.
