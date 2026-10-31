"""The model reads, code scores (design §5). The model's facts about a posting
go in; a 0-100 match score with fixed, visible weights comes out, plus the
lists the job page shows. Same facts, same score, every time."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.applaut.documents.tailor import skill_names

LEVELS = ["none", "A1", "A2", "B1", "B2", "C1", "C2", "native"]
WEIGHTS = {"must_have": 45, "role_fit": 20, "language": 15, "seniority": 10, "nice_to_have": 5, "location": 5}
GERMAN_MISS_CAP = 60
_LANG = re.compile(r"\b(english|german|deutsch|englisch|language|sprach)", re.I)
_SPLIT = re.compile(r"[,:/;&+()]| and ")


@dataclass
class ScoreResult:
    score: int
    parts: dict
    matched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    german_miss: bool = False
    ignored_matches: int = 0  # matches naming a skill the profile doesn't have


def _known(profile: dict) -> set[str]:
    return {n for ns in skill_names(profile).values() for n in ns}


def _is_match(item: dict, known: set[str]) -> bool:
    """A match counts only if it names a real profile skill (or alias). The
    model sometimes cites several at once ("React, TypeScript"); any one real
    skill in there is enough."""
    by = item.get("matched_by")
    if not by:
        return False
    return any(x.strip().lower() in known for x in _SPLIT.split(by) if x.strip())


def compute(facts: dict, profile: dict, years_experience: int | None, german_max_required: str) -> ScoreResult:
    known = _known(profile)
    must = [m for m in facts.get("must_have", []) if not _LANG.search(m.get("requirement", ""))]
    nice = [m for m in facts.get("nice_to_have", []) if not _LANG.search(m.get("requirement", ""))]
    must_hit = [m for m in must if _is_match(m, known)]
    nice_hit = [m for m in nice if _is_match(m, known)]

    parts = {
        "must_have": round(WEIGHTS["must_have"] * (len(must_hit) / len(must) if must else 0.7)),
        "role_fit": {"same": 20, "adjacent": 12}.get(facts.get("role_fit"), 0),
    }
    g = facts.get("german_required", "unclear")
    max_ok = LEVELS.index(german_max_required) if german_max_required in LEVELS else LEVELS.index("A2")
    german_miss = g in LEVELS and LEVELS.index(g) > max_ok
    parts["language"] = 0 if german_miss else (10 if g == "unclear" else 15)

    need, have = facts.get("years_required"), years_experience
    s = 10
    if need is not None and have is not None:
        s = 10 if need <= have + 1 else 5 if need <= have + 2 else 0
    if facts.get("seniority") in ("lead", "principal"):
        s = min(s, 3)
    parts["seniority"] = s
    parts["nice_to_have"] = round(WEIGHTS["nice_to_have"] * (len(nice_hit) / len(nice) if nice else 1))
    parts["location"] = WEIGHTS["location"]  # discovery already kept only the user's countries

    total = sum(parts.values())
    if german_miss:
        total = min(total, GERMAN_MISS_CAP)
    ignored = sum(1 for m in must + nice if m.get("matched_by") and not _is_match(m, known))
    return ScoreResult(
        score=total, parts=parts,
        matched=[m["requirement"] for m in must_hit],
        missing=[m["requirement"] for m in must if m not in must_hit],
        german_miss=german_miss, ignored_matches=ignored,
    )


def years_from(profile: dict) -> int | None:
    m = re.search(r"\d+", str(profile.get("years_experience") or ""))
    return int(m.group()) if m else None


def flags_for(facts: dict, result: ScoreResult) -> list[str]:
    flags = [f"CHECK: {f}" for f in facts.get("flags", [])][:3]
    if facts.get("contract") == "fixed_term":
        flags.append("CHECK: fixed-term contract")
    if result.german_miss:
        flags.append(f"German {facts.get('german_required')} required")
    return list(dict.fromkeys(flags))
