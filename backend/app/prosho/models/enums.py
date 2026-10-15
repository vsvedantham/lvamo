import enum


class ProshoUserRole(str, enum.Enum):
    student = "student"
    mentor = "mentor"
    admin = "admin"


class ProjectType(str, enum.Enum):
    data_science = "data_science"
    frontend = "frontend"


class Visibility(str, enum.Enum):
    private = "private"    # owner (and later mentors) only
    unlisted = "unlisted"  # anyone with the link
    public = "public"      # listed in the gallery; needs supervisor_ok_at


class DemoKind(str, enum.Enum):
    streamlit = "streamlit"
    url = "url"
    video = "video"


class ClaimTargetOp(str, enum.Enum):
    gte = "gte"          # value >= target
    lte = "lte"          # value <= target
    abs_lte = "abs_lte"  # |value| <= target  (e.g. prediction error within ±25%)
    between = "between"  # target <= value <= target_hi
    eq = "eq"


class ClaimManualStatus(str, enum.Enum):
    """Only for claims without a metric — shown as self-reported."""

    not_started = "not_started"
    in_progress = "in_progress"
    met = "met"
    not_met = "not_met"
