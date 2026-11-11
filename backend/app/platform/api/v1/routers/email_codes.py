"""Email codes for any vertical: ask for a code, and reset a password with
one. Sign-up itself stays on each vertical's own /auth/register, which takes
the code as `email_code` (see app/platform/services/email_codes.py)."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rate_limit
from app.db.session import get_db
from app.platform.services import email_codes

router = APIRouter(prefix="/auth")


def _ip_limits(name: str, per_minute: int, per_hour: int):
    def check(request: Request) -> None:
        ip = rate_limit.client_ip(request)
        if not rate_limit.hit(f"{name}:{ip}", per_minute):
            raise rate_limit.too_many()
        if not rate_limit.hit(f"{name}-hour:{ip}", per_hour, per_seconds=3600):
            raise rate_limit.too_many(retry_after=3600)
    return check


class EmailCodeRequest(BaseModel):
    vertical: str = Field(min_length=1, max_length=32)
    email: EmailStr
    purpose: Literal["register", "reset_password"]


class EmailCodeSent(BaseModel):
    resend_after_seconds: int
    expires_in_seconds: int


class PasswordResetRequest(BaseModel):
    vertical: str = Field(min_length=1, max_length=32)
    email: EmailStr
    code: str = Field(min_length=1, max_length=12)
    new_password: str = Field(min_length=8)


@router.post(
    "/email-codes",
    response_model=EmailCodeSent,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(_ip_limits("email-code", per_minute=5, per_hour=30))],
)
async def request_email_code(body: EmailCodeRequest, request: Request, db: AsyncSession = Depends(get_db)):
    accounts = await email_codes.enabled_accounts(db, body.vertical)
    exists = await accounts.account_exists(db, body.email)
    if body.purpose == "register" and exists:
        # The vertical's own sign-up already answers this way.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    # Password reset for an unknown address: same answer, nothing sent.
    deliver = exists if body.purpose == "reset_password" else True
    await email_codes.send_code(db, body.vertical, body.email, body.purpose,
                                deliver=deliver, requester_ip=rate_limit.client_ip(request))
    return EmailCodeSent(
        resend_after_seconds=int(email_codes.RESEND_AFTER.total_seconds()),
        expires_in_seconds=int(email_codes.CODE_TTL.total_seconds()),
    )


@router.post(
    "/password-reset",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_ip_limits("password-reset", per_minute=10, per_hour=60))],
)
async def reset_password(body: PasswordResetRequest, db: AsyncSession = Depends(get_db)):
    accounts = await email_codes.enabled_accounts(db, body.vertical)
    await email_codes.consume_code(db, body.vertical, body.email, "reset_password", body.code)
    if not await accounts.set_password(db, body.email, body.new_password):
        await db.rollback()  # unreachable in practice: no code is ever sent without an account
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="This code has expired. Ask for a new one.")
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
