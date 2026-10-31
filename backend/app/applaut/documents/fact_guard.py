"""Checks on model-written text before it goes into a document (principle 8).

Ported from the routine's `pipeline.py` (`check_numbers`, the skills check):
every number must appear in the profile (or, in the cover letter, the job
posting), and every skill on the CV must be the profile's own.
"""
from __future__ import annotations

import json
import re

from app.applaut.documents.tailor import skill_names

NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")

HEADLINE_MAX_WORDS = 22
PARAGRAPH_WORDS = (35, 160)
LETTER_BODY_MAX_WORDS = 430  # the routine's one-page limit, whole body


# The letter is the candidate speaking. A model told about "the candidate"
# sometimes writes "In your recent role you built…"; "you" may only be the company.
FIRST_PERSON_RE = re.compile(r"\b(I|I'm|I've|my|me)\b")
ABOUT_CANDIDATE_AS_YOU_RE = re.compile(
    r"\b(you|your)\s+(recent\s+|previous\s+|current\s+)?(established|engineered|owned|built|led|implemented|"
    r"migrated|designed|developed|automated|maintained|managed|created|delivered|role at|experience|background|"
    r"work on|work at|capability|skills)\b", re.I)


def _numbers(text: str) -> set[str]:
    return set(NUM_RE.findall(text))


def check_written(written: dict, profile: dict, job_text: str) -> list[str]:
    """`written` is the model's {"headline": str, "paragraphs": [p1, p2, p3]}.
    Returns problems, each phrased so it can be sent back to the model."""
    errors: list[str] = []
    headline = (written.get("headline") or "").strip()
    paras = [p.strip() for p in written.get("paragraphs") or []]
    profile_text = json.dumps(profile, ensure_ascii=False)

    if not headline:
        errors.append("headline is empty")
    elif len(headline.split()) > HEADLINE_MAX_WORDS:
        errors.append(f"headline has {len(headline.split())} words; keep it under {HEADLINE_MAX_WORDS}")
    for n in sorted(_numbers(headline) - _numbers(profile_text)):
        errors.append(f"headline: number '{n}' is not in the profile - remove it")

    if len(paras) != 3:
        errors.append(f"write exactly 3 paragraphs (got {len(paras)})")
    allowed = _numbers(profile_text) | _numbers(job_text)
    for i, p in enumerate(paras, 1):
        words = len(p.split())
        if not PARAGRAPH_WORDS[0] <= words <= PARAGRAPH_WORDS[1]:
            errors.append(f"paragraph {i} has {words} words; use {PARAGRAPH_WORDS[0]}-{PARAGRAPH_WORDS[1]}")
        for n in sorted(_numbers(p) - allowed):
            errors.append(f"paragraph {i}: number '{n}' is not in the profile or the job posting - remove it")
        if ABOUT_CANDIDATE_AS_YOU_RE.search(p) or not FIRST_PERSON_RE.search(p):
            errors.append(f"paragraph {i} must be in the first person, as the candidate (I, my); "
                          "'you'/'your' may only mean the company")
    return errors


def check_cv_skills(skill_rows: list[dict], technologies: dict[str, list[str]], profile: dict) -> list[str]:
    """Belt and braces: code builds these from the profile, so this only fails on a bug."""
    known = {n for ns in skill_names(profile).values() for n in ns}
    errors = []
    for row in skill_rows:
        errors += [f"cv.skills: '{x}' is not in the profile" for x in row["items"] if x.lower() not in known]
    for eid, tech in technologies.items():
        errors += [f"cv.{eid}.technologies: '{x}' is not in the profile" for x in tech if x.lower() not in known]
    return errors
