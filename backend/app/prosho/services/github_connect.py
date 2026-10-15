"""Linking a project to one of the student's GitHub repos.

Nothing from the browser is trusted for this: the backend asks GitHub which
installation of the ProSho App sits on the signed-in user's *own* account
(matched by numeric id, not login) and only offers repos from it. Beta
limitation: personal-account installations only, not organisations.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.prosho.models.prosho_claim import ProshoClaim
from app.prosho.models.prosho_project import ProshoProject
from app.prosho.models.prosho_user import ProshoUser
from app.prosho.services import audit, github
from app.prosho.services.manifest_sync import sync_project


def _bad_gateway(e: github.GitHubError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message)


async def _own_installation(user: ProshoUser) -> dict[str, Any] | None:
    inst = await github.get_user_installation(user.github_login)
    if inst is None or inst.get("account", {}).get("id") != user.github_id:
        return None
    return inst


async def available_repos(project: ProshoProject, user: ProshoUser) -> dict[str, Any]:
    try:
        inst = await _own_installation(user)
        if inst is None:
            return {"installed": False, "install_url": github.install_url(str(project.id)),
                    "manage_url": None, "repos": []}
        token = await github.installation_token(inst["id"])
        repos = await github.list_installation_repos(token)
    except github.GitHubError as e:
        raise _bad_gateway(e)
    return {
        "installed": True,
        "install_url": github.install_url(str(project.id)),
        "manage_url": github.installation_settings_url(inst["id"]),
        "repos": sorted(({"id": r["id"], "full_name": r["full_name"], "private": r["private"]} for r in repos),
                        key=lambda r: r["full_name"].lower()),
    }


async def connect_repo(project: ProshoProject, repo_id: int, user: ProshoUser, db: AsyncSession) -> ProshoProject:
    try:
        inst = await _own_installation(user)
        if inst is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="Install the ProSho GitHub App on your account first")
        token = await github.installation_token(inst["id"])
        repo = next((r for r in await github.list_installation_repos(token) if r["id"] == repo_id), None)
    except github.GitHubError as e:
        raise _bad_gateway(e)
    if repo is None:  # not theirs, or not shared with the App — same answer
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repo not found in your ProSho installation")

    taken = await db.scalar(select(ProshoProject.id).where(ProshoProject.repo_id == repo_id, ProshoProject.id != project.id))
    if taken:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That repo is already connected to another ProSho project")

    before = {"repo_full_name": project.repo_full_name}
    project.repo_id = repo["id"]
    project.repo_full_name = repo["full_name"]
    project.github_installation_id = inst["id"]
    audit.record(db, actor_id=user.id, action="project.repo_connect", entity="project", entity_id=project.id,
                 before=before, after={"repo_full_name": repo["full_name"], "repo_id": repo["id"]})
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That repo is already connected to another ProSho project")
    return await sync_project(project, db, actor_id=user.id)


async def disconnect_repo(project: ProshoProject, user: ProshoUser, db: AsyncSession) -> ProshoProject:
    """The story fields become editable on ProSho again; claims are archived
    (they only exist through the manifest) and come back on reconnect."""
    if project.repo_id is None:
        return project
    before = {"repo_full_name": project.repo_full_name}
    project.repo_id = project.repo_full_name = project.github_installation_id = None
    project.manifest_sha = project.manifest_synced_at = project.manifest_checked_at = None
    project.manifest_errors = None
    await db.execute(update(ProshoClaim)
                     .where(ProshoClaim.project_id == project.id, ProshoClaim.archived_at.is_(None))
                     .values(archived_at=datetime.now(timezone.utc)))
    audit.record(db, actor_id=user.id, action="project.repo_disconnect", entity="project", entity_id=project.id,
                 before=before, after={"repo_full_name": None})
    await db.commit()
    await db.refresh(project)
    return project
