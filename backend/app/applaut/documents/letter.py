"""The cover letter parts code writes: date, recipient, subject, salutation,
the logistics paragraph and the thank-you. The model writes paragraphs 1-3."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")


@dataclass
class JobInfo:
    title: str
    company: str
    location: str = ""
    reference: str | None = None  # requisition id, when the posting has one
    description: str = ""


def company_display(name: str, description: str = "") -> str:
    """Job boards give the board's slug ("helsing", "isaraerospace"). Use the
    name as the posting itself writes it ("Helsing", "Isar Aerospace"), else
    capitalise the slug. A name that already has capitals is kept."""
    key = re.sub(r"[^a-z0-9]", "", name.lower())
    if not key or name != name.lower():
        return name
    pattern = r"[\s.&-]?".join(map(re.escape, key))
    # Not inside a web or mail address ("helsing.ai", "jobs@helsing.ai", "/helsing").
    found = Counter(m.group(0) for m in re.finditer(rf"(?<![\w@/.]){pattern}(?![\w@/]|\.\w)", description, re.I))
    if found:  # most frequent spelling, ALL-CAPS headings last; on a tie, one with capitals
        return max(found.items(), key=lambda kv: (kv[0] != kv[0].upper(), kv[1], kv[0] != kv[0].lower()))[0]
    return " ".join(w.capitalize() for w in re.split(r"[-_\s]+", name) if w)


def _city(location: str) -> str:
    return location.split(",")[0].strip() if location else ""


def logistics_paragraph(profile: dict, job: JobInfo) -> str:
    p, lang = profile["personal"], profile.get("languages", {})
    parts = []
    if p.get("location"):
        parts.append(f"I am based in {p['location']}.")
    for k in ("work_authorization", "availability"):
        if p.get(k):
            parts.append(p[k].rstrip(".") + ".")
    if lang.get("english") or lang.get("german"):
        spoken = [f"{name} ({lang[k]})" for k, name in (("english", "English"), ("german", "German")) if lang.get(k)]
        parts.append(f"I speak {' and '.join(spoken)}.")
    parts.append(f"I would welcome the opportunity to discuss how I can contribute to {job.company}.")
    return " ".join(parts)


def build_letter(profile: dict, job: JobInfo, paragraphs: list[str], today: date | None = None) -> dict:
    """The `cl` context for cover_letter.html.j2."""
    today = today or datetime.now(BERLIN).date()
    recipient = ["Hiring Team", job.company] + ([_city(job.location)] if _city(job.location) else [])
    subject = f"Re: Application for {job.title}" + (f" (Ref. {job.reference})" if job.reference else "")
    return {
        "tagline": profile["default_cover_tagline"],
        "date": f"{today.day} {today.strftime('%B %Y')}",
        "recipient_lines": recipient,
        "subject": subject,
        "salutation": "Dear Hiring Team,",
        "paragraphs": [*paragraphs, logistics_paragraph(profile, job), "Thank you for your time and consideration."],
        "closing": "Sincerely,",
    }
