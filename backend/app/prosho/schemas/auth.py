import uuid

from pydantic import BaseModel, Field

from app.prosho.models.enums import ProshoUserRole


class LoginCodeExchange(BaseModel):
    code: str = Field(min_length=1, max_length=2000)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ProshoUserResponse(BaseModel):
    id: uuid.UUID
    github_login: str
    name: str | None
    email: str | None
    avatar_url: str | None
    role: ProshoUserRole

    model_config = {"from_attributes": True}
