"""GitHub App webhook (push + installation events), HMAC-verified.

Pushes to a connected repo's default branch re-sync prosho.yaml in the
background, so GitHub gets its answer well inside its 10-second timeout.
"""
import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, status
from sqlalchemy import select, update

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.prosho.models.prosho_project import ProshoProject
from app.prosho.services.manifest_sync import sync_project

router = APIRouter(prefix="/github")
log = logging.getLogger(__name__)


def verify_signature(body: bytes, signature: str | None) -> bool:
    secret = settings.prosho_github_webhook_secret
    if not secret or not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


async def _background_sync(repo_id: int, installation_id: int, commit_sha: str) -> None:
    try:
        async with AsyncSessionLocal() as db:
            project = await db.scalar(select(ProshoProject).where(
                ProshoProject.repo_id == repo_id, ProshoProject.is_active.is_(True)))
            if project and project.github_installation_id == installation_id:
                await sync_project(project, db, commit_sha=commit_sha)
    except Exception:  # never let a background task die silently
        log.exception("prosho: webhook sync failed for repo %s", repo_id)


async def _forget_installation(where) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(update(ProshoProject).where(where).values(github_installation_id=None))
        await db.commit()


@router.post("/webhook")
async def webhook(
    request: Request,
    background: BackgroundTasks,
    x_github_event: str = Header(default=""),
    x_hub_signature_256: str | None = Header(default=None),
):
    body = await request.body()
    if not verify_signature(body, x_hub_signature_256):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad signature")
    try:
        payload = json.loads(body)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Body is not JSON")

    if x_github_event == "ping":
        return {"status": "pong"}

    if x_github_event == "push":
        repo = payload.get("repository") or {}
        installation_id = (payload.get("installation") or {}).get("id")
        if payload.get("ref") != f"refs/heads/{repo.get('default_branch')}" or payload.get("deleted"):
            return {"status": "ignored", "reason": "not the default branch"}
        if not repo.get("id") or not installation_id or not payload.get("after"):
            return {"status": "ignored", "reason": "incomplete payload"}
        background.add_task(_background_sync, repo["id"], installation_id, payload["after"])
        return {"status": "queued"}

    if x_github_event == "installation" and payload.get("action") == "deleted":
        await _forget_installation(ProshoProject.github_installation_id == payload["installation"]["id"])
        return {"status": "ok"}

    if x_github_event == "installation_repositories" and payload.get("action") == "removed":
        removed = [r["id"] for r in payload.get("repositories_removed", [])]
        if removed:
            await _forget_installation(ProshoProject.repo_id.in_(removed))
        return {"status": "ok"}

    return {"status": "ignored"}
