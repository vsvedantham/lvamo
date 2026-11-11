from __future__ import annotations

import re
from datetime import date
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.jobref.models.enums import (
    JobSeekerStatus,
    JobrefUserType,
    ReferFrequency,
    ReferralViewCapacity,
)

# Loose German phone number check: optional +49/0049/0 prefix, then 6-14
# digits (spaces/hyphens allowed for readability).
GERMAN_PHONE_RE = re.compile(r"^(?:\+49|0049|0)[0-9 \-]{6,14}$")


class EmployeeDetails(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    working_since: date
    # How many incoming referral requests they're willing to review per
    # day — a distinct question from referral_capacity below (reviewing
    # incoming requests vs. actively making referrals).
    daily_referral_view_cap: ReferralViewCapacity
    # Always asked directly now — no more "can you refer at all?" gate
    # (Aug 2026 product decision). Uses the same bucketed scale as
    # daily_referral_view_cap rather than a raw count, for both fields to
    # read consistently.
    refer_frequency: ReferFrequency
    referral_capacity: ReferralViewCapacity
    company_careers_url: str = Field(min_length=1, max_length=1024)


class SeekerDetails(BaseModel):
    current_job_status: JobSeekerStatus
    notice_join_date: Optional[date] = None
    cv_drive_link: str = Field(min_length=1, max_length=1024)

    @model_validator(mode="after")
    def check_notice_date(self) -> "SeekerDetails":
        if self.current_job_status == JobSeekerStatus.SERVING_NOTICE:
            if self.notice_join_date is None:
                raise ValueError(
                    "notice_join_date is required when current_job_status is serving_notice"
                )
        else:
            self.notice_join_date = None
        return self


class EmployeeRegisterRequest(BaseModel):
    """Employees register directly — no LinkedIn involved (product
    decision, Aug 2026: LinkedIn OAuth is job-seeker-only, see
    services/linkedin.py). Dedup is by email, same as pre-LinkedIn."""

    user_type: Literal[JobrefUserType.EMPLOYEE] = JobrefUserType.EMPLOYEE
    first_name: str = Field(min_length=1, max_length=255)
    last_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    phone: str
    password: str = Field(min_length=8)
    domain: str = Field(min_length=1, max_length=255)
    employee: EmployeeDetails
    # The code emailed by /api/v1/platform/auth/email-codes. Required only
    # while `otp_verification_enabled` lists jobref. Job seekers have no
    # such field: LinkedIn already verified their email.
    email_code: Optional[str] = Field(default=None, max_length=12)

    @model_validator(mode="after")
    def check_phone(self) -> "EmployeeRegisterRequest":
        if not GERMAN_PHONE_RE.match(self.phone.strip()):
            raise ValueError("phone must be a valid German phone number")
        return self


class SeekerRegisterRequest(BaseModel):
    """Job seekers register via LinkedIn OAuth. Proves the registrant
    completed the flow and carries their verified LinkedIn id + email — see
    services/linkedin.py. No client-submitted email; it's always sourced
    server-side from this token so it can't be spoofed or mismatched."""

    user_type: Literal[JobrefUserType.JOB_SEEKER] = JobrefUserType.JOB_SEEKER
    registration_token: str
    first_name: str = Field(min_length=1, max_length=255)
    last_name: str = Field(min_length=1, max_length=255)
    phone: str
    password: str = Field(min_length=8)
    domain: str = Field(min_length=1, max_length=255)
    seeker: SeekerDetails

    @model_validator(mode="after")
    def check_phone(self) -> "SeekerRegisterRequest":
        if not GERMAN_PHONE_RE.match(self.phone.strip()):
            raise ValueError("phone must be a valid German phone number")
        return self


# Discriminated on user_type — FastAPI/Pydantic route the request body to
# the matching model automatically, so the two registration paths (direct
# for employees, LinkedIn-token-based for job seekers) share one endpoint
# without either shape leaking fields the other doesn't need.
RegisterRequest = Annotated[
    Union[EmployeeRegisterRequest, SeekerRegisterRequest],
    Field(discriminator="user_type"),
]


class ProfileUpdate(BaseModel):
    """Editable profile fields — everything except email (never editable,
    it's the account's stable identity/dedup key) and the system fields
    (id, is_active, created_at). Mirrors registration's shape: exactly one
    of employee/seeker must be set, matching the caller's own account
    type — enforced server-side in services/auth.py since Pydantic alone
    can't know which type the authenticated user is."""

    first_name: str = Field(min_length=1, max_length=255)
    last_name: str = Field(min_length=1, max_length=255)
    phone: str
    domain: str = Field(min_length=1, max_length=255)
    employee: Optional[EmployeeDetails] = None
    seeker: Optional[SeekerDetails] = None

    @model_validator(mode="after")
    def check_phone(self) -> "ProfileUpdate":
        if not GERMAN_PHONE_RE.match(self.phone.strip()):
            raise ValueError("phone must be a valid German phone number")
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LinkedInPrefillResponse(BaseModel):
    """What the registration form prefills from LinkedIn, plus the
    verification flag — shown to the user so it's transparent exactly what
    was pulled from their LinkedIn profile."""

    first_name: str
    last_name: str
    email: EmailStr
    email_verified: bool
