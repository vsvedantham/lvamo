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


class EvidenceKind(str, enum.Enum):
    metric = "metric"      # a number, e.g. prediction_error_pct = 12.4
    check = "check"        # pass / fail / warn, e.g. a data source is reachable
    artifact = "artifact"  # a file in R2 (Phase 4)
    run = "run"            # a pipeline run: success / failure


class EvidenceSource(str, enum.Enum):
    ci = "ci"                # POSTed by the student's CI with an ingest token
    webhook = "webhook"
    scheduler = "scheduler"  # LVAMO's own scheduled checks
    manual = "manual"
