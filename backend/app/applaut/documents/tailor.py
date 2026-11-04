"""Tailoring: which profile skills a job asks for, which bullets to show for
each role, and in what order skills and technologies appear.

Two ways in. `pick_entries` is code only: the user's own `facts`, unchanged,
ranked by the job's words (the layout preview, and the fallback). `apply_picks`
takes the writer model's choice: fact ids it ranked for the job and each
fact reworded for it; every reworded bullet is checked against its source fact
(`fact_guard.check_bullet`) and falls back to the original on its own, and
code fills any role the model left below its minimum (principle 8).
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


def names_as_written(names: dict[str, set[str]], text: str) -> list[str]:
    """The skills `text` mentions, spelled as `text` spells them, in order."""
    found = set()
    for ns in names.values():
        for n in sorted(ns, key=len, reverse=True):
            if m := _pattern(n).search(text):
                found.add(m.group(0))
                break
    return sorted(found, key=lambda s: text.lower().find(s.lower()))


def job_skills(profile: dict, job_text: str, hints: list[str] | None = None) -> set[str]:
    """The profile skills this job asks for. `hints` are the job's must-haves as
    extracted at scoring time (their matched profile skills count too)."""
    names = skill_names(profile)
    found = mentioned(names, job_text)
    if hints:
        found |= mentioned(names, "\n".join(hints))
    return found


@dataclass
class Bullet:
    fact_id: str           # "<entry id>.<n>", n from 1, in profile order
    original: str          # the fact as the profile has it
    text: str              # what the CV shows: the reworded text, or the original
    rank: tuple            # lower = more relevant; the fit loop drops the highest first
    tailored: bool = False
    note: str | None = None  # why the original is shown, when the model reworded it


@dataclass
class EntryPick:
    id: str
    items: list[Bullet]
    technologies: list[str]
    dropped: list[Bullet] = field(default_factory=list)  # lowest-ranked first
    min_bullets: int = 1

    @property
    def bullets(self) -> list[str]:
        return [b.text for b in self.items]


def fact_ids(profile: dict) -> dict[str, tuple[str, str]]:
    """Fact id → (entry id, fact), for every role and project."""
    return {f"{e['id']}.{n}": (e["id"], fact)
            for e in profile["experience"] + profile.get("projects", [])
            for n, fact in enumerate(e["facts"], 1)}


def entry_limits(profile: dict) -> dict[str, tuple[int, int]]:
    """Entry id → (min, max) bullets, the minimum capped at how many facts it has."""
    out = {}
    for kind in ("experience", "projects"):
        for i, e in enumerate(profile.get(kind, [])):
            lo, hi = bullet_limits(e, i if kind == "experience" else 1)
            out[e["id"]] = (min(lo, len(e["facts"])), hi)
    return out


_WORD = re.compile(r"[a-zäöüß][a-zäöüß-]{3,}")
_STOP = set("""with from that this have will your their they them were been into over more than such
also each using used across within about other which while where when what must should would could
team teams work working role roles experience years strong good very able skills knowledge""".split())


def job_words(job_text: str) -> set[str]:
    """Content words the job repeats (2+ times): what it is really about."""
    words = [w for w in _WORD.findall(job_text.lower()) if w not in _STOP]
    return {w for w in set(words) if words.count(w) >= 2}


def _rank_facts(facts: list[str], names: dict[str, set[str]], wanted: set[str],
                words: set[str]) -> list[tuple[int, str, int]]:
    """(profile index, fact, skill hits), best first."""
    def score(i_fact):
        i, fact = i_fact
        hits = len(mentioned(names, fact) & wanted)
        overlap = len(set(_WORD.findall(fact.lower())) & words)
        return (-(2 * hits + 0.5 * overlap + (1 if _NUM.search(fact) else 0)), i)  # ties keep profile order
    return [(i, f, len(mentioned(names, f) & wanted)) for i, f in sorted(enumerate(facts), key=score)]


def _code_bullet(entry_id: str, entry_order: int, pos: int, i: int, fact: str, hits: int) -> Bullet:
    # Ranked after every model pick (1, …); least relevant, then oldest entry, dropped first.
    return Bullet(f"{entry_id}.{i + 1}", fact, fact, (1, -hits, entry_order, pos))


def _order(items: list[str], names: dict[str, set[str]], wanted: set[str]) -> list[str]:
    """Items the job wants first, otherwise profile order."""
    hit = [x for x in items if mentioned(names, x) & wanted]
    return hit + [x for x in items if x not in hit]


def _entries(profile: dict) -> list[dict]:
    """Experience newest first, then projects: the order entries are aged in."""
    return profile["experience"] + profile.get("projects", [])


def pick_entries(profile: dict, wanted: set[str], job_text: str = "") -> dict[str, EntryPick]:
    """Code only: per experience/project, as many of its best facts as its limit
    allows. `fit` later drops the lowest-ranked ones if the CV runs over two pages."""
    names = skill_names(profile)
    words = job_words(job_text)
    limits = entry_limits(profile)
    picks: dict[str, EntryPick] = {}
    for order, e in enumerate(_entries(profile)):
        lo, hi = limits[e["id"]]
        ranked = _rank_facts(e["facts"], names, wanted, words)[:hi]
        picks[e["id"]] = EntryPick(
            id=e["id"], items=[_code_bullet(e["id"], order, pos, i, f, h) for pos, (i, f, h) in enumerate(ranked)],
            technologies=_order(e.get("technologies", []), names, wanted), min_bullets=lo,
        )
    return picks


def apply_picks(profile: dict, chosen: list[dict], wanted: set[str], job_text: str = "") -> dict[str, EntryPick]:
    """The writer's bullets ([{"id", "text"}], most relevant first; "text" empty
    for one it didn't reword) as entry picks.
    Unknown or repeated ids and picks beyond an entry's maximum are ignored; a
    reworded text that fails its check is replaced by the original fact; an
    entry left below its minimum is filled by code with original facts."""
    from app.applaut.documents.fact_guard import check_bullet

    names = skill_names(profile)
    facts = fact_ids(profile)
    limits = entry_limits(profile)
    picks = pick_entries(profile, wanted, job_text)
    code_items = {eid: p.items for eid, p in picks.items()}
    allowed = {e["id"]: mentioned(names, "\n".join(e["facts"] + e.get("technologies", []))) for e in _entries(profile)}
    for p in picks.values():
        p.items = []

    seen: set[str] = set()
    for pos, b in enumerate(chosen):
        fid = b.get("id")
        if fid not in facts or fid in seen:
            continue
        eid, original = facts[fid]
        if len(picks[eid].items) >= limits[eid][1]:
            continue
        seen.add(fid)
        text = (b.get("text") or "").strip()
        problem = check_bullet(original, text, allowed[eid], names) if text else None  # no text: not reworded
        picks[eid].items.append(Bullet(fid, original, text if text and not problem else original, (0, pos),
                                       tailored=bool(text) and not problem and text != original, note=problem))

    for eid, p in picks.items():  # a role the model left short gets code's best remaining facts
        for b in code_items[eid]:
            if len(p.items) >= p.min_bullets:
                break
            if b.fact_id not in seen:
                b.note = "added by code: the model chose fewer than this role's minimum"
                p.items.append(b)
    return picks


def drop_one(picks: dict[str, EntryPick], profile: dict | None = None, wanted: set[str] | None = None) -> bool:
    """Remove the lowest-ranked last bullet among entries above their minimum:
    code fills before the model's picks, the model's lowest-ranked first; among
    code-ranked ones the least relevant, then the oldest entry. False when
    nothing can be dropped."""
    candidates = [(p.items[-1].rank, eid) for eid, p in picks.items() if len(p.items) > p.min_bullets]
    if not candidates:
        return False
    p = picks[max(candidates)[1]]
    p.dropped.insert(0, p.items.pop())
    return True


def order_skill_rows(profile: dict, wanted: set[str], first: list[str] | None = None) -> list[dict]:
    """The profile's skill rows, labels and spelling unchanged. In each row: the
    writer's `first` skills in its order, then the job's other matching skills,
    then the rest in profile order. Names in `first` that aren't in a row are ignored."""
    names = skill_names(profile)
    first = first or []
    rows = []
    for label, items in profile["skills"].items():
        lead = [x for x in first if x in items]
        rows.append({"label": label, "items": lead + _order([x for x in items if x not in lead], names, wanted)})
    return rows


def all_skill_items(profile: dict) -> list[str]:
    """Every skill-row item, in profile order (what the writer may put first)."""
    return [x for items in profile["skills"].values() for x in items]
