"""One queue item each: score a job (`score_job`), write its documents
(`write_docs`), draft CV bullets from the user's notes (`draft_bullets`), or
make the user's own .docx CV into a template (`build_template`)."""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.applaut.ai import prompts, scoring
from app.applaut.ai.provider import Completion, HostUnreachable, ModelError, Provider
from app.applaut.ai.queue import enqueue
from app.applaut.documents.fact_guard import check_drafts, check_fact_rewording
from app.applaut.documents import own_template
from app.applaut.documents.letter import JobInfo, company_display
from app.applaut.documents.profile_schema import ProfileError, validate_profile
from app.applaut.documents.render import DocumentError, OwnCv, build_documents
from app.applaut.documents.tailor import fact_ids
from app.applaut.models.ai_queue import AIQueueItem
from app.applaut.models.bullet_draft import BulletDraft
from app.applaut.models.cv_template import CvTemplate
from app.applaut.models.generated_document import GeneratedDocument
from app.applaut.models.job_assessment import JobAssessment
from app.applaut.models.master_profile import MasterProfile
from app.applaut.models.opportunity import Opportunity
from app.applaut.models.profile import Profile
from app.config import settings

logger = logging.getLogger(__name__)
ENGINE = "applaut_ai"


class PermanentError(Exception):
    """Retrying can't help (no master profile, text that keeps breaking the rules).
    `answer` is the model's last answer, kept on the job so the failure can be read."""

    def __init__(self, message: str, answer: dict | None = None):
        super().__init__(message)
        self.answer = answer


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


async def fetch_file(key: str) -> bytes:
    """A file from Applaut's R2 bucket. Tests replace this."""
    if not settings.r2_bucket_name:
        raise PermanentError("Applaut's file storage isn't configured")
    from app.core.storage import get_r2_client

    def get() -> bytes:
        return get_r2_client().get_object(Bucket=settings.r2_bucket_name, Key=key)["Body"].read()
    return await asyncio.to_thread(get)


async def own_cv(db: AsyncSession, user_id, template_id=None) -> OwnCv | None:
    """The user's own CV template for rendering: the active one, or (to build an
    existing CV again) the one with `template_id`, whatever its status now."""
    q = select(CvTemplate).where(CvTemplate.user_id == user_id, CvTemplate.kind == "cv")
    q = q.where(CvTemplate.id == template_id) if template_id else q.where(CvTemplate.status == "active")
    t = await db.scalar(q)
    if t is None or not t.template_key or not t.slots:
        return None
    return OwnCv(str(t.id), await fetch_file(t.template_key), own_template.Slots.from_json(t.slots), t.pages or 2)


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


async def _reword(provider: Provider, system: str, mp: dict, focus: dict, usage: Usage) -> str:
    """One focus bullet reworded in its own short call, with one retry that
    names the problem. Returns the last wording; the CV shows the fact as
    written when that wording fails its checks (apply_picks notes why)."""
    message = prompts.reword_message(mp, focus["id"], focus.get("need") or "")
    user, text = message, ""
    for _ in range(2):
        try:
            c = await provider.complete_json(system, user, prompts.REWORD_SCHEMA, prompts.REWORD_MAX_TOKENS)
        except HostUnreachable:
            raise
        except ModelError:  # one bullet's bad answer: the fact stays as written
            return text
        usage.add(c)
        text = (c.data.get("text") or "").strip()
        problem = check_fact_rewording(mp, focus["id"], text)
        if problem is None:
            break
        user = prompts.reword_retry(message, text, problem)
    return text


async def write_docs(db: AsyncSession, item: AIQueueItem, provider: Provider) -> Usage:
    a, opp, profile, mp = await _load(db, item)
    company = company_display(opp.company_name, opp.description or "")
    job = JobInfo(title=opp.title, company=company, location=opp.location_raw or "",
                  description=opp.description or "")
    system = prompts.write_system(mp)
    message = prompts.job_message(opp.title, company, opp.location_raw, opp.description or "")
    hints = list(a.matched_skills or []) + list(a.missing_skills or [])
    own = await own_cv(db, item.user_id)
    usage = Usage()

    docs, errors = None, []
    reworded: dict[str, str] = {}  # fact id -> wording, kept if the letter needs a second try
    for attempt in range(2):  # the second try gets the fact guard's messages
        user = message if not errors else (
            f"{message}\n\nYour previous answer:\n{json.dumps(written, ensure_ascii=False)}\n\n{prompts.fix_message(errors)}")
        c = await provider.complete_json(system, user, prompts.write_schema(mp), prompts.WRITE_MAX_TOKENS)
        usage.add(c)
        written = c.data
        known, chosen = fact_ids(mp), written.get("bullets") or []
        for focus in (written.get("focus") or [])[:prompts.REWORD_MAX]:
            if focus.get("id") in known and focus["id"] in chosen and focus["id"] not in reworded:
                reworded[focus["id"]] = await _reword(provider, system, mp, focus, usage)
        answer = {**written, "reworded": [{"id": i, "text": t} for i, t in reworded.items()]}
        try:
            docs = await asyncio.to_thread(build_documents, mp, job, answer, hints, True, own)
            break
        except DocumentError as exc:
            errors = exc.errors
    if docs is None:
        raise PermanentError("the written text broke the rules twice: " + "; ".join(errors), answer=written)

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
            details=docs.cv_details if stem == "cv" else None,
        ))
    a.docs_status = "done"
    tailored = sum(b["tailored"] for b in docs.bullets)
    a.raw = {**(a.raw or {}), "write_docs": {
        "bullets": docs.bullets, "skills_first": docs.skills_first, "bullets_dropped": docs.bullets_dropped,
        "sentences_dropped": docs.sentences_dropped, "tailored": f"{tailored}/{len(docs.bullets)}"}}
    await db.commit()
    return usage


async def draft_bullets(db: AsyncSession, item: AIQueueItem, provider: Provider) -> Usage:
    """Bullet bank builder: CV bullets for one role from the user's notes,
    checked (check_drafts) and kept as drafts until the user approves them."""
    draft = await db.get(BulletDraft, item.bullet_draft_id)
    mp = await db.scalar(select(MasterProfile).where(MasterProfile.user_id == item.user_id))
    if draft is None or mp is None:
        raise PermanentError("the notes or the master profile no longer exist")
    try:
        profile = validate_profile(mp.data)
    except ProfileError as exc:
        raise PermanentError(f"the master profile is incomplete: {'; '.join(exc.errors)[:300]}")
    entry = next((e for e in profile["experience"] + profile.get("projects", []) if e["id"] == draft.entry_id), None)
    if entry is None:
        raise PermanentError("that role is no longer in the master profile")
    usage = Usage()
    c = await provider.complete_json(prompts.DRAFT_SYSTEM, prompts.draft_message(profile, entry, draft.notes),
                                     prompts.DRAFT_SCHEMA, prompts.DRAFT_MAX_TOKENS)
    usage.add(c)
    texts = [t for t in c.data.get("bullets") or [] if isinstance(t, str)][:prompts.DRAFT_MAX]
    draft.drafts, draft.left_out = check_drafts(profile, entry, draft.notes, texts)
    draft.status, draft.error, draft.finished_at = "done", None, datetime.now(timezone.utc)
    await db.commit()
    return usage


def template_report(slots: own_template.Slots, profile: dict | None) -> dict:
    """What the template fills per job, and from which part of the master
    profile (None: no profile yet, so nothing is matched)."""
    entries = own_template.match_entries(slots, profile) if profile else {}
    rows = own_template.match_rows(slots, profile) if profile else {}
    labels = {e["id"]: (f"{e['title']} at {e['company']}" if "company" in e else f"Project: {e['name']}")
              for e in (profile or {}).get("experience", []) + (profile or {}).get("projects", [])}
    return {
        "headline": slots.headline,
        "roles": [{"heading": b.heading, "bullets": len(b.original_bullets), "technologies": bool(b.tech_key),
                   "entry": labels.get(entries.get(n))}
                  for n, b in enumerate(slots.blocks) if b.bullets_key or b.tech_key],  # a block with nothing to fill: not shown
        "rows": [{"label": r.label, "row": rows.get(r.key)} for r in slots.rows],
    }


def _template_files(t: CvTemplate) -> str:
    return f"applaut/templates/{t.user_id}/{t.id}"


async def build_template(db: AsyncSession, item: AIQueueItem, provider: Provider) -> Usage:
    """The user's own .docx CV made into a template: the model labels its lines,
    code builds the template and checks the round trip; the user then compares
    the two PDFs and switches it on (or not)."""
    t = await db.get(CvTemplate, item.cv_template_id)
    if t is None or t.status != "reading":
        raise PermanentError("the upload was removed")
    source = await fetch_file(t.source_key)
    try:
        lines = await asyncio.to_thread(own_template.read_lines, source)
    except own_template.TemplateError as exc:
        raise PermanentError("; ".join(exc.problems))
    shown = [(ln.index, ln.style, ln.text) for ln in lines if ln.text.strip()]
    if not shown:
        raise PermanentError("the file has no text Applaut can read")
    if len(shown) > prompts.TEMPLATE_MAX_LINES:
        raise PermanentError(f"the file has {len(shown)} lines; Applaut reads CVs of up to {prompts.TEMPLATE_MAX_LINES}")
    usage = Usage()
    numbers = [n for n, _, _ in shown]
    c = await provider.complete_json(prompts.TEMPLATE_SYSTEM, prompts.template_message(shown),
                                     prompts.template_schema(numbers), prompts.template_max_tokens(len(shown)))
    usage.add(c)
    given = c.data.get("labels") if isinstance(c.data.get("labels"), dict) else {}
    missing = [n for n in numbers if str(n) not in given]
    if missing:
        raise ModelError(f"the model labelled {len(numbers) - len(missing)} of {len(numbers)} lines")
    labels = ["other"] * len(lines)
    for n in numbers:
        labels[n] = given[str(n)]

    mp = await db.scalar(select(MasterProfile).where(MasterProfile.user_id == t.user_id))
    try:
        profile = validate_profile(mp.data) if mp else None
    except ProfileError:
        profile = None

    def make():
        built = own_template.build(source, labels)
        differences = own_template.round_trip(source, built)
        original_pdf, pages = own_template.to_pdf(source)
        rebuilt_pdf, _ = own_template.to_pdf(own_template.render(built.template,
                                                                 own_template.round_trip_context(built.slots)))
        return built, differences, original_pdf, pages, rebuilt_pdf, own_template.font_report(source)
    try:
        built, differences, original_pdf, pages, rebuilt_pdf, fonts = await asyncio.to_thread(make)
    except own_template.TemplateError as exc:
        raise PermanentError("; ".join(exc.problems))
    except RuntimeError as exc:  # LibreOffice
        raise PermanentError(str(exc))

    base = _template_files(t)
    await store_file(f"{base}/template.docx", built.template, DOCX)
    await store_file(f"{base}/original.pdf", original_pdf, "application/pdf")
    await store_file(f"{base}/rebuilt.pdf", rebuilt_pdf, "application/pdf")
    t.template_key, t.original_pdf_key, t.rebuilt_pdf_key = f"{base}/template.docx", f"{base}/original.pdf", f"{base}/rebuilt.pdf"
    t.labels, t.slots, t.pages = built.labels, built.slots.to_json(), pages
    t.report = {**template_report(built.slots, profile), "differences": differences[:20], "fonts": fonts,
                "notes": built.notes}
    t.status, t.error, t.finished_at = "ready", None, datetime.now(timezone.utc)
    await db.commit()
    return usage


DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
HANDLERS = {"score_job": score_job, "write_docs": write_docs, "draft_bullets": draft_bullets,
            "build_template": build_template}


async def mark_failed(db: AsyncSession, item: AIQueueItem, error: str, answer: dict | None = None) -> None:
    """The item is finally failed: show it on the job (or the drafts), with the model's last answer if there was one."""
    if item.kind == "draft_bullets":
        draft = await db.get(BulletDraft, item.bullet_draft_id)
        if draft is not None:
            draft.status, draft.error, draft.finished_at = "failed", error[:1000], datetime.now(timezone.utc)
            await db.commit()
        return
    if item.kind == "build_template":
        t = await db.get(CvTemplate, item.cv_template_id)
        if t is not None and t.status == "reading":
            t.status, t.error, t.finished_at = "failed", error[:1000], datetime.now(timezone.utc)
            await db.commit()
        return
    a = await db.get(JobAssessment, item.assessment_id)
    if a is None:
        return
    if item.kind == "score_job":
        a.status = "failed"
    else:
        a.docs_status = "failed"
    a.raw = {**(a.raw or {}), f"{item.kind}_error": error[:1000]}
    if answer is not None:
        a.raw[f"{item.kind}_last_answer"] = answer
    await db.commit()

