"""What the model is asked, and the JSON shape of each answer.

Prompt order is fixed: instructions + the user's profile (identical for every
job of that user, so llama-server reuses the cached prefix), then the job.
Phase 0 lessons (APPLAUT_AI_ENGINE_DESIGN.md §10) are baked in: short
requirement names (output tokens are the slow part), one skill per match,
languages kept out of the skill list, "German or English" is not a German
requirement, and facts never move between roles.
"""
from __future__ import annotations

import re

from app.applaut.documents.fact_guard import BULLET_NUM_RE
from app.applaut.documents.tailor import all_skill_items, entry_limits, fact_ids, names_as_written, skill_names

JD_MAX_CHARS = 6000  # ~1,500 tokens; postings put requirements early


def trim_job(description: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", description or "").strip()[:JD_MAX_CHARS]


def job_message(title: str, company: str, location: str | None, description: str) -> str:
    return f"Posting: {title} at {company} ({location or 'location not given'})\n\n{trim_job(description)}"


def candidate_summary(p: dict) -> str:
    lines = [f"Years of experience: {p.get('years_experience') or 'not stated'}", "Skills (exact names):"]
    for label, items in p["skills"].items():
        lines.append(f"- {label}: {', '.join(items)}")
    if p.get("additional_skills"):
        lines.append(f"- Additional: {', '.join(p['additional_skills'])}")
    if p.get("skill_aliases"):
        lines.append("Also known as: " + "; ".join(f"{k} = {', '.join(v)}" for k, v in p["skill_aliases"].items()))
    lines.append("Roles:")
    for e in p["experience"]:
        lines.append(f"- {e['title']} at {e['company']} ({e.get('start', '')} – {e.get('end', '')}): "
                     f"{', '.join(e.get('technologies', []))}")
    for pr in p.get("projects", []):
        lines.append(f"- Project {pr['name']}: {', '.join(pr.get('technologies', []))}")
    lang = p.get("languages", {})
    lines.append(f"Languages: English {lang.get('english') or 'not stated'}; German {lang.get('german') or 'none'}")
    return "\n".join(lines)


# ---------------------------------------------------------------- scoring

_REQ = {"type": "object", "properties": {"requirement": {"type": "string"},
                                          "matched_by": {"type": ["string", "null"]}},
        "required": ["requirement", "matched_by"]}

SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "role_fit": {"enum": ["same", "adjacent", "different"]},
        "must_have": {"type": "array", "items": _REQ, "maxItems": 8},
        "nice_to_have": {"type": "array", "items": _REQ, "maxItems": 6},
        "german_required": {"enum": ["none", "A1", "A2", "B1", "B2", "C1", "C2", "native", "unclear"]},
        "years_required": {"type": ["integer", "null"]},
        "seniority": {"enum": ["intern", "junior", "mid", "senior", "lead", "principal", "unclear"]},
        "contract": {"enum": ["permanent", "fixed_term", "freelance", "working_student", "unclear"]},
        "work_mode": {"enum": ["onsite", "hybrid", "remote", "unclear"]},
        "flags": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
    },
    "required": ["role_fit", "must_have", "nice_to_have", "german_required", "years_required",
                 "seniority", "contract", "work_mode", "flags"],
}
SCORE_MAX_TOKENS = 1000  # Phase 0 answers: 300–630 tokens


def score_system(profile: dict, target_roles: list[str]) -> str:
    roles = ", ".join(target_roles) or "the candidate's current role family"
    return f"""You read job postings for one candidate and extract facts as JSON. You never judge the overall fit; code does that.

Rules:
- must_have: the required skills, tools and qualifications, most important first, at most 8. nice_to_have: the ones marked optional, a plus or bonus, at most 6.
- requirement: a short name, at most 5 words (e.g. "Apache Kafka", "dbt", "Degree in CS").
- Languages (English, German) never go in must_have or nice_to_have; use german_required.
- matched_by: exactly ONE skill name from the candidate's list below (or one of its "also known as" names) that covers the requirement, or null. Never a list, a row label or a skill the candidate does not have.
- german_required: the German level the posting requires. "none" if German is not required, only a plus, or if German OR English is enough. Fluent / business fluent = C1, very good = B2, good = B1.
- role_fit: "same" if the role belongs to the candidate's target roles ({roles}), "adjacent" if close to them, else "different".
- years_required: minimum years of experience asked for, or null.
- flags: up to 3 short things the candidate must check (e.g. "fixed-term contract", "security clearance", "on-call").
- Postings may be in German; always answer in English.
- Write the JSON on one line, without indentation.

Candidate:
{candidate_summary(profile)}"""


# ---------------------------------------------------------------- writing

REWORD_MAX = 5  # rewording every bullet doubled the answer (~1,000 tokens, ~5 min a set)


def write_schema(profile: dict) -> dict:
    """The writer's answer. Bullet ids and skill names are enums built from the
    profile, so the model can only pick facts and skills the user has."""
    ids = list(fact_ids(profile))
    limits = entry_limits(profile).values()
    least, most = sum(lo for lo, _ in limits), sum(hi for _, hi in limits)
    return {
        "type": "object",
        "properties": {
            "headline": {"type": "string"},
            # The bullets to reword, each with what the posting needs from it; the
            # rewording itself is a call of its own per bullet (reword_message).
            "focus": {"type": "array", "minItems": min(REWORD_MAX, len(ids)), "maxItems": REWORD_MAX, "items": {
                "type": "object",
                "properties": {"id": {"enum": ids}, "need": {"type": "string", "maxLength": 60}},
                "required": ["id", "need"]}},
            "bullets": {"type": "array", "minItems": least, "maxItems": most, "items": {"enum": ids}},
            "skills_first": {"type": "array", "maxItems": 8, "items": {"enum": all_skill_items(profile)}},
            "paragraphs": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3},
        },
        "required": ["headline", "focus", "bullets", "skills_first", "paragraphs"],
    }


WRITE_MAX_TOKENS = 1600  # ~350 letter, ~100 ids, needs and skills, headroom


def _facts(p: dict) -> str:
    limits = entry_limits(p)
    out = []
    for e in p["experience"] + p.get("projects", []):
        lo, hi = limits[e["id"]]
        name = f"Role: {e['title']} at {e['company']}" if "company" in e else f"Project: {e['name']}"
        out.append(f"## {name} ({e.get('start', '')} – {e.get('end', '')}) — CV shows {lo}-{hi} of these")
        out += [f"- [{e['id']}.{n}] {f}" for n, f in enumerate(e["facts"], 1)]
    return "\n".join(out)


def write_system(profile: dict) -> str:
    style = profile.get("cover_letter_style")
    return f"""You tailor one candidate's job application to one posting: the CV headline, which CV bullets to show and which of them to reword, which skills to put first, and the first three paragraphs of the cover letter. Output JSON only, on one line.

Hard rules:
- Use only the facts below. Never add a skill, tool, employer, title, date, number or achievement that is not there. Every number you write must appear in the facts (or, about the company, in the posting).
- Each fact belongs to the role or project it is listed under. Never credit a fact to a different role or to the project.
- Say nothing about the company that is not in the posting.
- No filler, no generic enthusiasm ("I am eager", "I am excited"), no claims about how the candidate works that the facts do not state. Specific and true beats long.
- headline: rewrite this default for THIS job, same style and length, naming the job's role family and 2-4 of the job's skills the candidate really has: "{profile['default_headline']}". Do not copy the default unchanged.
- focus: the {REWORD_MAX} facts that matter most for this posting, each as id and need: what this posting asks for that the fact proves, in the posting's own words (2-6 words).
- bullets: the ids of the facts the CV should show for this posting, most relevant first, for every role and project within its "CV shows" range (at least the lower number for each).
- skills_first: up to 8 different skills of the candidate (exact names from the list) that this posting needs most, most important first; each skill once.
- paragraph 1 (hook, 60-90 words): what the company does and the specific problem this role solves (from the posting), and why my background fits.
- paragraph 2 (evidence, 80-120 words): the most relevant role's facts matched to the posting's must-haves, with their real numbers.
- paragraph 3 (second angle, 50-90 words): another role or the project that fits a different part of the job.
- Write the letter AS the candidate, in the first person ("I built", "my work at"). "You"/"your" may only mean the company or the team, never the candidate.
- English, plain professional tone. No greeting, sign-off, availability, location or visa details (other code adds those).{f'''
- Style: {style}''' if style else ''}

Candidate:
{candidate_summary(profile)}

Facts (the only achievements you may use), with their ids:
{_facts(profile)}

{REWORD_RULES}"""


REWORD_SCHEMA = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}
REWORD_MAX_TOKENS = 200


# In write_system, so it is part of the prefix the server keeps cached: this CPU
# reads prompts at ~16 tokens/s, and each rewording call then sends ~80 tokens.
REWORD_RULES = """Rewording one bullet. Later messages may ask you to reword ONE fact as a CV bullet. Then answer {"text": "..."} only, with these rules:
- The same achievement, said with the fact's own words: reorder it so it opens with the part that matters for the given need (usually its result), then how. You may change word forms ("reducing" -> "Reduced") and add joining words (by, with, through, across, for).
- Add no other word: not the posting's words, not the need's words, nothing the fact doesn't say. Never change what the candidate did ("owned and maintained" stays that, not "built"). Use each word and tool as often as the fact does.
- Every number exactly as written ("20+" stays "20+"), every tool exactly as written. Start with a past-tense verb. No "I", "my", "we". Within 20% of the fact's length. Never copy the fact as it is.
Example. Fact: "Rewrote the Spark billing job, cutting runtime from 6 hours to 40 minutes." Answer: {"text": "Cut the Spark billing job's runtime from 6 hours to 40 minutes by rewriting it."}"""


def reword_message(profile: dict, fact_id: str, need: str) -> str:
    """One bullet's rewording, sent after write_system (the rules are there)."""
    fact = fact_ids(profile)[fact_id][1]
    tools = names_as_written(skill_names(profile), fact)
    return (f"Reword ONE bullet now (rules above).\nNeed: {need}\nFact: {fact}\n"
            f"Keep these numbers: {', '.join(BULLET_NUM_RE.findall(fact)) or 'none'}\n"
            f"Keep these tools: {', '.join(tools) or 'none'}")


def reword_retry(message: str, text: str, problem: str) -> str:
    return f"{message}\n\nYour previous answer: {text}\nIt can't be used: {problem}. Write it again, fixing that."


# ---------------------------------------------------------------- bullet bank builder

DRAFT_MAX = 5
DRAFT_SCHEMA = {"type": "object", "properties": {
    "bullets": {"type": "array", "minItems": 1, "maxItems": DRAFT_MAX, "items": {"type": "string"}}},
    "required": ["bullets"]}
DRAFT_MAX_TOKENS = 700
DRAFT_SYSTEM = f"""You turn a candidate's own notes about one role into CV bullet points. Output JSON only, on one line: {{"bullets": ["...", ...]}}.

Rules:
- Up to {DRAFT_MAX} bullets, each one achievement or responsibility the notes describe that the role's existing bullets don't already cover. Fewer is fine when the notes hold less.
- Use only what the notes and the existing bullets say. Never add a number, tool, product, team, result or employer that isn't in them. Where the notes give no number, write the bullet without one.
- Name every tool exactly as the notes or the role's technologies spell it.
- Each bullet: starts with a past-tense verb, 12-35 words, no "I", "my" or "we", in the same style as the existing bullets: what was done, with what, and the result when the notes give one.
- Never repeat or reword an existing bullet."""


def draft_message(profile: dict, entry: dict, notes: str) -> str:
    title = (f"Role: {entry['title']} at {entry['company']}" if "company" in entry else f"Project: {entry['name']}")
    skills = sorted({x for items in profile["skills"].values() for x in items} | set(profile.get("additional_skills", [])))
    existing = "\n".join(f"- {f}" for f in entry["facts"]) or "(none yet)"
    return (f"{title} ({entry.get('start', '')} – {entry.get('end', '')})\n"
            f"Technologies: {', '.join(entry.get('technologies', [])) or 'none listed'}\n"
            f"Candidate's skills: {', '.join(skills)}\n"
            f"Existing bullets:\n{existing}\n\n"
            f"Candidate's notes:\n{notes.strip()}")


def fix_message(errors: list[str]) -> str:
    return ("Your previous answer broke these rules. Write the answer again, fixing every point:\n"
            + "\n".join(f"- {e}" for e in errors))
