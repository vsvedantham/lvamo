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
