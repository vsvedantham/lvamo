#!/usr/bin/env python3
"""Job search automation pipeline.

The deterministic half of the routine. Claude does the judgment work (finding
jobs, deciding eligibility, writing tailored content); this script does
everything that must be exact: UIDs, the database merge, rendering the
documents in the fixed template, fact checks, R2 uploads and the CSV.

Commands (run `python scripts/pipeline.py <cmd> -h` for options):
  new-run-id   print a run id (YYYYMMDD_HHMM, Europe/Berlin)
  selftest     check DB, R2 and rendering; run this first when anything breaks
  init-db      create the results table if it does not exist
  known        list jobs already in the DB (so a run can skip re-assessing them)
  run-start    record a run as running in run_tracker (marks stale running runs failed)
  run-step     record the step a run is on
  run-finish   record a run's end: status, counts, summary
  merge        merge a run's jobs into the DB, write the to-generate list
               (rejects jobs where neither link opens the specific posting)
  render       validate tailored content and render CV + cover letter PDFs
  upload       upload a job's documents to R2 and mark it done
  fail         mark a job's document generation as failed
  export-csv   write and upload the CSV of jobs first found in a run
  sample       render the untailored CV/letter for a visual check

Environment:
  JOBSEARCH_DB_URL      SQLAlchemy URL of the job search database (Neon)
  R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY
  R2_BUCKET             default: job-search-automation-documents
  R2_PREFIX             default: jobautomationdocs
  R2_ENDPOINT           optional override of the R2 S3 endpoint
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"
OUT = ROOT / "out"
TABLE = "jobsearchautomationresults"
RUN_TABLE = "run_tracker"
RUN_STEPS = ["setup", "search", "assess", "merge", "documents", "export", "summary"]
RUN_STATUSES = ["running", "succeeded", "partial", "failed"]
STALE_RUN_HOURS = 6
BERLIN = ZoneInfo("Europe/Berlin")
MAX_DOC_ATTEMPTS = 3

JOB_FIELDS = [
    "company", "role_title", "role_family", "location", "city", "requisition_id", "work_mode",
    "seniority", "german_required", "employment_type", "match_score", "matched_skills",
    "missing_skills", "salary_range", "posted_date", "deadline", "source", "jd_url",
    "application_url", "notes",
]
REFRESHABLE = ["application_url", "match_score", "salary_range", "notes", "deadline"]


# ----------------------------------------------------------------------------- helpers

def die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def load_yaml(rel: str) -> dict:
    return yaml.safe_load((ROOT / rel).read_text(encoding="utf-8"))


def profile() -> dict:
    return load_yaml("profile/master_profile.yaml")


def file_stem() -> str:
    """Document file names start with your name: <First_Last>_CV.pdf."""
    name = (profile().get("personal") or {}).get("name") or "Candidate"
    return "_".join(slug(name).split("-")).title() or "Candidate"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


LEGAL_SUFFIXES = [
    "gmbh & co. kgaa", "gmbh & co. kg", "gmbh & co kg", "se & co. kgaa", "ag & co. kg", "ug (haftungsbeschränkt)",
    "gmbh", "ggmbh", "mbh", "ag", "se", "kgaa", "kg", "ohg", "ug", "e.v.", "ev", "inc.", "inc", "ltd.", "ltd",
    "llc", "plc", "b.v.", "bv", "n.v.", "nv", "s.a.", "sa", "corp.", "corp", "co.", "limited", "group",
]


def slug(text: str) -> str:
    text = (text or "").strip().lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(a, b)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")


def norm_company(name: str) -> str:
    n = (name or "").strip().lower()
    changed = True
    while changed:
        changed = False
        for suf in LEGAL_SUFFIXES:
            if n.endswith(" " + suf) or n == suf:
                n = n[: -len(suf)].rstrip(" ,-")
                changed = True
    return slug(n) or slug(name)


def norm_role(title: str) -> str:
    t = re.sub(r"\((?:[mwfdx]\s*/\s*){1,3}[mwfdx]\)|\b(?:m/w/d|w/m/d|m/f/d|f/m/d|m/w/x|all genders?)\b", " ", title or "", flags=re.I)
    t = re.sub(r"[\(\)\[\]*]", " ", t)
    return slug(t)


def norm_city(job: dict) -> str:
    mode = (job.get("work_mode") or "").lower()
    city = job.get("city") or (job.get("location") or "").split(",")[0]
    if mode == "remote" and (not city or "remote" in city.lower()):
        return "remote"
    return slug(city) or "unknown"


def make_uid(job: dict) -> str:
    parts = [norm_company(job["company"]), norm_role(job["role_title"]), norm_city(job)]
    req = slug(str(job.get("requisition_id") or ""))
    if req:
        parts.append(req)
    return "__".join(parts)[:120].strip("-_")


# ----------------------------------------------------------------------------- database

class _NeonResult:
    def __init__(self, data: dict):
        int8 = {f["name"] for f in data.get("fields", []) if f.get("dataTypeID") == 20}
        self._rows = [{k: (int(v) if k in int8 and v is not None else v) for k, v in r.items()}
                      for r in data.get("rows", [])]
        self.rowcount = data.get("rowCount") or 0

    def __iter__(self):
        return (tuple(r.values()) for r in self._rows)

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)

    def scalar(self):
        return next(iter(self._rows[0].values())) if self._rows else None


class _NeonConn:
    def __init__(self, eng: "NeonHTTPEngine"):
        self.eng = eng

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, stmt) -> _NeonResult:
        compiled = stmt.compile(dialect=self.eng.dialect, compile_kwargs={"render_postcompile": True})
        params = [compiled.params[name] for name in (getattr(compiled, "positiontup", None) or [])]
        params = [p.isoformat() if isinstance(p, datetime) else p for p in params]
        return _NeonResult(self.eng.query(str(compiled), params))


class NeonHTTPEngine:
    """Runs SQLAlchemy Core statements against Neon over HTTPS (POST https://<host>/sql).

    Cloud routine sessions only have an HTTPS proxy, so a normal Postgres (TCP) connection
    cannot get out. Each statement runs in its own transaction (autocommit).
    """

    def __init__(self, url: str):
        import ssl
        from urllib.parse import urlsplit
        from sqlalchemy.dialects import postgresql
        self.url = url
        self.endpoint = f"https://{urlsplit(url).hostname}/sql"
        self.dialect = postgresql.dialect(paramstyle="numeric_dollar")
        self.ssl = ssl.create_default_context()
        for ca in (os.environ.get("SSL_CERT_FILE"), os.environ.get("REQUESTS_CA_BUNDLE"),
                   os.environ.get("NODE_EXTRA_CA_CERTS"), "/root/.ccr/ca-bundle.crt"):
            if ca and os.path.isfile(ca):
                self.ssl.load_verify_locations(ca)

    def query(self, sql: str, params: list) -> dict:
        import urllib.error
        import urllib.request
        req = urllib.request.Request(
            self.endpoint, method="POST", data=json.dumps({"query": sql, "params": params}).encode(),
            headers={"Content-Type": "application/json", "Neon-Connection-String": self.url})
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=self.ssl))
        try:
            with opener.open(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read()).get("message")
            except Exception:  # noqa: BLE001
                msg = None
            raise RuntimeError(f"Neon HTTP {e.code}: {msg or e.reason}") from None
        except urllib.error.URLError as e:
            raise RuntimeError(f"Neon HTTP request failed: {e.reason}") from None

    def connect(self) -> _NeonConn:
        return _NeonConn(self)

    begin = connect


def ensure_table(eng, t) -> None:
    if isinstance(eng, NeonHTTPEngine):
        from sqlalchemy.schema import CreateTable
        with eng.begin() as conn:
            conn.execute(CreateTable(t, if_not_exists=True))
    else:
        t.metadata.create_all(eng)


def engine():
    url = os.environ.get("JOBSEARCH_DB_URL")
    if not url:
        die("JOBSEARCH_DB_URL is not set")
    from urllib.parse import urlsplit
    host = urlsplit(url).hostname or ""
    if host.endswith(".neon.tech") and os.environ.get("JOBSEARCH_DB_TRANSPORT", "https") == "https":
        return NeonHTTPEngine(url)
    from sqlalchemy import create_engine
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    if url.startswith("mysql://"):
        url = "mysql+pymysql://" + url[len("mysql://"):]
    return create_engine(url, pool_pre_ping=True)


def table(meta=None):
    from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Text
    meta = meta or MetaData()
    return Table(
        TABLE, meta,
        Column("uid", String(160), primary_key=True),
        Column("company", Text), Column("role_title", Text), Column("role_family", Text),
        Column("location", Text), Column("city", Text), Column("requisition_id", Text),
        Column("work_mode", Text), Column("seniority", Text), Column("german_required", Text),
        Column("employment_type", Text), Column("match_score", Integer),
        Column("matched_skills", Text), Column("missing_skills", Text), Column("salary_range", Text),
        Column("posted_date", Text), Column("deadline", Text), Column("source", Text),
        Column("jd_url", Text), Column("application_url", Text), Column("notes", Text),
        Column("first_seen_at", DateTime(timezone=True)), Column("last_seen_at", DateTime(timezone=True)),
        Column("first_seen_run_id", String(20)), Column("last_seen_run_id", String(20)),
        Column("times_seen", Integer, default=1),
        Column("docs_status", String(20), default="pending"), Column("docs_attempts", Integer, default=0),
        Column("docs_error", Text), Column("docs_path", Text),
        Column("application_status", String(30), default="new"),
    )


def cmd_init_db(_args) -> None:
    eng = engine()
    t = table()
    ensure_table(eng, t)
    print(f"table {TABLE} ready on {eng.dialect.name}{' (neon https)' if isinstance(eng, NeonHTTPEngine) else ''}")


GENERIC_PATH_PARTS = {
    "", "en", "de", "en-us", "en-gb", "de-de", "home", "index", "about", "company", "unternehmen",
    "careers", "career", "jobs", "job", "karriere", "stellenangebote", "stellen", "offene-stellen",
    "join-us", "joinus", "work-with-us", "openings", "vacancies", "positions", "search", "suche",
    "jobsuche", "jobboerse",
}
POSTING_QUERY_KEYS = {"id", "jobid", "job_id", "gh_jid", "jid", "refnr", "vacancyid", "postingid", "jobad"}


def is_specific_posting(url: str | None) -> bool:
    """True if the URL looks like one posting, not a homepage or a general careers/jobs page."""
    from urllib.parse import parse_qs, urlsplit
    if not url:
        return False
    u = urlsplit(url.strip())
    if u.scheme not in ("http", "https") or not u.netloc:
        return False
    parts = [p.lower().rsplit(".", 1)[0] for p in u.path.split("/") if p]
    if any(p not in GENERIC_PATH_PARTS for p in parts):
        return True
    return any(k.lower() in POSTING_QUERY_KEYS for k in parse_qs(u.query))


def clean_job(raw: dict) -> dict:
    job = {k: raw.get(k) for k in JOB_FIELDS}
    for k in ("matched_skills", "missing_skills"):
        if isinstance(job[k], list):
            job[k] = ", ".join(map(str, job[k]))
    if job["match_score"] is not None:
        job["match_score"] = int(round(float(job["match_score"])))
    explicit_app_url = bool(job.get("application_url"))
    if not explicit_app_url:
        job["application_url"] = job.get("jd_url")
    for req in ("company", "role_title", "jd_url"):
        if not job.get(req):
            raise ValueError(f"missing {req}: {raw}")
    job = {k: (v.strip() if isinstance(v, str) else v) for k, v in job.items()}
    if not (is_specific_posting(job["jd_url"]) or is_specific_posting(job["application_url"])):
        raise ValueError(f"no link opens the specific posting ({job['company']} / {job['role_title']}): "
                         f"jd_url={job['jd_url']} application_url={job['application_url']}")
    job["uid"] = make_uid(job)
    job["_explicit_app_url"] = explicit_app_url
    return job


def cmd_merge(args) -> None:
    from sqlalchemy import and_, or_, select
    jobs_raw = json.loads(Path(args.jobs).read_text(encoding="utf-8"))
    run_id = args.run_id
    by_uid: dict[str, dict] = {}
    rejected = []
    for raw in jobs_raw:
        try:
            job = clean_job(raw)
        except ValueError as e:
            rejected.append(str(e))
            continue
        prev = by_uid.get(job["uid"])
        if prev is None or sum(v is not None for v in job.values()) > sum(v is not None for v in prev.values()):
            if prev is not None and prev["_explicit_app_url"] and not job["_explicit_app_url"]:
                job["application_url"], job["_explicit_app_url"] = prev["application_url"], True
            by_uid[job["uid"]] = job

    eng = engine()
    t = table()
    ensure_table(eng, t)
    ts = now_utc()
    inserted, updated = [], []
    with eng.begin() as conn:
        existing = set()
        uids = list(by_uid)
        for i in range(0, len(uids), 500):
            existing |= {r[0] for r in conn.execute(select(t.c.uid).where(t.c.uid.in_(uids[i:i + 500])))}
        for uid, job in by_uid.items():
            if uid in existing:
                vals = {k: job[k] for k in REFRESHABLE if job.get(k) is not None}
                if not job["_explicit_app_url"]:
                    vals.pop("application_url", None)
                vals.update(last_seen_at=ts, last_seen_run_id=run_id, times_seen=t.c.times_seen + 1)
                conn.execute(t.update().where(t.c.uid == uid).values(**vals))
                updated.append(uid)
            else:
                conn.execute(t.insert().values(
                    **{k: v for k, v in job.items() if not k.startswith("_")}, first_seen_at=ts, last_seen_at=ts, first_seen_run_id=run_id,
                    last_seen_run_id=run_id, times_seen=1, docs_status="pending", docs_attempts=0,
                    application_status="new"))
                inserted.append(uid)
        todo = conn.execute(select(t).where(or_(
            t.c.first_seen_run_id == run_id,
            and_(t.c.docs_status.in_(["pending", "failed"]), t.c.docs_attempts < MAX_DOC_ATTEMPTS),
        ))).mappings().all()

    todo_list = [{k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in dict(r).items()}
                 for r in todo if r["docs_status"] != "done"]
    run_dir = OUT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "to_generate.json").write_text(json.dumps(todo_list, indent=2, ensure_ascii=False), encoding="utf-8")
    summary = {"run_id": run_id, "received": len(jobs_raw), "unique": len(by_uid), "inserted": len(inserted),
               "updated": len(updated), "to_generate": len(todo_list), "rejected": rejected,
               "to_generate_file": str(run_dir / "to_generate.json"),
               "to_generate_uids": [r["uid"] for r in todo_list]}
    (run_dir / "merge_result.json").write_text(json.dumps(
        {k: summary[k] for k in ("received", "unique", "inserted", "updated", "to_generate")}
        | {"rejected": len(rejected)}, indent=2), encoding="utf-8")
    try:
        tracker_update(run_id, eng=eng, current_step="merge", jobs_rejected=len(rejected), **job_counts(eng, run_id))
    except Exception as e:  # noqa: BLE001  (tracking must never break the merge)
        print(f"WARNING: run_tracker not updated: {e}", file=sys.stderr)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def set_docs_status(uid: str, status: str, error: str | None = None, path: str | None = None) -> None:
    eng = engine()
    t = table()
    with eng.begin() as conn:
        vals = {"docs_status": status, "docs_error": error}
        if path:
            vals["docs_path"] = path
        if status == "failed":
            vals["docs_attempts"] = t.c.docs_attempts + 1
        res = conn.execute(t.update().where(t.c.uid == uid).values(**vals))
        if res.rowcount == 0:
            die(f"uid not found in DB: {uid}")


def cmd_known(args) -> None:
    from sqlalchemy import select
    eng = engine()
    t = table()
    ensure_table(eng, t)
    cols = [t.c.uid, t.c.company, t.c.role_title, t.c.city, t.c.work_mode, t.c.requisition_id,
            t.c.jd_url, t.c.application_url, t.c.docs_status, t.c.last_seen_run_id]
    with eng.connect() as conn:
        rows = conn.execute(select(*cols).order_by(t.c.company)).mappings().all()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps([dict(r) for r in rows], indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"known_jobs": len(rows), "file": str(out)}))


def cmd_fail(args) -> None:
    set_docs_status(args.uid, "failed", error=args.reason[:2000])
    print(f"marked failed: {args.uid}")


# ----------------------------------------------------------------------------- R2

def r2():
    import boto3
    from botocore.config import Config
    missing = [k for k in ("R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY") if not os.environ.get(k)]
    endpoint = os.environ.get("R2_ENDPOINT")
    if not endpoint:
        if not os.environ.get("R2_ACCOUNT_ID"):
            missing.append("R2_ACCOUNT_ID")
        endpoint = f"https://{os.environ.get('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com"
    if missing:
        die("missing env vars: " + ", ".join(missing))
    client = boto3.client(
        "s3", endpoint_url=endpoint, region_name="auto",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4", retries={"max_attempts": 5, "mode": "standard"}),
    )
    return client, os.environ.get("R2_BUCKET", "job-search-automation-documents"), os.environ.get("R2_PREFIX", "jobautomationdocs").strip("/")


CONTENT_TYPES = {".pdf": "application/pdf", ".json": "application/json", ".md": "text/markdown; charset=utf-8",
                 ".csv": "text/csv; charset=utf-8"}


def put_verified(client, bucket: str, key: str, path: Path) -> None:
    data = path.read_bytes()
    client.put_object(Bucket=bucket, Key=key, Body=data,
                      ContentType=CONTENT_TYPES.get(path.suffix, "application/octet-stream"))
    head = client.head_object(Bucket=bucket, Key=key)
    if head["ContentLength"] != len(data):
        raise RuntimeError(f"size mismatch after upload: {key}")


def cmd_upload(args) -> None:
    doc_dir = OUT / "docs" / args.uid
    required = [f"{file_stem()}_CV.pdf", f"{file_stem()}_CoverLetter.pdf"]
    for name in required:
        if not (doc_dir / name).exists():
            die(f"{doc_dir / name} missing; run render first")
    client, bucket, prefix = r2()
    folder = f"{prefix}/{args.uid}/"
    try:
        for f in sorted(doc_dir.iterdir()):
            if f.is_file():
                put_verified(client, bucket, folder + f.name, f)
    except Exception as e:  # noqa: BLE001
        set_docs_status(args.uid, "failed", error=f"upload: {e}"[:2000])
        die(f"upload failed for {args.uid}: {e}")
    set_docs_status(args.uid, "done", path=folder)
    print(f"uploaded {args.uid} -> r2://{bucket}/{folder}")


# ----------------------------------------------------------------------------- rendering + fact guard

NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")


def profile_text(p: dict) -> str:
    return yaml.safe_dump(p, allow_unicode=True)


def allowed_skills(p: dict) -> set[str]:
    s = set()
    for items in p["skills"].values():
        s |= set(items)
    s |= set(p.get("additional_skills", []))
    for k, vals in p.get("skill_aliases", {}).items():
        s.add(k)
        s |= set(vals)
    for e in p["experience"] + p.get("projects", []):
        s |= set(e.get("technologies", []))
    return {x.strip().lower() for x in s}


def check_numbers(text: str, sources: str, where: str, errors: list) -> None:
    src_nums = set(NUM_RE.findall(sources))
    for n in NUM_RE.findall(text):
        if n not in src_nums:
            errors.append(f"{where}: number '{n}' does not appear in the profile (or JD) - possible fabrication")


def build_cv_context(p: dict, cv: dict, errors: list) -> dict:
    ptext = profile_text(p)
    skills_ok = allowed_skills(p)
    if not cv.get("headline"):
        errors.append("cv.headline missing")
    check_numbers(cv.get("headline", ""), ptext, "cv.headline", errors)

    rows = cv.get("skills") or [{"label": k, "items": v} for k, v in p["skills"].items()]
    for row in rows:
        for item in row.get("items", []):
            if item.strip().lower() not in skills_ok:
                errors.append(f"cv.skills: '{item}' is not in master_profile.yaml")

    tailored = {e["id"]: e for e in cv.get("experience", [])}
    unknown = set(tailored) - {e["id"] for e in p["experience"]}
    if unknown:
        errors.append(f"cv.experience: unknown ids {sorted(unknown)}")
    experience = []
    for e in p["experience"]:  # every real role always appears, in profile order
        t = tailored.get(e["id"], {})
        bullets = t.get("bullets") or e["facts"]
        if not 1 <= len(bullets) <= 6:
            errors.append(f"cv.experience[{e['id']}]: needs 1-6 bullets")
        for b in bullets:
            check_numbers(b, ptext, f"cv.experience[{e['id']}]", errors)
        tech = t.get("technologies") or e["technologies"]
        for x in tech:
            if x.strip().lower() not in skills_ok:
                errors.append(f"cv.experience[{e['id']}].technologies: '{x}' is not in master_profile.yaml")
        experience.append({**e, "bullets": bullets, "technologies": tech})

    tailored_p = {x["id"]: x for x in cv.get("projects", [])}
    projects = []
    for pr in p.get("projects", []):
        t = tailored_p.get(pr["id"], {})
        bullets = t.get("bullets") or pr["facts"]
        for b in bullets:
            check_numbers(b, ptext, f"cv.projects[{pr['id']}]", errors)
        projects.append({**pr, "bullets": bullets, "technologies": t.get("technologies") or pr["technologies"]})
    return {"p": p, "cv": {**cv, "skills": rows}, "experience": experience, "projects": projects}


def build_cl_context(p: dict, cl: dict, jd_text: str, errors: list) -> dict:
    for k in ("date", "recipient_lines", "subject", "salutation", "paragraphs"):
        if not cl.get(k):
            errors.append(f"cover_letter.{k} missing")
    cl.setdefault("tagline", p["default_cover_tagline"])
    cl.setdefault("closing", "Sincerely,")
    paras = cl.get("paragraphs") or []
    if not 3 <= len(paras) <= 6:
        errors.append("cover_letter.paragraphs: use 3-6 paragraphs")
    words = sum(len(x.split()) for x in paras)
    if words > 430:
        errors.append(f"cover_letter: {words} words in body, keep it under 430 so it fits one page")
    sources = profile_text(p) + "\n" + jd_text
    for i, para in enumerate(paras):
        check_numbers(para, sources, f"cover_letter.paragraphs[{i}]", errors)
    return {"p": p, "cl": cl}


def render_pdf(template: str, ctx: dict, out: Path) -> int:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
    from weasyprint import HTML
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]),
                      undefined=StrictUndefined)
    html = env.get_template(template).render(**ctx)
    doc = HTML(string=html, base_url=str(TEMPLATES)).render()
    doc.write_pdf(out)
    return len(doc.pages)


def cmd_render(args) -> None:
    p = profile()
    cv = json.loads(Path(args.cv).read_text(encoding="utf-8"))
    cl = json.loads(Path(args.cl).read_text(encoding="utf-8"))
    jd_text = Path(args.jd).read_text(encoding="utf-8") if args.jd else ""
    errors: list[str] = []
    cv_ctx = build_cv_context(p, cv, errors)
    cl_ctx = build_cl_context(p, cl, jd_text, errors)
    if errors:
        print("VALIDATION FAILED - fix the JSON and re-run render:", file=sys.stderr)
        for e in errors:
            print("  - " + e, file=sys.stderr)
        sys.exit(2)
    doc_dir = OUT / "docs" / args.uid
    doc_dir.mkdir(parents=True, exist_ok=True)
    cv_pages = render_pdf("cv.html.j2", cv_ctx, doc_dir / f"{file_stem()}_CV.pdf")
    cl_pages = render_pdf("cover_letter.html.j2", cl_ctx, doc_dir / f"{file_stem()}_CoverLetter.pdf")
    problems = []
    if cv_pages > 2:
        problems.append(f"CV is {cv_pages} pages; shorten bullets so it fits on 2")
    if cl_pages != 1:
        problems.append(f"cover letter is {cl_pages} pages; shorten it to fit on 1")
    if problems:
        print("LAYOUT FAILED - fix the JSON and re-run render:", file=sys.stderr)
        for e in problems:
            print("  - " + e, file=sys.stderr)
        sys.exit(3)
    (doc_dir / "cv_content.json").write_text(json.dumps(cv, indent=2, ensure_ascii=False), encoding="utf-8")
    (doc_dir / "cover_letter_content.json").write_text(json.dumps(cl, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.jd:
        (doc_dir / "job_description.md").write_text(jd_text, encoding="utf-8")
    print(f"rendered {args.uid}: CV {cv_pages}p, cover letter {cl_pages}p -> {doc_dir}")


def sample_content(p: dict) -> tuple[dict, dict]:
    """Untailored content for `sample` / `selftest`: built only from the profile."""
    cv = {"headline": p["default_headline"]}
    personal = p.get("personal") or {}
    first_role = (p.get("experience") or [{}])[0]
    cl = {
        "tagline": p["default_cover_tagline"],
        "date": datetime.now(BERLIN).strftime("%-d %B %Y"),
        "recipient_lines": ["Hiring Team", "Example Company"],
        "subject": "Re: Application for an example role",
        "salutation": "Dear Hiring Team,",
        "paragraphs": [
            "This is a layout sample. The routine replaces every paragraph with content written for the specific job.",
            f"My most recent role was {first_role.get('title', 'in my field')} at {first_role.get('company', 'my employer')}.",
            " ".join(x for x in (personal.get("work_authorization"), personal.get("availability")) if x)
            or "Logistics (location, work authorization, availability) come from master_profile.yaml.",
            "Thank you for your time and consideration.",
        ],
    }
    return cv, cl


def cmd_sample(args) -> None:
    p = profile()
    cv, cl = sample_content(p)
    errors: list[str] = []
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    a = render_pdf("cv.html.j2", build_cv_context(p, cv, errors), out / f"{file_stem()}_CV_sample.pdf")
    b = render_pdf("cover_letter.html.j2", build_cl_context(p, cl, "", errors), out / f"{file_stem()}_CoverLetter_sample.pdf")
    if errors:
        die("; ".join(errors))
    print(f"sample rendered: CV {a}p, cover letter {b}p -> {out}")


# ----------------------------------------------------------------------------- run tracker

RUN_DDL = """
CREATE TABLE IF NOT EXISTS run_tracker (
    run_id            text PRIMARY KEY,
    contract_version  integer NOT NULL DEFAULT 1,
    started_at        timestamptz NOT NULL,
    finished_at       timestamptz,
    status            text NOT NULL,
    current_step      text,
    error             text,
    searches_run      integer,
    search_budget     integer,
    postings_found    integer,
    postings_assessed integer,
    jobs_eligible     integer,
    jobs_new          integer,
    jobs_updated      integer,
    jobs_rejected     integer,
    docs_done         integer,
    docs_failed       integer,
    sources_failed    text,
    summary           text,
    updated_at        timestamptz NOT NULL DEFAULT now()
)"""
RUN_INT_FIELDS = ["searches_run", "postings_found", "postings_assessed", "jobs_eligible"]


def run_table(meta=None):
    from sqlalchemy import Column, DateTime, Integer, MetaData, Table, Text
    meta = meta or MetaData()
    ints = ["contract_version", "searches_run", "search_budget", "postings_found", "postings_assessed",
            "jobs_eligible", "jobs_new", "jobs_updated", "jobs_rejected", "docs_done", "docs_failed"]
    cols = [Column("run_id", Text, primary_key=True)]
    cols += [Column(c, Integer) for c in ints]
    cols += [Column(c, DateTime(timezone=True)) for c in ("started_at", "finished_at", "updated_at")]
    cols += [Column(c, Text) for c in ("status", "current_step", "error", "sources_failed", "summary")]
    return Table(RUN_TABLE, meta, *cols)


def ensure_run_table(eng) -> None:
    from sqlalchemy import text
    with eng.begin() as conn:
        conn.execute(text(RUN_DDL.replace("run_tracker", RUN_TABLE, 1)))


def tracker_update(run_id: str, eng=None, **vals) -> int:
    eng = eng or engine()
    t = run_table()
    vals["updated_at"] = now_utc()
    with eng.begin() as conn:
        return conn.execute(t.update().where(t.c.run_id == run_id).values(**vals)).rowcount


def tracker_update_quiet(run_id: str, **vals) -> None:
    """Best-effort tracker update from other commands; never breaks the run."""
    try:
        tracker_update(run_id, **vals)
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: run_tracker not updated: {e}", file=sys.stderr)


def job_counts(eng, run_id: str) -> dict:
    """New and refreshed jobs for a run, straight from the jobs table."""
    from sqlalchemy import and_, func, select
    t = table()
    with eng.connect() as conn:
        new = conn.execute(select(func.count()).select_from(t).where(t.c.first_seen_run_id == run_id)).scalar()
        upd = conn.execute(select(func.count()).select_from(t).where(and_(
            t.c.last_seen_run_id == run_id, t.c.first_seen_run_id != run_id))).scalar()
    return {"jobs_new": int(new or 0), "jobs_updated": int(upd or 0)}


def doc_counts(eng, run_id: str) -> dict:
    """Documents done vs not produced for the jobs this run had to generate."""
    from sqlalchemy import select
    t = table()
    f = OUT / run_id / "to_generate.json"
    with eng.connect() as conn:
        if f.exists():
            uids = [j["uid"] for j in json.loads(f.read_text(encoding="utf-8"))]
            rows = list(conn.execute(select(t.c.docs_status).where(t.c.uid.in_(uids)))) if uids else []
        else:
            rows = list(conn.execute(select(t.c.docs_status).where(t.c.first_seen_run_id == run_id)))
    done = sum(1 for r in rows if r[0] == "done")
    return {"docs_done": done, "docs_failed": len(rows) - done}


def cmd_run_start(args) -> None:
    from sqlalchemy import and_
    from sqlalchemy.dialects.postgresql import insert
    from datetime import timedelta
    eng = engine()
    ensure_table(eng, table())
    ensure_run_table(eng)
    t = run_table()
    ts = now_utc()
    budget = (load_yaml("config/search_config.yaml") or {}).get("max_searches_per_run")
    with eng.begin() as conn:
        stale = conn.execute(t.update().where(and_(
            t.c.status == "running", t.c.run_id != args.run_id,
            t.c.started_at < ts - timedelta(hours=STALE_RUN_HOURS),
        )).values(status="failed", updated_at=ts,
                  error=f"no completion recorded within {STALE_RUN_HOURS} h (session ended or crashed)")).rowcount
        row = {"run_id": args.run_id, "contract_version": 1, "started_at": ts, "status": "running",
               "current_step": "setup", "search_budget": budget, "updated_at": ts}
        stmt = insert(t).values(**row)
        conn.execute(stmt.on_conflict_do_update(index_elements=[t.c.run_id], set_={
            k: stmt.excluded[k] for k in ("started_at", "status", "current_step", "search_budget", "updated_at")
        } | {"finished_at": None, "error": None}))
    print(json.dumps({"run_id": args.run_id, "status": "running", "search_budget": budget,
                      "stale_runs_marked_failed": stale}))


def cmd_run_step(args) -> None:
    if not tracker_update(args.run_id, current_step=args.step):
        die(f"run {args.run_id} not in {RUN_TABLE}; call run-start first")
    print(json.dumps({"run_id": args.run_id, "current_step": args.step}))


def cmd_run_finish(args) -> None:
    eng = engine()
    stats = json.loads(Path(args.stats).read_text(encoding="utf-8")) if args.stats and Path(args.stats).exists() else {}
    vals = {k: int(stats[k]) for k in RUN_INT_FIELDS if stats.get(k) is not None}
    if stats.get("sources_failed"):
        sf = stats["sources_failed"]
        vals["sources_failed"] = "; ".join(sf) if isinstance(sf, list) else str(sf)
    for counts in (job_counts, doc_counts):
        try:
            vals |= counts(eng, args.run_id)
        except Exception as e:  # noqa: BLE001  (e.g. the run failed before the jobs table was reachable)
            print(f"WARNING: {counts.__name__} not computed: {e!r}", file=sys.stderr)
    mr = OUT / args.run_id / "merge_result.json"
    if mr.exists():
        vals["jobs_rejected"] = json.loads(mr.read_text(encoding="utf-8")).get("rejected")
    if args.summary_file and Path(args.summary_file).exists():
        vals["summary"] = Path(args.summary_file).read_text(encoding="utf-8").strip()
    if args.error:
        vals["error"] = args.error[:4000]
    status = args.status or ("failed" if args.error else "partial" if vals.get("docs_failed") else "succeeded")
    vals |= {"status": status, "finished_at": now_utc(), "current_step": args.step or ("summary" if status != "failed" else None)}
    if vals["current_step"] is None:
        vals.pop("current_step")
    if not tracker_update(args.run_id, eng=eng, **vals):
        die(f"run {args.run_id} not in {RUN_TABLE}; call run-start first")
    shown = {k: v for k, v in vals.items() if k not in ("summary", "finished_at")}
    print(json.dumps({"run_id": args.run_id, **shown, "summary_chars": len(vals.get("summary") or "")}, ensure_ascii=False))


# ----------------------------------------------------------------------------- CSV

CSV_COLUMNS = ["uid", "company", "role_title", "role_family", "location", "work_mode", "seniority",
               "german_required", "match_score", "matched_skills", "missing_skills", "salary_range",
               "posted_date", "deadline", "jd_url", "application_url", "cv_path", "cover_letter_path",
               "docs_status", "notes"]


def cmd_export_csv(args) -> None:
    from sqlalchemy import select
    eng = engine()
    t = table()
    tracker_update_quiet(args.run_id, current_step="export")
    with eng.connect() as conn:
        rows = conn.execute(select(t).where(t.c.first_seen_run_id == args.run_id)
                            .order_by(t.c.match_score.desc())).mappings().all()
    if not rows:
        print(json.dumps({"run_id": args.run_id, "new_jobs": 0, "csv": None}))
        return
    _, bucket, prefix = (None, os.environ.get("R2_BUCKET", "job-search-automation-documents"),
                         os.environ.get("R2_PREFIX", "jobautomationdocs").strip("/"))
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        d = dict(r)
        folder = f"{bucket}/{prefix}/{d['uid']}/"
        d["cv_path"] = folder + f"{file_stem()}_CV.pdf" if d["docs_status"] == "done" else ""
        d["cover_letter_path"] = folder + f"{file_stem()}_CoverLetter.pdf" if d["docs_status"] == "done" else ""
        w.writerow(d)
    path = OUT / args.run_id / f"new_jobs_{args.run_id}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("﻿" + buf.getvalue(), encoding="utf-8")
    if not args.no_upload:
        client, bucket, prefix = r2()
        put_verified(client, bucket, f"{prefix}/{path.name}", path)
    print(json.dumps({"run_id": args.run_id, "new_jobs": len(rows), "csv": f"{bucket}/{prefix}/{path.name}"}))


# ----------------------------------------------------------------------------- selftest

def cmd_selftest(args) -> None:
    ok = True
    try:
        cmd_sample(argparse.Namespace(out=str(OUT / "selftest")))
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        ok = False
        print(f"render: FAIL {e}")
    if not args.skip_db:
        try:
            from sqlalchemy import func, select
            eng = engine()
            t = table()
            ensure_table(eng, t)
            with eng.connect() as conn:
                n = conn.execute(select(func.count()).select_from(t)).scalar()
            print(f"db: OK ({eng.dialect.name}{' via neon https' if isinstance(eng, NeonHTTPEngine) else ''}, {TABLE} has {n} rows)")
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"db: FAIL {e}")
    if not args.skip_r2:
        try:
            client, bucket, prefix = r2()
            key = f"{prefix}/_selftest/ok.txt"
            client.put_object(Bucket=bucket, Key=key, Body=b"ok")
            client.head_object(Bucket=bucket, Key=key)
            client.delete_object(Bucket=bucket, Key=key)
            print(f"r2: OK (write/read/delete in {bucket}/{prefix}/)")
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"r2: FAIL {e}")
    sys.exit(0 if ok else 1)


# ----------------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("new-run-id").set_defaults(fn=lambda a: print(datetime.now(BERLIN).strftime("%Y%m%d_%H%M")))
    s = sub.add_parser("selftest")
    s.add_argument("--skip-db", action="store_true")
    s.add_argument("--skip-r2", action="store_true")
    s.set_defaults(fn=cmd_selftest)
    sub.add_parser("init-db").set_defaults(fn=cmd_init_db)
    s = sub.add_parser("known", help="list jobs already in the DB, so a run can skip re-assessing them")
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_known)
    s = sub.add_parser("run-start", help="record the run as running in run_tracker")
    s.add_argument("--run-id", required=True)
    s.set_defaults(fn=cmd_run_start)
    s = sub.add_parser("run-step", help="record the step the run is on")
    s.add_argument("--run-id", required=True)
    s.add_argument("--step", required=True, choices=RUN_STEPS)
    s.set_defaults(fn=cmd_run_step)
    s = sub.add_parser("run-finish", help="record the end of the run")
    s.add_argument("--run-id", required=True)
    s.add_argument("--status", choices=RUN_STATUSES[1:], help="default: failed if --error, partial if any "
                   "document was not produced, else succeeded")
    s.add_argument("--error", help="why the run failed or stopped")
    s.add_argument("--step", choices=RUN_STEPS, help="step to record (default: summary; for failures the step it stopped at)")
    s.add_argument("--stats", help="JSON with searches_run, postings_found, postings_assessed, jobs_eligible, sources_failed")
    s.add_argument("--summary-file", help="text file with the step-5 summary")
    s.set_defaults(fn=cmd_run_finish)
    s = sub.add_parser("merge")
    s.add_argument("--jobs", required=True, help="JSON list of eligible jobs found in this run")
    s.add_argument("--run-id", required=True)
    s.set_defaults(fn=cmd_merge)
    s = sub.add_parser("render")
    s.add_argument("--uid", required=True)
    s.add_argument("--cv", required=True, help="tailored CV content JSON")
    s.add_argument("--cl", required=True, help="tailored cover letter content JSON")
    s.add_argument("--jd", help="job description text file (saved alongside, used for the number check)")
    s.set_defaults(fn=cmd_render)
    s = sub.add_parser("upload")
    s.add_argument("--uid", required=True)
    s.set_defaults(fn=cmd_upload)
    s = sub.add_parser("fail")
    s.add_argument("--uid", required=True)
    s.add_argument("--reason", required=True)
    s.set_defaults(fn=cmd_fail)
    s = sub.add_parser("export-csv")
    s.add_argument("--run-id", required=True)
    s.add_argument("--no-upload", action="store_true")
    s.set_defaults(fn=cmd_export_csv)
    s = sub.add_parser("sample")
    s.add_argument("--out", default=str(OUT / "sample"))
    s.set_defaults(fn=cmd_sample)
    s = sub.add_parser("uid", help="print the UID for company/role/city (debugging)")
    s.add_argument("company")
    s.add_argument("role_title")
    s.add_argument("city")
    s.add_argument("--req")
    s.set_defaults(fn=lambda a: print(make_uid({"company": a.company, "role_title": a.role_title,
                                                 "city": a.city, "requisition_id": a.req})))
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
