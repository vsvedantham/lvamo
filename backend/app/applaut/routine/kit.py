"""The routine setup kit: everything a user needs to run their own Claude
routine that Applaut can read (docs/applaut/JOB_ENGINES_DESIGN.md §6.2, §6.7).

Static files (prompt, pipeline, templates, fonts) live in `setup_kit/`,
generalised from vsvedantham/job-search-automation (contract v1: the
jobsearchautomationresults and run_tracker tables, five files per job in R2).
The profile and search config are generated from the user's Applaut profile;
anything Applaut doesn't know is left as a TODO, never invented."""
from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from app.applaut.models.profile import Profile
from app.applaut.models.user import User

KIT_DIR = Path(__file__).parent / "setup_kit"
ROOT = "applaut-routine"
KIT_FILENAME = "applaut-routine-kit.zip"

READ_ONLY_SQL = """-- Run in Neon's SQL editor as the database owner (the role your routine uses),
-- after replacing the password. Use a long random one: `openssl rand -hex 24`.
CREATE ROLE applaut_reader WITH LOGIN PASSWORD '<a long random password>';
GRANT CONNECT ON DATABASE neondb TO applaut_reader;
GRANT USAGE ON SCHEMA public TO applaut_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO applaut_reader;
-- Tables the routine creates later (its first run creates both) are readable too:
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO applaut_reader;
"""

WORK_MODES = {"remote": ["remote"], "hybrid": ["hybrid", "remote"], "onsite": ["onsite"],
              "any": ["onsite", "hybrid", "remote"]}


def _q(value) -> str:
    """A YAML scalar (JSON strings are valid YAML)."""
    return json.dumps(value, ensure_ascii=False)


def _list(items: list[str], indent: str = "  ") -> str:
    return "\n".join(f"{indent}- {_q(i)}" for i in items) if items else f"{indent}[]"


def master_profile_yaml(user: User, profile: Profile) -> str:
    skills = [s for s in (profile.skills or []) if s.strip()]
    remote = getattr(profile.remote_preference, "value", profile.remote_preference) or "any"
    return f"""# The ONLY source of facts for your CVs and cover letters. The routine may select, reorder and
# reword these, never add to them: `pipeline.py render` rejects skills and numbers that aren't here.
# Applaut filled in what it knows from your profile; replace every TODO with your real details.
# Generated {datetime.now(timezone.utc):%Y-%m-%d}.

personal:
  name: {_q(user.name or "TODO Your Name")}        # also used for file names: Your_Name_CV.pdf
  location: "TODO City, Country"
  phone: "TODO +49 …"
  email: {_q(user.email)}
  linkedin_url: "TODO https://www.linkedin.com/in/…"
  linkedin_display: "TODO linkedin.com/in/…"
  github_url: "TODO https://github.com/…"
  github_display: "TODO github.com/…"
  work_authorization: "TODO e.g. EU citizen / work permit type"
  work_authorization_short: "TODO"
  availability: "TODO e.g. Available from 1 December"
  availability_short: "TODO"
  visa_sponsorship_needed: false
  # photo: assets/photo.jpg      # optional: put a square photo in templates/assets/

default_headline: "TODO one line, e.g. 'Data Engineer with N years in …'"
default_cover_tagline: "TODO e.g. 'Data Engineer | Python · SQL · Spark'"
years_experience: {profile.total_experience_years if profile.total_experience_years is not None else '"TODO"'}

# Skill rows shown on the CV: label -> items. Spell items the way you want them printed.
skills:
  Skills:
{_list(skills, "    ")}
additional_skills: []          # skills you have that don't need their own row
skill_aliases: {{}}            # e.g. {{PySpark: [Spark], "Azure Data Factory": [ADF]}}

# Every role you have had, newest first. `facts` are the only statements the CV may use:
# put real numbers here (the fact check rejects numbers that appear nowhere in this file).
experience:
  - id: role1                  # short id, used by the routine to tailor bullets
    title: "TODO Job title"
    company: "TODO Company"
    location: "TODO City, Country"
    start: "TODO Mon YYYY"
    end: "Present"
    # project: "optional one-line project description"
    cv_bullets: "3-5"
    facts:
      - "TODO What you did and its result, with real numbers"
    technologies: []

projects: []                   # same shape: id, name, subtitle, start, end, facts, technologies

certifications: []             # - {{status: "2024", name: "…", detail: "…"}}
education:
  - period: "TODO YYYY – YYYY"
    degree: "TODO Degree"
    school: "TODO University, Country"

languages:
  english: "TODO e.g. C1"
  german: "TODO e.g. A2"
  german_max_required: B1      # skip jobs needing more German than this
  german_applications: false   # write German letters for German postings

preferences:
  role_level: [junior, mid, senior]
  work_modes: {_q(WORK_MODES.get(str(remote), WORK_MODES["any"]))}
  locations: {_q(list(profile.target_countries or []))}
  employment_types: {_q([getattr(e, "value", e) for e in (profile.employment_types or [])])}
  # Your Applaut profile's languages: {_q(list(profile.languages or []))}
"""


def search_config_yaml(profile: Profile) -> str:
    roles = [r for r in (profile.target_roles or []) if r.strip()] or ["TODO your target role"]
    skills = [s for s in (profile.skills or []) if s.strip()][:15]
    tmpl = (KIT_DIR / "config" / "search_config.yaml.tmpl").read_text(encoding="utf-8")
    return (tmpl
            .replace("{{GENERATED_ON}}", f"{datetime.now(timezone.utc):%Y-%m-%d}")
            .replace("{{ROLE_FAMILIES}}", _list(roles))
            .replace("{{SKILL_TERMS}}", _list(skills))
            .replace("{{SEARCH_TERMS_DE}}", _list([f"{r} (m/w/d)" for r in roles])))


CLAUDE_MD = """# applaut-routine

Your own job search, run twice a day by a Claude Code cloud routine. It writes jobs to your Neon
Postgres and CVs / cover letters to your Cloudflare R2 bucket; Applaut reads both (read-only) and
shows them in your Applaut account.

## Layout

- `ROUTINE_PROMPT.md`: the full run procedure. The routine follows it step by step.
- `profile/master_profile.yaml`: the only source of facts for CVs and cover letters.
- `config/search_config.yaml`: role families, search terms, locations, limits, sources.
- `templates/`: `cv.html.j2` and `cover_letter.html.j2` (layout of the PDFs). Never edit them during a run.
- `scripts/pipeline.py`: deterministic steps (UIDs, DB merge, rendering with fact checks, R2 upload,
  run tracking, CSV). `python3 scripts/pipeline.py -h` lists commands.
- `scripts/setup.sh`: installs dependencies; safe to re-run.

## Credentials (environment variables, never in files)

- `JOBSEARCH_DB_URL`: your Neon connection string (the owner role, which can write). Cloud sessions
  only have an HTTPS proxy, so for `*.neon.tech` URLs `pipeline.py` talks to Neon over HTTPS.
  `JOBSEARCH_DB_TRANSPORT=tcp` forces a normal connection locally.
- `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`; optional `R2_PREFIX`
  (default `jobautomationdocs`; one folder per job UID).

Never print, log or commit these values.

## Rules

- Never fabricate experience. `pipeline.py render` rejects skills and numbers that are not in the profile.
- Never log in to LinkedIn, StepStone, Indeed or Xing, and never submit applications.
- Don't commit or push from routine runs.
- `application_status` in the DB belongs to the user; never change it.
"""

SETUP_PROMPT = """Set up my twice-daily job search as a Claude Code cloud routine. Everything is in
`applaut-routine-kit.zip` (look in ~/Downloads). Do the following yourself, in order, and only stop
to ask me if you're truly blocked.

1. Unzip it to `~/applaut-routine` and read `README.md`, `CLAUDE.md`, `ROUTINE_PROMPT.md` and
   `python3 scripts/pipeline.py -h`.
2. Help me finish `profile/master_profile.yaml`: ask me for each TODO (or read my CV if I give you
   the file). Never invent a fact, number or skill. Review `config/search_config.yaml` with me.
3. Credentials: ask me for my Neon connection string (owner role) and my R2 read & write key
   (account id, key id, secret, bucket). Save them to `~/.job-search-automation.env` (chmod 600) and
   export them in your shell. Never write them into the repo.
4. Local test: `bash scripts/setup.sh && python3 scripts/pipeline.py selftest` must show render, db
   and r2 as OK. Show me `out/selftest/*_CV_sample.pdf` and `*_CoverLetter_sample.pdf`, then delete `out/`.
5. GitHub: create a PRIVATE repo `applaut-routine` on my account (`gh`), commit everything and push
   to `main`. Confirm no credential appears anywhere in the repo.
6. Create the cloud routine (claude.ai/code/routines, or `/schedule`):
   - Repository: `applaut-routine`; model: the strongest available
   - Schedule: cron `7 6,18 * * *` in UTC (or what I ask for); note it, Applaut needs the same schedule
   - Environment: network access Full; environment variables from step 3
   - Instructions (paste exactly):
     > Follow ROUTINE_PROMPT.md in the repository root exactly, from step 0 to step 5. Work fully
     > autonomously: never ask questions, never commit or push, never log in to job sites or submit
     > applications. Finish with the summary described in step 5.
   For anything you can't set up yourself, give me click-by-click steps, wait for "done", continue.
7. Test run: set `max_new_jobs_per_run: 2`, push, "Run now", wait for it to finish, and check the
   rows in Neon and the files in R2. Then set it back and push.
8. Walk me through README.md section "Connect Applaut" (read-only Neon role and R2 key).
"""


def readme(user: User) -> str:
    return f"""# Your own Claude routine for Applaut

This kit runs an AI job search in **your own Claude account**, twice a day. Each run searches job
sites, reads every posting against your profile, keeps the ones you're eligible for, and writes a
tailored CV and cover letter (PDF) for each. Results go to **your** Neon database and Cloudflare R2
bucket; Applaut reads them with read-only keys and shows them under Opportunities, an hour after
each run.

**Time:** about 1½–2 hours the first time (≈45 min if you know GitHub, Neon and Cloudflare).
**Cost:** free in Applaut; the AI runs on your Claude plan.

Shortcut: give `SETUP_PROMPT.md` to Claude Code on your computer and it does most of the steps
below with you.

## 1. What you need
- A paid Claude plan with routines (claude.ai/code/routines)
- GitHub, Neon (neon.tech) and Cloudflare accounts (Cloudflare may ask for a card to enable R2,
  even on the free tier)

## 2. Your profile (20–40 min)
- `profile/master_profile.yaml`: Applaut pre-filled your name, email, skills and preferences.
  Replace every `TODO`. **Facts** are the only things your CV may say: put real numbers in them.
- `config/search_config.yaml`: the roles and terms to search for (from your Applaut profile). The
  sources are for jobs in Germany; change them if you search elsewhere.
- Optional photo: `templates/assets/photo.jpg` and `personal.photo: assets/photo.jpg`.

## 3. Database (Neon, 10 min)
1. Create a Neon project (any region in the EU is fine). Copy its connection string (the owner
   role): this is `JOBSEARCH_DB_URL` for the routine. The routine creates its tables itself.
2. For Applaut, create a **read-only** role: run `sql/applaut_reader.sql` in Neon's SQL editor.

## 4. File storage (Cloudflare R2, 10 min)
1. R2 → Create bucket (e.g. `job-search-automation-documents`).
2. Manage API tokens → **Object Read & Write**, this bucket only → for the routine.
3. Manage API tokens → **Object Read only**, this bucket only → for Applaut.
   Note the Account ID (R2 overview page), both key ids and secrets (shown once).

## 5. GitHub + the routine (15 min)
1. Create a **private** repository, add this folder's contents, push.
2. claude.ai/code/routines → New routine → your repository, the strongest model, schedule
   `7 6,18 * * *` (UTC), network access **Full**, environment variables:
   `JOBSEARCH_DB_URL`, `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`
   (the read & write key).
3. Instructions:
   > Follow ROUTINE_PROMPT.md in the repository root exactly, from step 0 to step 5. Work fully
   > autonomously: never ask questions, never commit or push, never log in to job sites or submit
   > applications. Finish with the summary described in step 5.
4. Press **Run now** for a first run (about 15 minutes). Tip: set `max_new_jobs_per_run: 2` in
   `config/search_config.yaml` for this first test.

## 6. Connect Applaut (5 min)
Applaut → **Settings → Job engine → Your Claude routine**: paste the read-only Neon connection
string (role `applaut_reader`), the Account ID, bucket, folder `jobautomationdocs`, the read-only
key id and secret, your routine's link, and the same schedule → **Test connection** → **Save and
connect**. The first sync starts within minutes.

## 7. Optional: documents on your Mac
`scripts/sync_to_mac.sh` copies new CVs and cover letters from R2 to `~/JobSearchDocuments`
(one folder per job; needs `rclone` from Homebrew and `~/.job-search-automation.env` with the R2
values). Run it by hand, or every 15 minutes with launchd. In Applaut, **Copy folder path** on a
job copies that job's folder; paste it in Finder with ⇧⌘G.

Kit generated for {user.email} on {datetime.now(timezone.utc):%Y-%m-%d}.
Fonts: Carlito (SIL Open Font License), Roboto (Apache License 2.0).
"""


def _static_files() -> list[tuple[str, Path]]:
    out = []
    for path in sorted(KIT_DIR.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".tmpl":
            continue
        rel = path.relative_to(KIT_DIR).as_posix()
        out.append((".gitignore" if rel == "gitignore" else rel, path))
    return out


def build_setup_kit(user: User, profile: Profile) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for rel, path in _static_files():
            info = zipfile.ZipInfo(f"{ROOT}/{rel}", date_time=(2026, 10, 18, 0, 0, 0))
            info.external_attr = (0o755 if rel.endswith(".sh") else 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, path.read_bytes())
        generated = {
            "README.md": readme(user),
            "CLAUDE.md": CLAUDE_MD,
            "SETUP_PROMPT.md": SETUP_PROMPT,
            "profile/master_profile.yaml": master_profile_yaml(user, profile),
            "config/search_config.yaml": search_config_yaml(profile),
            "sql/applaut_reader.sql": READ_ONLY_SQL,
            "templates/assets/.keep": "",
        }
        for rel, text in generated.items():
            z.writestr(f"{ROOT}/{rel}", text)
    return buf.getvalue()
