import enum


class RemotePreferenceEnum(str, enum.Enum):
    remote = "remote"
    hybrid = "hybrid"
    onsite = "onsite"
    any = "any"


class EmploymentTypeEnum(str, enum.Enum):
    full_time = "full_time"
    part_time = "part_time"
    contract = "contract"
    freelance = "freelance"
    internship = "internship"


class ApplicationStatusEnum(str, enum.Enum):
    pending_review = "pending_review"
    approved = "approved"
    submitted = "submitted"
    rejected = "rejected"
    withdrawn = "withdrawn"
    interviewing = "interviewing"
    offered = "offered"
    closed = "closed"


class DocumentTypeEnum(str, enum.Enum):
    tailored_resume = "tailored_resume"
    cover_letter = "cover_letter"


class JobEngineEnum(str, enum.Enum):
    """Which engine finds jobs and writes documents for a profile
    (docs/applaut/JOB_ENGINES_DESIGN.md)."""
    basic = "basic"
    applaut_ai = "applaut_ai"
    own_routine = "own_routine"
