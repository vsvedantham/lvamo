"""The user's own CV template (APPLAUT_AI_ENGINE_DESIGN.md §7.3, plan §5).

The look is kept by keeping the user's own .docx and replacing only the text
that changes per job:

- the headline line under the name, if the CV has one;
- the items of each skills row ("Languages: Python, SQL"; the label stays);
- each job's or project's bullets (one loop in the first bullet's formatting);
- each job's "Technologies: ..." line (its label stays).

Everything else (name, contact lines, headings, role titles, dates, education,
a summary paragraph) stays exactly as the user wrote it. The model only labels
the lines; code builds the template, and a round trip (the template filled with
the upload's own text must give back the upload's text, line for line) proves
it before the user can switch it on.

At render time each slot is filled from the master profile: a role's bullets
come from the profile entry whose company and title (or project name) the
role's heading names; a skills row from the profile row with the same label. A
role or row with no match keeps the upload's own text.
"""
from __future__ import annotations

import copy
import io
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field

from docx import Document
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

LABELS = ("name", "headline", "contact", "section", "skills", "role", "bullet", "technologies", "other")
HEADLINE_MAX_WORDS = 25
SEPARATORS = (" | ", " · ", " • ", "; ", ", ", " / ")
# A bullet typed by hand ("• Built ...", "- Built ..."): the mark stays, the text after it is filled.
TYPED_BULLET = re.compile(r"^\s*[•·▪◦‣∙\-–*]\s*")
JINJA_MARKS = ("{{", "{%", "{#", "}}", "%}", "#}")
SOFFICE_TIMEOUT = 90
MC_FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"

# Fonts LibreOffice replaces with a metric-compatible one (same widths, so the
# same line breaks): not a substitution worth telling the user about.
METRIC_TWINS = {"calibri": "Carlito", "cambria": "Caladea", "arial": "Liberation Sans",
                "times new roman": "Liberation Serif", "courier new": "Liberation Mono",
                "helvetica": "Liberation Sans", "times": "Liberation Serif"}


class TemplateError(ValueError):
    """The .docx can't be made into a template; `problems` say why, for the user."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


# ---------------------------------------------------------------- reading

@dataclass
class Line:
    index: int
    text: str
    style: str


def _paragraphs(doc) -> list[Paragraph]:
    """Every paragraph of the body in document order: plain ones, table cells,
    content controls and text boxes (not a drawing's duplicate fallback copy)."""
    out = []
    for p in doc.element.body.iter(qn("w:p")):
        if any(a.tag == MC_FALLBACK for a in p.iterancestors()):
            continue
        out.append(Paragraph(p, doc._body))
    return out


def _open(data: bytes):
    try:
        return Document(io.BytesIO(data))
    except Exception as exc:  # python-docx raises several kinds for a bad file
        raise TemplateError([f"this isn't a .docx file Applaut can read ({type(exc).__name__})"])


def read_lines(data: bytes) -> list[Line]:
    doc = _open(data)
    lines = []
    for i, p in enumerate(_paragraphs(doc)):
        try:
            style = p.style.name if p.style is not None else ""
        except Exception:
            style = ""
        lines.append(Line(i, p.text, style or ""))
    return lines


def lines_text(data: bytes) -> list[str]:
    return [" ".join(p.text.split()) for p in _paragraphs(_open(data))]


# ---------------------------------------------------------------- slots

@dataclass
class Row:
    key: str            # context key, e.g. "r3"
    label: str          # "Languages"
    sep: str            # how the upload separates items
    original: str       # the items as uploaded


@dataclass
class Block:
    heading: str                    # the role's or project's own lines, joined
    bullets_key: str | None = None  # "b2"
    original_bullets: list[str] = field(default_factory=list)
    tech_key: str | None = None     # "t2"
    tech_sep: str = ", "
    original_tech: str = ""


@dataclass
class Slots:
    headline: bool = False
    original_headline: str = ""
    rows: list[Row] = field(default_factory=list)
    blocks: list[Block] = field(default_factory=list)

    def to_json(self) -> dict:
        return {"headline": self.headline, "original_headline": self.original_headline,
                "rows": [r.__dict__ for r in self.rows],
                "blocks": [{**b.__dict__, "original_bullets": list(b.original_bullets)} for b in self.blocks]}

    @classmethod
    def from_json(cls, d: dict) -> "Slots":
        return cls(headline=d["headline"], original_headline=d.get("original_headline", ""),
                   rows=[Row(**r) for r in d["rows"]], blocks=[Block(**b) for b in d["blocks"]])


def _split_label(text: str) -> tuple[str, int] | None:
    """("Languages", offset where the items start) for "Languages: Python, SQL"
    (or a tab instead of the colon); None when the line has no label."""
    m = re.match(r"^\s*([^:\t]{1,40}?)\s*[:\t]\s*", text)
    if not m or not text[m.end():].strip():
        return None
    return m.group(1).strip(), m.end()


def _separator(items: str) -> str:
    counts = {s: items.count(s) for s in SEPARATORS}
    best = max(counts, key=lambda s: counts[s])
    return best if counts[best] else ", "


def _split_items(items: str, sep: str) -> list[str]:
    return [x.strip() for x in items.split(sep.strip() if sep.strip() else sep) if x.strip()]


# ---------------------------------------------------------------- building

def _runs_text(p: Paragraph) -> str:
    return "".join(r.text for r in p.runs)


def _clear_after(p: Paragraph, keep: int) -> None:
    for r in p.runs[keep:]:
        r._r.getparent().remove(r._r)


def _set_text(p: Paragraph, text: str) -> None:
    """The paragraph's text becomes `text`, in its first run's formatting."""
    runs = p.runs
    runs[0].text = text
    _clear_after(p, 1)


def _replace_from(p: Paragraph, offset: int, text: str) -> None:
    """Keep the paragraph's text before `offset` (and its runs' formatting) and
    put `text` after it, in the formatting of the run at `offset`."""
    pos = 0
    for i, r in enumerate(p.runs):
        end = pos + len(r.text)
        if offset < end or (offset == end and i == len(p.runs) - 1):
            head = r.text[: offset - pos]
            if head:
                tail = copy.deepcopy(r._r)
                r._r.addnext(tail)
                r.text = head
                p.runs[i + 1].text = text
                _clear_after(p, i + 2)
            else:
                r.text = text
                _clear_after(p, i + 1)
            return
        pos = end
    raise AssertionError("offset beyond the paragraph")


def _tag_paragraph(like: Paragraph, tag: str, before: bool) -> None:
    """A paragraph holding only a docxtpl paragraph tag ({%p ... %}), which
    docxtpl removes when rendering."""
    new = copy.deepcopy(like._p)
    for child in list(new):
        if child.tag != qn("w:pPr"):
            new.remove(child)
    r = new.makeelement(qn("w:r"), {})
    t = r.makeelement(qn("w:t"), {})
    t.text = tag
    r.append(t)
    new.append(r)
    (like._p.addprevious if before else like._p.addnext)(new)


def _check_labels(lines: list[Line], labels: list[str]) -> list[str]:
    """The model's labels made consistent: one headline at most and only a
    short one; bullets and technologies lines only inside a role's block."""
    labels = [lab if lab in LABELS else "other" for lab in labels]
    seen_headline = False
    in_block = False
    for i, (line, lab) in enumerate(zip(lines, labels)):
        if lab == "headline":
            if seen_headline or len(line.text.split()) > HEADLINE_MAX_WORDS or not line.text.strip():
                labels[i] = "other"
            seen_headline = True
        if lab == "role":
            in_block = True
        elif lab in ("section", "name", "contact", "skills"):
            in_block = False
        elif lab in ("bullet", "technologies") and not in_block:
            labels[i] = "other"
        if not line.text.strip():
            labels[i] = "other"
    return labels


@dataclass
class Built:
    template: bytes
    slots: Slots
    labels: list[str]
    notes: list[str] = field(default_factory=list)  # lines left as uploaded, and why


def build(data: bytes, labels: list[str]) -> Built:
    """The upload made into a docxtpl template from the model's labels (one per
    line of read_lines). Raises TemplateError when it can't be done faithfully."""
    doc = _open(data)
    paras = _paragraphs(doc)
    lines = [Line(i, p.text, "") for i, p in enumerate(paras)]
    if len(labels) != len(lines):
        raise TemplateError([f"the labels don't match the file ({len(labels)} for {len(lines)} lines)"])
    labels = _check_labels(lines, labels)
    problems = []
    for i, p in enumerate(paras):
        if any(m in p.text for m in JINJA_MARKS):
            problems.append(f'line {i + 1} ("{p.text[:40]}") contains "{{" or "{{%", which the template engine '
                            "would read as its own; remove them from the file")
    if problems:
        raise TemplateError(problems)

    slots = Slots()
    # Group the blocks first, before the document changes under us.
    blocks: list[dict] = []
    for i, lab in enumerate(labels):
        if lab == "role":
            if not blocks or blocks[-1]["bullets"] or blocks[-1]["tech"] is not None or blocks[-1]["closed"]:
                blocks.append({"heading": [], "bullets": [], "tech": None, "closed": False})
            blocks[-1]["heading"].append(i)
        elif lab == "bullet" and blocks:
            blocks[-1]["bullets"].append(i)
        elif lab == "technologies" and blocks and blocks[-1]["tech"] is None:
            blocks[-1]["tech"] = i
        elif lab in ("section", "name", "contact", "skills") and blocks:
            blocks[-1]["closed"] = True

    notes: list[str] = []

    def editable(i: int) -> bool:
        p = paras[i]
        if not p.runs or _runs_text(p) != p.text:
            notes.append(f'line {i + 1} ("{p.text[:40]}") has a link, field or text box text Applaut '
                            "can't fill; it stays as uploaded")
            return False
        return True

    # Headline
    for i, lab in enumerate(labels):
        if lab == "headline" and editable(i):
            slots.headline, slots.original_headline = True, " ".join(paras[i].text.split())
            _set_text(paras[i], "{{ s.h }}")

    # Skills rows
    for i, lab in enumerate(labels):
        if lab != "skills":
            continue
        split = _split_label(paras[i].text)
        if split is None or not editable(i):
            continue
        label, offset = split
        items = paras[i].text[offset:]
        row = Row(key=f"r{len(slots.rows)}", label=label, sep=_separator(items), original=" ".join(items.split()))
        slots.rows.append(row)
        _replace_from(paras[i], offset, "{{ s.%s }}" % row.key)

    # Roles and projects
    fatal = []
    for n, b in enumerate(blocks):
        block = Block(heading=" ".join(" ".join(paras[i].text.split()) for i in b["heading"]))
        bullets = b["bullets"]
        if bullets:
            parents = {paras[i]._p.getparent() for i in bullets}
            if bullets != list(range(bullets[0], bullets[-1] + 1)) or len(parents) != 1:
                fatal.append(f'the bullets under "{block.heading[:60]}" aren\'t one list (something sits between '
                             "them); Applaut needs each job's bullets together")
                continue
            if all(editable(i) for i in bullets):
                block.bullets_key = f"b{n}"
                marks = [TYPED_BULLET.match(paras[i].text) for i in bullets]
                typed = all(marks)
                block.original_bullets = [" ".join((paras[i].text[m.end():] if typed else paras[i].text).split())
                                          for i, m in zip(bullets, marks)]
                first = paras[bullets[0]]
                if typed:
                    _replace_from(first, marks[0].end(), "{{ b }}")
                else:
                    _set_text(first, "{{ b }}")
                _tag_paragraph(first, "{%%p for b in s.%s %%}" % block.bullets_key, before=True)
                _tag_paragraph(first, "{%p endfor %}", before=False)
                for i in bullets[1:]:
                    paras[i]._p.getparent().remove(paras[i]._p)
        t = b["tech"]
        if t is not None:
            split = _split_label(paras[t].text)
            if split is not None and editable(t):
                _, offset = split
                items = paras[t].text[offset:]
                block.tech_key, block.tech_sep = f"t{n}", _separator(items)
                block.original_tech = " ".join(items.split())
                _replace_from(paras[t], offset, "{{ s.%s }}" % block.tech_key)
        slots.blocks.append(block)
    if fatal:
        raise TemplateError(fatal)

    out = io.BytesIO()
    doc.save(out)
    return Built(out.getvalue(), slots, labels, notes)


# ---------------------------------------------------------------- filling

def round_trip_context(slots: Slots) -> dict:
    """The upload's own text in every slot: rendering with it must give the upload back."""
    s = {"h": slots.original_headline}
    s.update({r.key: r.original for r in slots.rows})
    for b in slots.blocks:
        if b.bullets_key:
            s[b.bullets_key] = list(b.original_bullets)
        if b.tech_key:
            s[b.tech_key] = b.original_tech
    return s


def match_entries(slots: Slots, profile: dict) -> dict[int, str]:
    """Block index → the profile entry it shows: the entry whose company (2
    points) and title (1) the block's heading names, or a project by name (2).
    Ties and entries already taken stay unmatched (the upload's text is kept)."""
    out: dict[int, str] = {}
    taken: set[str] = set()
    for n, b in enumerate(slots.blocks):
        h = b.heading.casefold()
        scores = []
        for e in profile.get("experience", []):
            s = 2 * (e["company"].casefold() in h) + (e["title"].casefold() in h)
            scores.append((s, e["id"]))
        for e in profile.get("projects", []):
            scores.append((2 * (e["name"].casefold() in h), e["id"]))
        scores = sorted((x for x in scores if x[0] >= 2 and x[1] not in taken), reverse=True)
        if scores and (len(scores) == 1 or scores[0][0] > scores[1][0]):
            out[n] = scores[0][1]
            taken.add(scores[0][1])
    return out


def match_rows(slots: Slots, profile: dict) -> dict[str, str]:
    """Row key → the profile skills row with the same label (case and spaces aside)."""
    labels = {" ".join(k.split()).casefold(): k for k in profile.get("skills", {})}
    return {r.key: labels[key] for r in slots.rows if (key := " ".join(r.label.split()).casefold()) in labels}


def job_context(slots: Slots, profile: dict, headline: str, skill_rows: list[dict], picks: dict) -> dict:
    """The slots filled for one job: the writer's headline, each matched row's
    items in the job's order, each matched entry's picked bullets and technologies."""
    s = round_trip_context(slots)
    if slots.headline:
        s["h"] = headline
    rows = {r["label"]: r["items"] for r in skill_rows}
    for key, label in match_rows(slots, profile).items():
        row = next(r for r in slots.rows if r.key == key)
        if rows.get(label):
            s[key] = row.sep.join(rows[label])
    for n, entry_id in match_entries(slots, profile).items():
        b, pick = slots.blocks[n], picks.get(entry_id)
        if pick is None:
            continue
        if b.bullets_key:
            s[b.bullets_key] = pick.bullets
        if b.tech_key and pick.technologies:
            s[b.tech_key] = b.tech_sep.join(pick.technologies)
    return s


def render(template: bytes, s: dict) -> bytes:
    from docxtpl import DocxTemplate

    tpl = DocxTemplate(io.BytesIO(template))
    tpl.render({"s": s}, autoescape=True)
    out = io.BytesIO()
    tpl.save(out)
    return out.getvalue()


def round_trip(source: bytes, built: Built) -> list[str]:
    """Differences between the upload and the template filled with the upload's
    own text, line by line (empty: the template is faithful)."""
    want = lines_text(source)
    got = lines_text(render(built.template, round_trip_context(built.slots)))
    diffs = []
    for i in range(max(len(want), len(got))):
        a = want[i] if i < len(want) else "(no line)"
        b = got[i] if i < len(got) else "(no line)"
        if a != b:
            diffs.append(f'line {i + 1}: "{a[:80]}" came back as "{b[:80]}"')
    return diffs


# ---------------------------------------------------------------- PDF and fonts

def to_pdf(data: bytes) -> tuple[bytes, int]:
    """The .docx as PDF via LibreOffice (headless), and its page count."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise RuntimeError("LibreOffice isn't installed in this image")
    with tempfile.TemporaryDirectory(prefix="applaut-docx-") as tmp:
        src = os.path.join(tmp, "cv.docx")
        with open(src, "wb") as f:
            f.write(data)
        profile_dir = os.path.join(tmp, f"lo-{uuid.uuid4().hex}")
        result = subprocess.run(
            [soffice, f"-env:UserInstallation=file://{profile_dir}", "--headless", "--norestore",
             "--convert-to", "pdf", "--outdir", tmp, src],
            capture_output=True, timeout=SOFFICE_TIMEOUT, env={**os.environ, "HOME": tmp})
        pdf_path = os.path.join(tmp, "cv.pdf")
        if result.returncode != 0 or not os.path.exists(pdf_path):
            raise RuntimeError(f"LibreOffice couldn't convert the file: {result.stderr.decode(errors='replace')[:300]}")
        pdf = open(pdf_path, "rb").read()
    return pdf, pdf_pages(pdf)


def pdf_pages(pdf: bytes) -> int:
    from pdfminer.pdfpage import PDFPage

    return sum(1 for _ in PDFPage.get_pages(io.BytesIO(pdf)))


def _installed_fonts() -> set[str]:
    try:
        out = subprocess.run(["fc-list", ":", "family"], capture_output=True, timeout=20).stdout.decode()
    except (OSError, subprocess.TimeoutExpired):
        return set()
    return {name.strip().casefold() for line in out.splitlines() for name in line.split(",")}


def fonts_used(data: bytes) -> set[str]:
    """Font families the text of the .docx is set in: its runs, the styles its
    paragraphs and runs use (with the styles they're based on), the document
    defaults and the theme's body and heading fonts. Styles nothing uses don't count."""
    doc = _open(data)
    body = doc.element.body
    names: set[str] = set()

    def add(el) -> None:
        for rf in el.iter(qn("w:rFonts")):
            for attr in ("w:ascii", "w:hAnsi"):
                if v := rf.get(qn(attr)):
                    names.add(v)

    add(body)
    styles_el = doc.styles.element
    by_id = {st.get(qn("w:styleId")): st for st in styles_el.iter(qn("w:style"))}
    used = {el.get(qn("w:val")) for tag in ("w:pStyle", "w:rStyle", "w:tblStyle") for el in body.iter(qn(tag))}
    used |= {st.get(qn("w:styleId")) for st in by_id.values() if st.get(qn("w:default")) == "1"}
    seen: set[str] = set()
    while used:
        sid = used.pop()
        if sid in seen or sid not in by_id:
            continue
        seen.add(sid)
        add(by_id[sid])
        based = by_id[sid].find(qn("w:basedOn"))
        if based is not None:
            used.add(based.get(qn("w:val")))
    for defaults in styles_el.iter(qn("w:docDefaults")):
        add(defaults)
    for rel in doc.part.rels.values():
        if rel.reltype.endswith("/theme"):
            xml = rel.target_part.blob.decode("utf-8", errors="replace")
            for kind in ("majorFont", "minorFont"):
                m = re.search(rf'<a:{kind}>\s*<a:latin typeface="([^"]*)"', xml)
                if m:
                    names.add(m.group(1))
    return {n for n in names if n and not n.startswith("+")}


def font_report(data: bytes) -> list[dict]:
    """[{font, shown_as}] for each font the server doesn't have: LibreOffice
    shows it in another font, so line breaks may differ from Word."""
    installed = _installed_fonts()
    out = []
    for name in sorted(fonts_used(data)):
        key = name.casefold()
        if key in installed:
            continue
        if key in METRIC_TWINS:
            continue  # same widths: nothing the user would see
        out.append({"font": name, "shown_as": "a similar font"})
    return out
