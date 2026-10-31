"""One queue item each: score a job (`score_job`) or write its documents (`write_docs`)."""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.applaut.ai import prompts, scoring
from app.applaut.ai.provider import Completion, Provider
from app.applaut.ai.queue import enqueue
from app.applaut.documents.letter import JobInfo
from app.applaut.documents.profile_schema import ProfileError, validate_profile
from app.applaut.documents.render import DocumentError, build_documents
from app.applaut.models.ai_queue import AIQueueItem
from app.applaut.models.generated_document import GeneratedDocument
from app.applaut.models.job_assessment import JobAssessment
from app.applaut.models.master_profile import MasterProfile
from app.applaut.models.opportunity import Opportunity
from app.applaut.models.profile import Profile
from app.config import settings

logger = logging.getLogger(__name__)
ENGINE = "applaut_ai"


class PermanentError(Exception):
    """Retrying can't help (no master profile, text that keeps breaking the rules)."""


@dataclass
class Usage:
    model: str | None = None
    prompt_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0

    def add(self, c: Completion) -> None:
        self.model = c.model
        self.prompt_tokens += c.prompt_tokens or 0
        self.output_tokens += c.output_tokens or 0
        self.duration_ms += c.duration_ms


async def store_file(key: str, data: bytes, content_type: str) -> None:
    """Applaut's own (private) R2 bucket. Tests replace this."""
    if not settings.r2_bucket_name:
        raise PermanentError("Applaut's file storage isn't configured")
    from app.core.storage import upload_file
    await asyncio.to_thread(upload_file, key, data, content_type)


async def _load(db: AsyncSession, item: AIQueueItem):
    a = await db.get(JobAssessment, item.assessment_id)
    opp = await db.get(Opportunity, a.opportunity_id) if a else None
    profile = await db.get(Profile, item.profile_id)
    mp = await db.scalar(select(MasterProfile).where(MasterProfile.user_id == item.user_id))
    if a is None or opp is None or profile is None:
        raise PermanentError("the job or profile no longer exists")
    if mp is None:
        raise PermanentError("no master profile yet (Settings → Master profile)")
    try:  # fills the defaults the templates expect, whatever wrote the row
        data = validate_profile(mp.data)
    except ProfileError as exc:
        raise PermanentError("the master profile is invalid: " + "; ".join(exc.errors)) from exc
    return a, opp, profile, data


async def score_job(db: AsyncSession, item: AIQueueItem, provider: Provider) -> Usage:
    a, opp, profile, mp = await _load(db, item)
    usage = Usage()
    c = await provider.complete_json(
        prompts.score_system(mp, profile.target_roles or []),
        prompts.job_message(opp.title, opp.company_name, opp.location_raw, opp.description or ""),
        prompts.SCORE_SCHEMA, prompts.SCORE_MAX_TOKENS)
    usage.add(c)
    r = scoring.compute(c.data, mp, scoring.years_from(mp), mp.get("languages", {}).get("german_max_required", "A2"))

    a.status, a.match_score = "scored", r.score
    a.matched_skills, a.missing_skills = r.matched, r.missing
    a.german_required = c.data.get("german_required")
    a.seniority = c.data.get("seniority")
    a.flags = scoring.flags_for(c.data, r)
    a.notes = " · ".join(f"{k.replace('_', ' ')} {v}/{scoring.WEIGHTS[k]}" for k, v in r.parts.items())
    a.model = c.model
    a.raw = {"facts": c.data, "parts": r.parts, "ignored_matches": r.ignored_matches}
    if r.score >= settings.applaut_ai_doc_threshold:
        a.docs_status = "pending"
        await enqueue(db, "write_docs", a, item.night_run_id)
    else:
        a.docs_status = "not_needed"
    await db.commit()
    return usage


async def write_docs(db: AsyncSession, item: AIQueueItem, provider: Provider) -> Usage:
    a, opp, profile, mp = await _load(db, item)
    job = JobInfo(title=opp.title, company=opp.company_name, location=opp.location_raw or "",
                  description=opp.description or "")
    system = prompts.write_system(mp)
    message = prompts.job_message(opp.title, opp.company_name, opp.location_raw, opp.description or "")
    hints = list(a.matched_skills or []) + list(a.missing_skills or [])
    usage = Usage()

    docs, errors = None, []
    for attempt in range(2):  # the second try gets the fact guard's messages
        user = message if not errors else (
            f"{message}\n\nYour previous answer:\n{json.dumps(written, ensure_ascii=False)}\n\n{prompts.fix_message(errors)}")
        c = await provider.complete_json(system, user, prompts.WRITE_SCHEMA, prompts.WRITE_MAX_TOKENS)
        usage.add(c)
        written = c.data
        try:
            docs = await asyncio.to_thread(build_documents, mp, job, written, hints)
            break
        except DocumentError as exc:
            errors = exc.errors
    if docs is None:
        raise PermanentError("the written text broke the rules twice: " + "; ".join(errors))

    for doc_type, rendered, stem in (("tailored_resume", docs.cv, "cv"), ("cover_letter", docs.cover_letter, "cover_letter")):
        key = f"applaut/documents/{a.user_id}/{opp.id}/{rendered.sha256[:8]}/{stem}.pdf"
        await store_file(key, rendered.pdf, "application/pdf")
        previous = await db.scalars(select(GeneratedDocument).where(
            GeneratedDocument.user_id == a.user_id, GeneratedDocument.opportunity_id == opp.id,
            GeneratedDocument.document_type == doc_type, GeneratedDocument.is_current == True))
        for doc in previous:
            doc.is_current = False
        name = mp["personal"]["name"].replace(" ", "_")
        db.add(GeneratedDocument(
            user_id=a.user_id, profile_id=a.profile_id, opportunity_id=opp.id, document_type=doc_type,
            generation_mode="ai", content=rendered.text, r2_key=key, ai_model=usage.model, is_current=True,
            engine=ENGINE, content_type="application/pdf", content_sha256=rendered.sha256,
            file_name=f"{name}_{'CV' if stem == 'cv' else 'CoverLetter'}.pdf",
        ))
    a.docs_status = "done"
    await db.commit()
    return usage


HANDLERS = {"score_job": score_job, "write_docs": write_docs}


async def mark_failed(db: AsyncSession, item: AIQueueItem, error: str) -> None:
    """The item is finally failed: show it on the job."""
    a = await db.get(JobAssessment, item.assessment_id)
    if a is None:
        return
    if item.kind == "score_job":
        a.status = "failed"
    else:
        a.docs_status = "failed"
    a.raw = {**(a.raw or {}), f"{item.kind}_error": error[:1000]}
    await db.commit()

