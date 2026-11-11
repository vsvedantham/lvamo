import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.exc import IntegrityError

from app.core.security import (
    create_access_token,
    decode_access_token_payload,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.jobref.models.jobref_company import JobrefCompany
from app.jobref.models.jobref_user import JobrefUser
from app.jobref.schemas.auth import (
    EmployeeRegisterRequest,
    LoginRequest,
    ProfileUpdate,
    RegisterRequest,
    SeekerRegisterRequest,
)
from app.jobref.services.linkedin import decode_registration_token
from app.platform.services import email_codes

bearer_scheme = HTTPBearer()

# Stamped on every Jobref access token so it can't be replayed against
# another vertical's protected endpoints (each vertical has its own user
# table/login, per the platform's multi-vertical auth architecture).
TOKEN_VERTICAL = "jobref"


def _issue_token(user_id: uuid.UUID) -> str:
    return create_access_token(user_id, extra_claims={"vertical": TOKEN_VERTICAL})


async def register(payload: RegisterRequest, db: AsyncSession) -> tuple[JobrefUser, str]:
    # Two distinct paths sharing one endpoint (Pydantic discriminates on
    # user_type — see schemas/auth.py): employees register directly, job
    # seekers go through LinkedIn OAuth. Both write to the same flat
    # jobref.users row (is_employee is the sole differentiator, see
    # models/jobref_user.py) — kept as separate helpers since the two paths
    # differ in where identity/dedup comes from, not just which fields they
    # populate.
    if isinstance(payload, EmployeeRegisterRequest):
        return await _register_employee(payload, db)
    return await _register_seeker(payload, db)


async def _register_employee(payload: EmployeeRegisterRequest, db: AsyncSession) -> tuple[JobrefUser, str]:
    existing = await db.scalar(select(JobrefUser).where(JobrefUser.email == payload.email))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    await email_codes.require_code(db, "jobref", payload.email, "register", payload.email_code)

    details = payload.employee
    user = JobrefUser(
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
        linkedin_id=None,
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        is_employee=True,
        domain=payload.domain,
        company_name=details.company_name,
        working_since=details.working_since,
        daily_referral_view_cap=details.daily_referral_view_cap,
        refer_frequency=details.refer_frequency,
        referral_capacity=details.referral_capacity,
        company_careers_url=details.company_careers_url,
    )
    db.add(user)
    try:
        await db.flush()  # assign user.id before building the companies row
    except IntegrityError:
        # Backstop for the race where two requests with the same email
        # flush concurrently — the DB-level UNIQUE constraint on email is
        # the real guarantee here.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Companies-gathering step: every employee registration seeds
    # jobref.companies with the company they named, for the future
    # referral-matching feature — see models/jobref_company.py.
    db.add(
        JobrefCompany(
            user_id=user.id,
            name=details.company_name,
            careers_url=details.company_careers_url,
        )
    )
    await db.commit()

    return user, _issue_token(user.id)


async def _register_seeker(payload: SeekerRegisterRequest, db: AsyncSession) -> tuple[JobrefUser, str]:
    # Identity (linkedin_id + verified email) always comes from the
    # LinkedIn-issued registration token, never from client-submitted
    # fields — see services/linkedin.py. This is what makes the LinkedIn id
    # dedup meaningful: it can't be spoofed by submitting a different email.
    claims = decode_registration_token(payload.registration_token)

    existing = await db.scalar(
        select(JobrefUser).where(
            (JobrefUser.linkedin_id == claims.linkedin_id) | (JobrefUser.email == claims.email)
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account already exists for this LinkedIn profile — please sign in instead",
        )

    details = payload.seeker
    user = JobrefUser(
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=claims.email,
        linkedin_id=claims.linkedin_id,
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        is_employee=False,
        domain=payload.domain,
        current_job_status=details.current_job_status,
        notice_join_date=details.notice_join_date,
        cv_drive_link=details.cv_drive_link,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        # Backstop for the race where two requests carrying the same
        # LinkedIn identity commit concurrently — the DB-level UNIQUE
        # constraint on linkedin_id/email is the real guarantee here.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account already exists for this LinkedIn profile — please sign in instead",
        )

    return user, _issue_token(user.id)


async def login(payload: LoginRequest, db: AsyncSession) -> tuple[JobrefUser, str]:
    user = await db.scalar(select(JobrefUser).where(JobrefUser.email == payload.email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account disabled",
        )
    return user, _issue_token(user.id)


async def update_profile(user: JobrefUser, payload: ProfileUpdate, db: AsyncSession) -> JobrefUser:
    """Edits everything except email (identity/dedup key, never editable)
    and the system fields. Exactly one of employee/seeker must be set,
    matching the caller's own account type — checked here since Pydantic
    alone can't know which type the authenticated user is."""
    if user.is_employee:
        if payload.employee is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="employee details are required",
            )
        details = payload.employee
        user.company_name = details.company_name
        user.working_since = details.working_since
        user.daily_referral_view_cap = details.daily_referral_view_cap
        user.refer_frequency = details.refer_frequency
        user.referral_capacity = details.referral_capacity
        user.company_careers_url = details.company_careers_url

        # Keep the jobref.companies row (seeded at registration — see
        # _register_employee) in sync so the companies list a seeker sees
        # doesn't go stale against the employee's own current profile.
        company = await db.scalar(select(JobrefCompany).where(JobrefCompany.user_id == user.id))
        if company:
            company.name = details.company_name
            company.careers_url = details.company_careers_url
    else:
        if payload.seeker is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="seeker details are required",
            )
        details = payload.seeker
        user.current_job_status = details.current_job_status
        user.notice_join_date = details.notice_join_date
        user.cv_drive_link = details.cv_drive_link

    user.first_name = payload.first_name
    user.last_name = payload.last_name
    user.phone = payload.phone
    user.domain = payload.domain

    await db.commit()
    await db.refresh(user)
    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> JobrefUser:
    try:
        payload = decode_access_token_payload(credentials.credentials)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    if payload.get("vertical") != TOKEN_VERTICAL:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    user = await db.get(JobrefUser, uuid.UUID(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user
