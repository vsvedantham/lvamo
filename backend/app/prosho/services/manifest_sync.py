"""Read prosho.yaml from the connected repo and apply it (BETA_PLAN §7).

Called on connect, on "Sync now", and from the push webhook. Whatever
happens, the outcome is recorded on the project (`manifest_checked_at`,
`manifest_errors`) so the dashboard can show it. A failed sync never
changes the project's story or claims — the page keeps the last good
version.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.prosho.models.prosho_claim import ProshoClaim
from app.prosho.models.prosho_project import ProshoProject
from app.prosho.services import audit, github
from app.prosho.services.manifest import MANIFEST_PATH, MAX_BYTES, TYPE_FROM_MANIFEST, ManifestV1, parse_manifest

STORY_FIELDS = ("title", "summary", "problem", "project_type", "demo_kind", "demo_url", "module_config")


def _error(message: str) -> list[dict[str, Any]]:
    return [{"line": None, "path": "", "message": message}]


async def _finish(project: ProshoProject, db: AsyncSession) -> ProshoProject:
    # Refresh too: updated_at is set by the database on update, so it's
    # expired after the commit and can't be lazily loaded in async code.
    await db.commit()
    await db.refresh(project)
    return project


async def sync_project(
    project: ProshoProject,
    db: AsyncSession,
    *,
    actor_id: Optional[uuid.UUID] = None,
    commit_sha: Optional[str] = None,
) -> ProshoProject:
    now = datetime.now(timezone.utc)
    project.manifest_checked_at = now

    if project.repo_id is None or project.github_installation_id is None:
        project.manifest_errors = _error("No GitHub repo connected — connect one to sync prosho.yaml")
        return await _finish(project, db)

    try:
        token = await github.installation_token(project.github_installation_id)
        repo = await github.get_repo(token, project.repo_id)
        project.repo_full_name = repo["full_name"]
        sha = commit_sha or await github.get_branch_head_sha(token, repo["full_name"], repo["default_branch"])
        raw = await github.get_file(token, repo["full_name"], MANIFEST_PATH, sha, MAX_BYTES)
    except github.GitHubError as e:
        project.manifest_errors = _error(e.message)
        return await _finish(project, db)

    project.manifest_sha = sha
    if raw is None:
        project.manifest_errors = _error(f"No {MANIFEST_PATH} at the root of {repo['full_name']} (branch {repo['default_branch']})")
        return await _finish(project, db)

    result = parse_manifest(raw)
    if not result.ok:
        project.manifest_errors = result.errors
        return await _finish(project, db)

    await _apply(project, result.manifest, db, actor_id=actor_id, now=now)
    project.manifest_errors = None
    project.manifest_synced_at = now
    return await _finish(project, db)


async def _apply(project: ProshoProject, m: ManifestV1, db: AsyncSession, *, actor_id, now: datetime) -> None:
    story = {
        "title": m.title,
        "summary": m.summary,
        "problem": m.problem,
        "project_type": TYPE_FROM_MANIFEST[m.type],
        "demo_kind": m.demo.kind if m.demo else None,
        "demo_url": str(m.demo.url) if m.demo else None,
        # The module section (data: / frontend:), kept so scheduled checks
        # don't need GitHub. JSON-ready so it compares cleanly on re-sync.
        "module_config": ({"data": m.data.model_dump(mode="json")} if m.data
                          else {"frontend": m.frontend.model_dump(mode="json")} if m.frontend else None),
    }
    before = {k: getattr(project, k) for k in STORY_FIELDS if getattr(project, k) != story[k]}
    after = {k: story[k] for k in before}
    for k, v in after.items():
        setattr(project, k, v)

    existing = {c.key: c for c in await db.scalars(select(ProshoClaim).where(ProshoClaim.project_id == project.id))}
    added, changed, archived = [], [], []
    for position, c in enumerate(m.claims):
        fields = {
            "text": c.text,
            "metric_key": c.metric,
            "target_op": c.target.op if c.target else None,
            "target_value": c.target.value if c.target else None,
            "target_value_hi": c.target.value_hi if c.target else None,
            "position": position,
            "archived_at": None,
        }
        claim = existing.get(c.id)
        if claim is None:
            db.add(ProshoClaim(project_id=project.id, key=c.id, **fields))
            added.append(c.id)
        elif any(getattr(claim, k) != v for k, v in fields.items()):
            for k, v in fields.items():
                setattr(claim, k, v)
            changed.append(c.id)
    manifest_keys = {c.id for c in m.claims}
    for key, claim in existing.items():
        if key not in manifest_keys and claim.archived_at is None:
            claim.archived_at = now
            archived.append(key)

    claim_changes = {k: v for k, v in (("claims_added", added), ("claims_changed", changed), ("claims_archived", archived)) if v}
    if after or claim_changes:
        audit.record(db, actor_id=actor_id, action="manifest.sync", entity="project", entity_id=project.id,
                     before=before or None, after={**after, **claim_changes, "manifest_sha": project.manifest_sha})
