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
  design) = 15 users × healthy hosts.

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

### B1. One writing call, more output (changed)

The `write_docs` model call returns:

```json
{
  "headline": "…",
  "bullets": [{"id": "exl_pa.3", "text": "…reworded…"}, …],   // ranked, most relevant first
  "skills_first": ["Apache Kafka", "Spark Structured Streaming", …],
  "paragraphs": ["…", "…", "…"]
}
```

- Fact IDs are made by code at prompt time: `<entry id>.<index>` (e.g.
  `exl_pa.3`). No master-profile schema change.
- The prompt lists each role's facts with IDs and that role's bullet limit
  (`bullet_limits`). Rules: pick up to the limit per role, most relevant
  first; reword each picked fact for this job; same facts, same numbers,
  same tools; lead with what this job cares about; CV style (verb first, no
  "I"), ±30% length.
- `WRITE_SCHEMA` / `WRITE_MAX_TOKENS` (→ 1,600) updated. Expected output
  ~750 tokens → ~4 min per set (was ~2.75). Capacity ~14 users/VM.

### B2. Checks, piece by piece (changed `fact_guard.py`, `tailor.py`)

| Piece | Check | If it fails |
|---|---|---|
| Bullet IDs | Exist; belong to an entry; per-entry min/max respected | Code picker fills / trims that entry (today's `_rank_facts`) |
| Each reworded bullet | Same set of numbers as its source fact; every skill/tool name it mentions is in that fact or that entry's `technologies` (no cross-role moves); 70–130% of source length; no first person | That bullet uses the original fact text; others keep theirs |
| `skills_first` | Every name is a profile skill | Code order (today's `order_skill_rows`) |
| Headline, paragraphs | As today (numbers, first person, lengths) | Feedback to the model once, then the job's docs fail (as today) |

Bullet and skill failures never fail the job; only headline/paragraph
failures do (they have no original to fall back to).

### B3. Fit and render (changed `render.py`)

The CV fit loop drops the lowest-ranked bullet using the model's ranking
(falls back to code ranking for entries the model didn't rank). Templates
untouched; the reworded text goes into the same `bullets` slots.

### B4. Original vs tailored (new)

- **DB**: `generated_documents.details` JSONB (in migration `0030`):
  per bullet `{id, original, tailored, used: tailored|original, reason}`,
  plus skills order and headline.
- **API**: `GET /documents/{id}/details`;
  `POST /documents/{id}/bullets/{fact_id}/use` `{version: original|tailored}`
  → re-renders the CV in code (no model, < 1 s), new `is_current` row,
  audit `document.bullet_choice`.
- **UI**: on the job's documents panel, "Tailored bullets" list with a
  per-bullet "use original" toggle.

### B5. Before switching on (benchmark)

Re-run the 5 Phase 0 writing jobs with the new call on the test container:
per-bullet pass rate (target ≥ 85% kept as tailored), time per set, and a
human read of every reworded bullet for truthfulness. Then a few real nights
on the branch before calling it done.

---

## 4. Workstream C — bullet bank builder (new)

Goal: more facts per role (target 8–12), so tailoring has material. One-time,
daytime, every bullet approved by the user.

- **API**: `POST /master-profile/entries/{entry_id}/draft-bullets`
  `{notes: str}` → enqueues `draft_bullets` (`ai_queue`, new kind, serves
  on the writer port); `GET …/drafts` returns status + drafts.
- **Model**: from the user's notes + that entry's existing facts and
  technologies, 3–5 CV bullets in the profile's style.
- **Checks**: every number must appear in the notes or the entry (else the
  number is marked `confirm` in the UI, not dropped); no tool outside notes
  + entry technologies + profile skills; no duplicate of an existing fact.
- **UI** (Settings → Master profile): per role, "Add bullets from notes" →
  drafts with Keep / Edit / Discard; kept ones are appended to `facts`
  (version bump, audit `master_profile.add_facts`).
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
| 1 | §6.1, §6.2 small fixes | Tests pass |
| 2 | A1 + A2 + A4 (lanes, host files) | Two fake hosts tested; one real host (test container) runs a night via a lane |
| 3 | B1–B3 (writer does more) | B5 benchmark passes; Venkat reads the reworded bullets |
| 4 | B4 (original vs tailored) | Toggle re-renders a CV in < 1 s, tested |
| 5 | C (bullet bank builder) | Venkat's bank reaches 8+ facts per role through it |
| 6 | Partner VM goes live | `setup.sh` on the VM, `APPLAUT_MODEL_HOSTS` set, deploy, verify in prod, `PROGRESS_APPLAUT.md` |
| 7 | D (own template) | As design doc §8 Phase 4 |

Steps 1–5 run on `applaut-ai-local` with the test container on
`lvamo-backend`; step 6 needs Venkat's go-ahead.
