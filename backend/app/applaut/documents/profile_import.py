"""A master profile drafted from the user's own CV (.docx or PDF).

The model never writes the profile's text. It answers with line numbers (the
CV's name, headline, each role's bullets, skills and technologies lines) and
splits heading lines into title, company, place and dates by copying. Code
builds the profile from the CV's own lines, and keeps a copied piece only if
it really is in the CV; anything else is left empty with a note. The user
then reviews the draft, fills what's missing and saves it like any profile.
"""
from __future__ import annotations

import io
import re

from app.applaut.documents import own_template

MAX_LINES = 250            # a longer CV is refused before it reaches the model
MAX_PDF_PAGES = 6
LINE_CHARS = 200           # each line as the model sees it

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"\+?\d[\d ()/.-]{6,}\d")
LINKEDIN = re.compile(r"(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/in/[\w%-]+/?", re.I)
GITHUB = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[\w-]+/?", re.I)
SEPARATORS = re.compile(r"[|,;·•]")  # how pieces are joined doesn't make them new words


class ImportProblem(ValueError):
    """The file can't be read; the message says why, for the user."""


def _clean(text: str) -> str:
    return " ".join(text.split())


def read_cv(data: bytes, file_name: str) -> list[str]:
    """The CV's non-empty lines, whitespace tidied. A .docx gives one line per
    paragraph; a PDF one per printed line (a long bullet may span several)."""
    name = file_name.lower()
    if name.endswith(".docx"):
        try:
            lines = own_template.lines_text(data)
        except own_template.TemplateError as exc:
            raise ImportProblem(exc.problems[0])
    elif name.endswith(".pdf"):
        from pdfminer.high_level import extract_text
        from pdfminer.pdfparser import PDFSyntaxError
        try:
            if own_template.pdf_pages(data) > MAX_PDF_PAGES:
                raise ImportProblem(f"The PDF has more than {MAX_PDF_PAGES} pages")
            text = extract_text(io.BytesIO(data))
        except ImportProblem:
            raise
        except (PDFSyntaxError, ValueError, TypeError, KeyError, AttributeError, OSError) as exc:
            raise ImportProblem("Applaut couldn't read this PDF") from exc
        lines = text.splitlines()
    else:
        raise ImportProblem("Upload your CV as a .docx or .pdf file")
    lines = [_clean(x) for x in lines]
    lines = [x for x in lines if x]
    if not lines:
        raise ImportProblem("The file has no text Applaut can read (a scanned PDF has none)")
    if len(lines) > MAX_LINES:
        raise ImportProblem(f"The file has {len(lines)} lines; Applaut reads CVs of up to {MAX_LINES}")
    return lines


# ---------------------------------------------------------------- the model's answer → a draft profile

class _Builder:
    def __init__(self, lines: list[str]):
        self.lines = lines                     # line n is lines[n - 1]
        self.whole = " ".join(lines)
        self.words = _words(self.whole)
        self.used: set[int] = set()
        self.notes: list[str] = []

    def line(self, n, what: str) -> str | None:
        """Line n's text, once: a line the draft already uses isn't used again."""
        if not isinstance(n, int) or isinstance(n, bool) or n == 0:
            return None
        if not 1 <= n <= len(self.lines):
            self.notes.append(f"Left out {what}: line {n} isn't in the CV")
            return None
        if n in self.used:
            return None
        self.used.add(n)
        return self.lines[n - 1]

    def copied(self, value, what: str) -> str:
        """`value` if it is word for word in the CV, else "" (with a note)."""
        if not isinstance(value, str):
            return ""
        value = _clean(value)
        if not value:
            return ""
        if value in self.whole or _words(value) in self.words:  # a piece over two lines, joined by " | "
            return value
        self.notes.append(f'Left out {what} "{value[:80]}": it isn\'t written that way in your CV')
        return ""

    def bullets(self, groups, what: str) -> list[str]:
        """Each group is the lines of one bullet (a PDF wraps long ones)."""
        out = []
        for group in groups if isinstance(groups, list) else []:
            nums = group if isinstance(group, list) else [group]
            parts = [t for t in (self.line(n, what) for n in nums) if t]
            if not parts:
                continue
            text = parts[0]
            for p in parts[1:]:  # "data-" + "driven" stays "data-driven"
                text = text + p if text.endswith("-") and p[:1].islower() else f"{text} {p}"
            text = own_template.TYPED_BULLET.sub("", text).strip()
            if text and text not in out:
                out.append(text)
        return out

    def items(self, n, what: str) -> tuple[str | None, list[str]]:
        """("Languages", ["Python", "SQL"]) for a line "Languages: Python, SQL"."""
        text = self.line(n, what)
        if not text:
            return None, []
        label = None
        split = own_template._split_label(text)
        if split:
            label, start = split
            text = text[start:]
        text = own_template.TYPED_BULLET.sub("", text)
        return label, own_template._split_items(text, own_template._separator(text))


def _words(text: str) -> str:
    return " " + " ".join(SEPARATORS.sub(" ", text).split()) + " "


def _slug(*parts: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", " ".join(p for p in parts if p).lower()).strip("_")
    return s[:40].strip("_") or "role"


def _unique(base: str, taken: set[str]) -> str:
    n, out = 2, base
    while out in taken:
        out, n = f"{base}_{n}", n + 1
    taken.add(out)
    return out


def _contact(whole: str) -> dict:
    out = {}
    if m := EMAIL.search(whole):
        out["email"] = m.group(0)
    for m in PHONE.finditer(whole):
        digits = re.sub(r"\D", "", m.group(0))
        years = re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", m.group(0))  # "03/2020 - 12/2021" is dates
        if 8 <= len(digits) <= 15 and len(years) < 2:
            out["phone"] = m.group(0).strip()
            break
    if m := LINKEDIN.search(whole):
        found = m.group(0).rstrip("/")
        out["linkedin_display"] = re.sub(r"^https?://(www\.)?", "", found, flags=re.I)
        out["linkedin_url"] = found if found.lower().startswith("http") else f"https://{found}"
    if m := GITHUB.search(whole):
        found = m.group(0).rstrip("/")
        out["github_display"] = re.sub(r"^https?://(www\.)?", "", found, flags=re.I)
        out["github_url"] = found if found.lower().startswith("http") else f"https://{found}"
    return out


_ORDER = {
    None: ["personal", "default_headline", "default_cover_tagline", "skills", "experience", "projects",
           "certifications", "education", "languages"],
    "personal": ["name", "location", "email", "phone", "linkedin_display", "linkedin_url", "github_display",
                 "github_url"],
    "experience": ["id", "title", "company", "location", "start", "end", "facts", "technologies"],
    "projects": ["id", "name", "facts", "technologies"],
    "certifications": ["name", "detail"],
    "education": ["period", "degree", "school"],
    "languages": ["english", "german"],
}


SKILLS_ORDER = "_skills_order"


def for_storage(draft: dict) -> dict:
    """The draft plus the CV's order of skill rows, which a JSONB object loses."""
    return {**draft, SKILLS_ORDER: list(draft.get("skills") or {})}


def in_order(stored: dict) -> dict:
    """The stored draft in reading order (JSONB keeps keys in its own order)."""
    def keyed(d: dict, keys: list[str]) -> dict:
        return {**{k: d[k] for k in keys if k in d}, **{k: v for k, v in d.items() if k not in keys}}
    draft = dict(stored)
    rows = draft.pop(SKILLS_ORDER, None) or []
    if isinstance(draft.get("skills"), dict):
        draft["skills"] = keyed(draft["skills"], [r for r in rows if isinstance(r, str)])
    out = keyed(draft, _ORDER[None])
    for part in ("personal", "languages"):
        if isinstance(out.get(part), dict):
            out[part] = keyed(out[part], _ORDER[part])
    for part in ("experience", "projects", "certifications", "education"):
        if isinstance(out.get(part), list):
            out[part] = [keyed(x, _ORDER[part]) if isinstance(x, dict) else x for x in out[part]]
    return out


def build_profile(lines: list[str], answer: dict) -> tuple[dict, list[str]]:
    """The draft profile (not yet valid: the user fills the gaps) and notes on
    what was left out or still needs filling."""
    b = _Builder(lines)
    a = answer if isinstance(answer, dict) else {}

    name = b.line(a.get("name_line"), "the name") or ""
    headline = b.line(a.get("headline_line"), "the headline") or ""
    personal = {"name": name, "location": b.copied(a.get("location"), "the location"), **_contact(b.whole)}
    if not name:
        b.notes.append("Fill in your name (personal.name)")

    skills: dict[str, list[str]] = {}
    for n in a.get("skills_lines") or []:
        label, items = b.items(n, "a skills line")
        if items and (label or len(items) > 1):  # one unlabelled item is a heading ("TECHNICAL SKILLS")
            skills.setdefault(label or "Skills", [])
            skills[label or "Skills"] += [i for i in items if i not in skills[label or "Skills"]]
    if not skills:
        b.notes.append("No skills list was found: add at least one row under skills")

    taken: set[str] = set()
    experience = []
    for i, r in enumerate(a.get("roles") or [], 1):
        if not isinstance(r, dict):
            continue
        title = b.copied(r.get("title"), f"role {i}'s title")
        company = b.copied(r.get("company"), f"role {i}'s company")
        facts = b.bullets(r.get("bullets"), f"a bullet of role {i}")
        _, tech = b.items(r.get("technologies_line"), f"role {i}'s technologies")
        if not (title or company or facts):
            continue
        entry = {"id": _unique(_slug(company, title), taken), "title": title, "company": company,
                 "location": b.copied(r.get("location"), f"role {i}'s place"),
                 "start": b.copied(r.get("start"), f"role {i}'s start date"),
                 "end": b.copied(r.get("end"), f"role {i}'s end date"),
                 "facts": facts, "technologies": tech}
        label = title or company or f"role {i}"
        if not title:
            b.notes.append(f"Fill in the job title of {label} (experience: title)")
        if not company:
            b.notes.append(f"Fill in the company of {label} (experience: company)")
        if not facts:
            b.notes.append(f"{label} has no bullets: add at least one under facts")
        experience.append(entry)
    if not experience:
        b.notes.append("No roles were found: add your experience")

    projects = []
    for i, p in enumerate(a.get("projects") or [], 1):
        if not isinstance(p, dict):
            continue
        pname = b.copied(p.get("name"), f"project {i}'s name")
        facts = b.bullets(p.get("bullets"), f"a bullet of project {i}")
        _, tech = b.items(p.get("technologies_line"), f"project {i}'s technologies")
        if not pname or not facts:
            if pname or facts:
                b.notes.append(f"Left out project {pname or i}: it needs a name and at least one bullet")
            continue
        projects.append({"id": _unique(_slug(pname), taken), "name": pname, "facts": facts, "technologies": tech})

    education = []
    for i, e in enumerate(a.get("education") or [], 1):
        if isinstance(e, dict) and (degree := b.copied(e.get("degree"), f"education {i}'s degree")):
            education.append({"period": b.copied(e.get("period"), f"education {i}'s dates"), "degree": degree,
                              "school": b.copied(e.get("school"), f"education {i}'s school")})
    certifications = []
    for i, c in enumerate(a.get("certifications") or [], 1):
        if isinstance(c, dict) and (cname := b.copied(c.get("name"), f"certification {i}")):
            certifications.append({"name": cname, "detail": b.copied(c.get("detail"), f"certification {i}'s detail")})
    langs = a.get("languages") if isinstance(a.get("languages"), dict) else {}
    languages = {k: v for k in ("english", "german") if (v := b.copied(langs.get(k), f"your {k.title()} level"))}

    if headline:
        b.notes.append("default_cover_tagline is your headline; shorten it for the cover letter if you like")
    else:
        b.notes.append("Fill in default_headline (one line under your name) and default_cover_tagline")
    draft = {
        "personal": personal,
        "default_headline": headline,
        "default_cover_tagline": headline,
        "skills": skills,
        "experience": experience,
        "projects": projects,
        "certifications": certifications,
        "education": education,
        "languages": languages,
    }
    return draft, b.notes
