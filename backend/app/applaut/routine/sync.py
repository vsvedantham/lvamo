"""Sync: copy a user's routine output into Applaut (docs/applaut/JOB_ENGINES_DESIGN.md §6.4).

- Reads (uid, last_seen_at, docs_status) for every job, then the full rows of
  the ones that are new or changed since Applaut last copied them.
- Each job becomes a private opportunity (source 'own_routine', external_id
  = uid), or is linked to the shared Applaut Basic posting with the same
  normalised apply URL, plus a job_assessments row (engine 'own_routine').
- For jobs with docs_status 'done' whose PDFs changed (R2 ETag), copies both
  PDFs into Applaut's R2 and adds generated_documents rows; older ones stop
  being current. job_description.md becomes the description; the content
  JSONs become the documents' text versions.
- A new job gets an application in pending_review (a review queue; nothing
  is ever submitted).
- One routine_syncs row, one audit-log entry, at most one notification.
Rows that disappear from the routine's database are kept and marked."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from urllib.parse import parse_qsl, urlencode, urlsplit

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.applaut.core import credentials
from app.applaut.discovery.location import resolve_country
from app.applaut.models.application import Application
from app.applaut.models.generated_document import GeneratedDocument
from app.applaut.models.job_assessment import JobAssessment
from app.applaut.models.opportunity import Opportunity
from app.applaut.models.profile import Profile
from app.applaut.models.routine import RoutineConnection, RoutineJob, RoutineSync
from app.applaut.routine import checks, source
from app.applaut.routine.source import (
    MAX_JOB_ROWS, NeonReader, R2Credentials, RoutineStorage, SourceError, StoredObject,
)
from app.config import settings
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

SOURCE = "own_routine"
ENGINE = "own_routine"
MAX_DOCS_PER_SYNC = 200       # §6.9
MAX_PDF_BYTES = 5_000_000     # §6.9
MAX_TEXT_BYTES = 1_000_000    # content JSONs and the job description
MAX_DESCRIPTION_CHARS = 200_000
TRACKING_PARAMS = {"gh_src", "source", "src", "ref", "referrer", "lever-source", "lever-origin", "trk", "trackingid"}
DOC_FILES = {
    "tailored_resume": ("_CV.pdf", "cv_content.json", "cv"),
    "cover_letter": ("_CoverLetter.pdf", "cover_letter_content.json", "cover_letter"),
}


class SyncBusy(Exception):
    """Another worker is syncing this user right now."""


class StorageNotConfigured(Exception):
    pass


async def store_file(key: str, data: bytes, content_type: str) -> None:
    """Write to Applaut's own (private) R2 bucket. Tests replace this."""
    if not settings.r2_bucket_name:
        raise StorageNotConfigured("Applaut's file storage isn't configured")
    from app.core.storage import upload_file
    await asyncio.to_thread(upload_file, key, data, content_type)


def r2_credentials(conn: RoutineConnection) -> R2Credentials:
    return R2Credentials(
        account_id=conn.r2_account_id, bucket=conn.r2_bucket, prefix=conn.r2_prefix.strip("/"),
        access_key_id=credentials.decrypt(conn.r2_access_key_id_enc), secret=credentials.decrypt(conn.r2_secret_enc),
    )


# ----------------------------------------------------------------------------- mapping

def normalise_url(url: str | None) -> str | None:
    """Scheme-less, lower-case host without www., no trailing slash, no
    fragment or tracking parameters: so the same posting matches."""
    if not url:
        return None
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    host = parts.hostname.lower().removeprefix("www.")
    query = sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                   if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS)
    path = parts.path.rstrip("/")
    return f"{host}{path}" + (f"?{urlencode(query)}" if query else "")


def safe_url(url) -> str | None:
    if not isinstance(url, str):
        return None
    url = url.strip()
    parts = urlsplit(url)
    if parts.scheme in ("http", "https") and parts.hostname and len(url) <= 2000:
        return url
    return None


def _json_safe(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _text(value, limit: int) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value[:limit] or None


def _split_skills(value) -> list[str]:
    if isinstance(value, list):
        items = value
    else:
        items = str(value or "").split(",")
    return [s.strip()[:100] for s in items if str(s).strip()][:50]


def _score(value) -> int | None:
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return None


WORK_MODES = {"remote": "remote", "hybrid": "hybrid", "onsite": "onsite", "on-site": "onsite", "on site": "onsite"}
EMPLOYMENT_TYPES = {"full-time": "full_time", "full_time": "full_time", "full time": "full_time",
                    "part-time": "part_time", "part_time": "part_time", "contract": "contract",
                    "freelance": "freelance", "internship": "internship"}


def _posted_at(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.strip()[:10]).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def opportunity_fields(row: dict) -> dict:
    location = _text(row.get("location"), 500) or _text(row.get("city"), 500)
    return {
        "title": _text(row.get("role_title"), 500) or "Untitled job",
        "company_name": _text(row.get("company"), 500) or "Unknown company",
        "location_raw": location,
        "country_code": resolve_country(location),
        "remote_option": WORK_MODES.get(str(row.get("work_mode") or "").strip().lower()),
        "employment_type": EMPLOYMENT_TYPES.get(str(row.get("employment_type") or "").strip().lower()),
        "application_url": safe_url(row.get("application_url")) or safe_url(row.get("jd_url")),
        "posted_at": _posted_at(row.get("posted_date")),
    }


def assessment_fields(row: dict) -> dict:
    notes = _text(row.get("notes"), 4000)
    flags = []
    if notes and notes.upper().startswith("CHECK:"):
        flags.append(notes.splitlines()[0][:300])
    return {
        "match_score": _score(row.get("match_score")),
        "matched_skills": _split_skills(row.get("matched_skills")),
        "missing_skills": _split_skills(row.get("missing_skills")),
        "german_required": _text(row.get("german_required"), 50),
        "seniority": _text(row.get("seniority"), 50),
        "notes": notes,
        "flags": flags,
        "model": "Claude (your routine)",
        "raw": _json_safe(row),
        "first_seen_at": row.get("first_seen_at") or datetime.now(timezone.utc),
        "last_seen_at": row.get("last_seen_at") or datetime.now(timezone.utc),
        "times_seen": int(row.get("times_seen") or 1),
    }


def _lines(value) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [line for v in value for line in _lines(v)]
    if isinstance(value, dict):
        return [line for v in value.values() for line in _lines(v)]
    return []


def cv_text(content: dict) -> str:
    """A plain-text version of cv_content.json (for copy and search)."""
    out = []
    if content.get("headline"):
        out += [str(content["headline"]).strip(), ""]
    for row in content.get("skills") or []:
        if isinstance(row, dict) and row.get("items"):
            out.append(f"{row.get('label', 'Skills')}: {', '.join(map(str, row['items']))}")
    for section in ("experience", "projects"):
        entries = [e for e in (content.get(section) or []) if isinstance(e, dict)]
        if entries:
            out += ["", section.capitalize()]
        for e in entries:
            out.append(str(e.get("title") or e.get("id") or "").strip())
            out += [f"• {b}" for b in _lines(e.get("bullets"))]
            if e.get("technologies"):
                out.append("Technologies: " + ", ".join(map(str, e["technologies"])))
    known = {"headline", "skills", "experience", "projects"}
    for key, value in content.items():
        if key not in known:
            extra = _lines(value)
            if extra:
                out += ["", key.replace("_", " ").capitalize(), *extra]
    return "\n".join(out).strip()


def cover_letter_text(content: dict) -> str:
    out = []
    for key in ("date",):
        if content.get(key):
            out.append(str(content[key]))
    out += _lines(content.get("recipient_lines"))
    if content.get("subject"):
        out += ["", str(content["subject"])]
    if content.get("salutation"):
        out += ["", str(content["salutation"])]
    for para in _lines(content.get("paragraphs")):
        out += ["", para]
    if content.get("closing"):
        out += ["", str(content["closing"])]
    return "\n".join(out).strip()


# ----------------------------------------------------------------------------- the sync

def needs_sync(index_row: dict, known: RoutineJob | None) -> bool:
    if known is None or known.removed_at is not None:
        return True
    if known.source_last_seen_at != index_row.get("last_seen_at") or known.docs_status != index_row.get("docs_status"):
        return True
    return index_row.get("docs_status") == "done" and (known.cv_etag is None or known.cover_letter_etag is None)


class _Run:
    """State for one sync of one user."""

    def __init__(self, db: AsyncSession, conn: RoutineConnection, profile: Profile, record: RoutineSync,
                 storage: RoutineStorage):
        self.db, self.conn, self.profile, self.record, self.storage = db, conn, profile, record, storage
        self.docs_budget = MAX_DOCS_PER_SYNC
        self.new_with_docs = 0
        # Kept here, not on `record`: a job that fails rolls back its savepoint,
        # and that would expire whatever ORM objects it touched.
        self.counts = {"jobs_new": 0, "jobs_updated": 0, "docs_copied": 0, "docs_skipped": 0}
        self.problems: list[str] = []

    def problem(self, message: str) -> None:
        if len(self.problems) < 50:
            self.problems.append(message[:500])

    async def _shared_match(self, url: str | None) -> Opportunity | None:
        key = normalise_url(url)
        if key is None:
            return None
        host = key.split("/", 1)[0].split("?", 1)[0]
        candidates = await self.db.scalars(select(Opportunity).where(
            Opportunity.owner_user_id.is_(None), Opportunity.is_active == True,
            func.lower(Opportunity.application_url).contains(host, autoescape=True),
        ).limit(500))
        return next((o for o in candidates if normalise_url(o.application_url) == key), None)

    async def _opportunity(self, row: dict, known: RoutineJob | None) -> tuple[Opportunity, bool]:
        fields = opportunity_fields(row)
        if known is not None:
            opp = await self.db.get(Opportunity, known.opportunity_id)
            if known.linked_to_shared:
                return opp, True
        else:
            shared = await self._shared_match(fields["application_url"]) or \
                await self._shared_match(safe_url(row.get("jd_url")))
            if shared is not None:
                return shared, True
            opp = await self.db.scalar(select(Opportunity).where(
                Opportunity.owner_user_id == self.conn.user_id, Opportunity.source == SOURCE,
                Opportunity.external_id == row["uid"],
            ))
        if opp is None:
            opp = Opportunity(owner_user_id=self.conn.user_id, source=SOURCE, external_id=row["uid"],
                              is_active=True, raw_data={})
            self.db.add(opp)
        for k, v in fields.items():
            setattr(opp, k, v)
        opp.is_active = True
        opp.raw_data = {"routine": _json_safe(row)}
        await self.db.flush()
        return opp, False

    async def _assessment(self, opp: Opportunity, row: dict) -> None:
        a = await self.db.scalar(select(JobAssessment).where(
            JobAssessment.profile_id == self.profile.id, JobAssessment.opportunity_id == opp.id,
            JobAssessment.engine == ENGINE,
        ))
        if a is None:
            a = JobAssessment(user_id=self.conn.user_id, profile_id=self.profile.id, opportunity_id=opp.id, engine=ENGINE)
            self.db.add(a)
        for k, v in assessment_fields(row).items():
            setattr(a, k, v)

    async def _get_json(self, obj: StoredObject | None) -> dict:
        if obj is None:
            return {}
        try:
            data = json.loads((await self.storage.get(obj.key, MAX_TEXT_BYTES)).decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except (SourceError, ValueError) as exc:
            self.problem(f"{obj.key.rsplit('/', 1)[-1]}: {exc}")
            return {}

    async def _copy_documents(self, opp: Opportunity, linked: bool, row: dict, known: RoutineJob,
                              application: Application | None) -> int:
        folder = (row.get("docs_path") or f"{self.conn.r2_prefix.strip('/')}/{row['uid']}/").strip("/") + "/"
        objects = await self.storage.list(folder, max_keys=50)
        by_name = {o.key[len(folder):]: o for o in objects}

        def find(suffix: str) -> StoredObject | None:
            return next((o for name, o in sorted(by_name.items()) if name.endswith(suffix) and "/" not in name), None)

        copied = 0
        jd = find("job_description.md")
        etag_attr = {"tailored_resume": "cv_etag", "cover_letter": "cover_letter_etag"}
        changed = [t for t, (suffix, _, _) in DOC_FILES.items()
                   if (pdf := find(suffix)) is not None and getattr(known, etag_attr[t]) != pdf.etag]
        missing = [t for t, (suffix, _, _) in DOC_FILES.items() if find(suffix) is None]
        for t in missing:
            self.problem(f"{row['uid']}: {DOC_FILES[t][0].lstrip('_')} not found in R2")

        if jd is not None and not linked and (changed or not opp.description):
            try:
                opp.description = (await self.storage.get(jd.key, MAX_TEXT_BYTES)).decode("utf-8", "replace")[:MAX_DESCRIPTION_CHARS]
            except SourceError as exc:
                self.problem(f"{row['uid']}: job description: {exc}")

        for doc_type in changed:
            if self.docs_budget <= 0:
                self.counts["docs_skipped"] += 1
                continue
            suffix, content_name, stem = DOC_FILES[doc_type]
            pdf = find(suffix)
            try:
                data = await self.storage.get(pdf.key, MAX_PDF_BYTES)
            except SourceError as exc:
                self.counts["docs_skipped"] += 1
                self.problem(f"{row['uid']}: {exc}")
                continue
            if not data.startswith(b"%PDF-"):
                self.counts["docs_skipped"] += 1
                self.problem(f"{row['uid']}: {pdf.key.rsplit('/', 1)[-1]} isn't a PDF; skipped")
                continue
            sha = hashlib.sha256(data).hexdigest()
            current = await self.db.scalar(select(GeneratedDocument).where(
                GeneratedDocument.user_id == self.conn.user_id, GeneratedDocument.opportunity_id == opp.id,
                GeneratedDocument.document_type == doc_type, GeneratedDocument.is_current == True,
                GeneratedDocument.content_sha256 == sha,
            ))
            if current is None:
                key = f"applaut/documents/{self.conn.user_id}/{opp.id}/{sha[:8]}/{stem}.pdf"
                try:
                    await store_file(key, data, "application/pdf")
                except StorageNotConfigured as exc:
                    # The job still syncs; its ETag isn't stored, so the next sync retries.
                    self.counts["docs_skipped"] += 1
                    self.problem(f"{row['uid']}: {exc}")
                    continue
                content = await self._get_json(find(content_name))
                body = cv_text(content) if doc_type == "tailored_resume" else cover_letter_text(content)
                previous = await self.db.scalars(select(GeneratedDocument).where(
                    GeneratedDocument.user_id == self.conn.user_id, GeneratedDocument.opportunity_id == opp.id,
                    GeneratedDocument.document_type == doc_type, GeneratedDocument.is_current == True,
                ))
                for doc in previous:
                    doc.is_current = False
                self.db.add(GeneratedDocument(
                    user_id=self.conn.user_id, profile_id=self.profile.id, opportunity_id=opp.id,
                    application_id=application.id if application else None, document_type=doc_type,
                    generation_mode="routine", content=body, file_name=pdf.key.rsplit("/", 1)[-1][:500],
                    r2_key=key, ai_model="Claude (your routine)", is_current=True, engine=ENGINE,
                    content_type="application/pdf", content_sha256=sha,
                ))
                self.docs_budget -= 1
                copied += 1
            setattr(known, etag_attr[doc_type], pdf.etag)
        return copied

    async def _application(self, opp: Opportunity, create: bool) -> Application | None:
        app = await self.db.scalar(select(Application).where(
            Application.user_id == self.conn.user_id, Application.opportunity_id == opp.id,
        ))
        if app is None and create:
            app = Application(user_id=self.conn.user_id, opportunity_id=opp.id, profile_id=self.profile.id,
                              status="pending_review")
            self.db.add(app)
            await self.db.flush()
        return app

    async def job(self, row: dict, known: RoutineJob | None) -> tuple[bool, int]:
        is_new = known is None
        opp, linked = await self._opportunity(row, known)
        if known is None:
            known = RoutineJob(user_id=self.conn.user_id, uid=row["uid"], opportunity_id=opp.id, linked_to_shared=linked)
            self.db.add(known)
        await self._assessment(opp, row)
        application = await self._application(opp, create=is_new)
        known.source_last_seen_at = row.get("last_seen_at")
        known.docs_status = _text(row.get("docs_status"), 20)
        known.docs_error = _text(row.get("docs_error"), 2000)
        known.removed_at = None
        known.last_synced_at = datetime.now(timezone.utc)
        copied = 0
        if known.docs_status == "done":
            copied = await self._copy_documents(opp, linked, row, known, application)
        elif known.docs_status == "failed" and known.docs_error:
            self.problem(f"{row['uid']}: documents failed in your routine: {known.docs_error[:300]}")
        return is_new, copied

    def count(self, is_new: bool, copied: int) -> None:
        self.counts["docs_copied"] += copied
        if is_new:
            self.counts["jobs_new"] += 1
            self.new_with_docs += 1 if copied else 0
        else:
            self.counts["jobs_updated"] += 1


async def _lock(lock_db: AsyncSession, user_id: uuid.UUID) -> bool:
    return bool(await lock_db.scalar(
        text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"applaut.routine_sync:{user_id}"},
    ))


async def sync_user(user_id: uuid.UUID, trigger: str = "scheduled", run_id: str | None = None) -> RoutineSync:
    """Run one sync for a user. Raises SyncBusy if one is already running,
    SourceError (after recording it) if their Neon/R2 can't be read."""
    async with AsyncSessionLocal() as lock_db:
        if not await _lock(lock_db, user_id):
            raise SyncBusy("A sync is already running")
        async with AsyncSessionLocal() as db:
            return await _sync_locked(db, user_id, trigger, run_id)


async def _sync_locked(db: AsyncSession, user_id: uuid.UUID, trigger: str, run_id: str | None) -> RoutineSync:
    conn = await db.scalar(select(RoutineConnection).where(RoutineConnection.user_id == user_id))
    profile = await db.scalar(select(Profile).where(Profile.user_id == user_id, Profile.is_active == True))
    if conn is None or profile is None:
        raise SourceError("No routine connection")
    record = RoutineSync(user_id=user_id, trigger=trigger, run_id=run_id, status="running",
                         started_at=datetime.now(timezone.utc), problems=[])
    db.add(record)
    await db.commit()

    try:
        async with NeonReader(checks.neon_url(conn)) as src:
            index, total = await src.job_index()
            known = {j.uid: j for j in await db.scalars(select(RoutineJob).where(RoutineJob.user_id == user_id))}
            todo = [r["uid"] for r in index if r.get("uid") and needs_sync(r, known.get(r["uid"]))]
            rows = await src.jobs(todo)
        storage = source.make_storage(r2_credentials(conn))
    except (SourceError, credentials.CredentialsUnavailable) as exc:
        # Raised while reading the user's Neon, before anything local changed.
        record.status, record.error, record.finished_at = "failed", str(exc)[:2000], datetime.now(timezone.utc)
        await db.commit()
        await checks.record_failure(db, conn, str(exc))
        await _finish(db, conn, record, run=None)
        raise SourceError(str(exc)) from None
    await checks.record_success(db, conn)

    await db.commit()

    run = _Run(db, conn, profile, record, storage)
    if total > MAX_JOB_ROWS:
        run.problem(f"Your routine has {total} jobs; Applaut reads the newest {MAX_JOB_ROWS}")
    for row in sorted(rows, key=lambda r: str(r["uid"])):
        try:
            async with db.begin_nested():
                is_new, copied = await run.job(row, known.get(row["uid"]))
            await db.commit()
            run.count(is_new, copied)
        except SourceError as exc:
            run.problem(f"{row['uid']}: {exc}")
        except Exception as exc:  # noqa: BLE001  (one bad row must not stop the others)
            logger.exception("Routine sync: job %s failed for user %s", row.get("uid"), user_id)
            run.problem(f"{row['uid']}: {type(exc).__name__}")

    removed = 0
    if total <= MAX_JOB_ROWS:
        seen = {r["uid"] for r in index}
        gone = await db.scalars(select(RoutineJob).where(
            RoutineJob.user_id == user_id, RoutineJob.removed_at.is_(None), RoutineJob.uid.notin_(list(seen) or [""]),
        ))
        for job in gone:
            job.removed_at = datetime.now(timezone.utc)
            removed += 1

    await db.refresh(record)
    for k, v in run.counts.items():
        setattr(record, k, v)
    record.jobs_removed = removed
    record.rows_read = len(rows)
    record.watermark = max((r["last_seen_at"] for r in index if r.get("last_seen_at")), default=None)
    record.problems = run.problems
    record.status = "partial" if run.problems else "succeeded"
    record.finished_at = datetime.now(timezone.utc)
    await db.commit()
    await _finish(db, conn, record, run)
    return record


async def _finish(db: AsyncSession, conn: RoutineConnection, record: RoutineSync, run: _Run | None) -> None:
    from app.applaut.services.audit import log_action
    from app.applaut.services.notification import create_notification
    counts = {k: getattr(record, k) for k in ("rows_read", "jobs_new", "jobs_updated", "jobs_removed",
                                               "docs_copied", "docs_skipped")}
    await log_action(
        action="routine.sync", db=db, user_id=str(conn.user_id), entity_type="routine_sync",
        entity_id=str(record.id),
        after_state={"status": record.status, "trigger": record.trigger, "run_id": record.run_id, **counts,
                     "problems": len(record.problems), "error": record.error},
    )
    await db.commit()

    if record.status == "failed":
        title, body = "Sync with your routine failed", record.error
    elif record.jobs_new:
        n = record.jobs_new
        title = f"Your routine found {n} new job{'s' if n != 1 else ''}"
        if run is not None and run.new_with_docs == n:
            title += " — CV and cover letter ready"
        body = f"{n} new, {record.jobs_updated} updated, {record.docs_copied} documents copied. They're waiting in Applications → To review."
    elif record.docs_copied:
        title, body = "New documents from your routine", f"{record.docs_copied} documents copied."
    else:
        return
    if record.problems:
        body += f" {len(record.problems)} problem{'s' if len(record.problems) != 1 else ''}: {record.problems[0]}"
    await create_notification(user_id=str(conn.user_id), type="routine_sync", title=title, body=body,
                              metadata={"sync_id": str(record.id), **counts}, db=db)
