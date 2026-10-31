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
SCORE_MAX_TOKENS = 450


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

Candidate:
{candidate_summary(profile)}"""


# ---------------------------------------------------------------- writing

WRITE_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "paragraphs": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3},
    },
    "required": ["headline", "paragraphs"],
}
WRITE_MAX_TOKENS = 700


def _facts(p: dict) -> str:
    out = []
    for e in p["experience"]:
        out.append(f"## Role: {e['title']} at {e['company']} ({e.get('start', '')} – {e.get('end', '')})")
        out += [f"- {f}" for f in e["facts"]]
    for pr in p.get("projects", []):
        out.append(f"## Project: {pr['name']} ({pr.get('start', '')} – {pr.get('end', '')})")
        out += [f"- {f}" for f in pr["facts"]]
    return "\n".join(out)


def write_system(profile: dict) -> str:
    style = profile.get("cover_letter_style")
    return f"""You write part of a job application for one candidate: a one-line CV headline and the first three paragraphs of a cover letter. Output JSON only.

Hard rules:
- Use only the facts below. Never add a skill, tool, employer, title, date, number or achievement that is not there. Every number you write must appear in the facts (or, about the company, in the posting).
- Each fact belongs to the role or project it is listed under. Never credit a fact to a different role or to the project.
- Say nothing about the company that is not in the posting.
- No filler, no generic enthusiasm ("I am eager", "I am excited"), no claims about how the candidate works that the facts do not state. Specific and true beats long.
- headline: rewrite this default for THIS job, same style and length, naming the job's role family and 2-4 of the job's skills the candidate really has: "{profile['default_headline']}". Do not copy the default unchanged.
- paragraph 1 (hook, 60-90 words): what the company does and the specific problem this role solves (from the posting), and why the candidate's background fits.
- paragraph 2 (evidence, 80-120 words): the most relevant role's facts matched to the posting's must-haves, with their real numbers.
- paragraph 3 (second angle, 50-90 words): another role or the project that fits a different part of the job.
- English, first person, plain professional tone. No greeting, sign-off, availability, location or visa details (other code adds those).{f'''
- Style: {style}''' if style else ''}

Candidate:
{candidate_summary(profile)}

Facts (the only achievements you may use):
{_facts(profile)}"""


def fix_message(errors: list[str]) -> str:
    return ("Your previous answer broke these rules. Write the answer again, fixing every point:\n"
            + "\n".join(f"- {e}" for e in errors))
