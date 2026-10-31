"""The master profile: everything a CV or cover letter may say about the user.

Same shape as the Claude routine's `master_profile.yaml`, so the routine's
templates render it unchanged and a routine user can paste their file in.
Unknown keys are kept (the routine's file may carry more than Applaut reads).
"""
from __future__ import annotations

import re

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

_RANGE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")


class _Model(BaseModel):
    model_config = ConfigDict(extra="allow")


class Personal(_Model):
    name: str = Field(min_length=1)
    location: str = ""
    phone: str = ""
    email: str = ""
    linkedin_url: str = ""
    linkedin_display: str = ""
    github_url: str = ""
    github_display: str = ""
    work_authorization: str = ""
    work_authorization_short: str = ""
    availability: str = ""
    availability_short: str = ""
    visa_sponsorship_needed: bool = False


def _check_range(v: str | None) -> str | None:
    if v is None:
        return v
    m = _RANGE.match(v)
    if not m or not 1 <= int(m[1]) <= int(m[2]) <= 6:
        raise ValueError('cv_bullets must look like "3-5" (between 1 and 6)')
    return v


# Field order = the routine's master_profile.yaml order, so a saved profile
# reads back the way the user wrote it.
class Experience(_Model):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    company: str = Field(min_length=1)
    location: str = ""
    start: str = ""
    end: str = ""
    project: str | None = None
    cv_bullets: str | None = None  # "min-max" bullets on the CV, e.g. "3-5"
    facts: list[str] = Field(min_length=1)
    technologies: list[str] = []

    _range = field_validator("cv_bullets")(_check_range)


class Project(_Model):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    subtitle: str = ""
    start: str = ""
    end: str = ""
    cv_bullets: str | None = None
    facts: list[str] = Field(min_length=1)
    technologies: list[str] = []

    _range = field_validator("cv_bullets")(_check_range)


class Certification(_Model):
    status: str = ""
    name: str = Field(min_length=1)
    detail: str = ""
    topics: str | None = None


class Education(_Model):
    period: str = ""
    degree: str = Field(min_length=1)
    school: str = ""


class Languages(_Model):
    english: str = ""
    german: str = ""
    german_max_required: str = "A2"
    german_applications: bool = False


class Preferences(_Model):
    role_level: list[str] = []
    work_modes: list[str] = []
    locations: list[str] = []
    employment_types: list[str] = []


class MasterProfileData(_Model):
    personal: Personal
    default_headline: str = Field(min_length=1)
    default_cover_tagline: str = Field(min_length=1)
    years_experience: str = ""
    skills: dict[str, list[str]] = Field(min_length=1)
    additional_skills: list[str] = []
    skill_aliases: dict[str, list[str]] = {}
    experience: list[Experience] = Field(min_length=1)
    projects: list[Project] = []
    certifications: list[Certification] = []
    education: list[Education] = []
    languages: Languages = Languages()
    preferences: Preferences = Preferences()

    @field_validator("years_experience", mode="before")
    @classmethod
    def _years_as_text(cls, v):
        return "" if v is None else str(v)

    @model_validator(mode="after")
    def _unique_ids(self):
        ids = [e.id for e in self.experience] + [p.id for p in self.projects]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"experience/project ids must be unique: {', '.join(dupes)}")
        return self


class ProfileError(ValueError):
    """The profile can't be used; `errors` lists what to fix, one line each."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def validate_profile(data: dict) -> dict:
    """Validate and normalise a master profile. Returns plain data for the templates."""
    try:
        # exclude_none: optional fields left out stay out (templates use .get for them)
        return MasterProfileData.model_validate(data).model_dump(mode="json", exclude_none=True)
    except ValidationError as exc:
        raise ProfileError([
            f"{'.'.join(str(p) for p in e['loc']) or 'profile'}: {e['msg']}" for e in exc.errors()
        ]) from exc


def parse_yaml(text: str) -> dict:
    """A pasted master_profile.yaml → validated profile data."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ProfileError([f"Not valid YAML: {exc}"]) from exc
    if not isinstance(data, dict):
        raise ProfileError(["The YAML must be a mapping (key: value pairs) at the top level"])
    return validate_profile(data)


def to_yaml(data: dict) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=100)


def bullet_limits(entry: dict, index: int) -> tuple[int, int]:
    """(min, max) bullets for an entry: its `cv_bullets`, else the routine's
    defaults (3-5 for the most recent role, 1-3 for older ones)."""
    m = _RANGE.match(entry.get("cv_bullets") or "")
    if m:
        return int(m[1]), int(m[2])
    return (3, 5) if index == 0 else (1, 3)
