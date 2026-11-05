"""Render the CV and cover letter PDFs: with the standard template (the Claude
routine's own `cv.html.j2` / `cover_letter.html.j2`, read from the setup kit
so both always look the same), or the CV with the user's own .docx template
(own_template.py; the cover letter stays standard)."""
from __future__ import annotations

import copy
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from app.applaut.documents import own_template
from app.applaut.documents.fact_guard import LETTER_BODY_MAX_WORDS, PARAGRAPH_WORDS, check_cv_skills, check_written
from app.applaut.documents.letter import JobInfo, build_letter
from app.applaut.documents.tailor import (
    Bullet, EntryPick, apply_picks, drop_one, job_skills, mentioned, order_skill_rows, pick_entries, skill_names,
)

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
    # Per CV bullet shown: fact id, original, text, whether reworded, why not.
    bullets: list[dict] = field(default_factory=list)
    skills_first: list[str] = field(default_factory=list)
    # What rerender_cv needs to build this CV again (stored on its row).
    cv_details: dict = field(default_factory=dict)


@dataclass
class OwnCv:
    """The user's active own template, as the renderer needs it."""
    template_id: str
    template: bytes
    slots: own_template.Slots
    pages: int  # the upload's page count: the CV keeps to it


def _fit_own(own: OwnCv, profile: dict, headline: str, skill_rows: list[dict], picks: dict,
             wanted: set[str] | None = None) -> tuple[bytes, int, int, str]:
    """The user's template filled for the job, dropping the lowest-ranked bullet
    until it has no more pages than their upload. With every role at its
    minimum it's kept as it is (their own layout, their own bullet counts).
    Returns the PDF, pages, bullets dropped and the CV's text."""
    dropped = 0
    while True:
        filled = own_template.render(own.template, own_template.job_context(own.slots, profile, headline,
                                                                            skill_rows, picks))
        pdf, pages = own_template.to_pdf(filled)
        if pages <= own.pages or not drop_one(picks, profile, wanted):
            break
        dropped += 1
    text = "\n".join(line for line in own_template.lines_text(filled) if line)
    return pdf, pages, dropped, text


def _shown(own: OwnCv, profile: dict, picks: dict) -> dict:
    """The picks of the entries the user's template shows, in template order."""
    return {eid: picks[eid] for eid in own_template.match_entries(own.slots, profile).values() if eid in picks}


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


def _fit_cv(profile: dict, headline: str, skill_rows: list[dict], picks: dict,
            wanted: set[str] | None = None) -> tuple[dict, bytes, int, int]:
    """Render the CV, dropping the lowest-ranked bullet until it fits two pages.
    Returns the context, PDF, pages and how many bullets were dropped."""
    dropped = 0
    while True:
        ctx = _cv_context(profile, headline, skill_rows, picks)
        pdf, pages = render_pdf("cv.html.j2", ctx)
        if pages <= CV_MAX_PAGES or not drop_one(picks, profile, wanted):
            break
        dropped += 1
    if pages > CV_MAX_PAGES:
        raise DocumentError([f"the CV is {pages} pages even with every role at its minimum bullets; "
                             "shorten the profile's bullets or lower cv_bullets"])
    return ctx, pdf, pages, dropped


def _cv_details(profile: dict, headline: str, skill_rows: list[dict], picks: dict, own: OwnCv | None = None) -> dict:
    """Everything a CV is built from, so one bullet can be switched between its
    tailored and original wording later without the model. The profile is a
    snapshot: editing the master profile afterwards doesn't change this CV.
    `template`: the user's own template it was built with (None: standard)."""
    return {
        "v": 1, "profile": copy.deepcopy(profile), "headline": headline, "skill_rows": skill_rows,
        "template": {"id": own.template_id} if own else None,
        "entries": [{"id": eid, "technologies": p.technologies, "min_bullets": p.min_bullets, "bullets": [
            {"id": b.fact_id, "original": b.original, "tailored": b.text if b.tailored else None,
             "use": "tailored" if b.tailored else "original", "rank": list(b.rank), "note": b.note}
            for b in p.items]} for eid, p in picks.items()],
        "choices": [],
    }


def rerender_cv(details: dict, own: OwnCv | None = None) -> tuple[Rendered, dict]:
    """The CV built again from its details, each bullet in the wording its
    "use" says. Code only (no model). A bullet the page fit has to drop leaves
    the returned details too. A CV built with the user's own template needs
    that template (`own`) again."""
    if (details.get("template") or None) and own is None:
        raise DocumentError(["this CV was built with your own template, which is needed to build it again"])
    def bullet(b: dict) -> Bullet:
        tailored = b["use"] == "tailored" and bool(b["tailored"])
        return Bullet(b["id"], b["original"], b["tailored"] if tailored else b["original"], tuple(b["rank"]),
                      tailored=tailored, note=b["note"])
    picks = {e["id"]: EntryPick(e["id"], [bullet(b) for b in e["bullets"]], e["technologies"],
                                min_bullets=e["min_bullets"]) for e in details["entries"]}
    if details.get("template"):
        pdf, pages, _, text = _fit_own(own, details["profile"], details["headline"], details["skill_rows"], picks)
    else:
        ctx, pdf, pages, _ = _fit_cv(details["profile"], details["headline"], details["skill_rows"], picks)
        text = _cv_text(ctx)
    shown = {b.fact_id for p in picks.values() for b in p.items}
    details = copy.deepcopy(details)
    for e in details["entries"]:
        e["bullets"] = [b for b in e["bullets"] if b["id"] in shown]
    return Rendered(pdf, pages, text), details


def _letter_text(profile: dict, cl: dict) -> str:
    return "\n\n".join([cl["date"], "\n".join(cl["recipient_lines"]), cl["subject"], cl["salutation"],
                        *cl["paragraphs"], cl["closing"], profile["personal"]["name"]])


def build_documents(profile: dict, job: JobInfo, written: dict, skill_hints: list[str] | None = None,
                    check: bool = True, own: OwnCv | None = None) -> DocumentSet:
    """CV + cover letter for one job from the writer's answer: "headline" and
    "paragraphs" (checked; a failure raises DocumentError with messages the model
    can act on), and optionally "bullets" and "skills_first" (checked piece by
    piece, falling back to code's choice; they never fail the job). `check=False`
    skips the fact guard (only for the layout preview, whose text Applaut wrote).
    `own`: the user's own CV template (only the entries it shows are picked from)."""
    errors = check_written(written, profile, job.description) if check else []
    paras = [p.strip() for p in written.get("paragraphs") or []]
    cl = build_letter(profile, job, paras)
    words = sum(len(p.split()) for p in cl["paragraphs"])
    if words > LETTER_BODY_MAX_WORDS:
        errors.append(f"the cover letter body is {words} words; shorten paragraphs 1-3 so the total stays under "
                      f"{LETTER_BODY_MAX_WORDS}")
    if errors:
        raise DocumentError(errors)

    job_text = f"{job.title}\n{job.description}"
    first = list(dict.fromkeys(x for x in written.get("skills_first") or [] if isinstance(x, str)))  # each once
    wanted = job_skills(profile, job_text, skill_hints) | mentioned(skill_names(profile), "\n".join(first))
    skill_rows = order_skill_rows(profile, wanted, first)
    if written.get("bullets"):
        reworded: dict = {}
        for r in written.get("reworded") or []:  # a repeated id keeps its first wording
            if isinstance(r, dict):
                reworded.setdefault(r.get("id"), r.get("text") or "")
        chosen = [{"id": i, "text": reworded.get(i, "")} for i in written["bullets"]]
        picks = apply_picks(profile, chosen, wanted, job_text)
    else:
        picks = pick_entries(profile, wanted, job_text)
    bug = check_cv_skills(skill_rows, {k: v.technologies for k, v in picks.items()}, profile)
    if bug:
        raise DocumentError(bug)

    headline = written["headline"].strip()
    if own:
        picks = _shown(own, profile, picks)
        cv_pdf, cv_pages, dropped, cv_text = _fit_own(own, profile, headline, skill_rows, picks, wanted)
    else:
        ctx, cv_pdf, cv_pages, dropped = _fit_cv(profile, headline, skill_rows, picks, wanted)
        cv_text = _cv_text(ctx)

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
        cv=Rendered(cv_pdf, cv_pages, cv_text),
        cover_letter=Rendered(cl_pdf, cl_pages, _letter_text(profile, cl)),
        bullets_dropped=dropped,
        sentences_dropped=trimmed,
        job_skills=sorted(wanted),
        bullets=[{"id": b.fact_id, "original": b.original, "text": b.text, "tailored": b.tailored, "note": b.note}
                 for p in picks.values() for b in p.items],
        skills_first=first,
        cv_details=_cv_details(profile, headline, skill_rows, picks, own),
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
