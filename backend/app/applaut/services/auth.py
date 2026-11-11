import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.applaut.models.user import User
from app.applaut.schemas.auth import LoginRequest, RegisterRequest
from app.platform.services import email_codes

bearer_scheme = HTTPBearer()


async def register(payload: RegisterRequest, db: AsyncSession) -> tuple[User, str]:
    existing = await db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    verified = await email_codes.require_code(db, "applaut", payload.email, "register", payload.email_code)
    user = User(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        is_verified=verified,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user, create_access_token(user.id)


async def login(payload: LoginRequest, db: AsyncSession) -> tuple[User, str]:
    user = await db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.password_hash or ""):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account disabled",
        )
    return user, create_access_token(user.id)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        user_id = decode_access_token(credentials.credentials)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    user = await db.get(User, uuid.UUID(user_id))
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user
