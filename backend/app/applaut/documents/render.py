"""Render the CV and cover letter PDFs with the standard template (the Claude
routine's own `cv.html.j2` / `cover_letter.html.j2`, read from the setup kit
so both always look the same)."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from app.applaut.documents.fact_guard import LETTER_BODY_MAX_WORDS, PARAGRAPH_WORDS, check_cv_skills, check_written
from app.applaut.documents.letter import JobInfo, build_letter
from app.applaut.documents.tailor import drop_one, job_skills, order_skill_rows, pick_entries

STANDARD_TEMPLATES = Path(__file__).resolve().parent.parent / "routine" / "setup_kit" / "templates"
CV_MAX_PAGES = 2


class DocumentError(ValueError):
    """The written content can't be used; `errors` say what to fix."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass
class Rendered:
    pdf: bytes
    pages: int
    text: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.pdf).hexdigest()


@dataclass
class DocumentSet:
    cv: Rendered
    cover_letter: Rendered
    bullets_dropped: int = 0
    sentences_dropped: int = 0
    job_skills: list[str] = field(default_factory=list)


SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


def _drop_sentence(paras: list[str]) -> bool:
    """Drop the last sentence of the longest paragraph that keeps its minimum
    length. What stays is still the model's checked text, so it stays true."""
    for i in sorted(range(len(paras)), key=lambda k: -len(paras[k].split())):
        sentences = SENTENCE_END.split(paras[i])
        shorter = " ".join(sentences[:-1])
        if len(sentences) > 1 and len(shorter.split()) >= PARAGRAPH_WORDS[0]:
            paras[i] = shorter
            return True
    return False


def render_pdf(template: str, ctx: dict, templates: Path = STANDARD_TEMPLATES) -> tuple[bytes, int]:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
    from weasyprint import HTML

    env = Environment(loader=FileSystemLoader(templates), autoescape=select_autoescape(["html", "j2"]),
                      undefined=StrictUndefined)
    html = env.get_template(template).render(**ctx)
    doc = HTML(string=html, base_url=str(templates)).render()
    return doc.write_pdf(), len(doc.pages)


def _cv_context(profile: dict, headline: str, skill_rows: list[dict], picks: dict) -> dict:
    def merged(entries):
        return [{**e, "bullets": picks[e["id"]].bullets, "technologies": picks[e["id"]].technologies} for e in entries]
    return {"p": profile, "cv": {"headline": headline, "skills": skill_rows},
            "experience": merged(profile["experience"]), "projects": merged(profile.get("projects", []))}


def _cv_text(ctx: dict) -> str:
    lines = [ctx["p"]["personal"]["name"], ctx["cv"]["headline"], ""]
    lines += [f"{r['label']}: {', '.join(r['items'])}" for r in ctx["cv"]["skills"]]
    for e in ctx["experience"] + ctx["projects"]:
        lines += ["", f"{e.get('title') or e.get('name')} — {e.get('company', '')} ({e['start']} – {e['end']})"]
        lines += [f"• {b}" for b in e["bullets"]]
        if e["technologies"]:
            lines.append("Technologies: " + ", ".join(e["technologies"]))
    return "\n".join(lines)


def _letter_text(profile: dict, cl: dict) -> str:
    return "\n\n".join([cl["date"], "\n".join(cl["recipient_lines"]), cl["subject"], cl["salutation"],
                        *cl["paragraphs"], cl["closing"], profile["personal"]["name"]])


def build_documents(profile: dict, job: JobInfo, written: dict, skill_hints: list[str] | None = None,
                    check: bool = True) -> DocumentSet:
    """CV + cover letter for one job from the model's {"headline", "paragraphs"}.
    Raises DocumentError with messages the model can act on. `check=False` skips
    the fact guard (only for the layout preview, whose text Applaut wrote)."""
    errors = check_written(written, profile, job.description) if check else []
    paras = [p.strip() for p in written.get("paragraphs") or []]
    cl = build_letter(profile, job, paras)
    words = sum(len(p.split()) for p in cl["paragraphs"])
    if words > LETTER_BODY_MAX_WORDS:
        errors.append(f"the cover letter body is {words} words; shorten paragraphs 1-3 so the total stays under "
                      f"{LETTER_BODY_MAX_WORDS}")
    if errors:
        raise DocumentError(errors)

    wanted = job_skills(profile, f"{job.title}\n{job.description}", skill_hints)
    skill_rows = order_skill_rows(profile, wanted)
    picks = pick_entries(profile, wanted, f"{job.title}\n{job.description}")
    bug = check_cv_skills(skill_rows, {k: v.technologies for k, v in picks.items()}, profile)
    if bug:
        raise DocumentError(bug)

    headline = written["headline"].strip()
    dropped = 0
    while True:
        ctx = _cv_context(profile, headline, skill_rows, picks)
        cv_pdf, cv_pages = render_pdf("cv.html.j2", ctx)
        if cv_pages <= CV_MAX_PAGES or not drop_one(picks, profile, wanted):
            break
        dropped += 1
    if cv_pages > CV_MAX_PAGES:
        raise DocumentError([f"the CV is {cv_pages} pages even with every role at its minimum bullets; "
                             "shorten the profile's bullets or lower cv_bullets"])

    trimmed = 0
    while True:
        cl_pdf, cl_pages = render_pdf("cover_letter.html.j2", {"p": profile, "cl": cl})
        if cl_pages == 1 or not _drop_sentence(paras):
            break
        cl = build_letter(profile, job, paras)
        trimmed += 1
    if cl_pages != 1:
        raise DocumentError([f"the cover letter is {cl_pages} pages; shorten paragraphs 1-3"])

    return DocumentSet(
        cv=Rendered(cv_pdf, cv_pages, _cv_text(ctx)),
        cover_letter=Rendered(cl_pdf, cl_pages, _letter_text(profile, cl)),
        bullets_dropped=dropped,
        sentences_dropped=trimmed,
        job_skills=sorted(wanted),
    )


def sample_documents(profile: dict) -> DocumentSet:
    """Untailored preview built only from the profile (the master-profile screen's Preview)."""
    first = profile["experience"][0]
    job = JobInfo(title="an example role", company="Example Company", location="Berlin, Germany")
    written = {"headline": profile["default_headline"], "paragraphs": [
        "This is a layout preview. For each job, Applaut AI replaces this paragraph and the next two with text "
        "written for that posting, using only facts from your master profile.",
        f"The second paragraph will cover your most relevant experience for the job, such as your work as "
        f"{first['title']} at {first['company']}, with the real results from your profile.",
        "The third paragraph will add a second angle: another role or a project from your profile that fits "
        "a different part of the job description.",
    ]}
    return build_documents(profile, job, written, check=False)
