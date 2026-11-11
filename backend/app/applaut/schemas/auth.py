from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8)
    # The code emailed by /api/v1/platform/auth/email-codes. Required only
    # while `otp_verification_enabled` lists applaut.
    email_code: str | None = Field(default=None, max_length=12)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
