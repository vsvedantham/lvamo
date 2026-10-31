"""Code-side tailoring: which profile skills a job asks for, which bullets to
show for each role, and in what order skills and technologies appear.

No model involved. Every bullet shown is one of the user's own `facts`,
unchanged (principle 8); tailoring is choosing and ordering.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.applaut.documents.profile_schema import bullet_limits

_NUM = re.compile(r"\d")


def skill_names(profile: dict) -> dict[str, set[str]]:
    """Canonical skill → every name it goes by (lowercase), from the skill
    rows, additional skills, technologies and `skill_aliases`."""
    names: dict[str, set[str]] = {}

    def add(skill: str) -> None:
        names.setdefault(skill, set()).add(skill.lower())

    for items in profile["skills"].values():
        for s in items:
            add(s)
    for s in profile.get("additional_skills", []):
        add(s)
    for e in profile["experience"] + profile.get("projects", []):
        for s in e.get("technologies", []):
            add(s)
    for canonical, aliases in profile.get("skill_aliases", {}).items():
        add(canonical)
        names[canonical] |= {a.lower() for a in aliases}
    return names


def _pattern(name: str) -> re.Pattern:
    # word boundaries that also work for names like "C#", "Node.js", "CI/CD"
    return re.compile(r"(?<![\w#+.])" + re.escape(name) + r"(?![\w#+])", re.I)


def mentioned(names: dict[str, set[str]], text: str) -> set[str]:
    """Canonical skills mentioned anywhere in `text`."""
    return {skill for skill, ns in names.items() if any(_pattern(n).search(text) for n in ns)}


def job_skills(profile: dict, job_text: str, hints: list[str] | None = None) -> set[str]:
    """The profile skills this job asks for. `hints` are the job's must-haves as
    extracted at scoring time (their matched profile skills count too)."""
    names = skill_names(profile)
    found = mentioned(names, job_text)
    if hints:
        found |= mentioned(names, "\n".join(hints))
    return found


@dataclass
class EntryPick:
    id: str
    bullets: list[str]
    technologies: list[str]
    dropped: list[str] = field(default_factory=list)  # lowest-ranked first
    min_bullets: int = 1


_WORD = re.compile(r"[a-zäöüß][a-zäöüß-]{3,}")
_STOP = set("""with from that this have will your their they them were been into over more than such
also each using used across within about other which while where when what must should would could
team teams work working role roles experience years strong good very able skills knowledge""".split())


def job_words(job_text: str) -> set[str]:
    """Content words the job repeats (2+ times): what it is really about."""
    words = [w for w in _WORD.findall(job_text.lower()) if w not in _STOP]
    return {w for w in set(words) if words.count(w) >= 2}


def _rank_facts(facts: list[str], names: dict[str, set[str]], wanted: set[str], words: set[str]) -> list[str]:
    def score(i_fact):
        i, fact = i_fact
        hits = len(mentioned(names, fact) & wanted)
        overlap = len(set(_WORD.findall(fact.lower())) & words)
        return (-(2 * hits + 0.5 * overlap + (1 if _NUM.search(fact) else 0)), i)  # ties keep profile order
    return [f for _, f in sorted(enumerate(facts), key=score)]


def _order(items: list[str], names: dict[str, set[str]], wanted: set[str]) -> list[str]:
    """Items the job wants first, otherwise profile order."""
    hit = [x for x in items if mentioned(names, x) & wanted]
    return hit + [x for x in items if x not in hit]


def pick_entries(profile: dict, wanted: set[str], job_text: str = "") -> dict[str, EntryPick]:
    """Per experience/project: as many of its best facts as its limit allows.
    `fit` later drops the lowest-ranked ones if the CV runs over two pages."""
    names = skill_names(profile)
    words = job_words(job_text)
    picks: dict[str, EntryPick] = {}
    for kind in ("experience", "projects"):
        for i, e in enumerate(profile.get(kind, [])):
            lo, hi = bullet_limits(e, i if kind == "experience" else 1)
            ranked = _rank_facts(e["facts"], names, wanted, words)
            lo = min(lo, len(ranked))
            picks[e["id"]] = EntryPick(
                id=e["id"], bullets=ranked[:hi], technologies=_order(e.get("technologies", []), names, wanted),
                dropped=[], min_bullets=lo,
            )
    return picks


def drop_one(picks: dict[str, EntryPick], profile: dict, wanted: set[str]) -> bool:
    """Remove the least relevant bullet among entries above their minimum,
    preferring older entries. False when nothing can be dropped."""
    names = skill_names(profile)
    order = [e["id"] for e in profile.get("projects", [])][::-1] + [e["id"] for e in profile["experience"]][::-1]
    best = None
    for rank, eid in enumerate(order):
        p = picks[eid]
        if len(p.bullets) <= p.min_bullets:
            continue
        last = p.bullets[-1]
        relevance = len(mentioned(names, last) & wanted)
        key = (relevance, -rank)  # least relevant first; among equals, the oldest entry
        if best is None or key < best[0]:
            best = (key, eid)
    if best is None:
        return False
    p = picks[best[1]]
    p.dropped.insert(0, p.bullets.pop())
    return True


def order_skill_rows(profile: dict, wanted: set[str]) -> list[dict]:
    """The profile's skill rows, labels and spelling unchanged, the job's
    matching skills first in each row."""
    names = skill_names(profile)
    return [{"label": label, "items": _order(items, names, wanted)} for label, items in profile["skills"].items()]
