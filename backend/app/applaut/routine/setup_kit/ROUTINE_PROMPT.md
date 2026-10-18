# Job search run procedure

You are running unattended as the job search automation for the candidate described in
`profile/master_profile.yaml`. Nobody is watching, so never stop to
ask a question: take the most reasonable decision, note it in the final summary, and keep going.
Do every step in order. Do not commit or push anything to this repository.

## 0. Setup

```bash
bash scripts/setup.sh
RUN_ID=$(python3 scripts/pipeline.py new-run-id)
mkdir -p out/$RUN_ID
python3 scripts/pipeline.py run-start --run-id $RUN_ID
```

`run-start` records this run in the `run_tracker` table with status `running`. Keep the tracker
current: at the start of each step below, run
`python3 scripts/pipeline.py run-step --run-id $RUN_ID --step <step>` with the step named there
(`merge` and `export` record themselves).

Read `profile/master_profile.yaml` and `config/search_config.yaml` in full. Both change over time;
always use what they say now.

If `setup.sh` fails, or a later pipeline command fails with a connection/credential error, run
`python3 scripts/pipeline.py selftest`, then record the failure and stop:

```bash
python3 scripts/pipeline.py run-finish --run-id $RUN_ID --status failed --step <step you were on> \
  --error "<what failed, plus the selftest result in one line>"
```

Record a stop for any other reason the same way. (If the database itself is unreachable this
command fails too; the next run's `run-start` then marks the run `failed`.)

## 1. Find jobs the candidate is eligible for

**Search is the most important part of the run. Be exhaustive, not fast:** finding every relevant
posting matters more than finishing quickly. Search all of Germany (any city) plus remote roles open
to Germany-based candidates, published within `posted_within_days`. Use every source in
`search_config.yaml`. If a source fails, note it and move on.

**Use the whole search budget.** Keep searching until you have run at least 90% of
`max_searches_per_run`. Only stop earlier if every source has genuinely run out of new results
(new queries keep returning postings you have already seen); then say so in the summary. When your
planned queries are done and budget remains, keep opening new angles:
- more skill-led terms: the candidate's strongest skills and tools from `master_profile.yaml`
  (and `skill_terms` in `search_config.yaml`, if set);
- adjacent titles that use the same stack as the `role_families` in `search_config.yaml`;
- English and German phrasings, "remote Germany" / "Remote (DE)" variants;
- more company job boards (Greenhouse, Lever, Ashby, Personio, SmartRecruiters, Workday, Recruitee,
  Workable) found in earlier results, and similar companies in the same industries.

Tracker step: `search`.

First list what the database already has, so you spend your time on new postings:

```bash
python3 scripts/pipeline.py known --out out/$RUN_ID/known.json
```

Work in passes:

1. **Collect.** Run the Arbeitsagentur API exhaustively first (every role family, every
   `search_terms_de` entry and the skill-led terms, all pages, Germany-wide), then the other sources.
   Keep a deduplicated candidate list (same company + role + city = same job) in
   `out/$RUN_ID/candidates.json`, with each candidate's source and links.
2. **Skip known jobs.** A candidate already in `known.json` (same company, role and city, or the same
   link) needs no re-assessment. Add it to `jobs.json` with just the fields copied from `known.json`
   (company, role_title, city, work_mode, requisition_id, jd_url) so its `last_seen` is refreshed.
3. **Screen titles.** Drop candidates whose title or snippet clearly fails a hard rule (excluded
   keywords, excluded seniority, obviously unrelated field such as hardware, SAP-only, sales).
   When in doubt, keep it for a full read.
4. **Read and assess every remaining candidate in full** (rules below; tracker step: `assess`). Confirm the posting is still
   open (the page loads and is not marked expired or filled).
5. **Find the best links.** For each eligible job, look for the employer's own posting and apply link.
   At least one of `jd_url` / `application_url` must open the specific posting (an Arbeitsagentur or
   job-board page for that exact posting is fine); a homepage or a general careers page does not
   count. `merge` rejects jobs without one.

Record counts per source (searches run, postings found, assessed, eligible) for the summary, and
write the run totals to `out/$RUN_ID/run_stats.json` for the tracker:

```json
{"searches_run": 231, "postings_found": 1910, "postings_assessed": 140, "jobs_eligible": 12,
 "sources_failed": ["jobs.sap.com: blocked (403)", "berlinstartupjobs.com: blocked (403)"]}
```

`jobs_eligible` counts the new eligible jobs you found (not the known jobs you only refreshed);
`sources_failed` is an empty list if none failed.

**Eligibility comes from the tech stack, not the title.** The candidate qualifies for any role in
`role_families`, and for adjacent titles whenever the required stack matches theirs. For each posting:

1. Open the actual posting and read the full job description.
2. List its must-have skills and nice-to-have skills.
3. A must-have counts as matched only if it is in `skills`, `additional_skills`, `skill_aliases` or an
   experience's `technologies` in `master_profile.yaml`. Anything else is missing.
4. `match_score` = matched must-haves ÷ total must-haves × 100.
5. Keep the posting only if all of these hold:
   - `match_score` ≥ `min_match_score`
   - required German level ≤ `languages.german_max_required` (a posting written entirely in German
     with no mention of English counts as requiring at least B2)
   - seniority is allowed and the title has none of `seniority_excluded_keywords`
   - the company is not in `excluded_companies`, the title has none of `excluded_keywords`
   - employment type is full-time (or unspecified)
   - the job is in Germany, or remote and open to Germany-based candidates
6. If a requirement is ambiguous, keep the job and explain the ambiguity in `notes`.
7. Keep the job, but start `notes` with `CHECK:` and the reason, when any of these apply:
   - **Security clearance:** the posting requires or mentions a security clearance
     (Sicherheitsüberprüfung, Ü1/Ü2/Ü3, "eligible for security clearance"), or the employer works in
     defence. Note that eligibility can depend on citizenship (see `personal.work_authorization`).
   - **Recruiting agency or intermediary:** the posting is from a staffing firm, personnel
     consultancy or job intermediary (e.g. Jobgether, Hays, Randstad, Darwin Recruitment) rather than
     the employer. Name the agency and the end client if the posting states it.
   - **Location doubt:** a "remote" posting mentions working from or being based in another country.

`max_new_jobs_per_run` is a safety ceiling on new jobs per run. If you reach it, stop assessing,
keep the highest-scoring jobs, and say in the summary how many candidates were left unassessed.

Write all eligible jobs to `out/$RUN_ID/jobs.json` as a JSON list. One object per job:

```json
{
  "company": "N26 GmbH",
  "role_title": "Senior Data Engineer (m/w/d)",
  "role_family": "Data Engineer",
  "location": "Berlin, Germany",
  "city": "Berlin",
  "requisition_id": "R-1234 or null",
  "work_mode": "onsite | hybrid | remote",
  "seniority": "junior | mid | senior",
  "german_required": "none | A1 | A2 | B1 | B2 | C1 | native",
  "employment_type": "full-time",
  "match_score": 82,
  "matched_skills": ["Python", "PySpark", "Airflow"],
  "missing_skills": ["Kafka"],
  "salary_range": "€65k–80k or null",
  "posted_date": "2026-10-14 or null",
  "deadline": "2026-11-01 or null",
  "source": "Greenhouse",
  "jd_url": "https://...",
  "application_url": "https://... (direct apply link, or null)",
  "notes": "anything worth knowing"
}
```

Prefer the employer's own posting or ATS page for `jd_url` / `application_url` whenever one exists.
At least one of the two must open the specific posting. Do not compute UIDs yourself; the pipeline
does that.

## 2. Merge into the database

```bash
python3 scripts/pipeline.py merge --jobs out/$RUN_ID/jobs.json --run-id $RUN_ID
```

This builds the UID (company + role + city [+ requisition id]), merges into the job search database table
`jobsearchautomationresults` (new UIDs are inserted; existing ones only get `last_seen_*` and a few
refreshed fields), and writes `out/$RUN_ID/to_generate.json`: the jobs that need documents (new in
this run, plus earlier jobs whose documents are still pending or failed).

If its output lists `rejected` jobs (for example, no link opens the specific posting), fix those
entries if you can (find the posting's own page), and run `merge` again with the same run id; it is
safe to repeat.

## 3. Generate the CV and cover letter for each job in `to_generate.json`

Tracker step: `documents`.

For each job, re-read its job description (fetch `jd_url` again if needed) and save the text to
`out/$RUN_ID/<uid>/jd.md`, starting with the URL. Then write two JSON files.

**`out/$RUN_ID/<uid>/cv.json`**, tailored CV content:

```json
{
  "headline": "one line based on `default_headline`, adapted to the role family",
  "skills": [
    {"label": "<a skills label from the profile>", "items": ["<skills from that row, as spelled in the profile>"]}
  ],
  "experience": [
    {"id": "<experience id from the profile>", "bullets": ["..."], "technologies": ["..."]}
  ],
  "projects": [{"id": "<project id from the profile>", "bullets": ["..."], "technologies": ["..."]}]
}
```

**`out/$RUN_ID/<uid>/cl.json`**, the cover letter:

```json
{
  "tagline": "based on `default_cover_tagline`: the role and about 5 skills, adapted to the job",
  "date": "15 October 2026",
  "recipient_lines": ["Hiring Team – <team or department>", "<Company legal name>", "<City, if known>"],
  "subject": "Re: Application for <exact role title> (Ref. <requisition id>, if any)",
  "salutation": "Dear <named hiring contact>, or Dear Hiring Team,",
  "paragraphs": ["...", "...", "...", "..."],
  "closing": "Sincerely,"
}
```

Writing rules. These are hard rules, and `render` enforces several of them:

- **Use only facts from `master_profile.yaml`.** Never add a skill, tool, employer, title, date,
  number or achievement that is not there. Select, reorder and reword to match the job, mirroring the
  job's terminology only where the candidate's experience genuinely matches it. Every number in the CV must
  appear in the profile; numbers in the cover letter must appear in the profile or the job
  description.
- Skill rows: keep the same labels as the profile, put the job's matching skills first in each row,
  and drop a row only if nothing in it is relevant (keep at least 4 rows). Items must be spelled as in
  the profile.
- Experience: every role in the profile always appears, in profile order (the template enforces
  this). Use `cv_bullets` on each experience/project entry when the profile sets it (e.g. `3-5`);
  otherwise 3–5 bullets for the most recent role and 1–3 for older ones (1–6 is the hard limit).
  Lead with the bullets most relevant to the job. Keep each bullet to 2 lines or less.
- Cover letter: 4–5 paragraphs, about 280–400 words in the body, in the style of `cover_letter_style`
  in the profile if set.
  **Never pad to reach a length.** A shorter letter in which every sentence is specific and true is
  better than a longer one. Do not add filler, generic enthusiasm, or claims about how the candidate works
  (e.g. "I regularly presented to stakeholders") unless `master_profile.yaml` says so. Structure:
  1. Hook: what the company does and the specific problem this role solves (from the JD/company
     site), and why the candidate's background fits.
  2. Evidence from the most relevant experience, matched to the job's must-haves, with the real
     numbers from the profile's `facts`.
  3. A second angle: another role or a project from the profile that fits a different part of the job.
  4. Logistics from `personal` (location, work authorization, availability, visa sponsorship) and
     `languages`, and a wish to discuss the role.
  5. A one-line thank-you.
- English only, unless `languages.german_applications` is true and the posting is in German.
- No invented company facts: anything you say about the company must come from the posting or the
  company's own website.

Render and validate:

```bash
python3 scripts/pipeline.py render --uid <uid> --cv out/$RUN_ID/<uid>/cv.json \
  --cl out/$RUN_ID/<uid>/cl.json --jd out/$RUN_ID/<uid>/jd.md
```

If it prints `VALIDATION FAILED` or `LAYOUT FAILED`, fix the JSON exactly as the messages say and
render again (up to 3 attempts). If it still fails, run
`python3 scripts/pipeline.py fail --uid <uid> --reason "<last error>"` and move to the next job.

Then upload (this also marks the job done in the database):

```bash
python3 scripts/pipeline.py upload --uid <uid>
```

Files land in R2 at `<R2_BUCKET>/<R2_PREFIX>/<uid>/` (default prefix `jobautomationdocs`):
`<Your_Name>_CV.pdf`, `<Your_Name>_CoverLetter.pdf`, `job_description.md`, and the two content JSONs.

## 4. CSV of this run's new jobs

```bash
python3 scripts/pipeline.py export-csv --run-id $RUN_ID
```

This writes `job-search-automation-documents/jobautomationdocs/new_jobs_<RUN_ID>.csv` (newly found jobs only,
sorted by match score, with apply links and document paths). If there were no new jobs it writes
nothing, which is fine.

## 5. Summary

Tracker step: `summary`. Write the summary below to `out/$RUN_ID/summary.md`, record the end of the
run, then end with the same summary as your final message:

```bash
python3 scripts/pipeline.py run-finish --run-id $RUN_ID \
  --stats out/$RUN_ID/run_stats.json --summary-file out/$RUN_ID/summary.md
```

`run-finish` fills in new / refreshed / rejected jobs and documents done / not produced from the
database itself, and sets the status: `succeeded`, or `partial` if any document was not produced.

The summary: run id; searches run (and the budget) and postings found per source;
if under 90% of the budget, why; postings assessed;
eligible; new vs already known; jobs `merge` rejected and why; documents done / failed (with reasons);
sources that failed; the CSV path; jobs flagged `CHECK:` and why; and any judgment calls on
ambiguous postings.
