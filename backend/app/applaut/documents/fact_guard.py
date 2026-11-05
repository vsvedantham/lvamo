"""Checks on model-written text before it goes into a document (principle 8).

Ported from the routine's `pipeline.py` (`check_numbers`, the skills check):
every number must appear in the profile (or, in the cover letter, the job
posting), and every skill on the CV must be the profile's own.
"""
from __future__ import annotations

import json
import re
from collections import Counter

from app.applaut.documents.tailor import _entries, fact_ids, mentioned, skill_names

NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")
BULLET_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?\+?%?")  # in a bullet "20+" -> "20" changes the claim

# A reworded bullet may reorder its fact, change word forms ("reducing" ->
# "Reduced") and add these joining words; any other word it adds is the model
# saying something the fact doesn't (the posting's "designed distributed
# services", "built" for "owned and maintained").
WORD_RE = re.compile(r"[a-z][a-z0-9+#]*")
JOINING_WORDS = frozenset(
    "the and with through for from into onto across using via while which that its their per over within "
    "including after before than thereby".split())
IRREGULAR = {"built": "build", "led": "lead", "ran": "run", "wrote": "write", "made": "make", "grew": "grow",
             "drove": "drive", "took": "take", "began": "begin", "brought": "bring", "kept": "keep",
             "sped": "speed", "spent": "spend", "taught": "teach", "rewrote": "rewrite", "rebuilt": "rebuild",
             "cut": "cut", "set": "set", "put": "put", "won": "win", "shipped": "ship"}

HEADLINE_MAX_WORDS = 22
BULLET_LENGTH = (0.7, 1.3)  # a reworded bullet's words, as a share of its source fact's
PARAGRAPH_WORDS = (35, 160)
LETTER_BODY_MAX_WORDS = 430  # the routine's one-page limit, whole body


# The letter is the candidate speaking. A model told about "the candidate"
# sometimes writes "In your recent role you built…"; "you" may only be the company.
FIRST_PERSON_RE = re.compile(r"\bI\b|\bI'm\b|\bI've\b|\b[Mm]y\b|\b[Mm]e\b")
ABOUT_CANDIDATE_AS_YOU_RE = re.compile(
    r"\b(you|your)\s+(recent\s+|previous\s+|current\s+)?(established|engineered|owned|built|led|implemented|"
    r"migrated|designed|developed|automated|maintained|managed|created|delivered|role at|experience|background|"
    r"work on|work at|capability|skills)\b", re.I)


def _numbers(text: str) -> set[str]:
    return set(NUM_RE.findall(text))


def _stem(word: str) -> str:
    word = IRREGULAR.get(word, word)
    for suffix in ("ing", "ied", "ies", "ed", "es", "s", "y"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[:-len(suffix)]
    return word


def new_words(source: str, text: str, vocabulary: str = "") -> list[str]:
    """Words of `text` that are not in `source` or `vocabulary` in any form,
    other than joining words and words of one or two letters."""
    known = {_stem(w) for w in WORD_RE.findall(f"{source} {vocabulary}".lower())}

    def is_known(stem: str) -> bool:
        return any(stem[:k] == k_stem[:k] for k_stem in known
                   for k in [min(5, len(stem), len(k_stem))] if k >= 3 or stem == k_stem)
    return sorted({w for w in WORD_RE.findall(text.lower())
                   if len(w) > 2 and w not in JOINING_WORDS and not is_known(_stem(w))})


def repeated_words(source: str, text: str) -> list[str]:
    """Words `text` uses more often than `source` does ("Tableau APIs, and Azure,
    Azure Key Vault"); a word the fact doesn't have may appear once."""
    def counts(s: str) -> Counter:
        return Counter(_stem(w)[:5] for w in WORD_RE.findall(s.lower()) if len(w) > 2 and w not in JOINING_WORDS)
    before = counts(source)
    return sorted(stem for stem, n in counts(text).items() if n > max(before[stem], 1))


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


CV_FIRST_PERSON_RE = re.compile(r"\b(I|I'm|I've|my|me|we|our)\b", re.I)


def check_bullet(source: str, text: str, allowed: set[str], names: dict[str, set[str]]) -> str | None:
    """A reworded CV bullet against the fact it rewords. None if it may be shown;
    otherwise why the original is shown instead. `allowed` is the canonical
    skills its own role or project mentions (its facts and technologies), so a
    rewording can't move a tool from another role onto this one. Every skill the
    fact names must stay: a rewording may reorder the fact, not thin it out,
    and may add no word of its own beyond joining words (`new_words`)."""
    if not text:
        return "empty"
    if " ".join(text.lower().split()) == " ".join(source.lower().split()):
        return "copied unchanged"
    before, after = Counter(BULLET_NUM_RE.findall(source)), Counter(BULLET_NUM_RE.findall(text))
    if before != after:  # counted: "R2" in the fact must not cover a new "2 hours"
        return f"numbers changed: {sorted(before.elements())} -> {sorted(after.elements())}"
    added = mentioned(names, text) - mentioned(names, source) - allowed
    if added:
        return f"names skills this role doesn't have: {sorted(added)}"
    dropped = mentioned(names, source) - mentioned(names, text)
    if dropped:
        return f"drops skills the fact names: {sorted(dropped)}"
    ratio = len(text.split()) / max(1, len(source.split()))
    if not BULLET_LENGTH[0] <= ratio <= BULLET_LENGTH[1]:
        return f"length {ratio:.0%} of the original"
    if CV_FIRST_PERSON_RE.search(text):
        return "first person in a CV bullet"
    first = (WORD_RE.findall(text.lower()) or [""])[0]
    if not (first.endswith("ed") or first in IRREGULAR or first == (WORD_RE.findall(source.lower()) or [""])[0]):
        return f"doesn't start with a past-tense verb: '{first}'"
    vocabulary = " ".join(n for skill in allowed | mentioned(names, source) for n in names.get(skill, ()))
    if added_words := new_words(source, text, vocabulary):
        return f"words the fact doesn't have: {added_words}"
    if repeats := repeated_words(source, text):
        return f"repeats words more often than the fact: {repeats}"
    return None


def check_fact_rewording(profile: dict, fact_id: str, text: str) -> str | None:
    """check_bullet for one of the profile's facts by id."""
    names = skill_names(profile)
    eid, source = fact_ids(profile)[fact_id]
    entry = next(e for e in _entries(profile) if e["id"] == eid)
    return check_bullet(source, text, mentioned(names, "\n".join(entry["facts"] + entry.get("technologies", []))), names)


def check_cv_skills(skill_rows: list[dict], technologies: dict[str, list[str]], profile: dict) -> list[str]:
    """Belt and braces: code builds these from the profile, so this only fails on a bug."""
    known = {n for ns in skill_names(profile).values() for n in ns}
    errors = []
    for row in skill_rows:
        errors += [f"cv.skills: '{x}' is not in the profile" for x in row["items"] if x.lower() not in known]
    for eid, tech in technologies.items():
        errors += [f"cv.{eid}.technologies: '{x}' is not in the profile" for x in tech if x.lower() not in known]
    return errors


# ---------------------------------------------------------------- bullet bank drafts

DRAFT_WORDS = (6, 45)
DUPLICATE_SIMILARITY = 0.6  # share of content words in common with an existing bullet
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9.#+/-]*")


def _names(text: str) -> list[str]:
    """What a bullet names: words after the first with a capital letter, a
    digit or ".#+" in them ("Kafka", "AWS", "S3", "Node.js", "C#")."""
    out = []
    for tok in TOKEN_RE.findall(text)[1:]:
        tok = tok.rstrip(".-/")
        if tok and (not tok.islower() or any(c.isdigit() or c in "#+" for c in tok) or "." in tok):
            out.append(tok)
    return out


def _content(text: str) -> set[str]:
    return {_stem(w)[:5] for w in WORD_RE.findall(text.lower()) if len(w) > 2 and w not in JOINING_WORDS}


def _similarity(a: str, b: str) -> float:
    x, y = _content(a), _content(b)
    return len(x & y) / max(1, min(len(x), len(y)))


# A tool's usual short form in notes: "k8s" in the notes covers "Kubernetes" in a draft.
SHORT_FORMS = {"kubernetes": "k8s", "postgresql": "postgres", "javascript": "js", "typescript": "ts"}


def _named_in(name: str, known: str) -> bool:
    """`name` (its singular, or its short form) as a whole word of `known`
    ("SQL" isn't in "PostgreSQL")."""
    forms = {name.lower(), name.lower().rstrip("s"), SHORT_FORMS.get(name.lower(), "")}
    return any(re.search(r"(?<![a-z0-9])" + re.escape(n) + r"(?![a-z0-9])", known) for n in forms if n)


# Verbs that claim the lead on something, and the words in the notes that back
# each one: "together with the platform team" never becomes "Led".
LEAD_CLAIMS = {
    "led": "lead", "leading": "lead", "managed": "manage", "owned": "own", "headed": "head",
    "spearheaded": "spearhead", "directed": "direct", "oversaw": "oversee", "supervised": "supervise",
    "architected": "architect", "championed": "champion", "drove": "drive",
}
LEAD_BACKING = {
    "lead": {"lead", "led", "leading", "leader", "leads"},
    "manage": {"manage", "managed", "managing", "manager", "management"},
    "own": {"own", "owned", "owning", "owner", "ownership"},
    "head": {"head", "headed", "heading"},
    "spearhead": {"spearhead", "spearheaded"},
    "direct": {"direct", "directed", "directing", "director"},
    "oversee": {"oversee", "oversaw", "overseeing", "oversight"},
    "supervise": {"supervise", "supervised", "supervising", "supervisor"},
    "architect": {"architect", "architected", "architecture"},
    "champion": {"champion", "championed"},
    "drive": {"drive", "drove", "driving"},
}


def _lead_claim(text: str, source_words: set[str]) -> str | None:
    """The bullet's lead claim ("Led", "Managed", ...) when the notes and the
    role's bullets don't back it: its opening verb, or "led"/"leading" anywhere."""
    words = re.findall(r"[a-z']+", text.lower())
    claims = words[:1] + [w for w in words[1:] if w in ("led", "leading")]
    for w in claims:
        root = LEAD_CLAIMS.get(w)
        if root and not (LEAD_BACKING[root] & source_words):
            return w
    return None


def check_drafts(profile: dict, entry: dict, notes: str, texts: list[str]) -> tuple[list[dict], list[dict]]:
    """The writer's drafted bullets for one role, from the user's notes: (kept,
    left out). Kept: [{"text", "confirm": numbers that are in neither the notes
    nor the role, for the user to check}]. Left out: [{"text", "reason"}] for a
    bullet that names something the user didn't give (a tool, product, team),
    claims the lead ("Led", "Managed") where the notes don't, repeats an existing bullet or another draft, is in the first person, or
    is too short or long. The user approves every kept one before it is saved."""
    names = skill_names(profile)
    known = " ".join([notes, entry.get("title", ""), entry.get("company", ""), entry.get("name", ""),
                      *entry["facts"], *entry.get("technologies", []), *(n for ns in names.values() for n in ns)]).lower()
    source_numbers = set(NUM_RE.findall(f"{notes} {' '.join(entry['facts'])}"))
    source_words = set(re.findall(r"[a-z']+", f"{notes} {' '.join(entry['facts'])}".lower()))
    kept: list[dict] = []
    left_out: list[dict] = []
    for text in texts:
        text = " ".join((text or "").split())
        words = len(text.split())
        unknown = [n for n in dict.fromkeys(_names(text)) if not _named_in(n, known)]
        if not DRAFT_WORDS[0] <= words <= DRAFT_WORDS[1]:
            reason = f"{words} words; a CV bullet needs {DRAFT_WORDS[0]}-{DRAFT_WORDS[1]}"
        elif CV_FIRST_PERSON_RE.search(text):
            reason = "written in the first person"
        elif unknown:
            reason = f"names {', '.join(unknown)}, which isn't in your notes, this role or your skills"
        elif claim := _lead_claim(text, source_words):
            reason = f"says you {claim} it, which your notes don't say"
        elif any(_similarity(text, f) >= DUPLICATE_SIMILARITY for f in entry["facts"]):
            reason = "already one of this role's bullets"
        elif any(_similarity(text, k["text"]) >= DUPLICATE_SIMILARITY for k in kept):
            reason = "repeats another draft"
        else:
            confirm = [n for n in dict.fromkeys(BULLET_NUM_RE.findall(text))
                       if NUM_RE.match(n).group(0) not in source_numbers]
            kept.append({"text": text, "confirm": confirm})
            continue
        left_out.append({"text": text, "reason": reason})
    return kept, left_out
