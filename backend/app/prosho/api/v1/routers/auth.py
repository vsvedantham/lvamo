from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.prosho.models.prosho_user import ProshoUser
from app.prosho.schemas.auth import LoginCodeExchange, ProshoUserResponse, TokenResponse
from app.prosho.services import auth as auth_service
from app.prosho.services import github

router = APIRouter(prefix="/auth")


def _to_login(reason: str) -> RedirectResponse:
    frontend = settings.frontend_base_url.rstrip("/")
    return RedirectResponse(f"{frontend}/prosho/login?error={reason}")


@router.get("/github/authorize")
async def github_authorize():
    """A plain browser navigation (not XHR) to GitHub's consent screen, so the
    client secret never reaches the frontend."""
    return RedirectResponse(github.build_authorize_url(auth_service.new_state()))


@router.get("/github/callback")
async def github_callback(
    code: str | None = None,
    state: str = "",
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    if error or not code:
        return _to_login("denied")
    try:
        login_code = await auth_service.handle_callback(code, state, db)
    except auth_service.SignInRefused as refused:
        return _to_login(refused.reason)
    except Exception:  # bad state, GitHub outage, … — never a raw 500 page
        return _to_login("failed")
    frontend = settings.frontend_base_url.rstrip("/")
    return RedirectResponse(f"{frontend}/prosho/auth/callback#code={login_code}")


@router.post("/exchange", response_model=TokenResponse)
async def exchange(body: LoginCodeExchange, db: AsyncSession = Depends(get_db)):
    return TokenResponse(access_token=await auth_service.exchange_login_code(body.code, db))


@router.get("/me", response_model=ProshoUserResponse)
async def me(user: ProshoUser = Depends(auth_service.get_current_user)):
    return user
