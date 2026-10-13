import enum


class ProshoUserRole(str, enum.Enum):
    student = "student"
    mentor = "mentor"
    admin = "admin"
