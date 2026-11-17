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

from app.applaut.documents import own_template, tailor

MAX_LINES = 250            # a longer CV is refused before it reaches the model
MAX_PDF_PAGES = 6
LINE_CHARS = 200           # each line as the model sees it

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"\+?\d[\d ()/.-]{6,}\d")
LINKEDIN = re.compile(r"(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/in/[\w%-]+/?", re.I)
GITHUB = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[\w-]+/?", re.I)
SEPARATORS = re.compile(r"[|,;·•]")  # how pieces are joined doesn't make them new words
LIST_SEPARATORS = (" | ", " · ", " • ", "; ", ", ")  # a line of several skills (" / " joins two names of one)
YEAR_START = re.compile(r"^(?:\d{1,2}[./])?(?:19|20)\d{2}\b")  # "2014 – 2018", "03/2020": a date line, not text
JOINERS = {"and", "or", "of", "the", "to", "for", "with", "in", "on", "by", "a", "an", "from", "across", "using",
           "via", "into", "at", "as", "while", "including", "und", "oder", "mit", "für", "von", "zu", "der", "die",
           "das", "den", "im", "auf"}
MAX_EXTRA_LINES = 3          # lines code adds to a bullet the model cut short


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
            nums = [n for n in nums if not self._marker(n)]  # a lone "–" ends a bullet, it isn't part of one
            got = [(n, t) for n in nums if (t := self.line(n, what))]
            if not got:
                continue
            text = _join([t for _, t in got])
            last = got[-1][0]
            for _ in range(MAX_EXTRA_LINES):  # the model often stops a long bullet at its second line
                nxt = last + 1
                if nxt > len(self.lines) or nxt in self.used or not _goes_on(text, self.lines[nxt - 1]):
                    break
                self.used.add(nxt)
                text, last = _join([text, self.lines[nxt - 1]]), nxt
            text = own_template.TYPED_BULLET.sub("", text).strip()
            if text and text not in out:
                out.append(text)
        return out

    def _marker(self, n) -> bool:
        """Line n is a bullet sign alone ("–", "•"), as a PDF prints it."""
        return (isinstance(n, int) and 1 <= n <= len(self.lines)
                and not own_template.TYPED_BULLET.sub("", self.lines[n - 1]).strip())

    def items(self, n, what: str) -> tuple[str | None, list[str]]:
        """("Languages", ["Python", "SQL"]) for a line "Languages: Python, SQL"."""
        text = self.line(n, what)
        return self.split(text) if text else (None, [])

    @staticmethod
    def split(text: str) -> tuple[str | None, list[str]]:
        label = None
        split = own_template._split_label(text)
        if split:
            label, start = split
            text = text[start:]
        text = own_template.TYPED_BULLET.sub("", text)
        return label, own_template._split_items(text, own_template._separator(text))


def _join(parts: list[str]) -> str:
    text = parts[0]
    for p in parts[1:]:  # "data-" + "driven" stays "data-driven"
        text = text + p if text.endswith("-") and p[:1].islower() else f"{text} {p}"
    return text


def _is_heading(text: str) -> bool:
    """"TECHNICAL SKILLS", "KERNKOMPETENZEN | CORE COMPETENCIES": a section heading."""
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 5 and text.isupper() and "/" not in text and "," not in text


def _goes_on(text: str, nxt: str) -> bool:
    """Whether CV line `nxt` continues the bullet `text` (a PDF breaks long ones)."""
    if text.rstrip().endswith((".", "!", "?")) or not nxt or own_template.TYPED_BULLET.match(nxt):
        return False
    if _is_heading(nxt) or EMAIL.search(nxt) or YEAR_START.match(nxt):
        return False
    words = text.split()
    return (nxt[0].islower() or nxt[0].isdigit() or text.endswith((",", "-", "–", "—", "/", "&", "("))
            or bool(words) and words[-1].lower() in JOINERS)


def _section_name(heading: str) -> str:
    """"KERNKOMPETENZEN | CORE COMPETENCIES" → "Core Competencies" (the last of
    a bilingual heading, in the case a skill row's name is written in)."""
    part = heading.split("|")[-1].strip()
    return part.title() if part.isupper() else part


def _is_label(text: str) -> bool:
    """A skill row's name alone on its line, its items on a later one."""
    return not _is_heading(text) and not _is_list(text) and len(text.split()) <= 5 and not text.endswith(".")


def _is_list(text: str) -> bool:
    return any(len(own_template._split_items(text, sep)) > 1 for sep in LIST_SEPARATORS if sep in text)


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
    None: ["personal", "default_headline", "default_cover_tagline", "skills", "additional_skills", "experience", "projects",
           "certifications", "education", "languages"],
    "personal": ["name", "location", "email", "phone", "linkedin_display", "linkedin_url", "github_display",
                 "github_url", "work_authorization", "work_authorization_short", "availability", "availability_short"],
    "experience": ["id", "title", "company", "location", "start", "end", "facts", "technologies"],
    "projects": ["id", "name", "start", "end", "facts", "technologies"],
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


def _skill_lines(b: _Builder, nums) -> list[int]:
    """The model's skills lines, plus what it skipped inside the same list: a
    line between two of its lines, and a label line just above where a list
    starts (a two-column PDF prints "Cloud Platforms" on one line, its items
    below)."""
    nums = sorted({n for n in (nums if isinstance(nums, list) else [])
                   if isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= len(b.lines)})
    out = set(nums)
    for x, y in zip(nums, nums[1:]):
        gap = range(x + 1, y)
        if len(gap) <= 3 and not any(g in b.used or _is_heading(b.lines[g - 1]) for g in gap):
            out.update(gap)
    for first in [n for n in sorted(out) if n - 1 not in out and n > 1]:  # where each list starts
        below = first  # the list's first line, past any labels it starts with
        while below <= len(b.lines) and _is_label(b.lines[below - 1]) and below - first < 4:
            below += 1
        if below > len(b.lines) or own_template._split_label(b.lines[below - 1]) or not _is_list(b.lines[below - 1]):
            continue
        m = first - 1  # every label stacked above it ("Cloud Platforms", "Architecture")
        while m >= 1 and first - m <= 4 and m not in b.used and m not in out and _is_label(b.lines[m - 1]):
            out.add(m)
            m -= 1
    return sorted(out)


def _skills(b: _Builder, nums) -> tuple[dict[str, list[str]], set[str]]:
    """Skill rows from the CV's skills lines. A row is "Label: items" on one
    line, or a label line with its items on a later line ("Architecture",
    "Web & APIs", then the two item lines, in that order); short lines with
    no list ("Python / SQL", "Cloud Cost Optimization") are skills of the
    section they stand under ("Core Competencies"), or of "Skills". Also
    returns which rows are such sections rather than labelled rows."""
    skills: dict[str, list[str]] = {}
    sections: set[str] = set()

    def add(row: str, items: list[str], loose: bool = False) -> None:
        if loose:
            sections.add(row)
        have = skills.setdefault(row, [])
        have += [i for i in items if i not in have]

    def flush(labels: list[str], section: str) -> None:
        for text in labels:
            add(section, own_template._split_items(text, own_template._separator(text)), loose=True)
        labels.clear()

    section, labels, items, prev = "Skills", [], [], None
    for n in _skill_lines(b, nums):
        if prev is not None and n != prev + 1:      # a new list elsewhere in the CV
            _pair(labels, items, section, add, flush)
            section = "Skills"
        if prev is None or n != prev + 1:
            above = b.lines[n - 2] if n > 1 else ""
            section = _section_name(above) if _is_heading(above) else section
        prev = n
        text = b.line(n, "a skills line")
        if not text:
            continue
        if _is_heading(text):
            _pair(labels, items, section, add, flush)
            section = _section_name(text)
            continue
        label, found = b.split(text)
        if label:
            _pair(labels, items, section, add, flush, drop_one=True)
            add(label, found)
        elif _is_list(text):
            items.append(found)
        else:
            if items:                                   # a label after item lines starts the next group
                _pair(labels, items, section, add, flush)
            labels.append(text)
    _pair(labels, items, section, add, flush)
    return {k: v for k, v in skills.items() if v}, sections


def _pair(labels: list[str], items: list[list[str]], section: str, add, flush, drop_one: bool = False) -> None:
    """Labels stacked above as many item lines name them in order (fewer
    labels name the last item lines); labels
    with no item lines are skills themselves (or, one alone right above a
    "Label: items" line, a heading such as "Skills")."""
    if items:
        k = min(len(labels), len(items))
        named = labels[len(labels) - k:]
        flush(labels[:len(labels) - k], section)
        start = len(items) - k  # a label the model skipped is one at the top: the last item lines have names
        for i, found in enumerate(items):
            add(named[i - start] if i >= start else section, found, loose=i < start)
        labels.clear()
        items.clear()
    elif drop_one and len(labels) == 1:
        labels.clear()
    else:
        flush(labels, section)


def _headline(b: _Builder, n) -> str:
    """The headline line, with the line under it when that one is a list of
    skills ("Data Engineer" over "Python | Azure Databricks | SQL")."""
    head = b.line(n, "the headline") or ""
    if not head or not isinstance(n, int) or n >= len(b.lines) or n + 1 in b.used:
        return head
    nxt = b.lines[n]
    if (_is_list(nxt) and len(nxt) <= 90 and not _is_heading(nxt) and not EMAIL.search(nxt)
            and not PHONE.search(nxt) and "linkedin" not in nxt.lower() and "http" not in nxt.lower()):
        b.used.add(n + 1)
        return f"{head} | {nxt}"
    return head


def _technologies(skills: dict[str, list[str]], additional: list[str], facts: list[str]) -> list[str]:
    """The profile's skills a role's own bullets name, in the order they come
    up: the role's technologies when the CV gives it no technologies line."""
    text = " ".join(facts)
    spans = []
    for skill in dict.fromkeys([s for row in skills.values() for s in row] + additional):
        if m := tailor._pattern(skill).search(text):
            spans.append((m.start(), -(m.end() - m.start()), m.end(), skill))
    out, covered = [], []
    for start, _, end, skill in sorted(spans):
        if any(s <= start and end <= e for s, e in covered):  # "Databricks" inside "Azure Databricks"
            continue
        if skill.lower() not in (o.lower() for o in out):
            out.append(skill)
            covered.append((start, end))
    return out


def build_profile(lines: list[str], answer: dict) -> tuple[dict, list[str]]:
    """The draft profile (not yet valid: the user fills the gaps) and notes on
    what was left out or still needs filling."""
    b = _Builder(lines)
    a = answer if isinstance(answer, dict) else {}

    name = b.line(a.get("name_line"), "the name") or ""
    headline = _headline(b, a.get("headline_line"))
    personal = {"name": name, "location": b.copied(a.get("location"), "the location"), **_contact(b.whole)}
    status = {}
    for key, what in (("work_authorization", "your work permit"), ("availability", "when you can start")):
        if value := b.copied(a.get(key), what):
            status[f"{key}_short"] = value[0].upper() + value[1:]  # "available immediately" → "Available immediately"
    personal.update(status)
    if not name:
        b.notes.append("Fill in your name (personal.name)")

    skills, sections = _skills(b, a.get("skills_lines"))
    additional: list[str] = []
    if any(row not in sections for row in skills):
        # Labelled rows ("Cloud Platforms: …") are the CV's skills list; a
        # competencies list beside it mostly repeats them in other words, so
        # its items count for matching without a row of their own on the CV.
        have = {s.lower() for row, items in skills.items() if row not in sections for s in items}
        for row in sections:
            additional += [s for s in skills.pop(row) if s.lower() not in have and s not in additional]
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
        elif not tech and len(found := _technologies(skills, additional, facts)) >= 2:  # one name says little
            entry["technologies"] = found
            b.notes.append(f"{label}: technologies are the skills its bullets name; check them")
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
        projects.append({"id": _unique(_slug(pname), taken), "name": pname,
                         "start": b.copied(p.get("start"), f"project {pname}'s start date"),
                         "end": b.copied(p.get("end"), f"project {pname}'s end date"),
                         "facts": facts, "technologies": tech or _technologies(skills, additional, facts)})

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

    for key, short in (("work_authorization", "Opportunity Card Holder"), ("availability", "Available immediately")):
        if f"{key}_short" in personal:
            b.notes.append(f"personal.{key}_short is from your CV (e.g. \"{short}\"); write personal.{key} as one "
                           f"sentence for your cover letters")
    if headline:
        b.notes.append("default_cover_tagline is your headline; shorten it for the cover letter if you like")
    else:
        b.notes.append("Fill in default_headline (one line under your name) and default_cover_tagline")
    draft = {
        "personal": personal,
        "default_headline": headline,
        "default_cover_tagline": headline,
        "skills": skills,
        **({"additional_skills": additional} if additional else {}),
        "experience": experience,
        "projects": projects,
        "certifications": certifications,
        "education": education,
        "languages": languages,
    }
    return draft, b.notes
